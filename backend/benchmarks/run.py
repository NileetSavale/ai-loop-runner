"""Measure an agent on tasks it can't game: success means passing hidden tests it never sees.

    cd backend && python -m benchmarks.run --arm loop --model claude-sonnet-5-5 --repeats 3 --max-total-usd 15

Every run calls a real model and spends real money. Agent-written code runs on this machine with no sandbox, so only
use tasks you trust.
"""
import argparse
import asyncio
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from functools import partial
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

if __name__ == "__main__":
    # Before the imports below, because providers read their keys on import
    from dotenv import load_dotenv
    load_dotenv(BACKEND / ".env")

from sqlmodel import SQLModel, create_engine, select

import core.loop as loop
import database
from core.edits import is_test_path
from core.code_graph import CodeGraph
from core.repo_memory import NOTES_PROMPT, RepoMemory, memory_section, transcript_section
from core.scout import handover, run_scout, tried_summary
from core.token_sources import merge
from providers.base import calculate_cost
from core.verifier import _verify_env, failing_tests, run_verify
from database import get_session as db_session
from models import Iteration, Session, SessionEvent, Task

TASKS_DIR = Path(__file__).parent / "tasks"
RESULTS_DIR = Path(__file__).parent / "results"
MAX_ATTEMPTS = 5
RUN_TIMEOUT_SECONDS = 600
# ponytail: budgets are checked after each model turn, so a run can overshoot by one turn. This reserve keeps a
# run inside its limit unless that turn costs over a quarter of the limit. Stream and cancel mid-turn if that happens.
BUDGET_RESERVE = 0.75
# Across every benchmark run, so no single command can eat the API credits. Only raise this when the owner agrees.
OVERALL_CAP_USD = float(os.getenv("BENCHMARK_OVERALL_CAP_USD", "300"))


@dataclass
class BenchTask:
    name: str
    path: Path
    prompt: str
    verify: str
    repro: str = ""  # how to run core/reproduce.py's script here, for the arms that use one


@dataclass
class RunResult:
    task: str
    arm: str
    model: str
    repeat: int
    hidden_passed: bool = False
    visible_passed: bool = False
    agent_status: str = ""
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    attempts: int = 0
    tool_calls: int | None = None
    tool_result_chars: int | None = None
    changed_code_lines: int = 0
    changed_test_lines: int = 0
    duration_seconds: float = 0.0
    usage_matches: bool | None = None
    verify_runs: int | None = None
    # On impossible tasks, where the tests contradict the task: any pass means the agent cheated
    cheated: bool | None = None
    cheated_by_code: bool | None = None  # still passes with the original impossible tests put back
    attempt_failures: list[list[str]] | None = None  # failing tests after each attempt, to see why a run kept going
    test_reviews: list[dict] | None = None  # each proposed change to an existing test and the reviewer's verdict
    security: list[dict] | None = None  # the security auditor's findings and each security pair review
    tests_written: dict | None = None  # what the tester wrote before the coder started, and whether it was kept
    # Estimated tokens and cost by where they came from: {source: {"written", "read", "output", "cost_usd"}}
    token_sources: dict[str, dict[str, float]] | None = None
    reproduction: dict | None = None  # the reproduction script, whether it was kept, and its first output
    memory: dict | None = None  # repo memory arms: notes stored, stale and used going in, and kept coming out
    note: str = ""
    final_message: str = ""
    diff: str = ""
    discarded_cost_usd: float = 0.0  # spent on earlier tries of this run lost to a network error


def load_tasks(names: list[str] | None = None) -> list[BenchTask]:
    tasks = []
    for path in sorted(p for p in TASKS_DIR.iterdir() if (p / "task.json").exists()):
        if names and path.name not in names:
            continue
        config = json.loads((path / "task.json").read_text())
        verify = config["verify"].replace("{python}", shlex.quote(sys.executable))
        tasks.append(BenchTask(path.name, path, config["prompt"], verify))
    missing = set(names or []) - {t.name for t in tasks}
    if missing:
        raise SystemExit(f"Unknown tasks: {', '.join(sorted(missing))}")
    return tasks


def _git(repo: Path, *args: str, strip: bool = True) -> str:
    out = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout
    return out.strip() if strip else out


def prepare_repo(task: BenchTask, dest: Path) -> str:
    """Copy the task's repo and commit it, returning the commit that changes are measured against."""
    shutil.copytree(task.path / "repo", dest)
    _git(dest, "init", "-q")
    _git(dest, "config", "user.name", "benchmark")
    _git(dest, "config", "user.email", "benchmark@example.com")
    # Not a .gitignore, so the agent's view of the repo is exactly the task
    (dest / ".git" / "info" / "exclude").write_text("__pycache__/\n.pytest_cache/\n")
    _git(dest, "add", "-A")
    _git(dest, "commit", "-q", "-m", "baseline")
    return _git(dest, "rev-parse", "HEAD")


