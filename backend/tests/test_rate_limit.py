"""Tests for the rate limiting middleware. POSTs use an empty body: it 422s, so no loop starts."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from types import SimpleNamespace

import fakeredis.aioredis
import jwt
import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlmodel import create_engine

import auth
import cache
import database
import ratelimit
from main import app

client = TestClient(app, raise_server_exceptions=False)
SECRET = "test-secret-that-is-long-enough-for-hs256"


@pytest.fixture(autouse=True)
def limiter(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "redis", fakeredis.aioredis.FakeRedis())
    monkeypatch.setattr(auth, "SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setattr(auth, "ALLOW_ANONYMOUS", True)
    monkeypatch.setattr(ratelimit, "EXPENSIVE_LIMIT", 2)
    monkeypatch.setattr(ratelimit, "GENERAL_LIMIT", 3)
    monkeypatch.setattr(database, "engine", create_engine(f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False}))
    clock = SimpleNamespace(time=lambda: 1000.0)  # 40s into its window
    monkeypatch.setattr(ratelimit, "time", clock)
    with client:  # one event loop across requests: FakeRedis binds to the first one it sees
        yield clock


def bearer(sub: str, secret: str = SECRET) -> dict:
    token = jwt.encode({"sub": sub, "aud": "authenticated"}, secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def post_sessions(headers: dict | None = None) -> int:
    return client.post("/sessions", json={}, headers=headers).status_code


def test_expensive_route_blocks_over_limit_with_retry_after():
    assert [post_sessions(), post_sessions()] == [422, 422]
    res = client.post("/sessions", json={})
    assert res.status_code == 429
    assert res.headers["retry-after"] == "20"


def test_every_llm_route_uses_expensive_tier():
    for path in ["/sessions", "/test-gen/generate", "/test-gen/apply-and-start", "/chat-sessions/c1/messages"]:
        assert ratelimit._EXPENSIVE_POST.match(path), path
    assert not ratelimit._EXPENSIVE_POST.match("/sessions/s1/stop")


def test_new_window_resets_count(limiter):
    post_sessions(), post_sessions()
    assert post_sessions() == 429
    limiter.time = lambda: 1020.0
    assert post_sessions() == 422


def test_users_have_separate_buckets():
    alice, bob = bearer("alice"), bearer("bob")
    post_sessions(alice), post_sessions(alice)
    assert post_sessions(alice) == 429
    assert post_sessions(bob) == 422


def test_forged_tokens_cannot_escape_the_ip_bucket():
    post_sessions(), post_sessions()
    assert post_sessions(bearer("anyone-else", secret="x" * 40)) == 429


def test_general_tier_is_separate_and_applies_to_reads():
    post_sessions(), post_sessions()
    assert post_sessions() == 429
    statuses = [client.get("/keys/models").status_code for _ in range(4)]
    assert statuses == [200, 200, 200, 429]


def test_health_is_exempt():
    assert {client.get("/health").status_code for _ in range(5)} == {200}


def test_429_includes_cors_headers():
    origin = {"Origin": "http://localhost:3000"}
    client.post("/sessions", json={}), client.post("/sessions", json={})
    res = client.post("/sessions", json={}, headers=origin)
    assert res.status_code == 429
    assert res.headers["access-control-allow-origin"] == origin["Origin"]


def test_redis_outage_fails_open(monkeypatch):
    class DownPipeline:
        async def __aenter__(self):
            raise RedisConnectionError("down")

        async def __aexit__(self, *exc):
            pass

    monkeypatch.setattr(cache, "redis", SimpleNamespace(pipeline=lambda transaction: DownPipeline()))
    assert post_sessions() == 422
