"""The study's reviewed cascade as a session option: a cheap model tries the task first, a stronger model reviews a fix
that passes the tests, and the session's own model redoes the task only if the cheap attempt fails or the review
rejects it.

In the study (research_notes/research_log.md), passing the repo's tests was weak evidence that a cheap model's fix was
right: about a fifth of the fixes Haiku's loop accepted failed SWE-bench's hidden tests. A cascade that escalated only
on failing tests solved little more than Haiku alone; with the review it came close to Sonnet alone. Each step goes
out as a "cascade" event, saved like the loop's own events so the page can show it after a reload.

The cheap attempt is undone by resetting the repo to the commit the session started from, so a repo with uncommitted
changes to tracked files is refused rather than have them lost. Untracked files the attempt created are removed; ones
that were there before stay, as the attempt left them. max_iterations applies to each model's loop, and the cost cap to the whole.
"""
import asyncio
import json
import subprocess
import uuid

from sqlmodel import select

from core.fix_review import REVIEWER_MODEL, edited_tests, review_fix
from core.loop import MAX_SESSION_COST_USD, BroadcastFn, _fail_session, _mark_session_failed, _running, run_loop
from core.scout import handover, run_scout, tried_summary
from database import get_session as db_session
from models import Iteration, Session, SessionEvent, Task, UsageEvent
from providers.router import _provider_for

CHEAP_MODEL = "claude-haiku-5-5"
SCOUT_BUDGET_USD = 0.05
REVIEW_PROMPT = "v2"


def _git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout


def _untracked(repo: str) -> set[str]:
    return set(_git(repo, "ls-files", "--others", "--exclude-standard", "-z").split("\0")) - {""}


def _show(repo: str, rev: str, path: str) -> str:
    """A file as it was at rev; empty if the fix created it."""
    try:
        return _git(repo, "show", f"{rev}:{path}")
    except subprocess.CalledProcessError:
        return ""


def _changed_files(diff: str) -> list[str]:
    return [line.split(" b/", 1)[1] for line in diff.splitlines() if line.startswith("diff --git ") and " b/" in line]


def cascade_problem(model: str) -> str | None:
    """Why a session can't run the cascade with this main model, or None."""
    if model == CHEAP_MODEL:
        return f"The cascade starts with {CHEAP_MODEL}, so pick a stronger main model to escalate to."
    if _provider_for(model) != _provider_for(CHEAP_MODEL):
        return "The cascade's cheap model and reviewer are Claude models, so pick a Claude model as the main one."
    return None


def _update(session_id: str, **fields):
    """Set Session fields, and the task's spec if given."""
    spec = fields.pop("spec", None)
    with db_session() as db:
        s = db.get(Session, session_id)
        for key, value in fields.items():
            setattr(s, key, value)
        db.add(s)
        if spec is not None:
            task = db.exec(select(Task).where(Task.session_id == session_id)).first()
            task.spec = spec
            db.add(task)
        db.commit()


def _charge(session_id: str, model: str, cost: float, input_tokens: int, output_tokens: int, byok: bool):
    """A call outside the loop (the scout, the review): added to the session's cost, and to billing for a user."""
    with db_session() as db:
        s = db.get(Session, session_id)
        s.total_cost_usd += cost
        s.total_tokens += input_tokens + output_tokens
        db.add(s)
        if s.user_id is not None:
            db.add(UsageEvent(id=str(uuid.uuid4()), user_id=s.user_id, session_id=session_id,
                              provider=_provider_for(model), model=model, input_tokens=input_tokens,
                              output_tokens=output_tokens, cost_usd=cost, byok=byok))
        db.commit()


def _spent(session_id: str) -> float:
    with db_session() as db:
        return db.get(Session, session_id).total_cost_usd


async def _run_stage(session_id: str, broadcast_fn: BroadcastFn, user_api_key: str | None, max_cost_usd: float,
                     loop_options: dict) -> tuple[dict | None, str]:
    """One model's loop. Its final pass or fail is held back, since the cascade decides when the session is done.
    Returns that final event's data (None if the loop sent none) and the last test output."""
    final: dict | None = None
    last_output = ""

    async def held(msg: dict):
        nonlocal final, last_output
        if msg["event"] == "verify_output":
            last_output = msg["data"].get("output") or ""
        if msg["event"] == "session_complete" and msg["data"].get("status") in ("passed", "failed"):
            final = msg["data"]
            if "iteration_number" in final:  # a pass carries its attempt, which the page still has to close
                await broadcast_fn({"event": "iteration_complete", "data": final})
            return
        await broadcast_fn(msg)

    # run_loop stops when the session leaves _running, and removes it when it ends, so each stage puts it back
    _running[session_id] = asyncio.current_task()
    await run_loop(session_id, held, user_api_key, max_cost_usd=max_cost_usd, **loop_options)
    return final, last_output


