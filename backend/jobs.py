"""Session runs as TaskQ jobs, so a run outlives the API process: a restart or crash no longer loses it, and runs can be
spread over several worker processes.

Off by default. With LOOP_RUNNER_QUEUE=taskq, start_session enqueues a job on the "sessions" queue and a worker
(`taskq worker --actors jobs:registry --queues sessions`) runs it; without it, runs stay asyncio tasks in the API
process. TaskQ keeps its jobs in Postgres (TASKQ_PG_DSN), separate from the app database. Run the worker with
DOTENV_DIR set to a folder without a .env: taskq-py 0.2.2 loads the .env of its folder over the process environment.

The job's payload is saved in Postgres, so it carries the session id and options only, never the user's API key: the
worker looks the key up from the vault when it starts the run. Events still reach the session page through Redis
pub/sub, which works from any process.
"""
import asyncio
import contextlib
import os
from collections.abc import Awaitable, Callable
from datetime import timedelta

from pydantic import BaseModel, field_validator
from taskq import JobContext, JobFilter, TaskQ, actor
from taskq.retry import RetryPolicy

QUEUE = "sessions"
# A session can run for a long time (sandbox setup, many iterations); this bounds a hung one.
START_TO_CLOSE = timedelta(hours=2)

_client: TaskQ | None = None


def enabled() -> bool:
    return os.getenv("LOOP_RUNNER_QUEUE") == "taskq"


class SessionJob(BaseModel):
    session_id: str
    cascade: bool = False
    sandboxed: bool = False
    max_cost_usd: float | None = None
    add_tests: bool = False
    use_map: bool = True

    @field_validator("session_id", mode="before")
    @classmethod
    def _uuid_as_text(cls, value):
        # taskq-py 0.2.2 hands the worker a UUID-shaped string back as a uuid.UUID
        return str(value)


def _tag(session_id: str) -> str:
    """TaskQ tags allow word characters and hyphens only, so no colon."""
    return f"session-{session_id}"


STOPPED_PART_WAY = "The worker running this session stopped part-way, so the run was not finished. Start it again."


Progress = Callable[..., Awaitable[None]]


async def _no_progress(**_) -> None:
    pass


async def run_job(job: SessionJob, cancel_event: asyncio.Event, attempt: int = 1,
                  progress: Progress = _no_progress) -> None:
    """Run one session to the end, or until cancel_event is set, then cancel it and raise CancelledError.

    A later attempt means a worker died during the run (TaskQ re-delivers the job once its lease expires). That run
    has already changed the repo, so it is not run again: the session is marked failed with the reason instead of
    staying "running" forever.

    progress is the job's progress report (JobContext.progress), so TaskQ's admin UI shows which attempt a session
    is on.
    """
    from core.loop import _fail_session, _mark_session_failed, _running
    from core.workspace import run_session
    from database import get_session as db_session
    from models import Session
    from routes.keys import get_user_api_key
    from routes.ws import broadcast

    with db_session() as db:
        session = db.get(Session, job.session_id)
        if session is None or session.status != "running":
            return  # deleted or stopped before a worker picked it up
        user_id, model, max_iterations = session.user_id, session.model, session.max_iterations

    async def broadcast_fn(msg: dict):
        await broadcast(job.session_id, msg)
        event, data = msg.get("event"), msg.get("data") or {}
        if event == "iteration_start":
            n = data.get("iteration", 0)
            await progress(step=n, percent=100.0 * (n - 1) / max_iterations,
                           detail=f"attempt {n} of {max_iterations}")
        elif event == "session_complete":
            await progress(percent=100.0, detail=f"session {data.get('status')}")

    if attempt > 1:
        _mark_session_failed(job.session_id, STOPPED_PART_WAY)
        await _fail_session(job.session_id, broadcast_fn, STOPPED_PART_WAY)
        return
    api_key = get_user_api_key(user_id, model) if user_id else None

    run = asyncio.create_task(run_session(
        job.session_id, broadcast_fn, job.cascade, job.sandboxed, user_api_key=api_key,
        max_cost_usd=job.max_cost_usd, add_tests=job.add_tests, use_map=job.use_map,
    ))
    # The loop runs only while its session is registered, as start_session does for an in-process run
    _running[job.session_id] = run
    stop = asyncio.create_task(cancel_event.wait())
    try:
        await asyncio.wait({run, stop}, return_when=asyncio.FIRST_COMPLETED)
        if run.done():
            run.result()
            return
        run.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await run
        raise asyncio.CancelledError
    finally:
        stop.cancel()
        _running.pop(job.session_id, None)


# Two attempts: the second only reports a run whose worker died (see run_job), it never re-runs the session.
@actor(name="run_session", queue=QUEUE, retry=RetryPolicy(max_attempts=2), start_to_close=START_TO_CLOSE)
async def run_session_job(payload: SessionJob, ctx: JobContext[SessionJob]) -> None:
    await run_job(payload, ctx.cancel_event, ctx.attempt, ctx.progress)


registry = [run_session_job]


async def _taskq() -> TaskQ:
    global _client
    if _client is None:
        client = TaskQ(dsn=os.environ["TASKQ_PG_DSN"])
        await client.open()
        _client = client
    return _client


async def enqueue(job: SessionJob) -> str:
    handle = await (await _taskq()).enqueue(run_session_job, job, tags=[_tag(job.session_id)])
    return str(handle.job_id)


async def cancel(session_id: str) -> None:
    """Cancel the session's job: one that has not started is dropped, a running one is stopped by its worker.

    taskq-py 0.2.2's client has no cancel_where, so the job is found by its tag. Cancelling a finished job does
    nothing, so every job with the tag is asked.
    """
    client = await _taskq()
    page = await client.list(JobFilter(tags=(_tag(session_id),)))
    for row in page.jobs:
        await client.cancel(row.id, reason="stopped")


async def close() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
