import asyncio
import json
import os
import re
import uuid
from datetime import datetime
from typing import Callable, Awaitable

from sqlmodel import select

from models import Session, SessionEvent, Task, Iteration, UsageEvent
from database import get_session as db_session
from core.agent import run_agent, AgentResult
from core.edits import apply_edits, describe_change, filter_edits, is_locked_path, is_test_path, read_current, resolve_in_repo
from core.repo_map import build_repo_map, locate_issue, map_for_prompt
from core.tools import RepoTools
from core.verifier import failing_tests, run_verify, VerifyResult
from core.git_ops import git_commit
from core.mutation import check_test_strength
from routes.analytics import invalidate_analytics
from providers.router import _provider_for

_running: dict[str, asyncio.Task] = {}

BroadcastFn = Callable[[dict], Awaitable[None]]

MAX_SESSION_COST_USD = float(os.getenv("MAX_SESSION_COST_USD", "5"))
MAX_IDENTICAL_FAILURES = 3
# Attempts in a row where every failing test was already failing before any change. On a repo with an unrelated
# broken test, retrying can't make the run green, and it once spent $1.51 trying.
MAX_ONLY_OLD_FAILURES = 2
MIN_MUTATION_SCORE = float(os.getenv("MIN_MUTATION_SCORE", "0.7"))
MAX_BASELINE_OUTPUT_CHARS = 1_500


def build_file_context(files: list[str], repo_path: str) -> str:
    parts = []
    for rel_path in files:
        try:
            content = open(resolve_in_repo(repo_path, rel_path)).read()
            parts.append(f"### {rel_path}\n```\n{content}\n```")
        except FileNotFoundError:
            parts.append(f"### {rel_path}\n(file not found)")
        except ValueError:
            parts.append(f"### {rel_path}\n(outside the repo, not read)")
    return "\n\n".join(parts)


def build_prompt(spec: str, context: str, iteration: int, last_verify_output: str | None = None, guide: str = "") -> str:
    retry_note = ""
    if iteration > 1:
        error_block = f"\n\n```\n{last_verify_output}\n```" if last_verify_output else ""
        retry_note = f"\n\n> attempt #{iteration}. Previous attempt failed verification. Fix the errors below.{error_block}"
    return f"## Task Spec\n{spec}{retry_note}\n\n{guide}## Current File Contents\n{context}"


def _build_guide(repo_map: dict, focus: list[dict], baseline: VerifyResult | None) -> str:
    """Tell the agent where to look, so it doesn't pay to find out.

    Names only, not file contents. Measured on one bug, including two files cost more than this on both Haiku 5.5
    and Sonnet 5.5, because reads later in the conversation are cheap once it's cached.
    """
    parts = []
    if focus:
        likely = "\n".join(f"- {f['path']} ({f['reason']})" for f in focus)
        parts.append(f"## Likely places to look\n{likely}")
    if repo_map["nodes"]:
        parts.append(f"## Repo map\n{map_for_prompt(repo_map, focus)}")
    if baseline and not baseline.passed:
        parts.append(f"## Test output before your changes\n```\n{baseline.output[-MAX_BASELINE_OUTPUT_CHARS:]}\n```")
    return "".join(f"{p}\n\n" for p in parts)


async def _judge_test_strength(result: VerifyResult, repo_path: str, verify_command: str, files: list[str]) -> VerifyResult:
    """Decide whether a green test run should count, given how many planted bugs the tests catch."""
    code = [f for f in files if not is_test_path(f) and not is_locked_path(f)]
    if not code:
        return VerifyResult(
            passed=False,
            output="Tests pass, but no implementation file was changed or listed, so nothing shows they test anything.",
            exit_code=1,
        )
    python = [f for f in code if f.endswith(".py")]
    strength = await check_test_strength(repo_path, verify_command, python) if python else None
    if strength is None or strength.skipped_reason:
        reason = strength.skipped_reason if strength else "it only supports Python so far"
        return VerifyResult(True, f"{result.output}\nTest strength NOT checked: {reason}.", result.exit_code)

    summary = f"Tests caught {strength.caught} of {strength.tested} deliberately planted bugs"
    if strength.tested < 3:
        summary += " (too few to say much about these tests)"
    if strength.caught / strength.tested >= MIN_MUTATION_SCORE:
        return VerifyResult(True, f"{result.output}\n{summary}.", result.exit_code)
    missed = "\n".join(f"- {s}" for s in strength.survivors)
    return VerifyResult(
        passed=False,
        output=f"Tests pass but are too weak. {summary} (need {MIN_MUTATION_SCORE:.0%}). "
               f"Add new test files that fail when these bugs exist:\n{missed}",
        exit_code=1,
    )


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


async def _fail_session(session_id: str, broadcast_fn: BroadcastFn, reason: str):
    # verify_output is what the UI displays, so the reason is visible without a frontend change
    await broadcast_fn({"event": "verify_output", "data": {"output": reason, "passed": False}})
    await broadcast_fn({"event": "session_complete", "data": {"status": "failed", "error": reason}})


