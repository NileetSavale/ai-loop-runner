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

from benchmarks.run import CHEAP_MODEL, RESULTS_DIR, check_caps
from benchmarks.swe_run import finished_pairs, load_instance
from providers.base import MAX_OUTPUT_TOKENS, calculate_cost
from core.fix_review import PROMPTS, REVIEWER_MODEL, edited_tests, hunk_ranges, review_fix

CONCURRENCY = 4
# One dropped connection used to end the whole replay with nothing saved; now a review retries, then is skipped
RETRY_WAITS_SECONDS = (5, 20, 60)
# A worst case per review, for the cap: the context and diff limits come to about 12k prompt tokens, and the reply
# can run to the output limit. Sonnet averaged $0.021 a review in step 2, but Carbon thinks for up to 16k tokens.
WORST_CASE_PROMPT_TOKENS = 12_000
UNREADABLE = "The reply couldn't be read."


def image_for(instance_id: str) -> str:
    return f"swebench/sweb.eval.x86_64.{instance_id.replace('__', '_1776_').lower()}:latest"


def by_cheap_model(run: dict, cheap_model: str = CHEAP_MODEL) -> bool:
    """The diff is the cheap model's: on its own, or a cascade it settled without the main model."""
    return run["arm"] == "swe-cheap-lean" or run.get("note", "").startswith(f"Solved by {cheap_model}")


def accepted(run: dict) -> bool:
    """As benchmarks.run.accepted: the loop counts it as done."""
    return run["agent_status"] == "passed" or "already failing before any change" in run.get("note", "")


def select(runs: list[dict], everyone: bool = False, cheap_model: str = CHEAP_MODEL) -> list[dict]:
    return [r for r in runs if accepted(r) and r.get("diff", "").strip() and (everyone or by_cheap_model(r, cheap_model))]


def finished_runs(saved: dict) -> list[dict]:
    """A stopped batch saves its runs still going, not yet checked against the hidden tests: those aren't reviewed."""
    done = finished_pairs(saved)
    return [r for r in saved["runs"] if (r["task"], r["arm"]) in done]


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
        # Escalated like any unclear verdict, but counted apart: a reply cut off at the output limit isn't a judgement
        "unreadable": {"hidden_failures": sum(r["why"] == UNREADABLE for r in bad),
                       "hidden_passes": sum(r["why"] == UNREADABLE for r in good)},
        "cost_usd": round(sum(r["cost_usd"] for r in reviews), 4),
    }


async def review(run: dict, args, specs: dict) -> dict:
    task = run["task"]
    if task not in specs:
        specs[task] = (await asyncio.to_thread(load_instance, task))["problem_statement"]
    files = {path: await asyncio.to_thread(original_file, image_for(task), path) for path in hunk_ranges(run["diff"])}
    for wait in (*RETRY_WAITS_SECONDS, None):
        try:
            verdict = await review_fix(specs[task], run["diff"], lambda path: files[path], run.get("note", ""),
                                       args.prompt, args.model, args.effort)
            break
        except Exception as error:  # the API or the network; the replay goes on without this review
            print(f"{task} {run['arm']}: {type(error).__name__}: {error}"
                  + (f", retrying in {wait}s" if wait else ", skipped"), flush=True)
            if wait is None:
                return None
            await asyncio.sleep(wait)
    flagged = edited_tests(run["diff"])
    print(f"{task} {run['arm']}: {'accept' if verdict['accept'] else 'ESCALATE'}, hidden "
          f"{'pass' if run['hidden_passed'] else 'FAIL'}, ${verdict['cost_usd']:.4f}"
          f"{', edits tests' if flagged else ''}. {verdict['why']}", flush=True)
    return {"task": task, "arm": f"review:{run['arm']}", "source_arm": run["arm"], "hidden_passed": run["hidden_passed"],
            "edited_tests": flagged, **verdict}


def write(out: Path, args, reviews: list[dict], summary: dict | None = None):
    """Saved after every review, so a stopped replay still counts toward the caps and can be resumed."""
    out.write_text(json.dumps({"settings": vars(args) | {"results": [str(p) for p in args.results],
                                                         "resume": str(args.resume) if args.resume else None},
                               "summary": summary, "runs": reviews}, indent=2))


async def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("results", nargs="+", type=Path, help="saved benchmark results to replay")
    parser.add_argument("--model", default=REVIEWER_MODEL)
    parser.add_argument("--prompt", choices=sorted(PROMPTS), default="v1", help="v1 as first run; v2 also asks about "
                        "sibling code and edited tests (core/fix_review.py)")
    parser.add_argument("--effort", default=None, help="the reviewer's effort; the model's default if left out")
    parser.add_argument("--everyone", action="store_true", help="also review accepted fixes by the main model")
    parser.add_argument("--cheap-model", default=CHEAP_MODEL, help="whose fixes to review, as the runs' --cheap-model")
    parser.add_argument("--resume", type=Path, help="a stopped replay's saved file: its reviews are kept, the rest done, "
                        "and the file updated in place")
    parser.add_argument("--max-total-usd", type=float, default=2.0)
    args = parser.parse_args()

    done = json.loads(args.resume.read_text())["runs"] if args.resume else []
    reviewed = {(r["task"], r["source_arm"]) for r in done}
    runs = [r for r in select([r for path in args.results for r in finished_runs(json.loads(path.read_text()))],
                              args.everyone, args.cheap_model) if (r["task"], r["arm"]) not in reviewed]
    # The cap covers the resumed reviews too. A review starts only if it can't take the total past the cap.
    per_review = calculate_cost(args.model, WORST_CASE_PROMPT_TOKENS, MAX_OUTPUT_TOKENS)
    spent = {"done": sum(r["cost_usd"] for r in done), "reserved": 0.0}
    worst_case = min(len(runs) * per_review, max(args.max_total_usd - spent["done"], 0))
    standing = check_caps(worst_case, {args.model})
    print(f"{len(runs)} accepted fixes to review with {args.model}, prompt {args.prompt}"
          f"{f' ({len(done)} already done)' if done else ''}: ${worst_case:.2f} at most. Overall: {standing}.", flush=True)

    out = args.resume or RESULTS_DIR / f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-review-offline.json"
    specs, lock, reviews = {}, asyncio.Semaphore(CONCURRENCY), list(done)

    stopped = []

    async def review_and_save(run: dict):
        async with lock:
            if spent["done"] + spent["reserved"] + per_review > args.max_total_usd:
                stopped.append(run)
                return
            spent["reserved"] += per_review
            result = await review(run, args, specs)
            spent["reserved"] -= per_review
            spent["done"] += result["cost_usd"] if result else 0
        if result:
            reviews.append(result)
            write(out, args, reviews)

    await asyncio.gather(*(review_and_save(r) for r in runs))
    summary = score(reviews)
    by_arm = {arm: score([r for r in reviews if r["source_arm"] == arm]) for arm in sorted({r["source_arm"] for r in reviews})}
    summary = {"overall": summary, "by_arm": by_arm, "skipped": len(done) + len(runs) - len(reviews) - len(stopped),
               "not_reviewed_at_cap": len(stopped)}
    if stopped:
        print(f"Stopped at the ${args.max_total_usd:.2f} cap: {len(stopped)} fixes not reviewed. --resume does them.")
    print(json.dumps(summary, indent=2))
    write(out, args, reviews, summary)
    print(f"Saved to {out}")


if __name__ == "__main__":
    asyncio.run(main())