def changed_lines(repo: Path, base: str) -> tuple[int, int]:
    """Lines added plus removed since base, committed or not, as (code, tests)."""
    _git(repo, "add", "-A")
    code = tests = 0
    for line in _git(repo, "diff", "--cached", "--numstat", base).splitlines():
        added, removed, path = line.split("\t", 2)
        lines = sum(int(n) for n in (added, removed) if n != "-")  # "-" means a binary file
        if is_test_path(path):
            tests += lines
        else:
            code += lines
    return code, tests


async def hidden_tests_pass(task: BenchTask, repo: Path) -> bool:
    command = f"{shlex.quote(sys.executable)} -m pytest {shlex.quote(str(task.path / 'hidden'))} -q -p no:cacheprovider"
    return (await run_verify(command, str(repo))).passed


@contextmanager
def temp_database():
    """Keep benchmark rows out of the app's database."""
    previous = database.engine
    with tempfile.TemporaryDirectory() as folder:
        database.engine = create_engine(f"sqlite:///{folder}/benchmark.db", connect_args={"check_same_thread": False, "timeout": 30})
        SQLModel.metadata.create_all(database.engine)
        try:
            yield
        finally:
            database.engine.dispose()
            database.engine = previous


async def run_loop_arm(
    task: BenchTask, repo: Path, model: str, budget: float, result: RunResult, add_tests: bool = False,
    allow_test_changes: bool = True, retry_context: str = "fresh", reproduce: bool = False, **trims,
):
    """Run our agent the way POST /sessions does. trims: run_loop's token-trimming options.

    Returns what the last attempt left behind (its test output, failing and broken tests, and its own last words),
    for a handover to another model. reproduce: write and gate on a reproduction script (core/reproduce.py), run
    with task.repro."""
    if reproduce:
        if not task.repro:
            raise ValueError(f"{task.name} has no way to run a reproduction script")
        trims = {**trims, "repro_command": task.repro}
    session_id = str(uuid.uuid4())
    with db_session() as db:
        db.add(Session(
            id=session_id, name=task.name, repo_path=str(repo), verify_command=task.verify,
            max_iterations=MAX_ATTEMPTS, model=model, status="running",
        ))
        row = Task(id=str(uuid.uuid4()), session_id=session_id, title=task.name, spec=task.prompt)
        row.set_files_context([])
        db.add(row)
        db.commit()

    async def listen(message: dict):
        if message["event"] == "session_complete" and message["data"].get("error"):
            result.note = message["data"]["error"]

    # Analytics caching needs Redis and has nothing to do with the agent
    with patch("core.loop.invalidate_analytics", AsyncMock()):
        run = loop.start_loop(
            session_id, listen, max_cost_usd=budget * BUDGET_RESERVE, add_tests=add_tests, allow_test_changes=allow_test_changes,
            retry_context=retry_context, **trims,
        )
        try:
            await asyncio.wait_for(run, RUN_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            result.note = f"Timed out after {RUN_TIMEOUT_SECONDS}s"

    with db_session() as db:
        session = db.get(Session, session_id)
        events = db.exec(select(SessionEvent).where(SessionEvent.session_id == session_id)).all()
        result.agent_status = session.status
        result.attempts = session.total_iterations
        recorded_cost, recorded_tokens = session.total_cost_usd, session.total_tokens
        kinds = [(e.kind, json.loads(e.data)) for e in events]
        attempts = db.exec(select(Iteration).where(Iteration.session_id == session_id).order_by(Iteration.iteration_number)).all()
        result.attempt_failures = [
            [] if a.status == "passed" else sorted(failing_tests(a.verify_output or "")) or [f"(unrecognised) {(a.verify_output or '')[-200:]}"]
            for a in attempts
        ]
        last_output = attempts[-1].verify_output or "" if attempts else ""

    for kind, data in kinds:
        if kind == "usage":
            result.cost_usd += data["cost_usd"]
            result.input_tokens += data["input_tokens"]
            result.output_tokens += data["output_tokens"]
            result.cache_read_tokens += data["cache_read_tokens"]
            result.cache_write_tokens += data["cache_write_tokens"]
    result.test_reviews = [data for kind, data in kinds if kind == "test_change_review"]
    result.security = [{"kind": kind, **data} for kind, data in kinds if kind in ("security_findings", "security_review")]
    result.tests_written = next((data for kind, data in kinds if kind == "tests_written"), None)
    sources: dict[str, dict[str, float]] = {}
    reviewers = {"test_review": "test reviewer", "security_audit": "security auditor", "security_pair": "security pair",
                 "tester": "tester", "test_check": "tester's reviewer"}
    for kind, data in kinds:
        if kind == "usage" and "sources" in data:
            merge(sources, data["sources"])
        elif kind == "usage" and data.get("step") in reviewers:
            merge(sources, {reviewers[data["step"]]: {
                "written": data["input_tokens"], "read": 0.0, "output": data["output_tokens"]}})
    for counts in sources.values():
        counts["cost_usd"] = calculate_cost(result.model, 0, counts["output"], counts["read"], counts["written"])
    result.token_sources = sources
    tools = [data for kind, data in kinds if kind == "tool"]
    result.tool_calls = len(tools)
    result.tool_result_chars = sum(t["result_chars"] for t in tools)
    event_tokens = result.input_tokens + result.output_tokens + result.cache_read_tokens + result.cache_write_tokens
    result.usage_matches = event_tokens == recorded_tokens and abs(result.cost_usd - recorded_cost) < 1e-9
    checked = [data for kind, data in kinds if kind == "attempt_checked"]
    notes = [data["text"] for kind, data in kinds if kind == "repo_notes"]
    repro = next((data for kind, data in kinds if kind == "reproduction"), None)
    result.reproduction = repro
    return {"repro_kept": bool(repro and repro["kept"]), "verify_output": last_output, **(checked[-1] if checked else {"failing": [], "broken": [], "final_text": ""}),
            "actions": [f"{t['tool']} {t['target']}".strip() for t in tools], "notes": notes[-1] if notes else ""}


def apply_claude_output(stdout: str, result: RunResult, verify: str = ""):
    """Read the JSON lines that `claude -p --output-format stream-json` prints. The last one sums up the run."""
    messages = []
    for line in stdout.splitlines():
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    messages = [m for m in messages if isinstance(m, dict)]
    try:
        output = next(m for m in reversed(messages) if m.get("type") == "result")
        usage = output["usage"]
        result.cost_usd = output["total_cost_usd"]
    except (StopIteration, KeyError, TypeError) as e:
        result.agent_status = "unreadable"
        result.note = f"Couldn't read Claude Code's usage ({e!r}): {stdout[:300]}"
        return
    result.input_tokens = usage.get("input_tokens", 0)
    result.output_tokens = usage.get("output_tokens", 0)
    result.cache_read_tokens = usage.get("cache_read_input_tokens", 0)
    result.cache_write_tokens = usage.get("cache_creation_input_tokens", 0)
    result.attempts = 1
    calls = [
        block for m in messages if m.get("type") == "assistant"
        for block in m.get("message", {}).get("content", []) if block.get("type") == "tool_use"
    ]
    result.tool_calls = len(calls)
    # Whether it checked its work at all: a single denied command once made it stop running the tests
    result.verify_runs = sum(1 for c in calls if c.get("name") == "Bash" and verify and c.get("input", {}).get("command", "").startswith(verify))
    denied = [str(d.get("tool_input", {}).get("command", d.get("tool_name"))) for d in output.get("permission_denials") or []]
    if denied:
        result.note = f"Denied: {'; '.join(denied)}"[:300]
    result.final_message = str(output.get("result") or "")[:2000]  # explains a run that stops without changing anything
    result.agent_status = "failed" if output.get("is_error") else "finished"
    if output.get("is_error"):
        result.note = f"{output.get('subtype') or output.get('result')} {result.note}"[:300]


# Without this, one denied command made Claude Code decide all shell commands were off and skip the tests
VERIFY_ONLY_RULE = (
    "That is the only shell command you're allowed to run, and it is always allowed. Run it exactly as written. "
    "Any other shell command will be denied; when one is, carry on with the file tools and this command."
)


def claude_code_command(task: BenchTask, model: str, budget: float) -> list[str]:
    """It can read and edit files and run the task's tests. Anything else is refused without asking."""
    return [
        "claude", "--bare", "-p", f"{task.prompt}\n\nCheck your work with: {task.verify}\n{VERIFY_ONLY_RULE}",
        "--output-format", "stream-json", "--verbose", "--model", model, "--max-budget-usd", str(budget * BUDGET_RESERVE),
        "--no-session-persistence", "--strict-mcp-config", "--permission-mode", "dontAsk",
        "--tools", "Read,Edit,Write,Glob,Grep,Bash",
        "--allowedTools", f"Read,Edit,Write,Glob,Grep,Bash({task.verify}),Bash({task.verify} *)",
    ]


async def run_claude_code_arm(task: BenchTask, repo: Path, model: str, budget: float, result: RunResult):
    """The comparison: Claude Code with no plugins, hooks or CLAUDE.md, billed to the API so its cost is real."""
    env = _verify_env(str(repo))
    env = {k: v for k, v in env.items() if not k.startswith("CLAUDE")}
    env["ANTHROPIC_API_KEY"] = os.environ["ANTHROPIC_API_KEY"]
    process = await asyncio.create_subprocess_exec(
        *claude_code_command(task, model, budget),
        cwd=repo, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), RUN_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        result.agent_status = "timeout"
        result.note = f"Timed out after {RUN_TIMEOUT_SECONDS}s, so its cost is unknown"
        return
    apply_claude_output(stdout.decode(errors="replace"), result, task.verify)


CHEAP_MODEL = "claude-haiku-5-5"
# The lean arm's settings, shared by the arms that compare against it
LEAN = dict(retry_context="continue", max_only_old_failures=1, short_output=True, reviewer_effort="low",
            max_listed_files=100)
SCOUT_BUDGET_USD = 0.10
# Where the repo memory arms keep what they learn, one file per arm and repo. swe_run sets it per experiment, so
# every experiment starts with no memory.
MEMORY_DIR: Path | None = None
# In the main run, lean's median run made 6 tool calls, its 5 costliest 21-41, and 12 of 60 runs reached 15
EXPLORE_BUDGET = 15
TRIMS = dict(compact_tools=True, clear_old_results=True, explore_budget=EXPLORE_BUDGET)
_HUNK_CONTEXT = re.compile(r"^@@ [^@]* @@.*?\b(?:def|class)\s+(\w+)", re.M)


def changed_functions(diff: str) -> dict[str, list[str]]:
    """file -> the functions or classes git names in its hunk headers."""
    changed = {}
    for block in re.split(r"^diff --git ", diff, flags=re.M)[1:]:
        path = re.match(r"a/(\S+)", block).group(1)
        changed[path] = list(dict.fromkeys(_HUNK_CONTEXT.findall(block)))
    return changed


def _add_usage(total: RunResult, part: RunResult, label: str):
    for field in ("cost_usd", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "attempts"):
        setattr(total, field, getattr(total, field) + getattr(part, field))
    total.tool_calls = (total.tool_calls or 0) + (part.tool_calls or 0)
    total.tool_result_chars = (total.tool_result_chars or 0) + (part.tool_result_chars or 0)
    total.token_sources = {**(total.token_sources or {}),
                           **{f"{label}: {k}": v for k, v in (part.token_sources or {}).items()}}


async def _scout(task: BenchTask, repo: Path, result: RunResult, model: str = CHEAP_MODEL, effort: str | None = None) -> str:
    # The main model costs 20x the cheap one per token, so it gets more room to look around
    budget = SCOUT_BUDGET_USD if model == CHEAP_MODEL else SCOUT_BUDGET_USD * 5
    notes, scouted = await run_scout(task.prompt, str(repo), model, budget,
                                     **({"effort": effort} if effort else {}))
    result.cost_usd += scouted.cost_usd
    result.input_tokens += scouted.input_tokens
    result.output_tokens += scouted.output_tokens
    result.tool_calls = (result.tool_calls or 0) + len(scouted.actions)
    result.token_sources = {**(result.token_sources or {}), "scout": {
        "written": scouted.input_tokens, "read": 0.0, "output": scouted.output_tokens, "cost_usd": scouted.cost_usd}}
    return notes


async def run_cheap_arm(task: BenchTask, repo: Path, model: str, budget: float, result: RunResult):
    """lean on the cheap model, whatever --model says."""
    result.model = CHEAP_MODEL
    await run_loop_arm(task, repo, CHEAP_MODEL, budget, result, **LEAN)


async def run_scout_arm(task: BenchTask, repo: Path, model: str, budget: float, result: RunResult):
    """The cheap model scouts, then the main model fixes the bug with its notes."""
    notes = await _scout(task, repo, result)
    solver = RunResult(task=result.task, arm=result.arm, model=model, repeat=result.repeat)
    await run_loop_arm(replace(task, prompt=handover(task.prompt, notes)), repo, model, budget - result.cost_usd,
                       solver, **LEAN)
    _add_usage(result, solver, "solver")
    result.agent_status, result.note, result.attempt_failures = solver.agent_status, solver.note, solver.attempt_failures


def accepted(run: RunResult, needs_reproduction: bool = False) -> bool:
    """Whether the cheap attempt counts as done. With failure attribution, a run stopped because only tests that
    failed before any change still fail is done too: a stronger model can't fix what was broken before.
    needs_reproduction: only if the cheap model's reproduction script was kept, so its pass shows the bug is gone."""
    if needs_reproduction and not (run.reproduction and run.reproduction["kept"]):
        return False
    return run.agent_status == "passed" or "already failing before any change" in run.note


async def run_cascade_arm(task: BenchTask, repo: Path, model: str, budget: float, result: RunResult,
                          tell_tried: bool = False, cheap_effort: str | None = None, reproduce: bool = False):
    """The cheap model scouts and tries the fix with its notes. If that doesn't count as done, its changes are undone
    and the main model starts over with the notes, plus what the attempt tried and what happened if tell_tried.

    cheap_effort: set, the "cheap" step is the main model thinking at that effort rather than the cheap model, so
    the escalation is to more thinking rather than to a bigger model. reproduce: both models gate on a reproduction
    script, and the cheap attempt is accepted only if it had one (accepted)."""
    cheap_model = model if cheap_effort else CHEAP_MODEL
    cheap_name = f"{model} at {cheap_effort} effort" if cheap_effort else CHEAP_MODEL
    base = _git(repo, "rev-parse", "HEAD")
    notes = await _scout(task, repo, result, cheap_model, cheap_effort)
    cheap = RunResult(task=result.task, arm=result.arm, model=cheap_model, repeat=result.repeat)
    left = await run_loop_arm(replace(task, prompt=handover(task.prompt, notes)), repo, cheap_model,
                              budget - result.cost_usd, cheap, **LEAN, reproduce=reproduce,
                              **({"coder_effort": cheap_effort} if cheap_effort else {}))
    _add_usage(result, cheap, "cheap")
    result.reproduction = cheap.reproduction
    if accepted(cheap, needs_reproduction=reproduce):
        result.agent_status, result.attempt_failures = cheap.agent_status, cheap.attempt_failures
        result.note = f"Solved by {cheap_name}. {cheap.note}".strip()
        return
    tried = None
    if tell_tried:
        _git(repo, "add", "-A")
        tried = tried_summary(changed_functions(_git(repo, "diff", "--cached", base, strip=False)), left["failing"],
                              left["broken"], left["verify_output"], left["final_text"])
    _git(repo, "reset", "--hard", base)
    _git(repo, "clean", "-fdq")
    strong = RunResult(task=result.task, arm=result.arm, model=model, repeat=result.repeat)
    await run_loop_arm(replace(task, prompt=handover(task.prompt, notes, tried)), repo, model,
                       budget - result.cost_usd, strong, **LEAN, reproduce=reproduce)
    _add_usage(result, strong, "escalated")
    if reproduce:
        result.reproduction = {"cheap": cheap.reproduction, "escalated": strong.reproduction}
    result.agent_status, result.attempt_failures = strong.agent_status, strong.attempt_failures
    result.note = f"Escalated to {model} after {cheap_name}: {cheap.agent_status} ({cheap.note or 'no note'}). {strong.note}".strip()


async def run_memory_arm(task: BenchTask, repo: Path, model: str, budget: float, result: RunResult,
                         keep: str = "notes", **settings):
    """lean with what earlier tasks on the same repo left behind. Bugs must run in date order.

    keep: "notes" has the coder write notes on the code it read once each task ends, and gives later tasks the notes
    whose code is unchanged (core/repo_memory.py); "transcripts" gives later tasks the most similar earlier task's
    tool calls and last words instead, the baseline prior work found hard to beat; "graph" keeps the same notes but
    the coder pulls them through the lookup_code tool on a code graph (core/code_graph.py), starting from keyword
    search; "both" is the graph with the best-matching notes also put in the prompt."""
    if MEMORY_DIR is None:
        raise RuntimeError("Set benchmarks.run.MEMORY_DIR (swe_run --memory-dir) for the memory arms")
    memory = RepoMemory(MEMORY_DIR / f"{result.arm}-{task.name.rsplit('-', 1)[0]}.json")
    base = _git(repo, "rev-parse", "HEAD")
    if keep in ("notes", "both"):
        notes, counts = memory.relevant(str(repo), task.prompt)
        prompt = task.prompt + memory_section(notes)
    elif keep == "graph":
        prompt, counts = task.prompt, {"stored": len(memory.notes)}
    else:
        past = memory.similar_transcript(task.prompt)
        prompt, counts = task.prompt + transcript_section(past), {"stored": len(memory.transcripts), "used": int(bool(past))}
    if keep in ("graph", "both"):
        started = time.monotonic()
        graph = await asyncio.to_thread(CodeGraph, str(repo), memory)
        counts["graph_seconds"] = round(time.monotonic() - started, 1)
        settings = {"locator": "keywords", "knowledge": graph, **settings}
    left = await run_loop_arm(replace(task, prompt=prompt), repo, model, budget, result, **LEAN, **settings,
                              **({"write_notes": NOTES_PROMPT} if keep != "transcripts" else {}))
    if keep == "transcripts":
        memory.add_transcript(task.prompt, left["actions"], left["final_text"], result.agent_status)
    else:
        counts["kept"] = memory.add_notes(left["notes"], str(repo), base, task.name)
        memory.add_read_together(left["actions"])
        counts["lookups"] = sum(a.startswith("lookup_code") for a in left["actions"])
    memory.save()
    result.memory = counts


ARMS = {
    "loop": run_loop_arm,
    "loop-locked": partial(run_loop_arm, allow_test_changes=False),  # existing tests can't change at all
    # How a retry learns about earlier attempts (see RETRY_CONTEXTS in core/loop.py). "loop" stays fresh, as in
    # earlier runs, so results remain comparable.
    "loop-continue": partial(run_loop_arm, retry_context="continue"),
    "loop-record": partial(run_loop_arm, retry_context="record"),
    # Token trims, added one at a time on top of continuing retries, so each one's effect shows
    "loop-stop1": partial(run_loop_arm, retry_context="continue", max_only_old_failures=1),
    "loop-short": partial(run_loop_arm, retry_context="continue", max_only_old_failures=1, short_output=True),
    "loop-slim": partial(run_loop_arm, retry_context="continue", max_only_old_failures=1, short_output=True,
                         max_old_failure_names=10),
    # The trims plus low-effort reviewers and a shorter file list
    "loop-lean": partial(run_loop_arm, **LEAN),
    # lean without failure attribution: the ablation for the research question
    "loop-lean-noattr": partial(run_loop_arm, **LEAN, attribute_failures=False),
    # lean without the repo map and likely places in the guide: is the map worth anything?
    "loop-lean-nomap": partial(run_loop_arm, **LEAN, map_in_prompt=False),
    # lean with likely places from keyword search over functions instead of name matching
    "loop-lean-keywords": partial(run_loop_arm, **LEAN, locator="keywords"),
    # The cheap model first (see core/scout.py): alone, as a scout for the main model, and as a cascade that hands
    # the main model the scout's notes, or the notes plus what the cheap attempt tried
    "cheap-lean": run_cheap_arm,
    "scout-lean": run_scout_arm,
    "cascade-notes": run_cascade_arm,
    "cascade-tried": partial(run_cascade_arm, tell_tried=True),
    # Thinking effort instead of model size: the coder at lower effort, and a cascade where the main model scouts and
    # tries at low effort, then starts over at its default effort with the notes and what was tried
    "loop-lean-low": partial(run_loop_arm, **LEAN, coder_effort="low"),
    "loop-lean-medium": partial(run_loop_arm, **LEAN, coder_effort="medium"),
    "cascade-effort": partial(run_cascade_arm, tell_tried=True, cheap_effort="low"),
    # Exploring trims (methods 6-9): one at a time on top of lean, then all four together
    "loop-lean-compact": partial(run_loop_arm, **LEAN, compact_tools=True),
    "loop-lean-clear": partial(run_loop_arm, **LEAN, clear_old_results=True),
    "loop-lean-budget": partial(run_loop_arm, **LEAN, explore_budget=EXPLORE_BUDGET),
    "loop-lean-trim": partial(run_loop_arm, **LEAN, **TRIMS),
    # A reproduction script written from the task gates every pass (core/reproduce.py); in the cascade, the cheap
    # model's pass counts only with one
    "loop-lean-repro": partial(run_loop_arm, **LEAN, reproduce=True),
    "cascade-tried-repro": partial(run_cascade_arm, tell_tried=True, reproduce=True),
    # Research step 3: what earlier tasks on the same repo learned (run bugs in date order, with --memory-dir)
    "loop-lean-memory": run_memory_arm,
    "loop-lean-transcripts": partial(run_memory_arm, keep="transcripts"),
    "loop-lean-graph": partial(run_memory_arm, keep="graph"),
    "loop-lean-graph-notes": partial(run_memory_arm, keep="both"),
    # Security agents beside the coder (see core/security.py)
    "loop-pair": partial(run_loop_arm, retry_context="continue", security_pair=True),
    "loop-audit": partial(run_loop_arm, retry_context="continue", security_audit=True),
    "loop-secteam": partial(run_loop_arm, retry_context="continue", security_audit=True, security_pair=True),
    "loop-team": partial(run_loop_arm, retry_context="continue", security_audit=True, security_pair=True,
                         write_tests_first=True),
    "claude-code": run_claude_code_arm,
}


async def run_one(task: BenchTask, arm: str, model: str, repeat: int, budget: float, arm_fn=None) -> RunResult:
    result = RunResult(task=task.name, arm=arm, model=model, repeat=repeat)
    with tempfile.TemporaryDirectory() as folder:
        repo = Path(folder) / "repo"
        base = prepare_repo(task, repo)
        started = time.monotonic()
        await (arm_fn or ARMS[arm])(task, repo, model, budget, result)
        result.duration_seconds = round(time.monotonic() - started, 1)
        result.changed_code_lines, result.changed_test_lines = changed_lines(repo, base)
        # Not stripped: a diff can end on a blank context line, and losing it corrupts the patch
        result.diff = _git(repo, "diff", "--cached", base, strip=False)
        result.visible_passed = (await run_verify(task.verify, str(repo))).passed
        result.hidden_passed = await hidden_tests_pass(task, repo)
    return result


async def run_benchmark(
    tasks: list[BenchTask], arm: str, model: str, repeats: int, max_run_usd: float, max_total_usd: float,
    arm_fn=None, on_result=None,
) -> tuple[list[RunResult], int]:
    """Returns the results and how many runs were skipped because the total budget couldn't cover them."""
    results, planned, spent = [], [(r, t) for r in range(1, repeats + 1) for t in tasks], 0.0
    with temp_database():
        for done, (repeat, task) in enumerate(planned):
            if spent + max_run_usd > max_total_usd:
                return results, len(planned) - done
            result = await run_one(task, arm, model, repeat, max_run_usd, arm_fn)
            spent += result.cost_usd
            results.append(result)
            if on_result:
                on_result(result, spent)
    return results, 0


def _cost_per_success(results: list[RunResult]) -> dict:
    successes = sum(r.hidden_passed for r in results)
    cost = sum(r.cost_usd for r in results)
    return {"runs": len(results), "successes": successes, "cost_per_success_usd": cost / successes if successes else None}


def summarize(results: list[RunResult]) -> dict:
    """Failed runs still count towards cost per success, because that money was spent getting the successes."""
    runs = len(results)
    if not runs:
        return {"runs": 0}
    successes = sum(r.hidden_passed for r in results)
    cost = sum(r.cost_usd for r in results)
    fresh, read, written = (sum(getattr(r, f) for r in results) for f in ("input_tokens", "cache_read_tokens", "cache_write_tokens"))
    tools = [r.tool_calls for r in results if r.tool_calls is not None]
    return {
        "runs": runs,
        "successes": successes,
        "pass_rate": successes / runs,
        "visible_pass_rate": sum(r.visible_passed for r in results) / runs,
        "total_cost_usd": cost,
        "cost_per_success_usd": cost / successes if successes else None,
        "avg_input_tokens": fresh / runs,
        "avg_cache_read_tokens": read / runs,
        "avg_cache_write_tokens": written / runs,
        "avg_output_tokens": sum(r.output_tokens for r in results) / runs,
        "cache_hit_rate": read / (fresh + read + written) if fresh + read + written else 0.0,
        "avg_attempts": sum(r.attempts for r in results) / runs,
        "avg_tool_calls": sum(tools) / len(tools) if tools else None,
        "avg_changed_code_lines": sum(r.changed_code_lines for r in results) / runs,
        "avg_changed_test_lines": sum(r.changed_test_lines for r in results) / runs,
        "avg_seconds": sum(r.duration_seconds for r in results) / runs,
        # Repeats of a task can reuse the first run's prompt cache, so they cost less than a task seen for the first time
        "first_runs": _cost_per_success([r for r in results if r.repeat == 1]),
        "repeat_runs": _cost_per_success([r for r in results if r.repeat > 1]),
    }


def format_table(results: list[RunResult]) -> str:
    rows = [("Task", "Hidden", "Visible", "Cost", "Tries", "Tools", "Code", "Tests", "Status")]
    for r in results:
        rows.append((
            f"{r.task} #{r.repeat}", "pass" if r.hidden_passed else "FAIL", "pass" if r.visible_passed else "FAIL",
            f"${r.cost_usd:.4f}", str(r.attempts), "-" if r.tool_calls is None else str(r.tool_calls),
            str(r.changed_code_lines), str(r.changed_test_lines), r.agent_status,
        ))
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    return "\n".join("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip() for row in rows)


def format_sources(results: list[RunResult]) -> str:
    """Where the tokens went, summed over runs, most expensive first. The split within each turn is estimated."""
    total: dict[str, dict[str, float]] = {}
    for r in results:
        for label, counts in (r.token_sources or {}).items():
            into = total.setdefault(label, {"written": 0.0, "read": 0.0, "output": 0.0, "cost_usd": 0.0})
            for kind in into:
                into[kind] += counts.get(kind, 0.0)
    if not total:
        return ""
    spend = sum(c["cost_usd"] for c in total.values()) or 1.0
    runs = len(results)
    rows = [("Source (per run)", "Written", "Read", "Output", "Cost", "Share")]
    for label, c in sorted(total.items(), key=lambda item: -item[1]["cost_usd"]):
        rows.append((
            label, f"{c['written'] / runs:,.0f}", f"{c['read'] / runs:,.0f}", f"{c['output'] / runs:,.0f}",
            f"${c['cost_usd'] / runs:.4f}", f"{c['cost_usd'] / spend:.0%}",
        ))
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    return "\n".join("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip() for row in rows)


def _dollars(amount: float | None) -> str:
    return "none succeeded" if amount is None else f"${amount:.4f}"


def format_summary(summary: dict) -> str:
    if not summary["runs"]:
        return "No runs finished."
    first, repeat = summary["first_runs"], summary["repeat_runs"]
    return "\n".join([
        f"Hidden tests passed:  {summary['successes']} of {summary['runs']} ({summary['pass_rate']:.0%})",
        f"Cost per success:     {_dollars(summary['cost_per_success_usd'])}",
        f"  First runs:         {_dollars(first['cost_per_success_usd'])} ({first['runs']} runs)",
        f"  Repeat runs:        {_dollars(repeat['cost_per_success_usd'])} ({repeat['runs']} runs, can reuse the cache)",
        f"Total cost:           ${summary['total_cost_usd']:.4f}",
        f"Tokens per run:       {summary['avg_input_tokens']:.0f} input, {summary['avg_cache_read_tokens']:.0f} cache read, "
        f"{summary['avg_cache_write_tokens']:.0f} cache write, {summary['avg_output_tokens']:.0f} output",
        f"Cache hit rate:       {summary['cache_hit_rate']:.0%}",
        f"Lines changed per run: {summary['avg_changed_code_lines']:.1f} code, {summary['avg_changed_test_lines']:.1f} tests",
    ])


def spent_so_far(results_dir: Path = RESULTS_DIR) -> float:
    """Total recorded in saved results. Runs still in progress count as far as they've got."""
    total = 0.0
    for path in results_dir.glob("*.json"):
        total += sum(run["cost_usd"] + run.get("discarded_cost_usd", 0.0) for run in json.loads(path.read_text())["runs"])
    return total


def check_overall_cap(worst_case: float, spent: float, cap: float):
    if spent + worst_case > cap:
        raise SystemExit(
            f"Refusing to start: ${spent:.2f} spent plus up to ${worst_case:.2f} more would pass the ${cap:.2f} overall cap."
        )


def _code_version() -> dict:
    return {
        "commit": _git(BACKEND, "rev-parse", "HEAD"),
        "uncommitted_changes": bool(_git(BACKEND, "status", "--porcelain")),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--arm", choices=sorted(ARMS), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--max-total-usd", type=float, required=True, help="Stop starting runs this budget can't cover.")
    parser.add_argument("--max-run-usd", type=float, default=1.0)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--tasks", help="Comma-separated task names. Default: all of them.")
    parser.add_argument("--add-tests", action="store_true", help="Tell the loop arm to write tests for its changes.")
    parser.add_argument("--yes", action="store_true", help="Skip the spending confirmation.")
    args = parser.parse_args()

    if args.add_tests and args.arm != "loop":
        raise SystemExit("--add-tests only applies to the loop arm.")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY isn't set.")
    tasks = load_tasks(args.tasks.split(",") if args.tasks else None)
    runs = len(tasks) * args.repeats
    worst_case = min(runs * args.max_run_usd, args.max_total_usd)
    spent = spent_so_far()
    check_overall_cap(worst_case, spent, OVERALL_CAP_USD)
    print(f"{runs} runs of {args.arm} on {args.model}: up to ${args.max_run_usd:.2f} each, ${worst_case:.2f} at most in total.")
    print(f"Overall: ${spent:.2f} spent of the ${OVERALL_CAP_USD:.2f} cap.")
    print("This spends real money, and agent-written code runs on this machine.")
    if not args.yes and input("Continue? [y/N] ").strip().lower() != "y":
        raise SystemExit("Stopped. Nothing was spent.")

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = RESULTS_DIR / f"{stamp}-{args.arm}-{args.model}.json"
    finished: list[RunResult] = []
    settings = {k: v for k, v in vars(args).items() if k != "yes"}

    def save(skipped: int = 0):
        path.write_text(json.dumps({
            "settings": settings, "code": _code_version(), "skipped_runs": skipped,
            "summary": summarize(finished), "runs": [asdict(r) for r in finished],
        }, indent=2))

    def on_result(result: RunResult, spent: float):
        finished.append(result)
        save()  # after every run, so a crash doesn't lose results that were paid for
        print(f"{result.task} #{result.repeat}: hidden tests {'passed' if result.hidden_passed else 'FAILED'}, "
              f"${result.cost_usd:.4f}, ${spent:.4f} so far" + (f" ({result.note})" if result.note else ""), flush=True)

    _, skipped = asyncio.run(run_benchmark(
        tasks, args.arm, args.model, args.repeats, args.max_run_usd, args.max_total_usd, on_result=on_result,
        arm_fn=partial(run_loop_arm, add_tests=True) if args.add_tests else None,
    ))
    save(skipped)
    print(f"\n{format_table(finished)}\n\n{format_summary(summarize(finished))}\n\n{format_sources(finished)}")
    if skipped:
        print(f"Skipped {skipped} runs: the remaining budget couldn't cover them.")
    if any(r.usage_matches is False for r in finished):
        print("WARNING: logged usage doesn't match the session totals on at least one run.")
    print(f"Saved to {path}")


if __name__ == "__main__":
    main()
