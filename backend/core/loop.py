import asyncio
import json
import os
import re
import subprocess
import uuid
from datetime import datetime
from typing import Callable, Awaitable

from sqlmodel import select

from models import Session, SessionEvent, Task, Iteration, UsageEvent
from database import get_session as db_session
from core.agent import run_agent, AgentResult, FileEdit, parse_file_blocks
from core.edits import apply_edits, describe_change, filter_edits, is_locked_path, is_secret_path, is_test_path, read_current, resolve_in_repo
from core.repo_map import build_repo_map, locate_issue, map_for_prompt
from core.security import (AUDIT_SYSTEM_PROMPT, PAIR_SYSTEM_PROMPT, AuditCache, audit_prompt, files_to_audit,
                           findings_for, findings_guide, pair_prompt, parse_findings, parse_verdict)
from core.tester import TEST_REVIEW_SYSTEM_PROMPT, TESTER_SYSTEM_PROMPT, test_review_prompt, tester_prompt, tests_guide
from core.tools import MAX_LISTED_FILES, MAX_TEST_OUTPUT_CHARS, RepoTools
from core.verifier import failing_tests, run_verify, short_test_output, tail, VerifyResult
from core.git_ops import git_commit
from core.mutation import check_test_strength
from core.sandbox import Sandbox
from core.test_changes import REVIEW_SYSTEM_PROMPT, parse_review, review_prompt
from providers.base import calculate_cost
from providers.router import get_provider
from routes.analytics import invalidate_analytics
from providers.router import _provider_for

_running: dict[str, asyncio.Task] = {}

BroadcastFn = Callable[[dict], Awaitable[None]]

MAX_SESSION_COST_USD = float(os.getenv("MAX_SESSION_COST_USD", "5"))
MAX_IDENTICAL_FAILURES = 3
# Attempts in a row where every failing test was already failing before any change. On a repo with an unrelated
# broken test, retrying can't make the run green, and it once spent $1.51 trying.
MAX_ONLY_OLD_FAILURES = 2
# Attempts in a row that changed nothing. Once the agent stops editing, more attempts only add cost.
MAX_NO_EDIT_ATTEMPTS = 2
MIN_MUTATION_SCORE = float(os.getenv("MIN_MUTATION_SCORE", "0.7"))
MAX_BASELINE_OUTPUT_CHARS = 1_500
# How a retry learns about earlier attempts. continue is the default: on the two pilot bugs that retry it was the
# cheapest in all 6 head-to-head runs (2026-11-07), 33-40% below fresh with the same solves.
#   fresh     a new conversation with the task, the last test output and the full files it changed
#   continue  the same conversation, with the test output added as the next message
#   record    a new conversation with the diff so far and a short record of each earlier attempt
RETRY_CONTEXTS = ("fresh", "continue", "record")
MAX_DIFF_CHARS = 8_000
MAX_RECORD_ACTIONS = 20
MAX_RECORD_SUMMARY_CHARS = 600
MAX_RECORD_TESTS = 15


def build_file_context(files: list[str], repo_path: str) -> str:
    parts = []
    for rel_path in files:
        if is_secret_path(rel_path):
            parts.append(f"### {rel_path}\n(holds credentials, not read)")
            continue
        try:
            content = open(resolve_in_repo(repo_path, rel_path)).read()
            parts.append(f"### {rel_path}\n```\n{content}\n```")
        except FileNotFoundError:
            parts.append(f"### {rel_path}\n(file not found)")
        except ValueError:
            parts.append(f"### {rel_path}\n(outside the repo, not read)")
    return "\n\n".join(parts)


def diff_so_far(repo_path: str, paths: list[str]) -> str:
    """The agent's changes against the last commit, with new files in full."""
    if not paths:
        return ""
    git = lambda *args: subprocess.run(["git", *args], cwd=repo_path, capture_output=True, text=True).stdout
    diff = git("diff", "HEAD", "--", *paths)
    for path in git("ls-files", "--others", "--exclude-standard", "--", *paths).split():
        try:
            diff += f"\n(new file) {path}\n{open(resolve_in_repo(repo_path, path)).read()}"
        except (OSError, ValueError):
            pass
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n(diff cut here; read the files for the rest)"
    return diff


