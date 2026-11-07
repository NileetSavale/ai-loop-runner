"""Run TeamNotes tasks one after another on the same repo, the way a team keeps working on one app.

    cd backend && python -m benchmarks.demo_sequence --repeats 2 --max-total-usd 3

Each repeat starts from the original TeamNotes and runs sharing, then attachments, then note editing, each task on
the result of the one before. It does this twice: with the security auditor auditing from scratch every task, and
with it keeping findings per file between tasks (audit_cache). The auditor's cost per task shows what the cache saves,
and each task's hidden checks show whether anything was lost.
"""
import argparse
import asyncio
import json
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

if __name__ == "__main__":
    # Before the imports below, because providers read their keys on import
    from dotenv import load_dotenv
    load_dotenv(BACKEND / ".env")

from benchmarks.run import (OVERALL_CAP_USD, RESULTS_DIR, BenchTask, RunResult, _code_version, _git, check_overall_cap,
                            load_tasks, prepare_repo, run_loop_arm, spent_so_far, temp_database)

DEMO = BACKEND.parent / "demo_apps"
EDIT_PROMPT = (
    "Add note editing. PUT /notes/{note_id} with JSON {\"title\": ..., \"body\": ...} updates the note and returns it "
    "with status 200. Only the note's owner can edit it; anyone else, including users it's shared with, can't. "
    "Editing a note that doesn't exist returns 404."
)


def steps() -> list[tuple[str, str, Path]]:
    """(name, prompt, hidden checks) for each task in order."""
    tasks = {t.name: t for t in load_tasks(["notes_sharing", "notes_attachments"])}
    sharing, attachments = tasks["notes_sharing"], tasks["notes_attachments"]
    return [
        ("sharing", sharing.prompt, sharing.path / "hidden"),
        ("attachments", attachments.prompt, attachments.path / "hidden"),
        ("editing", EDIT_PROMPT, DEMO / "notes_edit_checks"),
    ]


def hidden_checks(repo: Path, folder: Path) -> dict[str, bool]:
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "-rA", "-q", "-p", "no:cacheprovider", str(folder)],
        cwd=repo, capture_output=True, text=True, env={"PYTHONPATH": str(repo), "PATH": "/usr/bin:/bin"},
    ).stdout
    return {m.group(2).split("::")[-1]: m.group(1) == "PASSED" for m in re.finditer(r"^(PASSED|FAILED|ERROR) (\S+)", out, re.M)}


async def run_sequence(mode: str, repeat: int, model: str, budget: float, on_result):
    first = load_tasks(["notes_sharing"])[0]
    verify = f"{shlex.quote(sys.executable)} -m pytest tests -q"
    with tempfile.TemporaryDirectory() as folder:
        repo = Path(folder) / "repo"
        prepare_repo(first, repo)
        cache = str(Path(folder) / "audit.json") if mode == "cached" else None
        for name, prompt, hidden in steps():
            result = RunResult(task=f"notes-{name}", arm=f"sequence-{mode}", model=model, repeat=repeat)
            await run_loop_arm(BenchTask(name, first.path, prompt, verify), repo, model, budget, result,
                               retry_context="continue", security_audit=True, audit_cache=cache)
            checks = hidden_checks(repo, hidden)
            result.hidden_passed = bool(checks) and all(checks.values())
            result.note = json.dumps({"checks": checks, "error": result.note})
            _git(repo, "add", "-A")
            _git(repo, "-c", "user.name=benchmark", "-c", "user.email=benchmark@example.com", "commit", "-qm", name, "--allow-empty")
            on_result(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="claude-sonnet-5-5")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--max-run-usd", type=float, default=1.0)
    parser.add_argument("--max-total-usd", type=float, required=True)
    args = parser.parse_args()

    runs = args.repeats * 2 * len(steps())
    worst_case = min(runs * args.max_run_usd, args.max_total_usd)
    check_overall_cap(worst_case, spent_so_far(), OVERALL_CAP_USD)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = RESULTS_DIR / f"{stamp}-sequence-{args.model}.json"
    finished: list[RunResult] = []

    def on_result(result: RunResult):
        finished.append(result)
        path.write_text(json.dumps({"settings": vars(args), "code": _code_version(), "runs": [asdict(r) for r in finished]}, indent=2))
        audit = (result.token_sources or {}).get("security auditor", {}).get("cost_usd", 0.0)
        found = next((e for e in result.security or [] if e["kind"] == "security_findings"), {})
        print(f"{result.arm} #{result.repeat} {result.task}: checks {'passed' if result.hidden_passed else 'FAILED'}, "
              f"${result.cost_usd:.4f} (auditor ${audit:.4f}), audited {found.get('audited')}, cached {found.get('cached')}", flush=True)
        if sum(r.cost_usd for r in finished) > args.max_total_usd:
            raise SystemExit(f"Stopped: over the ${args.max_total_usd:.2f} budget.")

    async def run_all():
        with temp_database():
            for repeat in range(1, args.repeats + 1):
                for mode in ("fresh", "cached"):
                    await run_sequence(mode, repeat, args.model, args.max_run_usd, on_result)

    asyncio.run(run_all())
    print(f"Saved to {path}")


if __name__ == "__main__":
    main()
