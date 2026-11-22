"""Tests for login enforcement, ownership, and per-user analytics across the API."""
import base64, hashlib, hmac, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

import fakeredis.aioredis
import jwt
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine
from starlette.websockets import WebSocketDisconnect

import auth
import cache
import database
from database import get_session as db_session
from main import app
from models import ChatSession, Session
import routes.analytics
import routes.ws

client = TestClient(app, raise_server_exceptions=False)
SECRET = "test-secret-that-is-long-enough-for-hs256"
PUBLIC = {"/health", "/keys/models", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    fake = fakeredis.aioredis.FakeRedis()
    monkeypatch.setattr(cache, "redis", fake)
    monkeypatch.setattr(routes.analytics, "redis", fake)
    monkeypatch.setattr(auth, "SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setattr(auth, "ALLOW_ANONYMOUS", False)
    monkeypatch.setattr(auth, "ALLOWED_USER_IDS", {"alice", "bob"})
    engine = create_engine(f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    with client:  # one event loop across requests: FakeRedis binds to the first one it sees
        yield


def bearer(sub: str, secret: str = SECRET) -> dict:
    token = jwt.encode({"sub": sub, "aud": "authenticated"}, secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def seed_session(id: str, owner: str | None, **fields):
    with db_session() as db:
        db.add(Session(id=id, user_id=owner, name=id, repo_path="/tmp", verify_command="true", **fields))
        db.commit()


def seed_chat(id: str, owner: str | None):
    with db_session() as db:
        db.add(ChatSession(id=id, user_id=owner, name=id, repo_path="/tmp", verify_command="true"))
        db.commit()


def api_routes():
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path not in PUBLIC:
            for method in route.methods:
                yield method, route.path.replace("{session_id}", "x").replace("{chat_session_id}", "x") \
                    .replace("{iteration_id}", "x").replace("{key_id}", "x")


@pytest.mark.parametrize("method,path", sorted(api_routes()))
def test_every_route_rejects_missing_token(method, path):
    """Walks the real route table, so a new unprotected route fails here."""
    assert client.request(method, path, json={}).status_code == 401


def test_forged_token_rejected():
    assert client.get("/sessions", headers=bearer("alice", secret="x" * 40)).status_code == 401


def test_invalid_token_is_not_downgraded_to_anonymous(monkeypatch):
    monkeypatch.setattr(auth, "ALLOW_ANONYMOUS", True)
    assert client.get("/sessions", headers=bearer("alice", secret="x" * 40)).status_code == 401


def test_unset_secret_rejects_tokens(monkeypatch):
    monkeypatch.setattr(auth, "SUPABASE_JWT_SECRET", "")
    # Signed with an empty key by hand: PyJWT itself now refuses to sign with one
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=")
    signed = b64(b'{"alg":"HS256","typ":"JWT"}') + b"." + b64(b'{"sub":"alice","aud":"authenticated"}')
    token = (signed + b"." + b64(hmac.new(b"", signed, hashlib.sha256).digest())).decode()
    assert client.get("/sessions", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_valid_user_outside_allowlist_is_forbidden():
    assert client.get("/sessions", headers=bearer("stranger")).status_code == 403


def test_allowlisted_user_gets_in():
    assert client.get("/sessions", headers=bearer("alice")).status_code == 200


def test_local_mode_allows_anonymous_but_only_ownerless_rows(monkeypatch):
    monkeypatch.setattr(auth, "ALLOW_ANONYMOUS", True)
    seed_session("mine", None)
    seed_session("theirs", "alice")
    seed_chat("their-chat", "alice")
    assert client.get("/sessions/mine").status_code == 200
    assert client.get("/sessions/theirs").status_code == 404
    assert client.post("/sessions/theirs/stop", json={}).status_code == 404
    assert client.delete("/sessions/theirs").status_code == 404
    assert client.get("/chat-sessions/their-chat").status_code == 404


def test_chat_is_scoped_to_owner():
    seed_chat("c1", "alice")
    assert [c["id"] for c in client.get("/chat-sessions", headers=bearer("alice")).json()] == ["c1"]
    assert client.get("/chat-sessions", headers=bearer("bob")).json() == []
    assert client.get("/chat-sessions/c1", headers=bearer("bob")).status_code == 404


def test_cannot_start_a_loop_on_someone_elses_chat():
    seed_chat("c1", "alice")
    with patch("routes.chat.start_loop") as start:
        res = client.post("/chat-sessions/c1/messages", json={"prompt": "hi"}, headers=bearer("bob"))
    assert res.status_code == 404
    start.assert_not_called()


def test_chat_loop_is_billed_to_owner_with_their_key():
    seed_chat("c1", "alice")
    with patch("routes.chat.start_loop") as start, patch("routes.chat.get_user_api_key", return_value="byok"):
        res = client.post("/chat-sessions/c1/messages", json={"prompt": "hi"}, headers=bearer("alice"))
    assert res.status_code == 200
    assert start.call_args.kwargs["user_api_key"] == "byok"
    with db_session() as db:
        assert db.get(Session, res.json()["loop_session_id"]).user_id == "alice"


@pytest.mark.parametrize("path,extra", [
    ("/chat-sessions", {"name": "n", "verify_command": "true"}),
    ("/test-gen/apply-and-start", {"test_files": [], "verify_command": "true", "implementation_spec": "s", "session_name": "n"}),
])
def test_iteration_cap_enforced_outside_sessions_route(path, extra):
    body = {"repo_path": "/tmp", "max_iterations": 100000, **extra}
    assert client.post(path, json=body, headers=bearer("alice")).status_code == 422


def test_analytics_only_counts_your_sessions():
    seed_session("a", "alice", status="passed", total_cost_usd=1.0)
    seed_session("b", "bob", status="failed", total_cost_usd=5.0)
    for _ in range(2):  # second pass reads from cache, which must not leak across users either
        alice = client.get("/analytics/summary", headers=bearer("alice")).json()
        bob = client.get("/analytics/summary", headers=bearer("bob")).json()
        assert (alice["total_sessions"], alice["total_cost_usd"]) == (1, 1.0)
        assert (bob["total_sessions"], bob["total_cost_usd"]) == (1, 5.0)
    top = client.get("/analytics/top-tasks", headers=bearer("alice")).json()
    assert [t["id"] for t in top] == ["a"]


def ws_token(sub: str) -> str:
    return bearer(sub)["Authorization"].removeprefix("Bearer ")


@pytest.fixture
def subscribed(monkeypatch):
    async def fake_listen(websocket, channel):
        await websocket.send_text(f"subscribed:{channel}")
    monkeypatch.setattr(routes.ws, "_listen_and_forward", fake_listen)


@pytest.mark.parametrize("token", ["", "garbage", ws_token("bob"), ws_token("stranger")])
def test_ws_rejects_everyone_but_the_owner(subscribed, token):
    seed_session("s1", "alice")
    with client.websocket_connect("/ws/sessions/s1") as ws:
        ws.send_text(token)
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_text()
    assert exc.value.code == routes.ws.CLOSE_UNAUTHORIZED


def test_ws_owner_is_subscribed_after_sending_token(subscribed):
    seed_session("s1", "alice")
    seed_chat("c1", "alice")
    with client.websocket_connect("/ws/sessions/s1") as ws:
        ws.send_text(ws_token("alice"))
        assert ws.receive_text() == "subscribed:s1"
    with client.websocket_connect("/ws/chat/c1") as ws:
        ws.send_text(ws_token("alice"))
        assert ws.receive_text() == "subscribed:chat:c1"


def test_ws_silent_client_is_dropped(subscribed, monkeypatch):
    monkeypatch.setattr(routes.ws, "AUTH_TIMEOUT_SECONDS", 0.01)
    seed_session("s1", "alice")
    with client.websocket_connect("/ws/sessions/s1") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_text()
    assert exc.value.code == routes.ws.CLOSE_UNAUTHORIZED


# --- Supabase signing keys (ES256, from the project's JWKS) ---

from fastapi import HTTPException

def _signed_with_key(sub: str, key, kid: str = "k1") -> str:
    return jwt.encode({"sub": sub, "aud": "authenticated"}, key, algorithm="ES256", headers={"kid": kid})


@pytest.fixture
def signing_key(monkeypatch):
    """A project's signing key pair, with the JWKS fetch replaced by its public half."""
    from types import SimpleNamespace
    from cryptography.hazmat.primitives.asymmetric import ec
    private = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(auth, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(auth, "_signing_keys", lambda: SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=private.public_key())))
    return private


def test_a_token_signed_with_the_projects_key_is_accepted(signing_key):
    assert auth.resolve_user(_signed_with_key("alice", signing_key))["sub"] == "alice"


def test_a_token_signed_with_another_key_is_refused(signing_key):
    from cryptography.hazmat.primitives.asymmetric import ec
    other = ec.generate_private_key(ec.SECP256R1())
    with pytest.raises(HTTPException) as e:
        auth.resolve_user(_signed_with_key("alice", other))
    assert e.value.status_code == 401


def test_a_signing_key_token_needs_supabase_url(signing_key, monkeypatch):
    monkeypatch.setattr(auth, "SUPABASE_URL", "")
    with pytest.raises(HTTPException) as e:
        auth.resolve_user(_signed_with_key("alice", signing_key))
    assert "SUPABASE_URL" in e.value.detail


def test_an_unsigned_token_is_refused(signing_key):
    unsigned = jwt.encode({"sub": "alice", "aud": "authenticated"}, None, algorithm="none")
    with pytest.raises(HTTPException) as e:
        auth.resolve_user(unsigned)
    assert e.value.status_code == 401


def test_the_legacy_secret_still_works_beside_signing_keys(signing_key):
    token = jwt.encode({"sub": "bob", "aud": "authenticated"}, SECRET, algorithm="HS256")
    assert auth.resolve_user(token)["sub"] == "bob"
