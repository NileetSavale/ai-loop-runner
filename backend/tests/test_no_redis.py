"""Running without Redis: a plain `uvicorn` on one machine needs none (live events stay in the process, the
analytics cache is skipped)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio


def test_without_redis_live_events_still_reach_this_process_listeners(monkeypatch):
    """A plain `uvicorn` with no Redis: broadcast falls back to the in-process listeners."""
    import routes.ws as ws
    from redis.exceptions import ConnectionError as RedisConnectionError

    class NoRedis:
        async def publish(self, *args):
            raise RedisConnectionError("Error 61 connecting to localhost:6379")

    monkeypatch.setattr(ws, "redis", NoRedis())
    monkeypatch.setattr(ws, "_redis_down", False)

    async def scenario():
        queue = asyncio.Queue()
        ws._local.setdefault("s1", set()).add(queue)
        try:
            await ws.broadcast("s1", {"event": "focus", "data": {}})
            return await asyncio.wait_for(queue.get(), 1)
        finally:
            ws._local.pop("s1", None)

    assert '"event": "focus"' in asyncio.run(scenario())
    assert ws._redis_down is True


def test_analytics_work_without_redis(monkeypatch):
    import routes.analytics as analytics
    from redis.exceptions import ConnectionError as RedisConnectionError

    class NoRedis:
        async def get(self, *a): raise RedisConnectionError("down")
        async def setex(self, *a): raise RedisConnectionError("down")
        async def delete(self, *a): raise RedisConnectionError("down")

    monkeypatch.setattr(analytics, "redis", NoRedis())

    @analytics.cached("t")
    def compute(user=None):
        return {"answer": 42}

    assert asyncio.run(compute(user=None)) == {"answer": 42}
    asyncio.run(analytics.invalidate_analytics(None))  # no Redis, nothing to clear, no error
