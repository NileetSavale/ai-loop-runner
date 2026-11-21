"""Session runs as TaskQ jobs (jobs.py), with the session run, the vault and the broadcast replaced by fakes. No
Postgres: run_job is the actor's body, driven directly with its cancel event."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine

import fakeredis.aioredis
import cache
import jobs
from database import get_session as db_session
from models import Session


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    import database
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(cache, "redis", fakeredis.aioredis.FakeRedis())


def add_session(status="running", user_id="u1"):
    with db_session() as db:
        db.add(Session(id="s1", user_id=user_id, name="x", repo_path="/tmp", verify_command="true", status=status,
                       model="claude-haiku-5-5"))
        db.commit()


def test_the_payload_never_carries_an_api_key():
    """TaskQ saves the payload in Postgres, so the key must not be in it."""
    assert not any("key" in name for name in jobs.SessionJob.model_fields)


def test_a_session_id_decoded_as_a_uuid_still_validates():
    """The worker gets the saved payload back with UUID-shaped strings turned into uuid.UUID."""
    import uuid
    sid = uuid.uuid4()
    assert jobs.SessionJob.model_validate({"session_id": sid}).session_id == str(sid)


def test_the_session_tag_is_one_taskq_accepts():
    from taskq.client._args import _validate_and_dedup_tags  # the check enqueue runs
    assert _validate_and_dedup_tags([jobs._tag("24f5fe06-2f59-4d61-afc8-0c2dc535808c")])


def test_a_job_runs_the_session_with_the_key_from_the_vault():
    add_session()
    seen = {}

    async def fake_run_session(session_id, broadcast_fn, cascade, sandboxed, **options):
        from core.loop import _running
        seen.update(session_id=session_id, cascade=cascade, sandboxed=sandboxed, registered=session_id in _running,
                    **options)
        await broadcast_fn({"event": "done"})

    with patch("core.workspace.run_session", fake_run_session), \
            patch("routes.keys.get_user_api_key", return_value="sk-from-vault") as lookup, \
            patch("routes.ws.broadcast", new_callable=AsyncMock) as broadcast:
        job = jobs.SessionJob(session_id="s1", cascade=True, max_cost_usd=0.5)
        asyncio.run(jobs.run_job(job, asyncio.Event()))

    lookup.assert_called_once_with("u1", "claude-haiku-5-5")
    # run_loop stops at once for a session missing from _running, so the job must register it
    from core.loop import _running
    assert seen["registered"] is True and "s1" not in _running
    assert seen["user_api_key"] == "sk-from-vault"
    assert seen["cascade"] is True and seen["max_cost_usd"] == 0.5
    broadcast.assert_awaited_once_with("s1", {"event": "done"})


@pytest.mark.parametrize("status", ["stopped", "failed"])
def test_a_job_for_a_session_no_longer_running_does_nothing(status):
    add_session(status=status)
    run_session = AsyncMock()
    with patch("core.workspace.run_session", run_session):
        asyncio.run(jobs.run_job(jobs.SessionJob(session_id="s1"), asyncio.Event()))
    run_session.assert_not_awaited()


def test_a_job_for_a_deleted_session_does_nothing():
    run_session = AsyncMock()
    with patch("core.workspace.run_session", run_session):
        asyncio.run(jobs.run_job(jobs.SessionJob(session_id="gone"), asyncio.Event()))
    run_session.assert_not_awaited()


def test_a_cancel_request_stops_the_run_and_cancels_the_job():
    add_session(user_id=None)
    state = {}

    async def endless_run(session_id, broadcast_fn, cascade, sandboxed, **options):
        state["started"] = True
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise

    async def scenario():
        cancel = asyncio.Event()
        job = asyncio.create_task(jobs.run_job(jobs.SessionJob(session_id="s1"), cancel))
        while "started" not in state:
            await asyncio.sleep(0)
        cancel.set()
        with pytest.raises(asyncio.CancelledError):
            await job

    with patch("core.workspace.run_session", endless_run):
        asyncio.run(scenario())
    assert state["cancelled"] is True


def test_a_retry_after_a_worker_died_fails_the_session_instead_of_running_it_again():
    add_session()
    run_session = AsyncMock()
    with patch("core.workspace.run_session", run_session), \
            patch("routes.ws.broadcast", new_callable=AsyncMock) as broadcast:
        asyncio.run(jobs.run_job(jobs.SessionJob(session_id="s1"), asyncio.Event(), attempt=2))
    run_session.assert_not_awaited()
    with db_session() as db:
        assert db.get(Session, "s1").status == "failed"
    sent = [call.args[1] for call in broadcast.await_args_list]
    assert sent[-1] == {"event": "session_complete", "data": {"status": "failed", "error": jobs.STOPPED_PART_WAY}}


def test_cancel_asks_every_job_with_the_session_tag(monkeypatch):
    from types import SimpleNamespace
    asked = []

    class FakeClient:
        async def list(self, filter):
            assert filter.tags == (jobs._tag("s1"),)
            return SimpleNamespace(jobs=[SimpleNamespace(id="j1"), SimpleNamespace(id="j2")])

        async def cancel(self, job_id, reason=None):
            asked.append((job_id, reason))

    monkeypatch.setattr(jobs, "_client", FakeClient())
    asyncio.run(jobs.cancel("s1"))
    assert asked == [("j1", "stopped"), ("j2", "stopped")]


def test_stop_cancels_the_job_when_the_queue_is_on(monkeypatch):
    import auth
    from main import app
    monkeypatch.setattr(auth, "ALLOW_ANONYMOUS", True)
    add_session(user_id=None)
    monkeypatch.setenv("LOOP_RUNNER_QUEUE", "taskq")
    with patch("jobs.cancel", new_callable=AsyncMock) as cancel, patch("routes.sessions.stop_loop") as stop_loop:
        response = TestClient(app).post("/sessions/s1/stop")
    assert response.status_code == 200
    cancel.assert_awaited_once_with("s1")
    stop_loop.assert_not_called()


def test_stop_cancels_the_task_when_the_queue_is_off(monkeypatch):
    import auth
    from main import app
    monkeypatch.setattr(auth, "ALLOW_ANONYMOUS", True)
    add_session(user_id=None)
    monkeypatch.delenv("LOOP_RUNNER_QUEUE", raising=False)
    with patch("jobs.cancel", new_callable=AsyncMock) as cancel, patch("routes.sessions.stop_loop") as stop_loop:
        response = TestClient(app).post("/sessions/s1/stop")
    assert response.status_code == 200
    stop_loop.assert_called_once_with("s1")
    cancel.assert_not_awaited()
