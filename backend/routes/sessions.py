import asyncio
import shutil
import uuid
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator
from sqlmodel import select

from models import Session, SessionEvent, Task, Iteration
from database import get_session as db_session
from core.cascade import cascade_problem
from core.loop import stop_loop
from core.workspace import (HOSTED, WORKSPACES, CloneError, base_commit, clone, diff, github_repo, head,
                            owns_workspace, record, start_session)
from core.repo_map import build_repo_map
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
    # One of these: a folder on this machine, or a GitHub repo to clone (core/workspace.py)
    repo_path: str | None = None
    repo_url: str | None = None
    branch: str | None = None
    github_token: str | None = Field(None, repr=False)  # used once to clone a private repo, never stored
    sandbox: bool = False  # run a local folder's checks in a container too; a cloned repo's always are
    verify_command: str
    max_iterations: int = 10
    max_cost_usd: float | None = Field(None, gt=0)  # None = server default
    add_tests: bool = False
    cascade: bool = False  # a cheap model tries first; see core/cascade.py
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
    if (body.repo_path is None) == (body.repo_url is None):
        raise HTTPException(status_code=400, detail="Give either repo_path or repo_url.")
    if body.repo_path is not None:
        if HOSTED:
            raise HTTPException(status_code=400, detail="This server only runs sessions on GitHub repos: use repo_url.")
        if not os.path.isdir(body.repo_path):
            raise HTTPException(status_code=400, detail=f"repo_path does not exist: {body.repo_path}")
    else:
        try:
            github_repo(body.repo_url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    if body.cascade and (problem := cascade_problem(body.model)):
        raise HTTPException(status_code=400, detail=problem)

    uid = user_id(user) if user else None
    api_key = get_user_api_key(uid, body.model) if uid else None

    session_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    if body.repo_url is not None:
        repo_path = str(WORKSPACES / session_id)
        try:
            base = await asyncio.to_thread(clone, body.repo_url, WORKSPACES / session_id, body.branch, body.github_token)
        except (CloneError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        repo_path = body.repo_path
        base = head(repo_path)

    with db_session() as db:
        session = Session(
            id=session_id,
            user_id=uid,
            name=body.name,
            repo_path=repo_path,
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

    record(session_id, body.repo_url, body.branch, base)
    start_session(session_id, broadcast_fn, cascade=body.cascade, sandboxed=body.repo_url is not None or body.sandbox,
                  user_api_key=api_key, max_cost_usd=body.max_cost_usd, add_tests=body.add_tests, use_map=True)
    return {"id": session_id}


@router.get("/sessions/{session_id}")
def get_session(session_id: str, user: dict | None = Depends(get_optional_user)):
    uid = user_id(user) if user else None
    with db_session() as db:
        session = _own_session(session_id, uid, db)
        iterations = db.exec(
            select(Iteration).where(Iteration.session_id == session_id).order_by(Iteration.started_at)
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
        for e in db.exec(select(SessionEvent).where(SessionEvent.session_id == session_id)).all():
            db.delete(e)
        task = db.exec(select(Task).where(Task.session_id == session_id)).first()
        if task:
            db.delete(task)
        repo_path = session.repo_path
        db.delete(session)
        db.commit()
    stop_loop(session_id)
    if owns_workspace(repo_path):
        shutil.rmtree(repo_path, ignore_errors=True)
    return {"deleted": session_id}


@router.get("/sessions/{session_id}/diff", response_class=PlainTextResponse)
def session_diff(session_id: str, user: dict | None = Depends(get_optional_user)):
    """The session's changes as a patch the user can apply with git apply."""
    uid = user_id(user) if user else None
    with db_session() as db:
        repo_path = _own_session(session_id, uid, db).repo_path
    base = base_commit(session_id)
    if not base or not os.path.isdir(repo_path):
        raise HTTPException(status_code=404, detail="No changes to show: the repo or its starting commit is gone.")
    return PlainTextResponse(diff(repo_path, base), headers={
        "Content-Disposition": f'attachment; filename="loop-runner-{session_id[:8]}.diff"'})


@router.get("/sessions/{session_id}/iterations")
def list_iterations(session_id: str, user: dict | None = Depends(get_optional_user)):
    uid = user_id(user) if user else None
    with db_session() as db:
        _own_session(session_id, uid, db)  # ownership check
        iterations = db.exec(
            select(Iteration).where(Iteration.session_id == session_id).order_by(Iteration.started_at)
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


@router.get("/repo-map")
def repo_map(repo_path: str, user: dict | None = Depends(get_optional_user)):
    """The map of a repo, for choosing files before a session exists."""
    if HOSTED:
        raise HTTPException(status_code=404, detail="Not available on this server.")
    if not os.path.isdir(repo_path):
        raise HTTPException(status_code=400, detail="repo_path does not exist")
    return build_repo_map(repo_path)


@router.get("/sessions/{session_id}/map")
def session_map(session_id: str, user: dict | None = Depends(get_optional_user)):
    uid = user_id(user) if user else None
    with db_session() as db:
        repo_path = _own_session(session_id, uid, db).repo_path
    if not os.path.isdir(repo_path):
        raise HTTPException(status_code=404, detail="The repo for this session no longer exists")
    return build_repo_map(repo_path)


@router.get("/sessions/{session_id}/events")
def session_events(session_id: str, user: dict | None = Depends(get_optional_user)):
    uid = user_id(user) if user else None
    with db_session() as db:
        _own_session(session_id, uid, db)
        rows = db.exec(select(SessionEvent).where(SessionEvent.session_id == session_id).order_by(SessionEvent.id)).all()
        return [{"id": r.id, "kind": r.kind, **json.loads(r.data)} for r in rows]
