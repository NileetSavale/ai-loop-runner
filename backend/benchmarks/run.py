"""Measure an agent on tasks it can't game: success means passing hidden tests it never sees.

    cd backend && python -m benchmarks.run --arm loop --model claude-sonnet-5-5 --repeats 3 --max-total-usd 15

Every run calls a real model and spends real money. Agent-written code runs on this machine with no sandbox, so only
use tasks you trust.
"""
import argparse
import asyncio
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
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
from core.verifier import _verify_env, run_verify
from database import get_session as db_session
from models import Session, SessionEvent, Task

TASKS_DIR = Path(__file__).parent / "tasks"
RESULTS_DIR = Path(__file__).parent / "results"
MAX_ATTEMPTS = 5
RUN_TIMEOUT_SECONDS = 600
# ponytail: budgets are checked after each model turn, so a run can overshoot by one turn. This reserve keeps a
# run inside its limit unless that turn costs over a quarter of the limit. Stream and cancel mid-turn if that happens.
BUDGET_RESERVE = 0.75


@dataclass
class BenchTask:
    name: str
    path: Path
    prompt: str
    verify: str


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
    changed_lines: int = 0
    duration_seconds: float = 0.0
    usage_matches: bool | None = None
    note: str = ""
    diff: str = ""


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


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


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


def changed_lines(repo: Path, base: str) -> int:
    """Lines added plus removed since base, committed or not."""
    _git(repo, "add", "-A")
    total = 0
    for line in _git(repo, "diff", "--cached", "--numstat", base).splitlines():
        added, removed, _ = line.split("\t", 2)
        total += sum(int(n) for n in (added, removed) if n != "-")  # "-" means a binary file
    return total


async def hidden_tests_pass(task: BenchTask, repo: Path) -> bool:
    command = f"{shlex.quote(sys.executable)} -m pytest {shlex.quote(str(task.path / 'hidden'))} -q -p no:cacheprovider"
    return (await run_verify(command, str(repo))).passed


