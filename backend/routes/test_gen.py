import json
import os
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import select

from agents.test_gen import generate_tests, apply_tests, detect_stack
from models import Session, Task, UsageEvent
from database import get_session as db_session
from core.loop import start_loop
from providers.router import _provider_for
from routes.analytics import invalidate_analytics
from routes.ws import broadcast
from routes.keys import get_user_api_key
from auth import get_optional_user, user_id

router = APIRouter(prefix="/test-gen", tags=["test-gen"])


class GenerateRequest(BaseModel):
    description: str
    repo_path: str
    tech_stack: str | None = None
    context_files: list[str] = []
    model: str = "claude-sonnet-4-6"


class ApplyAndStartRequest(BaseModel):
    repo_path: str
    test_files: list[dict]          # [{"path": str, "content": str}]
    verify_command: str
    implementation_spec: str
    session_name: str
    model: str = "claude-sonnet-4-6"
    max_iterations: int = Field(10, ge=1, le=50)
    max_cost_usd: float | None = Field(None, gt=0)  # None = server default


@router.get("/detect-stack")
def detect_stack_endpoint(repo_path: str, user: dict | None = Depends(get_optional_user)):
    if not os.path.isdir(repo_path):
        raise HTTPException(status_code=400, detail="repo_path does not exist")
    return {"stack": detect_stack(repo_path)}


@router.post("/generate")
async def generate(body: GenerateRequest, user: dict | None = Depends(get_optional_user)):
    if not os.path.isdir(body.repo_path):
        raise HTTPException(status_code=400, detail="repo_path does not exist")

    uid = user_id(user) if user else None
    api_key = get_user_api_key(uid, body.model) if uid else None

    try:
        result = await generate_tests(
            description=body.description,
            repo_path=body.repo_path,
            tech_stack=body.tech_stack,
            context_files=body.context_files,
            model=body.model,
            user_api_key=api_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Recorded even if the reply is unusable: the call was still paid for. No loop session exists yet.
    if uid is not None:
        with db_session() as db:
            db.add(UsageEvent(
                id=str(uuid.uuid4()),
                user_id=uid,
                session_id="test-generation",
                provider=_provider_for(body.model),
                model=body.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
                byok=api_key is not None,
            ))
            db.commit()
        await invalidate_analytics()

    if result.truncated:
        raise HTTPException(status_code=400, detail="The test suite was cut off by the output limit. Describe a smaller feature.")

    return {
        "cost_usd": result.cost_usd,
        "test_files": result.test_files,
        "verify_command": result.verify_command,
        "implementation_spec": result.implementation_spec,
    }


@router.post("/apply-and-start")
async def apply_and_start(body: ApplyAndStartRequest, user: dict | None = Depends(get_optional_user)):
    if not os.path.isdir(body.repo_path):
        raise HTTPException(status_code=400, detail="repo_path does not exist")

    uid = user_id(user) if user else None
    api_key = get_user_api_key(uid, body.model) if uid else None

    # 1. write test files to disk
    try:
        await apply_tests(body.repo_path, body.test_files)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. create session + task
    session_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())

    with db_session() as db:
        session = Session(
            id=session_id,
            user_id=uid,
            name=body.session_name,
            repo_path=body.repo_path,
            verify_command=body.verify_command,
            max_iterations=body.max_iterations,
            model=body.model,
        )
        task = Task(
            id=task_id,
            session_id=session_id,
            title=body.session_name,
            spec=body.implementation_spec,
            files_context=json.dumps(
                [f["path"] for f in body.test_files]
            ),
        )
        db.add(session)
        db.add(task)
        db.commit()

    async def broadcast_fn(msg: dict):
        await broadcast(session_id, msg)

    # Generated tests promise to fail until the feature exists, so hold them to it
    start_loop(session_id, broadcast_fn, user_api_key=api_key, require_failing=True, max_cost_usd=body.max_cost_usd)
    return {"session_id": session_id}
