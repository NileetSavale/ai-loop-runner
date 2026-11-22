"""The study's reviewed cascade as a session option: a cheap model tries the task first, a stronger model reviews a fix
that passes the tests, and the session's own model redoes the task only if the cheap attempt fails or the review
rejects it.

In the study (research_notes/research_log.md), passing the repo's tests was weak evidence that a cheap model's fix was
right: about a fifth of the fixes Haiku's loop accepted failed SWE-bench's hidden tests. A cascade that escalated only
on failing tests solved little more than Haiku alone; with the review it came close to Sonnet alone. Each step goes
out as a "cascade" event, saved like the loop's own events so the page can show it after a reload.

The steps are data: run_cascade walks a pipeline (core/pipeline.py), by default pipelines/reviewed-cascade.yaml, and
this module runs each step kind (scout, fix, review). Another pipeline changes the order or the models, not the code.

The cheap attempt is undone by resetting the repo to the commit the session started from, so a repo with uncommitted
changes to tracked files is refused rather than have them lost. Untracked files the attempt created are removed; ones
that were there before stay, as the attempt left them. max_iterations applies to each model's loop, and the cost cap to the whole.
"""
import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
import subprocess
import uuid

from sqlmodel import select

from core.fix_review import REVIEWER_MODEL, edited_tests, review_fix
from core.pipeline import DONE, Pipeline, Step, load as load_pipeline, resolve as resolve_model
from core.loop import MAX_SESSION_COST_USD, BroadcastFn, _fail_session, _mark_session_failed, _running, run_loop
from core.scout import handover, run_scout, tried_summary
from core.verifier import run_verify
from database import get_session as db_session
from models import Iteration, Session, SessionEvent, Task, UsageEvent
from providers.router import _provider_for

CHEAP_MODEL = "claude-haiku-5-5"
SCOUT_BUDGET_USD = 0.05
REVIEW_PROMPT = "v2"


def _git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout


def _untracked(repo: str) -> set[str]:
    return set(_git(repo, "ls-files", "--others", "--exclude-standard", "-z").split("\0")) - {""}


def _show(repo: str, rev: str, path: str) -> str:
    """A file as it was at rev; empty if the fix created it."""
    try:
        return _git(repo, "show", f"{rev}:{path}")
    except subprocess.CalledProcessError:
        return ""


def _changed_files(diff: str) -> list[str]:
    return [line.split(" b/", 1)[1] for line in diff.splitlines() if line.startswith("diff --git ") and " b/" in line]


def cascade_problem(model: str) -> str | None:
    """Why a session can't run the cascade with this main model, or None."""
    if model == CHEAP_MODEL:
        return f"The cascade starts with {CHEAP_MODEL}, so pick a stronger main model to escalate to."
    if _provider_for(model) != _provider_for(CHEAP_MODEL):
        return "The cascade's cheap model and reviewer are Claude models, so pick a Claude model as the main one."
    return None


def _update(session_id: str, **fields):
    """Set Session fields, and the task's spec if given."""
    spec = fields.pop("spec", None)
    with db_session() as db:
        s = db.get(Session, session_id)
        for key, value in fields.items():
            setattr(s, key, value)
        db.add(s)
        if spec is not None:
            task = db.exec(select(Task).where(Task.session_id == session_id)).first()
            task.spec = spec
            db.add(task)
        db.commit()


def _charge(session_id: str, model: str, cost: float, input_tokens: int, output_tokens: int, byok: bool):
    """A call outside the loop (the scout, the review): added to the session's cost, and to billing for a user."""
    with db_session() as db:
        s = db.get(Session, session_id)
        s.total_cost_usd += cost
        s.total_tokens += input_tokens + output_tokens
        db.add(s)
        if s.user_id is not None:
            db.add(UsageEvent(id=str(uuid.uuid4()), user_id=s.user_id, session_id=session_id,
                              provider=_provider_for(model), model=model, input_tokens=input_tokens,
                              output_tokens=output_tokens, cost_usd=cost, byok=byok))
        db.commit()