def attempt_record(iteration: int, result: AgentResult, changed: list[str], failing: set[str], broken: set[str]) -> str:
    """A few lines on what one attempt did, so a fresh retry knows what was already tried."""
    looked = list(dict.fromkeys(a for a in result.actions if not a.startswith(("edit_file", "write_file"))))
    lines = [f"### Attempt {iteration}"]
    lines.append(f"Looked at: {', '.join(looked[:MAX_RECORD_ACTIONS]) or 'nothing'}"
                 + (f" and {len(looked) - MAX_RECORD_ACTIONS} more" if len(looked) > MAX_RECORD_ACTIONS else ""))
    lines.append(f"Changed: {', '.join(changed) or 'nothing'}")
    if result.final_text.strip():
        lines.append(f"Its summary when it stopped: {result.final_text.strip()[-MAX_RECORD_SUMMARY_CHARS:]}")
    names = sorted(failing)
    lines.append(f"Tests failing after it: {', '.join(names[:MAX_RECORD_TESTS]) or 'none could be read from the output'}"
                 + (f" and {len(names) - MAX_RECORD_TESTS} more" if len(names) > MAX_RECORD_TESTS else ""))
    if broken:
        lines.append(f"Of those, passing before any change: {', '.join(sorted(broken)[:MAX_RECORD_TESTS])}")
    return "\n".join(lines)


def record_guide(records: list[str], diff: str) -> str:
    parts = ["## What earlier attempts did\n" + "\n\n".join(records)]
    if diff:
        parts.append(
            "## Your changes so far\nThese are in the files now. Build on them, or undo the parts that don't help.\n"
            f"```diff\n{diff}\n```"
        )
    return "".join(f"{p}\n\n" for p in parts)


def continue_prompt(iteration: int, last_verify_output: str | None) -> str:
    return (
        f"> attempt #{iteration}. You stopped, and the system ran the tests: they still fail. Your changes are still in "
        f"place. Fix the errors below.\n\n```\n{last_verify_output or ''}\n```"
    )


def build_prompt(spec: str, context: str, iteration: int, last_verify_output: str | None = None, guide: str = "") -> str:
    retry_note = ""
    if iteration > 1:
        error_block = f"\n\n```\n{last_verify_output}\n```" if last_verify_output else ""
        retry_note = f"\n\n> attempt #{iteration}. Previous attempt failed verification. Fix the errors below.{error_block}"
    return f"## Task Spec\n{spec}{retry_note}\n\n{guide}## Current File Contents\n{context}"


def _build_guide(repo_map: dict, focus: list[dict], baseline: VerifyResult | None, old_failures: set[str] = frozenset(),
                 max_old_failure_names: int | None = None) -> str:
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
    if old_failures:
        # Said up front, since most of the spend happens inside the first attempt
        shown = sorted(old_failures)[:max_old_failure_names]
        names = "\n".join(f"- {n}" for n in shown)
        if len(shown) < len(old_failures):
            names += f"\n- and {len(old_failures) - len(shown)} more"
        parts.append(
            f"## Tests already failing before your changes\n{names}\n"
            "These fail before you change anything, so they are not part of your task unless it names them. "
            "Don't try to make them pass; expect them to keep failing when you run the tests."
        )
    if baseline and not baseline.passed:
        parts.append(f"## Test output before your changes\n```\n{baseline.output[-MAX_BASELINE_OUTPUT_CHARS:]}\n```")
    return "".join(f"{p}\n\n" for p in parts)


