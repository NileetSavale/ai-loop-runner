import uuid, json, os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select

from models import ChatSession, ChatMessage, Session, Task
from database import get_session as db_session
from core.loop import start_loop
from routes.ws import broadcast
from routes.keys import get_user_api_key
from auth import get_optional_user, user_id

router = APIRouter()


class ChatSessionCreate(BaseModel):
    name: str
    repo_path: str
    verify_command: str
    model: str = "claude-sonnet-4-6"
    max_iterations: int = Field(10, ge=1, le=50)


class MessageCreate(BaseModel):
    prompt: str
    files_context: list[str] = []


def _own_chat(chat_session_id: str, uid: str | None, db) -> ChatSession:
    """Return chat session if it belongs to uid. Someone else's → 404, same as sessions."""
    cs = db.get(ChatSession, chat_session_id)
    if not cs or cs.user_id != uid:
        raise HTTPException(status_code=404)
    return cs


@router.get("/chat-sessions")
def list_chat_sessions(user: dict | None = Depends(get_optional_user)):
    uid = user_id(user) if user else None
    with db_session() as db:
        rows = db.exec(
            select(ChatSession).where(ChatSession.user_id == uid).order_by(ChatSession.created_at.desc())
        ).all()
        return [r.model_dump() for r in rows]


@router.post("/chat-sessions")
def create_chat_session(body: ChatSessionCreate, user: dict | None = Depends(get_optional_user)):
    if not os.path.isdir(body.repo_path):
        raise HTTPException(status_code=400, detail=f"repo_path does not exist: {body.repo_path}")
    uid = user_id(user) if user else None
    cs = ChatSession(id=str(uuid.uuid4()), user_id=uid, **body.model_dump())
    with db_session() as db:
        db.add(cs)
        db.commit()
    return cs.model_dump()


@router.get("/chat-sessions/{chat_session_id}")
def get_chat_session(chat_session_id: str, user: dict | None = Depends(get_optional_user)):
    uid = user_id(user) if user else None
    with db_session() as db:
        cs = _own_chat(chat_session_id, uid, db)
        messages = db.exec(
            select(ChatMessage).where(ChatMessage.chat_session_id == chat_session_id)
            .order_by(ChatMessage.created_at)
        ).all()
        return {**cs.model_dump(), "messages": [m.model_dump() for m in messages]}


@router.post("/chat-sessions/{chat_session_id}/messages")
async def send_message(chat_session_id: str, body: MessageCreate, user: dict | None = Depends(get_optional_user)):
    uid = user_id(user) if user else None
    with db_session() as db:
        cs = _own_chat(chat_session_id, uid, db)
    api_key = get_user_api_key(uid, cs.model) if uid else None

    # Each message gets its own underlying loop Session
    loop_session_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    msg_id = str(uuid.uuid4())

    with db_session() as db:
        loop_session = Session(
            id=loop_session_id,
            user_id=uid,
            name=body.prompt[:80],
            repo_path=cs.repo_path,
            verify_command=cs.verify_command,
            max_iterations=cs.max_iterations,
            model=cs.model,
        )
        task = Task(
            id=task_id,
            session_id=loop_session_id,
            title=body.prompt[:80],
            spec=body.prompt,
            files_context=json.dumps(body.files_context),
        )
        msg = ChatMessage(
            id=msg_id,
            chat_session_id=chat_session_id,
            prompt=body.prompt,
            loop_session_id=loop_session_id,
        )
        db.add(loop_session)
        db.add(task)
        db.add(msg)
        db.commit()

    async def broadcast_fn(event: dict):
        # broadcast on both the loop session channel AND the chat session channel
        await broadcast(loop_session_id, event)
        await broadcast(f"chat:{chat_session_id}", {**event, "message_id": msg_id})

        # when the loop completes, update the ChatMessage row
        if event["event"] == "session_complete":
            data = event["data"]
            with db_session() as db:
                m = db.get(ChatMessage, msg_id)
                s = db.get(Session, loop_session_id)
                m.status = data.get("status", "failed")
                m.git_commit_hash = data.get("commit")
                m.total_iterations = s.total_iterations
                m.total_cost_usd = s.total_cost_usd
                m.completed_at = datetime.utcnow()
                db.add(m)
                db.commit()

    start_loop(loop_session_id, broadcast_fn, user_api_key=api_key)
    return {"message_id": msg_id, "loop_session_id": loop_session_id}
