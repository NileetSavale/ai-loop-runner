import asyncio
import json
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from auth import resolve_user, user_id
from cache import redis
from database import get_session as db_session
from models import ChatSession, Session

router = APIRouter()

AUTH_TIMEOUT_SECONDS = 5
CLOSE_UNAUTHORIZED = 4401


async def broadcast(channel: str, message: dict):
    """Publish to Redis — all subscribers on any instance receive it."""
    await redis.publish(f"ws:{channel}", json.dumps(message))


async def _listen_and_forward(websocket: WebSocket, channel: str):
    """Subscribe to a Redis channel and forward messages to the WebSocket."""
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"ws:{channel}")
    try:
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                await websocket.send_text(msg["data"])
    except Exception:
        pass
    finally:
        await pubsub.unsubscribe(f"ws:{channel}")
        await pubsub.aclose()


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
