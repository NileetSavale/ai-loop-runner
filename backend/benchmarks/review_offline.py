"""Would a stronger model reviewing the cheap model's fix catch the ones that pass the visible tests but not the hidden
ones? Replays saved benchmark runs, with no agent runs.

    cd backend && python -m benchmarks.review_offline results/a.json results/b.json --max-total-usd 2

In the step 2 cascade, Haiku's accepted fixes often failed SWE-bench's hidden tests, and the cascade never escalated
because the visible tests passed. Here the reviewer (Sonnet by default) sees what the cascade would have at that
point: the task, the cheap model's diff and the original code around it, and that the visible tests passed. It says
accept or escalate. Scored against the hidden tests: a good reviewer escalates the hidden failures and accepts the
hidden passes. A review costs one call, against a Sonnet run from scratch.
"""
import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(BACKEND / ".env")

from benchmarks.run import CHEAP_MODEL, OVERALL_CAP_USD, RESULTS_DIR, check_overall_cap, spent_so_far
from benchmarks.swe_run import load_instance
from core.fix_review import PROMPTS, REVIEWER_MODEL, edited_tests, hunk_ranges, review_fix

CONCURRENCY = 4
# A worst case per review, for the cap: the context and diff limits come to about 12k prompt tokens, plus a short reply
WORST_CASE_REVIEW_USD = 0.03


def image_for(instance_id: str) -> str:
    return f"swebench/sweb.eval.x86_64.{instance_id.replace('__', '_1776_').lower()}:latest"


def by_cheap_model(run: dict) -> bool:
    """The diff is the cheap model's: Haiku on its own, or a cascade Haiku settled without Sonnet."""
    return run["arm"] == "swe-cheap-lean" or run.get("note", "").startswith(f"Solved by {CHEAP_MODEL}")


def accepted(run: dict) -> bool:
    """As benchmarks.run.accepted: the loop counts it as done."""
    return run["agent_status"] == "passed" or "already failing before any change" in run.get("note", "")


def select(runs: list[dict], everyone: bool = False) -> list[dict]:
    return [r for r in runs if accepted(r) and r.get("diff", "").strip() and (everyone or by_cheap_model(r))]


def original_file(image: str, path: str) -> str:
    done = subprocess.run(["docker", "run", "--rm", "--platform", "linux/amd64", "--entrypoint", "cat", image,
                           f"/testbed/{path}"], capture_output=True, text=True)
    return done.stdout if done.returncode == 0 else ""


def score(reviews: list[dict]) -> dict:
    """The reviewer's catches and false escalations, and the same for the edited-tests rule alone and for either."""
    bad = [r for r in reviews if not r["hidden_passed"]]
    good = [r for r in reviews if r["hidden_passed"]]

    def counts(escalates) -> dict:
        return {"caught": sum(escalates(r) for r in bad), "wrongly_escalated": sum(escalates(r) for r in good)}

    return {
        "reviewed": len(reviews), "hidden_failures": len(bad), "hidden_passes": len(good),
        **counts(lambda r: not r["accept"]),
        "rule": counts(lambda r: bool(r["edited_tests"])),
        "either": counts(lambda r: not r["accept"] or bool(r["edited_tests"])),
        "cost_usd": round(sum(r["cost_usd"] for r in reviews), 4),
    }


async def review(run: dict, args, specs: dict, lock: asyncio.Semaphore) -> dict:
    async with lock:
        task = run["task"]
        if task not in specs:
            specs[task] = (await asyncio.to_thread(load_instance, task))["problem_statement"]
        files = {path: await asyncio.to_thread(original_file, image_for(task), path) for path in hunk_ranges(run["diff"])}
        verdict = await review_fix(specs[task], run["diff"], lambda path: files[path], run.get("note", ""),
                                   args.prompt, args.model, args.effort)
    flagged = edited_tests(run["diff"])
    print(f"{task} {run['arm']}: {'accept' if verdict['accept'] else 'ESCALATE'}, hidden "
          f"{'pass' if run['hidden_passed'] else 'FAIL'}, ${verdict['cost_usd']:.4f}"
          f"{', edits tests' if flagged else ''}. {verdict['why']}", flush=True)
    return {"task": task, "arm": f"review:{run['arm']}", "source_arm": run["arm"], "hidden_passed": run["hidden_passed"],
            "edited_tests": flagged, **verdict}


async def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("results", nargs="+", type=Path, help="saved benchmark results to replay")
    parser.add_argument("--model", default=REVIEWER_MODEL)
    parser.add_argument("--prompt", choices=sorted(PROMPTS), default="v1", help="v1 as first run; v2 also asks about "
                        "sibling code and edited tests (core/fix_review.py)")
    parser.add_argument("--effort", default=None, help="the reviewer's effort; the model's default if left out")
    parser.add_argument("--everyone", action="store_true", help="also review accepted fixes by the main model")
    parser.add_argument("--max-total-usd", type=float, default=2.0)
    args = parser.parse_args()

    runs = select([r for path in args.results for r in json.loads(path.read_text())["runs"]], args.everyone)
    worst_case = len(runs) * WORST_CASE_REVIEW_USD
    if worst_case > args.max_total_usd:
        raise SystemExit(f"{len(runs)} reviews could cost ${worst_case:.2f}, over --max-total-usd ${args.max_total_usd:.2f}.")
    spent = spent_so_far()
    check_overall_cap(worst_case, spent, OVERALL_CAP_USD)
    print(f"{len(runs)} accepted fixes to review with {args.model}, prompt {args.prompt}: ${worst_case:.2f} at most. "
          f"Overall: ${spent:.2f} spent of the ${OVERALL_CAP_USD:.2f} cap.", flush=True)

    specs, lock = {}, asyncio.Semaphore(CONCURRENCY)
    reviews = await asyncio.gather(*(review(r, args, specs, lock) for r in runs))
    summary = score(list(reviews))
    by_arm = {arm: score([r for r in reviews if r["source_arm"] == arm]) for arm in sorted({r["source_arm"] for r in reviews})}
    print(json.dumps({"overall": summary, "by_arm": by_arm}, indent=2))
    out = RESULTS_DIR / f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-review-offline.json"
    out.write_text(json.dumps({"settings": vars(args) | {"results": [str(p) for p in args.results]},
                               "summary": {"overall": summary, "by_arm": by_arm}, "runs": list(reviews)}, indent=2))
    print(f"Saved to {out}")


if __name__ == "__main__":
    asyncio.run(main())
