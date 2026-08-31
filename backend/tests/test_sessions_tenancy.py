"""
Tests for multi-tenancy enforcement and input validation in the sessions route.
Uses FastAPI TestClient with an in-memory SQLite DB — no real auth tokens needed.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Patch Redis before importing main so cache.py doesn't fail on connection
import fakeredis.aioredis
import cache

@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    r = fakeredis.aioredis.FakeRedis()
    monkeypatch.setattr(cache, "redis", r)


from main import app
from routes.sessions import _own_session
from models import Session
from fastapi import HTTPException

client = TestClient(app, raise_server_exceptions=False)


# --- _own_session ownership logic ---

class _FakeDb:
    def __init__(self, session):
        self._session = session

    def get(self, model, session_id):
        return self._session if session_id == "s1" else None


def test_own_session_no_user_passes():
    """Unauthenticated local use: uid=None skips ownership check."""
    s = Session(id="s1", name="x", repo_path="/tmp", verify_command="true", user_id=None)
    result = _own_session("s1", None, _FakeDb(s))
    assert result is s


def test_own_session_matching_uid_passes():
    s = Session(id="s1", name="x", repo_path="/tmp", verify_command="true", user_id="u1")
    result = _own_session("s1", "u1", _FakeDb(s))
    assert result is s


def test_own_session_wrong_uid_raises_404():
    s = Session(id="s1", name="x", repo_path="/tmp", verify_command="true", user_id="u1")
    with pytest.raises(HTTPException) as exc_info:
        _own_session("s1", "u2", _FakeDb(s))
    assert exc_info.value.status_code == 404


def test_own_session_missing_session_raises_404():
    with pytest.raises(HTTPException) as exc_info:
        _own_session("nonexistent", "u1", _FakeDb(None))
    assert exc_info.value.status_code == 404


# --- SessionCreate validation ---

from routes.sessions import SessionCreate


def test_session_create_rejects_bad_model():
    with pytest.raises(Exception):  # pydantic ValidationError
        SessionCreate(
            name="test", repo_path="/tmp", verify_command="true",
            model="gpt-999-turbo-ultra",
            task={"title": "t", "spec": "s"},
        )


def test_session_create_rejects_zero_iterations():
    with pytest.raises(Exception):
        SessionCreate(
            name="test", repo_path="/tmp", verify_command="true",
            max_iterations=0,
            task={"title": "t", "spec": "s"},
        )


def test_session_create_rejects_over_50_iterations():
    with pytest.raises(Exception):
        SessionCreate(
            name="test", repo_path="/tmp", verify_command="true",
            max_iterations=51,
            task={"title": "t", "spec": "s"},
        )


def test_session_create_accepts_valid_model():
    body = SessionCreate(
        name="test", repo_path="/tmp", verify_command="true",
        model="claude-sonnet-4-6",
        task={"title": "t", "spec": "s"},
    )
    assert body.model == "claude-sonnet-4-6"


def test_session_create_accepts_max_boundary():
    body = SessionCreate(
        name="test", repo_path="/tmp", verify_command="true",
        max_iterations=50,
        task={"title": "t", "spec": "s"},
    )
    assert body.max_iterations == 50