async def _judge_test_strength(result: VerifyResult, repo_path: str, verify_command: str, files: list[str],
                               sandbox: Sandbox | None = None) -> VerifyResult:
    """Decide whether a green test run should count, given how many planted bugs the tests catch."""
    code = [f for f in files if not is_test_path(f) and not is_locked_path(f)]
    if not code:
        return VerifyResult(
            passed=False,
            output="Tests pass, but no implementation file was changed or listed, so nothing shows they test anything.",
            exit_code=1,
        )
    python = [f for f in code if f.endswith(".py")]
    strength = await check_test_strength(repo_path, verify_command, python, sandbox) if python else None
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
    allow_test_changes: bool = True,
    retry_context: str = "continue",
    max_only_old_failures: int = MAX_ONLY_OLD_FAILURES,
    short_output: bool = False,
    max_old_failure_names: int | None = None,
    security_audit: bool = False,
    security_pair: bool = False,
    write_tests_first: bool = False,
    reviewer_effort: str | None = None,
    max_listed_files: int = MAX_LISTED_FILES,
    audit_cache: str | None = None,
    sandbox: Sandbox | None = None,
    attribute_failures: bool = True,
):
    """The last three trim tokens and are off by default until measured: stop sooner when only tests that failed
    before any change still fail, give the agent failing names and the end of test output rather than 8k characters
    of it, and list at most this many already-failing tests up front.

    security_audit: before work starts, an auditor reads the code the task touches and its findings go to the coder.
    security_pair: a reviewer checks the coder's changes each time it runs the tests, and again before it can finish.
    write_tests_first: a tester writes tests for the task before the coder starts, checked by a reviewer.
    reviewer_effort: thinking effort for the yes-or-no reviewers (test changes, security pair, the tester's tests).
    They think at the model's default otherwise, which was most of their output tokens.
    max_listed_files: how many paths list_files returns.
    audit_cache: a file where the security auditor keeps findings per file, so later tasks on the same repo only pay
    to audit files that are new or changed.
    sandbox: run every check in a container (core/sandbox.py) rather than on this machine.
    attribute_failures: False is the ablation for the research question. Every failing test counts as the agent's,
    as in a plain verify-and-retry loop: it isn't told which tests failed before it started, isn't stopped when only
    those still fail, and test changes are reviewed without that information."""
    if retry_context not in RETRY_CONTEXTS:
        raise ValueError(f"retry_context must be one of {RETRY_CONTEXTS}")
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
    no_edit_attempts = 0
    cost_limit = MAX_SESSION_COST_USD if max_cost_usd is None else max_cost_usd
    added_tests: set[str] = set()
    touched: set[str] = set()
    guide = ""
    history: list | None = None  # the last attempt's conversation, for retry_context="continue"
    records: list[str] = []      # what each attempt did, for retry_context="record"

    async def emit(kind: str, data: dict):
        """Save what happened and send it to the website. The id lets the page merge saved and live events."""
        with db_session() as db:
            event = SessionEvent(session_id=session_id, kind=kind, data=json.dumps({**data, "iteration": iteration}))
            db.add(event)
            db.commit()
            event_id = event.id
        await broadcast_fn({"event": kind, "data": {**data, "id": event_id, "iteration": iteration}})

    try:
        baseline = await run_verify(verify_command, repo_path, sandbox) if require_failing or use_map else None
        if require_failing and baseline.passed:
            reason = "The tests already pass before any work, so a pass would prove nothing. Stopped without calling the LLM."
            _mark_session_failed(session_id, reason)
            await _fail_session(session_id, broadcast_fn, reason)
            return

        # When the task is to make failing tests pass, those failures are the job, not someone else's breakage
        old_failures = failing_tests(baseline.output) if baseline and not baseline.passed and not require_failing else set()
        baseline_failures = failing_tests(baseline.output) if baseline and not baseline.passed else set()
        if not attribute_failures:
            old_failures, baseline_failures = set(), set()

        if use_map:
            # No LLM here: this costs time, not tokens, and it's what saves them later
            repo_map = await asyncio.to_thread(build_repo_map, repo_path)
            focus = locate_issue(repo_map, spec, baseline.output if baseline and not baseline.passed else None, files, repo_path)
            guide = _build_guide(repo_map, focus, baseline if attribute_failures else None, old_failures,
                                 max_old_failure_names)
            await emit("focus", {"files": focus, "tests_passing": baseline.passed})

        review_spend = {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0}
        flagged: list[str] = []  # tests the reviewer thinks a human should check

        async def ask(system: str, prompt: str, step: str, effort: str | None = None) -> str:
            """A reviewer's model call. Its spend is added to the current attempt."""
            result = await get_provider(model, user_api_key).complete(system, prompt, model, None, effort=effort)
            cost = calculate_cost(model, result.input_tokens, result.output_tokens)
            review_spend["cost_usd"] += cost
            review_spend["input_tokens"] += result.input_tokens
            review_spend["output_tokens"] += result.output_tokens
            await emit("usage", {
                "step": step, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
                "cache_read_tokens": 0, "cache_write_tokens": 0, "cost_usd": cost,
            })
            return result.text

        findings: list[dict] = []
        if security_audit:
            audited = files_to_audit(focus, repo_map["edges"], is_test_path) if use_map else [f for f in files if not is_test_path(f)]
            contents = {p: c for p in audited if not is_secret_path(p) and (c := read_current(repo_path, p))}
            cache = AuditCache(audit_cache, model) if audit_cache else None
            known = {p: found for p, c in contents.items() if cache and (found := cache.get(p, c)) is not None}
            todo = {p: c for p, c in contents.items() if p not in known}
            new: list[dict] = []
            if todo:
                context = {p: contents[p] for p in known}
                new = parse_findings(await ask(AUDIT_SYSTEM_PROMPT, audit_prompt(todo, context), "security_audit"))
                if cache:
                    for p, c in todo.items():
                        cache.put(p, c, findings_for(p, new))
                    cache.save()
            findings = new + [f for found in known.values() for f in found]
            await emit("security_findings", {"files": list(contents), "audited": list(todo), "cached": list(known),
                                             "findings": findings})
            guide += findings_guide(findings)

        task_tests: set[str] = set()  # the tester's tests: the coder's job, never something it broke
        if write_tests_first:
            code_paths = files_to_audit(focus, repo_map["edges"], is_test_path) if use_map else [f for f in files if not is_test_path(f)]
            test_paths = [n["path"] for n in repo_map["nodes"] if n["is_test"]] if use_map else []
            code = {p: c for p in code_paths if not is_secret_path(p) and (c := read_current(repo_path, p))}
            existing_tests = {p: c for p in test_paths if not is_secret_path(p) and (c := read_current(repo_path, p))}
            written, problems, approved = {}, None, False
            for _ in range(2):  # one rewrite if the reviewer sends the tests back
                reply = await ask(TESTER_SYSTEM_PROMPT, tester_prompt(spec, code, existing_tests, problems), "tester")
                written = {e.path: e.content for e in parse_file_blocks(reply)
                           if is_test_path(e.path) and not read_current(repo_path, e.path)}
                if not written:
                    break
                approved, problems = parse_verdict(await ask(TEST_REVIEW_SYSTEM_PROMPT, test_review_prompt(spec, written), "test_check", reviewer_effort))
                if approved:
                    break
            if written and approved:
                apply_edits([FileEdit(path, content) for path, content in written.items()], repo_path)
                check = await run_verify(verify_command, repo_path, sandbox)
                failing = failing_tests(check.output) - baseline_failures
                ours = {n for n in failing if any(n.startswith(path) for path in written)}
                # Only keep tests that fail for the right reason: a feature that's missing, not a file that won't load,
                # and without breaking tests that passed before
                if ours and failing == ours and not any(n in written for n in ours):
                    task_tests = ours
                    guide += tests_guide(sorted(written), task_tests)
            if written and not task_tests:
                for path in written:
                    try:
                        os.remove(resolve_in_repo(repo_path, path))
                    except OSError:
                        pass
            await emit("tests_written", {"files": sorted(written), "tests": sorted(task_tests), "approved": approved,
                                         "problems": problems or [], "kept": bool(task_tests)})

        security_reviews: dict[str, tuple[bool, list[str]]] = {}  # by diff, so an unchanged diff isn't paid for twice

        async def security_review(changed: list[str]) -> list[str]:
            diff = diff_so_far(repo_path, sorted(touched | set(changed)))
            if not diff:
                return []
            if diff not in security_reviews:
                approved, problems = parse_verdict(await ask(PAIR_SYSTEM_PROMPT, pair_prompt(spec, findings, diff), "security_pair", reviewer_effort))
                security_reviews[diff] = (approved, problems)
                await emit("security_review", {"approved": approved, "problems": problems})
            approved, problems = security_reviews[diff]
            return [] if approved else problems

        async def review_test_change(path: str, diff: str, reason: str) -> tuple[bool, str]:
            """A separate model call that sees the task, the test diff and the reason, but not the coder's reasoning."""
            text = await ask(REVIEW_SYSTEM_PROMPT, review_prompt(spec, diff, reason, baseline_failures), "test_review", reviewer_effort)
            approved, why, escalate = parse_review(text)
            await emit("test_change_review", {
                "path": path, "reason": reason, "approved": approved, "escalate": escalate, "why": why, "diff": diff,
            })
            if escalate:
                flagged.append(f"{path}: {why}")
                why += " The test has been flagged for a human to check. Don't change it again or work around it."
            return approved, why

        while iteration <= max_iterations:
            if session_id not in _running:
                break

            # Files this session created have to be visible, or retries can't build on them
            if retry_context == "continue" and history:
                prompt = continue_prompt(iteration, last_verify_output)
            elif retry_context == "record" and records:
                # The changed files come as a diff, and the agent reads more if it needs to
                prompt = build_prompt(spec, build_file_context(files, repo_path), iteration, last_verify_output,
                                      guide + record_guide(records, diff_so_far(repo_path, sorted(touched))))
            else:
                context = build_file_context(files + sorted(touched - set(files)), repo_path)
                prompt = build_prompt(spec, context, iteration, last_verify_output, guide)

            await broadcast_fn({"event": "iteration_start", "data": {"iteration": iteration}})

            started = datetime.utcnow()

            async def on_token(chunk: str):
                await broadcast_fn({"event": "agent_token", "data": {"token": chunk}})

            agent_result = await run_agent(
                prompt, model, user_api_key=user_api_key, on_token=on_token,
                tools=RepoTools(repo_path, verify_command, added_tests, review_test_change if allow_test_changes else None,
                                short_output, old_failures, security_review if security_pair else None, max_listed_files,
                                sandbox),
                max_cost_usd=cost_limit - total_cost,
                on_event=emit,
                add_tests=add_tests,
                history=history if retry_context == "continue" else None,
            )
            history = agent_result.messages or None
            # The reviewer's spend belongs to this attempt, so limits and records include it
            agent_result.cost_usd += review_spend["cost_usd"]
            agent_result.input_tokens += review_spend["input_tokens"]
            agent_result.output_tokens += review_spend["output_tokens"]
            review_spend.update(cost_usd=0.0, input_tokens=0, output_tokens=0)

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

            no_edit_attempts = 0 if changed else no_edit_attempts + 1
            # No change can't make this attempt pass: already-green tests prove nothing new
            if changed:
                verify_result = await run_verify(verify_command, repo_path, sandbox)
            elif touched:
                # Earlier changes are still in place, so the agent needs to know what they still break
                current = await run_verify(verify_command, repo_path, sandbox)
                verify_result = VerifyResult(
                    passed=False,
                    output=f"You made no changes in this attempt. With your earlier changes, the tests give:\n{current.output}",
                    exit_code=current.exit_code if not current.passed else -1,
                )
            else:
                verify_result = VerifyResult(
                    passed=False,
                    output='No edits were applied. Respond only with complete <file path="..."> blocks.',
                    exit_code=-1,
                )
            if verify_result.passed and (added_tests or require_failing):
                verify_result = await _judge_test_strength(
                    verify_result, repo_path, verify_command, sorted(touched | set(files)), sandbox
                )
            if verify_result.passed and security_pair:
                # The agent can't finish with changes the security reviewer sent back
                problems = await security_review(changed)
                if problems:
                    verify_result = VerifyResult(False, verify_result.output + "\n\nThe tests pass, but the security reviewer "
                                                 "sent your changes back:\n" + "\n".join(f"- {p}" for p in problems), 1)
                agent_result.cost_usd += review_spend["cost_usd"]
                agent_result.input_tokens += review_spend["input_tokens"]
                agent_result.output_tokens += review_spend["output_tokens"]
                review_spend.update(cost_usd=0.0, input_tokens=0, output_tokens=0)
            # Fed into the next retry, so it is cut like run_tests output: the full output once cost $0.35 on a
            # single retry. The end is kept, since that is where test runners print the summary.
            shown = (short_test_output(verify_result.output, old_failures) if short_output
                     else tail(verify_result.output, MAX_TEST_OUTPUT_CHARS))
            last_verify_output = "\n".join(rejected + [shown])

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
                broken = failing - baseline_failures - task_tests if baseline and attribute_failures else set()
                if retry_context == "record":
                    records.append(attempt_record(iteration, agent_result, changed, failing, broken))
                if broken:
                    last_verify_output += (
                        f"\n\nThese tests passed before your changes and fail now, so your changes broke them: "
                        f"{', '.join(sorted(broken))}."
                    )
                if flagged:
                    # Retrying can't help: the agent mustn't touch the test, and the test may be wrong
                    stop_reason = f"Stopped: flagged a test for a human to check ({flagged[0]})"
                elif total_cost >= cost_limit:
                    stop_reason = f"Stopped: spent ${total_cost:.2f}, over the ${cost_limit:.2f} session limit."
                elif no_edit_attempts >= MAX_NO_EDIT_ATTEMPTS:
                    stop_reason = f"Stopped: {no_edit_attempts} attempts in a row made no changes."
                elif only_old_failures >= max_only_old_failures:
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
    allow_test_changes: bool = True,
    retry_context: str = "continue",
    **trims,
):
    """trims: run_loop's token-trimming options."""
    task = asyncio.create_task(run_loop(
        session_id, broadcast_fn, user_api_key, require_failing, max_cost_usd, use_map, add_tests, allow_test_changes,
        retry_context, **trims,
    ))
    _running[session_id] = task
    return task


def stop_loop(session_id: str):
    task = _running.pop(session_id, None)
    if task:
        task.cancel()
