import asyncio
import json
import os
import uuid
from datetime import datetime
from typing import Callable, Awaitable

from sqlmodel import select

from models import Session, Task, Iteration, UsageEvent
from database import get_session as db_session
from core.agent import run_agent, AgentResult
from core.verifier import run_verify
from core.git_ops import git_commit
from routes.analytics import invalidate_analytics
from providers.router import _provider_for

_running: dict[str, asyncio.Task] = {}

BroadcastFn = Callable[[dict], Awaitable[None]]


def build_file_context(files: list[str], repo_path: str) -> str:
    parts = []
    for rel_path in files:
        abs_path = os.path.join(repo_path, rel_path)
        try:
            content = open(abs_path).read()
            parts.append(f"### {rel_path}\n```\n{content}\n```")
        except FileNotFoundError:
            parts.append(f"### {rel_path}\n(file not found)")
    return "\n\n".join(parts)


def build_prompt(spec: str, context: str, iteration: int, last_verify_output: str | None = None) -> str:
    retry_note = ""
    if iteration > 1:
        error_block = f"\n\n```\n{last_verify_output}\n```" if last_verify_output else ""
        retry_note = f"\n\n> attempt #{iteration}. Previous attempt failed verification. Fix the errors below.{error_block}"
    return f"## Task Spec\n{spec}{retry_note}\n\n## Current File Contents\n{context}"


def apply_edits(edits, repo_path: str) -> list[str]:
    changed = []
    for edit in edits:
        path = os.path.join(repo_path, edit.path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").write(edit.content)
        changed.append(edit.path)
    return changed


def _mark_session_failed(session_id: str, reason: str):
    try:
        with db_session() as db:
            s = db.get(Session, session_id)
            if s and s.status == "running":
                s.status = "failed"
                s.completed_at = datetime.utcnow()
                db.add(s)
                db.commit()
    except Exception:
        pass  # best-effort; don't mask the original error


async def run_loop(session_id: str, broadcast_fn: BroadcastFn, user_api_key: str | None = None):
    # Load session + task once; scalar columns are eagerly loaded so safe to use detached
    with db_session() as db:
        session = db.get(Session, session_id)
        task = db.exec(select(Task).where(Task.session_id == session_id)).first()
        # Copy scalars we need so we don't touch the detached ORM object later
        session_user_id = session.user_id
        max_iterations = session.max_iterations
        repo_path = session.repo_path
        model = session.model
        verify_command = session.verify_command
        spec = task.spec
        task_title = task.title
        files = task.get_files_context()

    iteration = 1
    last_verify_output: str | None = None

    try:
        while iteration <= max_iterations:
            if session_id not in _running:
                break

            context = build_file_context(files, repo_path)
            prompt = build_prompt(spec, context, iteration, last_verify_output)

            await broadcast_fn({"event": "iteration_start", "data": {"iteration": iteration}})

            started = datetime.utcnow()

            async def on_token(chunk: str):
                await broadcast_fn({"event": "agent_token", "data": {"token": chunk}})

            agent_result = await run_agent(prompt, model, user_api_key=user_api_key, on_token=on_token)

            changed = apply_edits(agent_result.edits, repo_path)

            verify_result = await run_verify(verify_command, repo_path)
            last_verify_output = verify_result.output  # feed into next retry prompt

            await broadcast_fn({"event": "verify_output", "data": {"output": verify_result.output, "passed": verify_result.passed}})

            duration = (datetime.utcnow() - started).total_seconds()
            status = "passed" if verify_result.passed else "failed"

            iter_id = str(uuid.uuid4())
            commit_hash = None

            if verify_result.passed:
                try:
                    commit_hash = git_commit(repo_path, f"loop-runner: {task_title} (iter {iteration})")
                except Exception:
                    pass

            with db_session() as db:
                db.add(Iteration(
                    id=iter_id,
                    session_id=session_id,
                    iteration_number=iteration,
                    status=status,
                    agent_output=agent_result.raw_output,
                    files_changed=json.dumps(changed),
                    verify_output=verify_result.output,
                    input_tokens=agent_result.input_tokens,
                    output_tokens=agent_result.output_tokens,
                    cost_usd=agent_result.cost_usd,
                    duration_seconds=duration,
                    git_commit_hash=commit_hash,
                    started_at=started,
                    completed_at=datetime.utcnow(),
                ))
                # Record usage for billing/audit — only for authenticated users
                if session_user_id is not None:
                    db.add(UsageEvent(
                        id=str(uuid.uuid4()),
                        user_id=session_user_id,
                        session_id=session_id,
                        provider=_provider_for(model),
                        model=model,
                        input_tokens=agent_result.input_tokens,
                        output_tokens=agent_result.output_tokens,
                        cost_usd=agent_result.cost_usd,
                        byok=user_api_key is not None,
                    ))
                s = db.get(Session, session_id)
                s.total_iterations += 1
                s.total_tokens += agent_result.input_tokens + agent_result.output_tokens
                s.total_cost_usd += agent_result.cost_usd
                if verify_result.passed:
                    s.status = "passed"
                    s.completed_at = datetime.utcnow()
                elif iteration >= max_iterations:
                    s.status = "failed"
                    s.completed_at = datetime.utcnow()
                db.add(s)
                db.commit()

            iter_payload = {
                "id": iter_id,
                "iteration_number": iteration,
                "status": status,
                "cost_usd": agent_result.cost_usd,
                "input_tokens": agent_result.input_tokens,
                "output_tokens": agent_result.output_tokens,
                "duration_seconds": duration,
                "git_commit_hash": commit_hash,
            }

            if verify_result.passed:
                await broadcast_fn({"event": "session_complete", "data": {"status": "passed", "commit": commit_hash, **iter_payload}})
                await invalidate_analytics()
                break
            else:
                await broadcast_fn({"event": "iteration_complete", "data": iter_payload})
                iteration += 1
                if iteration > max_iterations:
                    await broadcast_fn({"event": "session_complete", "data": {"status": "failed"}})

    except asyncio.CancelledError:
        _mark_session_failed(session_id, "cancelled")
        await broadcast_fn({"event": "session_complete", "data": {"status": "cancelled"}})
        raise  # re-raise so asyncio knows the task was cancelled

    except Exception as e:
        _mark_session_failed(session_id, str(e))
        await broadcast_fn({"event": "session_complete", "data": {"status": "failed", "error": str(e)}})

    finally:
        _running.pop(session_id, None)


def start_loop(session_id: str, broadcast_fn: BroadcastFn, user_api_key: str | None = None):
    task = asyncio.create_task(run_loop(session_id, broadcast_fn, user_api_key))
    _running[session_id] = task
    return task


def stop_loop(session_id: str):
    task = _running.pop(session_id, None)
    if task:
        task.cancel()