def _spent(session_id: str) -> float:
    with db_session() as db:
        return db.get(Session, session_id).total_cost_usd


async def _run_stage(session_id: str, broadcast_fn: BroadcastFn, user_api_key: str | None, max_cost_usd: float,
                     loop_options: dict) -> tuple[dict | None, str]:
    """One model's loop. Its final pass or fail is held back, since the cascade decides when the session is done.
    Returns that final event's data (None if the loop sent none) and the last test output."""
    final: dict | None = None
    last_output = ""

    async def held(msg: dict):
        nonlocal final, last_output
        if msg["event"] == "verify_output":
            last_output = msg["data"].get("output") or ""
        if msg["event"] == "session_complete" and msg["data"].get("status") in ("passed", "failed"):
            final = msg["data"]
            if "iteration_number" in final:  # a pass carries its attempt, which the page still has to close
                await broadcast_fn({"event": "iteration_complete", "data": final})
            return
        await broadcast_fn(msg)

    # run_loop stops when the session leaves _running, and removes it when it ends, so each stage puts it back
    _running[session_id] = asyncio.current_task()
    await run_loop(session_id, held, user_api_key, max_cost_usd=max_cost_usd, **loop_options)
    return final, last_output


@dataclass
class _Run:
    """What the steps of one session's pipeline share."""
    session_id: str
    broadcast_fn: BroadcastFn
    user_api_key: str | None
    loop_options: dict
    repo: str
    spec: str
    main_model: str
    cheap_model: str
    limit: float
    base: str
    before: set[str]
    notes: str | None = None
    scout_cost: float = 0.0
    final: dict | None = None
    last_output: str = ""
    diff: str | None = None
    rejected: str | None = None
    command_passed: bool | None = None  # the last command step's result

    @property
    def byok(self) -> bool:
        return self.user_api_key is not None

    async def step(self, data: dict):
        with db_session() as db:
            event = SessionEvent(session_id=self.session_id, kind="cascade", data=json.dumps(data))
            db.add(event)
            db.commit()
            event_id = event.id
        await self.broadcast_fn({"event": "cascade", "data": {**data, "id": event_id}})

    def attempt_diff(self) -> str:
        """The last fix's changes since the session started, staged so new files show."""
        if self.diff is None:
            _git(self.repo, "add", "-A")
            # The loop's commit takes every untracked file, the user's own too; they aren't the attempt's work
            self.diff = _git(self.repo, "diff", "--cached", self.base, "--", ".",
                             *(f":(exclude,literal){path}" for path in self.before))
        return self.diff


async def _scout(run: _Run, step: Step, model: str) -> str:
    await run.step({"step": step.id, "model": model})
    run.notes, scouted = await run_scout(run.spec, run.repo, model, step.options.get("budget_usd", SCOUT_BUDGET_USD),
                                         user_api_key=run.user_api_key)
    run.scout_cost = scouted.cost_usd
    _charge(run.session_id, model, scouted.cost_usd, scouted.input_tokens, scouted.output_tokens, run.byok)
    return "next"