@contextmanager
def temp_database():
    """Keep benchmark rows out of the app's database."""
    previous = database.engine
    with tempfile.TemporaryDirectory() as folder:
        database.engine = create_engine(f"sqlite:///{folder}/benchmark.db", connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(database.engine)
        try:
            yield
        finally:
            database.engine.dispose()
            database.engine = previous


async def run_loop_arm(task: BenchTask, repo: Path, model: str, budget: float, result: RunResult):
    """Run our agent the way POST /sessions does."""
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
        run = loop.start_loop(session_id, listen, max_cost_usd=budget * BUDGET_RESERVE)
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

    for kind, data in kinds:
        if kind == "usage":
            result.cost_usd += data["cost_usd"]
            result.input_tokens += data["input_tokens"]
            result.output_tokens += data["output_tokens"]
            result.cache_read_tokens += data["cache_read_tokens"]
            result.cache_write_tokens += data["cache_write_tokens"]
    tools = [data for kind, data in kinds if kind == "tool"]
    result.tool_calls = len(tools)
    result.tool_result_chars = sum(t["result_chars"] for t in tools)
    event_tokens = result.input_tokens + result.output_tokens + result.cache_read_tokens + result.cache_write_tokens
    result.usage_matches = event_tokens == recorded_tokens and abs(result.cost_usd - recorded_cost) < 1e-9


def apply_claude_output(stdout: str, result: RunResult):
    """Read the JSON that `claude -p --output-format json` prints."""
    try:
        output = json.loads(stdout)
        usage = output["usage"]
        result.cost_usd = output["total_cost_usd"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        result.agent_status = "unreadable"
        result.note = f"Couldn't read Claude Code's usage ({e!r}): {stdout[:300]}"
        return
    result.input_tokens = usage.get("input_tokens", 0)
    result.output_tokens = usage.get("output_tokens", 0)
    result.cache_read_tokens = usage.get("cache_read_input_tokens", 0)
    result.cache_write_tokens = usage.get("cache_creation_input_tokens", 0)
    result.attempts = 1
    result.agent_status = "failed" if output.get("is_error") else "finished"
    if output.get("is_error"):
        result.note = str(output.get("subtype") or output.get("result"))[:300]


async def run_claude_code_arm(task: BenchTask, repo: Path, model: str, budget: float, result: RunResult):
    """The comparison: Claude Code with no plugins, hooks or CLAUDE.md, billed to the API so its cost is real."""
    env = _verify_env(str(repo))
    env = {k: v for k, v in env.items() if not k.startswith("CLAUDE")}
    env["ANTHROPIC_API_KEY"] = os.environ["ANTHROPIC_API_KEY"]
    process = await asyncio.create_subprocess_exec(
        "claude", "--bare", "-p", f"{task.prompt}\n\nCheck your work with: {task.verify}",
        "--output-format", "json", "--model", model, "--max-budget-usd", str(budget * BUDGET_RESERVE),
        "--no-session-persistence", "--strict-mcp-config", "--dangerously-skip-permissions",
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
    apply_claude_output(stdout.decode(errors="replace"), result)


ARMS = {"loop": run_loop_arm, "claude-code": run_claude_code_arm}


async def run_one(task: BenchTask, arm: str, model: str, repeat: int, budget: float, arm_fn=None) -> RunResult:
    result = RunResult(task=task.name, arm=arm, model=model, repeat=repeat)
    with tempfile.TemporaryDirectory() as folder:
        repo = Path(folder) / "repo"
        base = prepare_repo(task, repo)
        started = time.monotonic()
        await (arm_fn or ARMS[arm])(task, repo, model, budget, result)
        result.duration_seconds = round(time.monotonic() - started, 1)
        result.changed_lines = changed_lines(repo, base)
        result.diff = _git(repo, "diff", "--cached", base)
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
        "avg_changed_lines": sum(r.changed_lines for r in results) / runs,
        "avg_seconds": sum(r.duration_seconds for r in results) / runs,
    }


def format_table(results: list[RunResult]) -> str:
    rows = [("Task", "Hidden", "Visible", "Cost", "Tries", "Tools", "Lines", "Status")]
    for r in results:
        rows.append((
            f"{r.task} #{r.repeat}", "pass" if r.hidden_passed else "FAIL", "pass" if r.visible_passed else "FAIL",
            f"${r.cost_usd:.4f}", str(r.attempts), "-" if r.tool_calls is None else str(r.tool_calls),
            str(r.changed_lines), r.agent_status,
        ))
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    return "\n".join("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip() for row in rows)


def format_summary(summary: dict) -> str:
    if not summary["runs"]:
        return "No runs finished."
    per_success = summary["cost_per_success_usd"]
    return "\n".join([
        f"Hidden tests passed:  {summary['successes']} of {summary['runs']} ({summary['pass_rate']:.0%})",
        f"Cost per success:     {'none succeeded' if per_success is None else f'${per_success:.4f}'}",
        f"Total cost:           ${summary['total_cost_usd']:.4f}",
        f"Tokens per run:       {summary['avg_input_tokens']:.0f} input, {summary['avg_cache_read_tokens']:.0f} cache read, "
        f"{summary['avg_cache_write_tokens']:.0f} cache write, {summary['avg_output_tokens']:.0f} output",
        f"Cache hit rate:       {summary['cache_hit_rate']:.0%}",
        f"Lines changed per run: {summary['avg_changed_lines']:.1f}",
    ])


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
    parser.add_argument("--yes", action="store_true", help="Skip the spending confirmation.")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY isn't set.")
    tasks = load_tasks(args.tasks.split(",") if args.tasks else None)
    runs = len(tasks) * args.repeats
    worst_case = min(runs * args.max_run_usd, args.max_total_usd)
    print(f"{runs} runs of {args.arm} on {args.model}: up to ${args.max_run_usd:.2f} each, ${worst_case:.2f} at most in total.")
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
    ))
    save(skipped)
    print(f"\n{format_table(finished)}\n\n{format_summary(summarize(finished))}")
    if skipped:
        print(f"Skipped {skipped} runs: the remaining budget couldn't cover them.")
    if any(r.usage_matches is False for r in finished):
        print("WARNING: logged usage doesn't match the session totals on at least one run.")
    print(f"Saved to {path}")


if __name__ == "__main__":
    main()
