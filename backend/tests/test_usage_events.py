"""
Tests for UsageEvent recording in the loop and the /analytics/usage endpoint.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import uuid
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import cache

@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    monkeypatch.setattr(cache, "redis", fakeredis.aioredis.FakeRedis())


from core.loop import run_loop, start_loop
from models import UsageEvent, Session, Task
from database import get_session as db_session, init_db
from sqlmodel import select


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    import database
    from sqlmodel import create_engine, SQLModel
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)


def _seed(session_id: str, user_id: str | None):
    """Insert a Session + Task so run_loop can load them."""
    with db_session() as db:
        db.add(Session(
            id=session_id,
            user_id=user_id,
            name="test",
            repo_path="/tmp",
            verify_command="true",
            model="claude-sonnet-4-6",
            max_iterations=1,
            status="running",
        ))
        t = Task(id=str(uuid.uuid4()), session_id=session_id, title="t", spec="do it")
        t.set_files_context([])
        db.add(t)
        db.commit()


def _fake_agent_result():
    from core.agent import AgentResult
    return AgentResult(raw_output="", edits=[], input_tokens=100, output_tokens=50, cost_usd=0.002)


def _fake_verify_pass():
    from core.verifier import VerifyResult
    return VerifyResult(passed=True, output="ok", exit_code=0)


def _fake_verify_fail():
    from core.verifier import VerifyResult
    return VerifyResult(passed=False, output="FAIL", exit_code=1)


async def _noop_broadcast(msg):
    pass


async def _run(session_id: str, broadcast_fn, **kwargs):
    """Populate _running before calling run_loop (required by the stop-check guard)."""
    from core.loop import _running
    _running[session_id] = asyncio.current_task()
    await run_loop(session_id, broadcast_fn, **kwargs)


# --- UsageEvent written for authenticated user ---

def test_usage_event_written_for_authed_user():
    sid = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    _seed(sid, user_id=uid)

    with patch("core.loop.run_agent", new_callable=AsyncMock, return_value=_fake_agent_result()), \
         patch("core.loop.run_verify", new_callable=AsyncMock, return_value=_fake_verify_pass()), \
         patch("core.loop.git_commit", return_value="abc123"), \
         patch("core.loop.invalidate_analytics", new_callable=AsyncMock):

        asyncio.run(_run(sid, _noop_broadcast))

    with db_session() as db:
        events = db.exec(select(UsageEvent).where(UsageEvent.session_id == sid)).all()

    assert len(events) == 1
    e = events[0]
    assert e.user_id == uid
    assert e.provider == "anthropic"
    assert e.model == "claude-sonnet-4-6"
    assert e.input_tokens == 100
    assert e.output_tokens == 50
    assert abs(e.cost_usd - 0.002) < 1e-9


def test_usage_event_byok_false_when_no_user_key():
    sid = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    _seed(sid, user_id=uid)

    with patch("core.loop.run_agent", new_callable=AsyncMock, return_value=_fake_agent_result()), \
         patch("core.loop.run_verify", new_callable=AsyncMock, return_value=_fake_verify_pass()), \
         patch("core.loop.git_commit", return_value="abc123"), \
         patch("core.loop.invalidate_analytics", new_callable=AsyncMock):

        # user_api_key=None → platform key → byok=False
        asyncio.run(_run(sid, _noop_broadcast, user_api_key=None))

    with db_session() as db:
        e = db.exec(select(UsageEvent).where(UsageEvent.session_id == sid)).first()
    assert e.byok is False


def test_usage_event_byok_true_when_user_key_provided():
    sid = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    _seed(sid, user_id=uid)

    with patch("core.loop.run_agent", new_callable=AsyncMock, return_value=_fake_agent_result()), \
         patch("core.loop.run_verify", new_callable=AsyncMock, return_value=_fake_verify_pass()), \
         patch("core.loop.git_commit", return_value="abc123"), \
         patch("core.loop.invalidate_analytics", new_callable=AsyncMock):

        asyncio.run(_run(sid, _noop_broadcast, user_api_key="sk-user-key"))

    with db_session() as db:
        e = db.exec(select(UsageEvent).where(UsageEvent.session_id == sid)).first()
    assert e.byok is True


def test_no_usage_event_for_unauthenticated_session():
    sid = str(uuid.uuid4())
    _seed(sid, user_id=None)  # local / unauthed

    with patch("core.loop.run_agent", new_callable=AsyncMock, return_value=_fake_agent_result()), \
         patch("core.loop.run_verify", new_callable=AsyncMock, return_value=_fake_verify_pass()), \
         patch("core.loop.git_commit", return_value="abc123"), \
         patch("core.loop.invalidate_analytics", new_callable=AsyncMock):

        asyncio.run(_run(sid, _noop_broadcast))

    with db_session() as db:
        events = db.exec(select(UsageEvent).where(UsageEvent.session_id == sid)).all()
    assert events == []


def test_one_event_per_iteration():
    """Two failed iterations + one final pass = 3 UsageEvents."""
    sid = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    with db_session() as db:
        db.add(Session(
            id=sid, user_id=uid, name="test", repo_path="/tmp",
            verify_command="true", model="claude-sonnet-4-6",
            max_iterations=3, status="running",
        ))
        t = Task(id=str(uuid.uuid4()), session_id=sid, title="t", spec="s")
        t.set_files_context([])
        db.add(t)
        db.commit()

    fail = _fake_verify_fail()
    ok = _fake_verify_pass()
    verify_sequence = [fail, fail, ok]

    with patch("core.loop.run_agent", new_callable=AsyncMock, return_value=_fake_agent_result()), \
         patch("core.loop.run_verify", new_callable=AsyncMock, side_effect=verify_sequence), \
         patch("core.loop.git_commit", return_value="abc"), \
         patch("core.loop.invalidate_analytics", new_callable=AsyncMock):

        asyncio.run(_run(sid, _noop_broadcast, user_api_key=None))

    with db_session() as db:
        events = db.exec(select(UsageEvent).where(UsageEvent.session_id == sid)).all()
    assert len(events) == 3


def _generate(tmp_path, reply, user={"sub": "u1"}):
    from routes.test_gen import GenerateRequest, generate
    from providers.base import LLMResult
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=LLMResult(input_tokens=1000, output_tokens=500, **reply))
    with patch("agents.test_gen.get_provider", return_value=provider), \
         patch("routes.test_gen.invalidate_analytics", new_callable=AsyncMock):
        return asyncio.run(generate(GenerateRequest(description="d", repo_path=str(tmp_path), model="claude-sonnet-4-6"), user))


def test_test_generation_is_billed(tmp_path):
    response = _generate(tmp_path, {"text": '<file path="tests/test_a.py">x</file>'})
    with db_session() as db:
        event = db.exec(select(UsageEvent)).one()
    assert event.user_id == "u1" and event.session_id == "test-generation"
    assert (event.input_tokens, event.output_tokens) == (1000, 500)
    assert event.cost_usd == pytest.approx(0.0105) == response["cost_usd"]


def test_cut_off_test_generation_is_still_billed_then_refused(tmp_path):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _generate(tmp_path, {"text": "partial", "truncated": True})
    assert e.value.status_code == 400
    with db_session() as db:
        assert db.exec(select(UsageEvent)).one().cost_usd > 0