async def _fix(run: _Run, step: Step, model: str) -> str:
    if step.options.get("undo"):
        diff = run.attempt_diff()
        tried = tried_summary({path: [] for path in _changed_files(diff)}, [], [],
                              "" if run.rejected else run.last_output, "")
        # Not reset --hard: that would delete the user's untracked files, which the loop's commit made tracked
        _git(run.repo, "reset", "-q", run.base)
        _git(run.repo, "checkout", "-q", "--", ".")
        created = sorted(_untracked(run.repo) - run.before)
        if created:
            _git(run.repo, "clean", "-fq", "--", *created)
        with db_session() as db:
            earlier = len(db.exec(select(Iteration).where(Iteration.session_id == run.session_id)).all())
        await run.step({"step": step.id, "model": model, "cheap_iterations": earlier,
                        "reason": f"the reviewer rejected its fix: {run.rejected}" if run.rejected
                        else "its fix didn't pass the tests"})
        spec = handover(run.spec, run.notes or "", tried, run.rejected)
        _update(run.session_id, model=model, status="running", completed_at=None, spec=spec)
    else:
        announce = {"step": step.id, "model": model}
        if run.notes is not None:
            announce |= {"notes": run.notes, "cost_usd": run.scout_cost}
        await run.step(announce)
        _update(run.session_id, model=model, spec=handover(run.spec, run.notes) if run.notes is not None else run.spec)
    run.final, run.last_output = await _run_stage(run.session_id, run.broadcast_fn, run.user_api_key,
                                                  run.limit - _spent(run.session_id), run.loop_options)
    run.diff, run.rejected = None, None
    return "on_pass" if run.final and run.final.get("status") == "passed" else "on_fail"


async def _review(run: _Run, step: Step, model: str) -> str:
    diff = run.attempt_diff()
    await run.step({"step": step.id, "model": model})
    _running[run.session_id] = asyncio.current_task()
    # The default reviewer is the one the cascade has always called; another model is passed by name
    which = {} if model == REVIEWER_MODEL else {"model": model}
    verdict = await review_fix(run.spec, diff, lambda path: _show(run.repo, run.base, path), "", REVIEW_PROMPT,
                               user_api_key=run.user_api_key, **which)
    _charge(run.session_id, model, verdict["cost_usd"], verdict["input_tokens"], verdict["output_tokens"], run.byok)
    await run.step({"step": "reviewed", "model": model, "accept": verdict["accept"], "why": verdict["why"],
                    "edited_tests": edited_tests(diff), "cost_usd": verdict["cost_usd"]})
    run.rejected = None if verdict["accept"] else verdict["why"]
    return "on_accept" if verdict["accept"] else "on_reject"


async def _command(run: _Run, step: Step, model: str) -> str:
    """A shell command in the repo (a linter, a type checker, more tests), run like the session's own test command."""
    result = await run_verify(step.options["run"], run.repo, run.loop_options.get("sandbox"))
    await run.step({"step": step.id, "kind": "command", "command": step.options["run"], "passed": result.passed,
                    "exit_code": result.exit_code, "output": result.output[-4000:]})
    run.command_passed = result.passed
    return "on_pass" if result.passed else "on_fail"


APPROVAL_POLL_SECONDS = 2.0


def _approval(session_id: str, step_id: str, after: int) -> dict | None:
    """A person's answer to this approve step, saved after its waiting event by POST /sessions/{id}/approval."""
    with db_session() as db:
        rows = db.exec(select(SessionEvent).where(SessionEvent.session_id == session_id,
                                                  SessionEvent.kind == "approval", SessionEvent.id > after)).all()
    for row in rows:
        data = json.loads(row.data)
        if data.get("step") == step_id:
            return data
    return None


async def _approve(run: _Run, step: Step, model: str) -> str:
    """Wait for a person to accept or reject the last fix. The answer is read from the database rather than held in
    this process, so it reaches a run on a TaskQ worker as well as one in the API."""
    diff = run.attempt_diff()
    hours = step.options.get("timeout_hours", 24)
    with db_session() as db:
        waiting = SessionEvent(session_id=run.session_id, kind="cascade", data=json.dumps(
            {"step": step.id, "kind": "approve", "waiting": True, "files": _changed_files(diff), "timeout_hours": hours}))
        db.add(waiting)
        db.commit()
        waiting_id = waiting.id
    await run.broadcast_fn({"event": "cascade", "data": {**json.loads(waiting.data), "id": waiting_id}})
    deadline = asyncio.get_running_loop().time() + hours * 3600
    while (answer := _approval(run.session_id, step.id, waiting_id)) is None:
        if asyncio.get_running_loop().time() > deadline:
            answer = {"accept": False, "note": f"No one answered within {hours:g} hours."}
            break
        _running[run.session_id] = asyncio.current_task()
        await asyncio.sleep(APPROVAL_POLL_SECONDS)
    accept = bool(answer.get("accept"))
    note = (answer.get("note") or "").strip()
    await run.step({"step": "approved", "of": step.id, "accept": accept, "why": note or None})
    run.rejected = None if accept else (note or "A person rejected the fix.")
    return "on_accept" if accept else "on_reject"


