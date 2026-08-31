import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from cache import redis

router = APIRouter()


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


async def _ws_handler(websocket: WebSocket, channel: str):
    await websocket.accept()
    # run the Redis listener as a background task
    listener = asyncio.create_task(_listen_and_forward(websocket, channel))
    try:
        while True:
            await websocket.receive_text()  # keep-alive
    except WebSocketDisconnect:
        pass
    finally:
        listener.cancel()


@router.websocket("/ws/sessions/{session_id}")
async def ws_session(websocket: WebSocket, session_id: str):
    await _ws_handler(websocket, session_id)


@router.websocket("/ws/chat/{chat_session_id}")
async def ws_chat(websocket: WebSocket, chat_session_id: str):
    await _ws_handler(websocket, f"chat:{chat_session_id}")