async def run_cascade(session_id: str, broadcast_fn: BroadcastFn, user_api_key: str | None = None,
                      max_cost_usd: float | None = None, cheap_model: str = CHEAP_MODEL, **loop_options):
    """loop_options: run_loop's, for both models' loops."""
    with db_session() as db:
        session = db.get(Session, session_id)
        repo, model = session.repo_path, session.model
        spec = db.exec(select(Task).where(Task.session_id == session_id)).first().spec
    limit = MAX_SESSION_COST_USD if max_cost_usd is None else max_cost_usd
    byok = user_api_key is not None

    async def step(data: dict):
        with db_session() as db:
            event = SessionEvent(session_id=session_id, kind="cascade", data=json.dumps(data))
            db.add(event)
            db.commit()
            event_id = event.id
        await broadcast_fn({"event": "cascade", "data": {**data, "id": event_id}})

    async def fail(reason: str):
        _mark_session_failed(session_id, reason)
        await _fail_session(session_id, broadcast_fn, reason)

    try:
        base = _git(repo, "rev-parse", "HEAD").strip()
        dirty = _git(repo, "status", "--porcelain", "--untracked-files=no").strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        await fail("The cascade needs a git repo with at least one commit: it undoes the cheap model's attempt by "
                   "resetting to the commit the session started from.")
        return
    if dirty:
        await fail("Commit or stash your changes first: the cascade undoes the cheap model's attempt by resetting to "
                   "the last commit, which would lose them.")
        return
    before = _untracked(repo)

    try:
        await step({"step": "scout", "model": cheap_model})
        notes, scouted = await run_scout(spec, repo, cheap_model, SCOUT_BUDGET_USD, user_api_key=user_api_key)
        _charge(session_id, cheap_model, scouted.cost_usd, scouted.input_tokens, scouted.output_tokens, byok)
        await step({"step": "cheap", "model": cheap_model, "notes": notes, "cost_usd": scouted.cost_usd})
        _update(session_id, model=cheap_model, spec=handover(spec, notes))
        final, last_output = await _run_stage(session_id, broadcast_fn, user_api_key, limit - _spent(session_id),
                                              loop_options)

        _git(repo, "add", "-A")
        # The loop's commit takes every untracked file, the user's own too; they aren't the attempt's work
        diff = _git(repo, "diff", "--cached", base, "--", ".", *(f":(exclude,literal){path}" for path in before))
        rejected = None
        if final and final.get("status") == "passed":
            await step({"step": "review", "model": REVIEWER_MODEL})
            _running[session_id] = asyncio.current_task()
            verdict = await review_fix(spec, diff, lambda path: _show(repo, base, path), "", REVIEW_PROMPT,
                                       user_api_key=user_api_key)
            _charge(session_id, REVIEWER_MODEL, verdict["cost_usd"], verdict["input_tokens"],
                    verdict["output_tokens"], byok)
            await step({"step": "reviewed", "model": REVIEWER_MODEL, "accept": verdict["accept"],
                        "why": verdict["why"], "edited_tests": edited_tests(diff), "cost_usd": verdict["cost_usd"]})
            if verdict["accept"]:
                await broadcast_fn({"event": "session_complete", "data": final})
                return
            rejected = verdict["why"]

        tried = tried_summary({path: [] for path in _changed_files(diff)}, [], [], "" if rejected else last_output, "")
        # Not reset --hard: that would delete the user's untracked files, which the loop's commit made tracked
        _git(repo, "reset", "-q", base)
        _git(repo, "checkout", "-q", "--", ".")
        created = sorted(_untracked(repo) - before)
        if created:
            _git(repo, "clean", "-fq", "--", *created)
        with db_session() as db:
            cheap_iterations = len(db.exec(select(Iteration).where(Iteration.session_id == session_id)).all())
        await step({"step": "escalated", "model": model, "cheap_iterations": cheap_iterations,
                    "reason": f"the reviewer rejected its fix: {rejected}" if rejected
                    else "its fix didn't pass the tests"})
        _update(session_id, model=model, status="running", completed_at=None,
                spec=handover(spec, notes, tried, rejected))
        final, _ = await _run_stage(session_id, broadcast_fn, user_api_key, limit - _spent(session_id), loop_options)
        if final:
            await broadcast_fn({"event": "session_complete", "data": final})

    except asyncio.CancelledError:
        _mark_session_failed(session_id, "cancelled")
        await broadcast_fn({"event": "session_complete", "data": {"status": "cancelled"}})
        raise

    except Exception as e:
        await fail(f"The run crashed: {e}")

    finally:
        # The session reads as what it was asked: the main model and the user's own task
        _update(session_id, model=model, spec=spec)
        _running.pop(session_id, None)


def start_cascade(session_id: str, broadcast_fn: BroadcastFn, user_api_key: str | None = None,
                  max_cost_usd: float | None = None, use_map: bool = True, add_tests: bool = False):
    task = asyncio.create_task(run_cascade(session_id, broadcast_fn, user_api_key, max_cost_usd,
                                           use_map=use_map, add_tests=add_tests))
    _running[session_id] = task
    return task
