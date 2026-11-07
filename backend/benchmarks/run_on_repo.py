"""Run Loop Runner's agent team on tasks in an existing repo, in place, one task after another.

    cd backend && python -m benchmarks.run_on_repo --repo /path/to/repo --tasks tasks.json --verify "npm test" \\
        --max-run-usd 1.5 --max-total-usd 8

tasks.json is a list of {"name": ..., "prompt": ...}. Unlike the benchmarks, this changes the repo itself: work on a
branch you can throw away. A task whose checks pass is committed by the loop, so each fix lands as its own commit.
There are no hidden checks here: a person reviews the commits.
"""
import argparse
import asyncio
import json
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

if __name__ == "__main__":
    # Before the imports below, because providers read their keys on import
    from dotenv import load_dotenv
    load_dotenv(BACKEND / ".env")

from benchmarks.run import (OVERALL_CAP_USD, RESULTS_DIR, BenchTask, RunResult, _code_version, check_overall_cap,
                            run_loop_arm, spent_so_far, temp_database)

# The full team: an auditor before work starts, a tester whose tests the coder must pass, the coder, and a security
# reviewer beside it, with the token trims measured so far (the loop-lean arm: same solves, lowest cost, no cheating)
TEAM = dict(retry_context="continue", max_only_old_failures=1, short_output=True, reviewer_effort="low",
            max_listed_files=100, security_audit=True, security_pair=True, write_tests_first=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--verify", required=True, help="Command that checks the repo, run from its root.")
    parser.add_argument("--model", default="claude-sonnet-5-5")
    parser.add_argument("--max-run-usd", type=float, default=1.5)
    parser.add_argument("--max-total-usd", type=float, required=True)
    parser.add_argument("--audit-cache", help="File for the auditor's findings, kept between tasks.")
    args = parser.parse_args()

    tasks = json.loads(args.tasks.read_text())
    if subprocess.run(["git", "status", "--porcelain"], cwd=args.repo, capture_output=True, text=True).stdout.strip():
        raise SystemExit("The repo has uncommitted changes. Commit or stash them first, so every change here is revertible.")
    check_overall_cap(min(len(tasks) * args.max_run_usd, args.max_total_usd), spent_so_far(), OVERALL_CAP_USD)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = RESULTS_DIR / f"{stamp}-repo-{args.repo.name}.json"
    finished: list[RunResult] = []

    async def run_all():
        with temp_database():
            for task in tasks:
                if sum(r.cost_usd for r in finished) + args.max_run_usd > args.max_total_usd:
                    print(f"Stopped before {task['name']}: the budget can't cover another run.")
                    break
                result = RunResult(task=task["name"], arm="team", model=args.model, repeat=1)
                await run_loop_arm(BenchTask(task["name"], args.repo, task["prompt"], args.verify), args.repo, args.model,
                                   args.max_run_usd, result, audit_cache=args.audit_cache, **TEAM)
                finished.append(result)
                if subprocess.run(["git", "status", "--porcelain"], cwd=args.repo, capture_output=True, text=True).stdout.strip():
                    # A task that didn't pass leaves its changes uncommitted. Keep them, out of the next task's way.
                    subprocess.run(["git", "stash", "push", "-u", "-m", f"loop-runner: {task['name']} (didn't pass)"],
                                   cwd=args.repo, check=True, capture_output=True)
                    result.note = (result.note + " " if result.note else "") + "Its changes are in git stash."
                path.write_text(json.dumps({"settings": {k: str(v) for k, v in vars(args).items()}, "code": _code_version(),
                                            "runs": [asdict(r) for r in finished]}, indent=2))
                head = subprocess.run(["git", "log", "--oneline", "-1"], cwd=args.repo, capture_output=True, text=True).stdout.strip()
                print(f"{task['name']}: {result.agent_status}, {result.attempts} attempts, ${result.cost_usd:.4f}, "
                      f"last commit: {head}" + (f" ({result.note})" if result.note else ""), flush=True)

    asyncio.run(run_all())
    print(f"Saved to {path}")


if __name__ == "__main__":
    main()