async def run_loop(
    session_id: str,
    broadcast_fn: BroadcastFn,
    user_api_key: str | None = None,
    require_failing: bool = False,
    max_cost_usd: float | None = None,
    use_map: bool = False,
    add_tests: bool = False,
):
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
    total_cost = 0.0
    last_failure: str | None = None
    identical_failures = 0
    only_old_failures = 0
    cost_limit = MAX_SESSION_COST_USD if max_cost_usd is None else max_cost_usd
    added_tests: set[str] = set()
    touched: set[str] = set()
    guide = ""

    async def emit(kind: str, data: dict):
        """Save what happened and send it to the website. The id lets the page merge saved and live events."""
        with db_session() as db:
            event = SessionEvent(session_id=session_id, kind=kind, data=json.dumps({**data, "iteration": iteration}))
            db.add(event)
            db.commit()
            event_id = event.id
        await broadcast_fn({"event": kind, "data": {**data, "id": event_id, "iteration": iteration}})

    try:
        baseline = await run_verify(verify_command, repo_path) if require_failing or use_map else None
        if require_failing and baseline.passed:
            reason = "The tests already pass before any work, so a pass would prove nothing. Stopped without calling the LLM."
            _mark_session_failed(session_id, reason)
            await _fail_session(session_id, broadcast_fn, reason)
            return

        if use_map:
            # No LLM here: this costs time, not tokens, and it's what saves them later
            repo_map = await asyncio.to_thread(build_repo_map, repo_path)
            focus = locate_issue(repo_map, spec, baseline.output if baseline and not baseline.passed else None, files, repo_path)
            guide = _build_guide(repo_map, focus, baseline)
            await emit("focus", {"files": focus, "tests_passing": baseline.passed})
        # When the task is to make failing tests pass, those failures are the job, not someone else's breakage
        old_failures = failing_tests(baseline.output) if baseline and not baseline.passed and not require_failing else set()

        while iteration <= max_iterations:
            if session_id not in _running:
                break

            # Files this session created have to be visible, or retries can't build on them
            context = build_file_context(files + sorted(touched - set(files)), repo_path)
            prompt = build_prompt(spec, context, iteration, last_verify_output, guide)

            await broadcast_fn({"event": "iteration_start", "data": {"iteration": iteration}})

            started = datetime.utcnow()

            async def on_token(chunk: str):
                await broadcast_fn({"event": "agent_token", "data": {"token": chunk}})

            agent_result = await run_agent(
                prompt, model, user_api_key=user_api_key, on_token=on_token,
                tools=RepoTools(repo_path, verify_command, added_tests),
                max_cost_usd=cost_limit - total_cost,
                on_event=emit,
                add_tests=add_tests,
            )

            allowed, rejected = filter_edits(agent_result.edits, repo_path, added_tests)
            # Tool agents report their own changes as they go. This is the one-shot path.
            befores = [(e, read_current(repo_path, e.path)) for e in allowed]
            changed = apply_edits(allowed, repo_path) + agent_result.applied
            for edit, before in befores:
                await emit("file_changed", describe_change(edit.path, before, edit.content))
            rejected += agent_result.notes
            touched.update(changed)
            if agent_result.truncated:
                rejected.append("Your reply hit the output limit, so any unfinished file was dropped. Change fewer or smaller files.")

            # No change means nothing to verify. Already-green tests must not count as this attempt passing.
            if changed:
                verify_result = await run_verify(verify_command, repo_path)
            else:
                verify_result = VerifyResult(
                    passed=False,
                    output='No edits were applied. Respond only with complete <file path="..."> blocks.',
                    exit_code=-1,
                )
            if verify_result.passed and (added_tests or require_failing):
                verify_result = await _judge_test_strength(
                    verify_result, repo_path, verify_command, sorted(touched | set(files))
                )
            last_verify_output = "\n".join(rejected + [verify_result.output])  # feed into next retry prompt

            stop_reason = None
            if not verify_result.passed:
                total_cost += agent_result.cost_usd
                failing = failing_tests(verify_result.output)
                failure = re.sub(r"\d+", "#", verify_result.output)  # ignore timings and line numbers
                identical_failures = identical_failures + 1 if failure == last_failure else 1
                last_failure = failure
                only_old = changed and bool(failing) and failing <= old_failures
                only_old_failures = only_old_failures + 1 if only_old else 0
                if only_old:
                    names = ", ".join(sorted(failing))
                    last_verify_output += (
                        f"\n\nEvery test still failing was already failing before your changes: {names}. "
                        "Leave them alone unless the task is about them."
                    )
                if total_cost >= cost_limit:
                    stop_reason = f"Stopped: spent ${total_cost:.2f}, over the ${cost_limit:.2f} session limit."
                elif only_old_failures >= MAX_ONLY_OLD_FAILURES:
                    stop_reason = f"Stopped: the only failing tests were already failing before any change ({', '.join(sorted(failing))})."
                elif identical_failures >= MAX_IDENTICAL_FAILURES:
                    stop_reason = f"Stopped: the same failure repeated {identical_failures} times in a row."

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
                elif iteration >= max_iterations or stop_reason:
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
                await invalidate_analytics(session_user_id)
                break
            else:
                await broadcast_fn({"event": "iteration_complete", "data": iter_payload})
                if stop_reason:
                    await _fail_session(session_id, broadcast_fn, stop_reason)
                    break
                iteration += 1
                if iteration > max_iterations:
                    await broadcast_fn({"event": "session_complete", "data": {"status": "failed"}})

    except asyncio.CancelledError:
        _mark_session_failed(session_id, "cancelled")
        await broadcast_fn({"event": "session_complete", "data": {"status": "cancelled"}})
        raise  # re-raise so asyncio knows the task was cancelled

    except Exception as e:
        _mark_session_failed(session_id, str(e))
        await _fail_session(session_id, broadcast_fn, f"The run crashed: {e}")

    finally:
        _running.pop(session_id, None)


def start_loop(
    session_id: str,
    broadcast_fn: BroadcastFn,
    user_api_key: str | None = None,
    require_failing: bool = False,
    max_cost_usd: float | None = None,
    use_map: bool = True,
    add_tests: bool = False,
):
    task = asyncio.create_task(run_loop(session_id, broadcast_fn, user_api_key, require_failing, max_cost_usd, use_map, add_tests))
    _running[session_id] = task
    return task


def stop_loop(session_id: str):
    task = _running.pop(session_id, None)
    if task:
        task.cancel()
