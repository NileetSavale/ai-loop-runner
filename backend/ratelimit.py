import logging
import os
import re
import time

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

import cache
from auth import _decode

logger = logging.getLogger(__name__)
_warned = False  # the no-Redis warning has been logged

WINDOW_SECONDS = 60
GENERAL_LIMIT = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
# Requests that spend LLM money or start a loop
EXPENSIVE_LIMIT = int(os.getenv("RATE_LIMIT_EXPENSIVE_PER_MINUTE", "10"))
_EXPENSIVE_POST = re.compile(r"^/(sessions|test-gen/generate|test-gen/apply-and-start|chat-sessions/[^/]+/messages)$")


def _client_id(request: Request) -> str:
    """Verified JWT subject, else client IP. Unverified tokens must not pick the bucket."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer":
        try:
            return f"user:{_decode(token)['sub']}"
        except jwt.InvalidTokenError:
            pass
    return f"ip:{request.client.host if request.client else 'unknown'}"


async def rate_limit(request: Request, call_next):
    if request.url.path == "/health":
        return await call_next(request)

    expensive = request.method == "POST" and _EXPENSIVE_POST.match(request.url.path)
    tier, limit = ("expensive", EXPENSIVE_LIMIT) if expensive else ("general", GENERAL_LIMIT)
    now = int(time.time())
    key = f"ratelimit:{tier}:{_client_id(request)}:{now // WINDOW_SECONDS}"

    # ponytail: fixed window, allows up to 2x limit across a window edge; sliding window if that matters
    try:
        async with cache.redis.pipeline(transaction=True) as pipe:
            count, _ = await pipe.incr(key).expire(key, WINDOW_SECONDS).execute()
    except (RedisError, OSError) as e:
        # Fail open: a Redis outage (or no Redis, locally) shouldn't also take down the whole API. Said once, not
        # on every request.
        global _warned
        if not _warned:
            logger.warning("Rate limiter off, no Redis: %s", e)
            _warned = True
        return await call_next(request)

    if count > limit:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": str(WINDOW_SECONDS - now % WINDOW_SECONDS)},
        )
    return await call_next(request)