_KINDS = {"scout": _scout, "fix": _fix, "review": _review, "command": _command, "approve": _approve}


async def run_cascade(session_id: str, broadcast_fn: BroadcastFn, user_api_key: str | None = None,
                      max_cost_usd: float | None = None, cheap_model: str = CHEAP_MODEL,
                      pipeline: Pipeline | None = None, **loop_options):
    """Run the session through a pipeline (core/pipeline.py), by default the reviewed cascade.
    loop_options: run_loop's, for every fix step's loop."""
    pipeline = pipeline or load_pipeline("reviewed-cascade")
    with db_session() as db:
        session = db.get(Session, session_id)
        repo, model = session.repo_path, session.model
        spec = db.exec(select(Task).where(Task.session_id == session_id)).first().spec
    limit = MAX_SESSION_COST_USD if max_cost_usd is None else max_cost_usd

    async def fail(reason: str):
        _mark_session_failed(session_id, reason)
        await _fail_session(session_id, broadcast_fn, reason)

    try:
        base = _git(repo, "rev-parse", "HEAD").strip()
        dirty = _git(repo, "status", "--porcelain", "--untracked-files=no").strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        await fail("The cascade needs a git repo with at least one commit: it undoes the cheap model's attempt by "
                   "resetting to the commit the session started from.")
        return
    if dirty:
        await fail("Commit or stash your changes first: the cascade undoes the cheap model's attempt by resetting to "
                   "the last commit, which would lose them.")
        return
    run = _Run(session_id, broadcast_fn, user_api_key, loop_options, repo, spec, model, cheap_model, limit, base,
               _untracked(repo))
    # Which pipeline this session runs, saved for the page's map (the sessions table has no column for it)
    with db_session() as db:
        db.add(SessionEvent(session_id=session_id, kind="pipeline", data=json.dumps({"name": pipeline.name})))
        db.commit()

    try:
        current = pipeline.start
        while current != DONE:
            step = pipeline.steps[current]
            outcome = await _KINDS[step.kind](run, step, resolve_model(step.model, cheap_model, model))
            current = step.after(outcome)
        # The last fix's pass or fail, held back while later steps might still run, ends the session; a pipeline
        # with no fix step ends with its last command's result
        if run.final is None and run.command_passed is not None:
            status = "passed" if run.command_passed else "failed"
            _update(session_id, status=status, completed_at=datetime.utcnow())
            run.final = {"status": status}
        if run.final:
            await broadcast_fn({"event": "session_complete", "data": run.final})

    except asyncio.CancelledError:
        _mark_session_failed(session_id, "cancelled")
        await broadcast_fn({"event": "session_complete", "data": {"status": "cancelled"}})
        raise

    except Exception as e:
        await fail(f"The run crashed: {e}")

    finally:
        # The session reads as what it was asked: the main model and the user's own task
        _update(session_id, model=model, spec=spec)
        _running.pop(session_id, None)


def start_cascade(session_id: str, broadcast_fn: BroadcastFn, user_api_key: str | None = None,
                  max_cost_usd: float | None = None, use_map: bool = True, add_tests: bool = False):
    task = asyncio.create_task(run_cascade(session_id, broadcast_fn, user_api_key, max_cost_usd,
                                           use_map=use_map, add_tests=add_tests))
    _running[session_id] = task
    return task
