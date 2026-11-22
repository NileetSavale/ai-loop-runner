import asyncio
import json
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from auth import resolve_user, user_id
from redis.exceptions import RedisError

from cache import redis
from core.notify import notify
from database import get_session as db_session
from models import ChatSession, Session

router = APIRouter()

AUTH_TIMEOUT_SECONDS = 5
CLOSE_UNAUTHORIZED = 4401


# Redis is optional. With it, an event reaches every API instance and a TaskQ worker's events reach the page. Without
# it (a plain `uvicorn` on one machine, where the API runs the sessions itself), events go to this process's own
# listeners instead, so a fresh clone needs no Redis.
_local: dict[str, set[asyncio.Queue]] = {}
_redis_down = False


def _redis_failed(e: Exception):
    global _redis_down
    if not _redis_down:
        print(f"Redis unavailable ({e}); live events stay in this process")
    _redis_down = True


async def broadcast(channel: str, message: dict):
    """Publish to Redis — all subscribers on any instance receive it — or, without Redis, to this process's own
    listeners. A session's end, or a wait for approval, also goes to the owner's devices as a push notification once
    push is configured (core/notify.py)."""
    text = json.dumps(message)
    try:
        await redis.publish(f"ws:{channel}", text)
    except (RedisError, OSError) as e:
        _redis_failed(e)
    for queue in list(_local.get(channel, ())):
        queue.put_nowait(text)
    if not channel.startswith("chat:"):
        try:
            notify(channel, message)
        except Exception:
            pass  # a notification must never break the session's own events


async def _listen_and_forward(websocket: WebSocket, channel: str):
    """Forward the channel's events to the WebSocket: from Redis when it's there, from this process otherwise."""
    if not _redis_down:
        pubsub = redis.pubsub()
        try:
            await pubsub.subscribe(f"ws:{channel}")
        except (RedisError, OSError) as e:
            _redis_failed(e)
            await pubsub.aclose()
        else:
            try:
                async for msg in pubsub.listen():
                    if msg["type"] == "message":
                        await websocket.send_text(msg["data"])
            except Exception:
                pass
            finally:
                await pubsub.unsubscribe(f"ws:{channel}")
                await pubsub.aclose()
            return
    queue: asyncio.Queue = asyncio.Queue()
    _local.setdefault(channel, set()).add(queue)
    try:
        while True:
            await websocket.send_text(await queue.get())
    except Exception:
        pass
    finally:
        _local[channel].discard(queue)
        if not _local[channel]:
            del _local[channel]


async def _authorized(websocket: WebSocket, model, row_id: str) -> bool:
    """The first message is the JWT: browsers can't set WS headers, and query strings end up in logs."""
    try:
        token = await asyncio.wait_for(websocket.receive_text(), AUTH_TIMEOUT_SECONDS)
        user = resolve_user(token or None)
    except (asyncio.TimeoutError, HTTPException):
        return False
    uid = user_id(user) if user else None
    with db_session() as db:
        row = db.get(model, row_id)
        return row is not None and row.user_id == uid


async def _ws_handler(websocket: WebSocket, channel: str, model, row_id: str):
    await websocket.accept()
    try:
        if not await _authorized(websocket, model, row_id):
            await websocket.close(code=CLOSE_UNAUTHORIZED)
            return
        # run the Redis listener as a background task
        listener = asyncio.create_task(_listen_and_forward(websocket, channel))
        try:
            while True:
                await websocket.receive_text()  # keep-alive
        finally:
            listener.cancel()
    except WebSocketDisconnect:
        pass


@router.websocket("/ws/sessions/{session_id}")
async def ws_session(websocket: WebSocket, session_id: str):
    await _ws_handler(websocket, session_id, Session, session_id)


@router.websocket("/ws/chat/{chat_session_id}")
async def ws_chat(websocket: WebSocket, chat_session_id: str):
    await _ws_handler(websocket, f"chat:{chat_session_id}", ChatSession, chat_session_id)
