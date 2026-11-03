import uuid
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, field_validator
from sqlmodel import select

from models import Session, Task, Iteration
from database import get_session as db_session
from core.loop import start_loop, stop_loop
from routes.ws import broadcast
from auth import get_optional_user, get_current_user, user_id
from routes.keys import get_user_api_key
from providers.base import SUPPORTED_MODELS
import os

router = APIRouter()

_ALL_MODEL_IDS = {m["id"] for models in SUPPORTED_MODELS.values() for m in models}


class TaskCreate(BaseModel):
    title: str
    spec: str
    files_context: list[str] = []


class SessionCreate(BaseModel):
    name: str
    repo_path: str
    verify_command: str
    max_iterations: int = 10
    model: str = "claude-sonnet-4-6"
    task: TaskCreate

    @field_validator("model")
    @classmethod
    def model_must_be_supported(cls, v: str) -> str:
        if v not in _ALL_MODEL_IDS:
            raise ValueError(f"Unsupported model '{v}'. Supported: {sorted(_ALL_MODEL_IDS)}")
        return v

    @field_validator("max_iterations")
    @classmethod
    def iterations_in_range(cls, v: int) -> int:
        if not 1 <= v <= 50:
            raise ValueError("max_iterations must be between 1 and 50")
        return v


def _own_session(session_id: str, uid: str | None, db) -> Session:
    """Return session if it belongs to uid. uid=None (anonymous local use) only reaches ownerless sessions."""
    session = db.get(Session, session_id)
    # Someone else's session → 404 (not 403, to avoid info leak)
    if not session or session.user_id != uid:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/sessions")
def list_sessions(user: dict | None = Depends(get_optional_user)):
    uid = user_id(user) if user else None
    with db_session() as db:
        query = select(Session).order_by(Session.created_at.desc())
        if uid is not None:
            query = query.where(Session.user_id == uid)
        else:
            # Local / unauthenticated: only show sessions with no user_id
            query = query.where(Session.user_id == None)  # noqa: E711
        sessions = db.exec(query).all()
        return [s.model_dump() for s in sessions]


@router.post("/sessions")
async def create_session(body: SessionCreate, user: dict | None = Depends(get_optional_user)):
    if not os.path.isdir(body.repo_path):
        raise HTTPException(status_code=400, detail=f"repo_path does not exist: {body.repo_path}")

    uid = user_id(user) if user else None
    api_key = get_user_api_key(uid, body.model) if uid else None

    session_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())

    with db_session() as db:
        session = Session(
            id=session_id,
            user_id=uid,
            name=body.name,
            repo_path=body.repo_path,
            verify_command=body.verify_command,
            max_iterations=body.max_iterations,
            model=body.model,
        )
        task = Task(
            id=task_id,
            session_id=session_id,
            title=body.task.title,
            spec=body.task.spec,
            files_context=json.dumps(body.task.files_context),
        )
        db.add(session)
        db.add(task)
        db.commit()

    async def broadcast_fn(msg: dict):
        await broadcast(session_id, msg)

    start_loop(session_id, broadcast_fn, user_api_key=api_key)
    return {"id": session_id}


@router.get("/sessions/{session_id}")
def get_session(session_id: str, user: dict | None = Depends(get_optional_user)):
    uid = user_id(user) if user else None
    with db_session() as db:
        session = _own_session(session_id, uid, db)
        iterations = db.exec(
            select(Iteration).where(Iteration.session_id == session_id).order_by(Iteration.iteration_number)
        ).all()
        task = db.exec(select(Task).where(Task.session_id == session_id)).first()
        return {
            **session.model_dump(),
            "task": task.model_dump() if task else None,
            "iterations": [i.model_dump() for i in iterations],
        }


@router.post("/sessions/{session_id}/stop")
def stop_session(session_id: str, user: dict | None = Depends(get_optional_user)):
    uid = user_id(user) if user else None
    with db_session() as db:
        session = _own_session(session_id, uid, db)
        stop_loop(session_id)
        session.status = "stopped"
        session.completed_at = datetime.utcnow()
        db.add(session)
        db.commit()
    return {"status": "stopped"}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, user: dict | None = Depends(get_optional_user)):
    uid = user_id(user) if user else None
    with db_session() as db:
        session = _own_session(session_id, uid, db)
        for i in db.exec(select(Iteration).where(Iteration.session_id == session_id)).all():
            db.delete(i)
        task = db.exec(select(Task).where(Task.session_id == session_id)).first()
        if task:
            db.delete(task)
        db.delete(session)
        db.commit()
    return {"deleted": session_id}


@router.get("/sessions/{session_id}/iterations")
def list_iterations(session_id: str, user: dict | None = Depends(get_optional_user)):
    uid = user_id(user) if user else None
    with db_session() as db:
        _own_session(session_id, uid, db)  # ownership check
        iterations = db.exec(
            select(Iteration).where(Iteration.session_id == session_id).order_by(Iteration.iteration_number)
        ).all()
        return [i.model_dump() for i in iterations]


@router.get("/iterations/{iteration_id}")
def get_iteration(iteration_id: str, user: dict | None = Depends(get_optional_user)):
    uid = user_id(user) if user else None
    with db_session() as db:
        it = db.get(Iteration, iteration_id)
        if not it:
            raise HTTPException(status_code=404)
        # Verify ownership via the parent session
        _own_session(it.session_id, uid, db)
        return it.model_dump()
