"""The paper's numbers for the fresh set, straight from the result files.

Solve rates and accepted-but-wrong rates with Wilson 95% intervals, exact McNemar tests between setups on the same
bugs, a paired bootstrap for the reviewed cascade against Sonnet, the reviewers' catch and false-reject rates, and
the reviewed cascade's cost split into its stages with the break-even escalation rate.

    .venv/bin/python -m benchmarks.paper_stats [--json results/stats/out.json]
"""
import argparse
import json
import math
import random
from pathlib import Path

RESULTS = Path(__file__).parent / "results"
CLAUDE = ["20261112-031736-swe-claude-sonnet-5-5.json", "20261112-233401-swe-claude-sonnet-5-5.json",
          "20261113-123616-swe-claude-sonnet-5-5.json", "20261114-010445-swe-claude-sonnet-5-5.json",
          "20261114-094154-swe-claude-sonnet-5-5.json"]  # the last reruns crashed and missing runs, so it goes last
LITE = ["20261112-100346-swe-gemini-3.5-flash-lite.json", "20261113-061845-swe-gemini-3.5-flash-lite.json",
        "20261113-185251-swe-gemini-3.5-flash-lite.json", "20261114-065045-swe-gemini-3.5-flash-lite.json"]
CARBON = ["20261112-100604-review-offline.json", "20261113-061943-review-offline.json",
          "20261113-185255-review-offline.json", "20261114-065415-review-offline.json",
          "20261114-211612-review-offline.json",
          "20261114-214427-review-offline.json"]
SONNET_ON_LITE = ["20261112-194618-review-offline.json", "20261113-074600-review-offline.json",
                  "20261113-202930-review-offline.json", "20261114-084153-review-offline.json",
                  "20261114-214842-review-offline.json"]
ARMS = {"swe-cheap-lean": "haiku", "swe-cascade-tried": "cascade", "swe-cascade-tried-review": "reviewed",
        "swe-loop-lean-keywords": "sonnet"}
SETUPS = ["haiku", "cascade", "reviewed", "sonnet", "lite"]
PAIRS = [("haiku", "cascade"), ("cascade", "reviewed"), ("reviewed", "sonnet"), ("haiku", "sonnet"),
         ("haiku", "reviewed"), ("lite", "haiku")]
UNREADABLE = "The reply couldn't be read."
BOOTSTRAP = 10_000


def outcome(run):
    if (run.get("note") or "").startswith(("The run crashed", "Runner error")):
        return "crash"
    if run["hidden_passed"]:
        return "solved"
    return "wrong" if run.get("agent_status") == "passed" else "failed"


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (centre - half, centre + half)


def mcnemar(b, c):
    """Exact two-sided McNemar p: b and c are the bugs only one of the two setups solved."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def load():
    bugs = {}
    for f in CLAUDE:
        for run in json.loads((RESULTS / f).read_text())["runs"]:
            if run["arm"] in ARMS:
                bugs.setdefault(run["task"], {})[ARMS[run["arm"]]] = run
    for f in LITE:
        for run in json.loads((RESULTS / f).read_text())["runs"]:
            bugs.setdefault(run["task"], {})["lite"] = run
    reviews = {"carbon": {}, "sonnet_on_lite": {}}
    for name, files, arm in (("carbon", CARBON, "swe-cheap-lean"), ("sonnet_on_lite", SONNET_ON_LITE, None)):
        for f in files:
            for rev in json.loads((RESULTS / f).read_text())["runs"]:
                if arm is None or rev["source_arm"] == arm:
                    reviews[name][rev["task"]] = rev
    return {t: a for t, a in bugs.items() if all(s in a for s in SETUPS)}, reviews


def rate(k, n):
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": k / n if n else None, "ci95": [lo, hi]}


def stage_costs(run):
    """The reviewed cascade's cost split into Haiku (scout and loop), the review, and the escalated main model.
    The review isn't itemised in token_sources, so it is what the total leaves over."""
    sources = run.get("token_sources") or {}
    haiku = sum(v["cost_usd"] for k, v in sources.items() if k == "scout" or k.startswith("cheap:"))
    main = sum(v["cost_usd"] for k, v in sources.items() if k.startswith("escalated:"))
    return haiku, max(0.0, run["cost_usd"] - haiku - main), main


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", help="also write the numbers to this file")
    args = parser.parse_args()
    bugs, reviews = load()
    tasks = sorted(bugs)
    n = len(tasks)
    out = {"bugs": n, "setups": {}, "mcnemar": {}, "reviewers": {}}

    print(f"Fresh set: {n} bugs\n")
    print(f"{'setup':10} {'solved':>16} {'95% CI':>15} {'$/bug':>7}  {'wrong of accepted':>18} {'95% CI':>15}  crashes")
    for s in SETUPS:
        o = [outcome(bugs[t][s]) for t in tasks]
        solved, wrong = o.count("solved"), o.count("wrong")
        accepted = sum(bugs[t][s].get("agent_status") == "passed" for t in tasks)
        cost = sum(bugs[t][s]["cost_usd"] for t in tasks) / n
        out["setups"][s] = {"solved": rate(solved, n), "wrong_of_accepted": rate(wrong, accepted),
                            "cost_per_bug": cost, "crashes": o.count("crash")}
        sl, sh = wilson(solved, n)
        wl, wh = wilson(wrong, accepted)
        print(f"{s:10} {solved:4} ({100 * solved / n:4.1f}%) [{100 * sl:4.1f}, {100 * sh:4.1f}] {cost:7.4f}  "
              f"{wrong:4}/{accepted:<4} ({100 * wrong / accepted:4.1f}%) [{100 * wl:4.1f}, {100 * wh:4.1f}]  {o.count('crash')}")

    print("\nExact McNemar on the same bugs (b: only A solved, c: only B solved)")
    for a, b in PAIRS:
        only_a = sum(bugs[t][a]["hidden_passed"] is True and bugs[t][b]["hidden_passed"] is not True for t in tasks)
        only_b = sum(bugs[t][b]["hidden_passed"] is True and bugs[t][a]["hidden_passed"] is not True for t in tasks)
        p = mcnemar(only_a, only_b)
        out["mcnemar"][f"{a}_vs_{b}"] = {"only_a": only_a, "only_b": only_b, "p": p}
        print(f"  {a:9} vs {b:9} b={only_a:3} c={only_b:3}  p={p:.4f}")

    # Paired bootstrap over bugs: the reviewed cascade minus Sonnet, solves and cost
    rng = random.Random(7)
    solve_d, cost_d = [], []
    for _ in range(BOOTSTRAP):
        sample = [tasks[rng.randrange(n)] for _ in range(n)]
        solve_d.append(sum((bugs[t]["reviewed"]["hidden_passed"] is True) - (bugs[t]["sonnet"]["hidden_passed"] is True)
                           for t in sample) / n)
        cost_d.append(sum(bugs[t]["reviewed"]["cost_usd"] - bugs[t]["sonnet"]["cost_usd"] for t in sample) / n)
    solve_d.sort()
    cost_d.sort()
    lo, hi = int(0.025 * BOOTSTRAP), int(0.975 * BOOTSTRAP) - 1
    obs_cost = out["setups"]["reviewed"]["cost_per_bug"] - out["setups"]["sonnet"]["cost_per_bug"]
    out["reviewed_minus_sonnet"] = {"solve_rate_ci95": [solve_d[lo], solve_d[hi]],
                                    "cost_per_bug": obs_cost, "cost_ci95": [cost_d[lo], cost_d[hi]]}
    print(f"\nReviewed cascade minus Sonnet (paired bootstrap, {BOOTSTRAP} resamples):")
    print(f"  solve rate [{100 * solve_d[lo]:+.1f}, {100 * solve_d[hi]:+.1f}] points;"
          f"  cost {obs_cost:+.4f} $/bug [{cost_d[lo]:+.4f}, {cost_d[hi]:+.4f}]"
          f" ({100 * obs_cost / out['setups']['sonnet']['cost_per_bug']:+.0f}% of Sonnet)")

    # A review is judged by the hidden tests of the fix it read. It covers every fix the loop accepted, including on
    # bugs whose tests already failed before any change, so there are more reviews than "accepted" runs above.
    print("\nOffline reviewers (an unreadable reply counts as a reject; 'readable' leaves those out)")
    for name, source in (("carbon", "haiku"), ("sonnet_on_lite", "lite")):
        revs = {t: reviews[name][t] for t in tasks if t in reviews[name]}
        accepted = [t for t in tasks if bugs[t][source].get("agent_status") == "passed"]
        # An accepted run with an empty diff changed nothing, so there is nothing to review
        row = {"accepted_not_reviewed": sum(t not in revs and (bugs[t][source].get("diff") or "").strip() != ""
                                            for t in accepted),
               "accepted_empty_diff": sum(not (bugs[t][source].get("diff") or "").strip() for t in accepted)}
        for label, keep in (("all", lambda r: True), ("readable", lambda r: r["why"] != UNREADABLE)):
            wrong = [t for t, r in revs.items() if keep(r) and not r["hidden_passed"]]
            good = [t for t, r in revs.items() if keep(r) and r["hidden_passed"]]
            row[label] = {"caught": rate(sum(not revs[t]["accept"] for t in wrong), len(wrong)),
                          "false_reject": rate(sum(not revs[t]["accept"] for t in good), len(good))}
        unread = sum(r["why"] == UNREADABLE for r in revs.values())
        cost = sum(r["cost_usd"] for r in revs.values())
        row.update({"reviews": len(revs), "unreadable": unread, "cost_usd": cost})
        out["reviewers"][name] = row
        print(f"  {name}: {len(revs)} reviews, {unread} unreadable, ${cost:.2f} (${cost / len(revs):.3f} each);"
              f" {row['accepted_not_reviewed']} accepted fixes not reviewed, {row['accepted_empty_diff']} accepted with"
              " an empty diff")
        for label in ("all", "readable"):
            c, f = row[label]["caught"], row[label]["false_reject"]
            print(f"    {label:8} caught {c['k']}/{c['n']} ({100 * c['rate']:.0f}%, CI {100 * c['ci95'][0]:.0f}-"
                  f"{100 * c['ci95'][1]:.0f})  wrongly rejected {f['k']}/{f['n']} ({100 * f['rate']:.0f}%, CI "
                  f"{100 * f['ci95'][0]:.0f}-{100 * f['ci95'][1]:.0f})")

    # The reviewed cascade's cost, stage by stage, and when it would beat Sonnet on cost
    haiku, review, main_ = zip(*(stage_costs(bugs[t]["reviewed"]) for t in tasks))
    escalated = [t for t, m in zip(tasks, main_) if m > 0]
    e = len(escalated) / n
    redo = sum(main_) / len(escalated)
    sonnet = out["setups"]["sonnet"]["cost_per_bug"]
    fixed = (sum(haiku) + sum(review)) / n
    break_even = (sonnet - fixed) / redo
    out["cost_model"] = {"haiku_per_bug": sum(haiku) / n, "review_per_bug": sum(review) / n,
                         "escalation_rate": e, "redo_per_escalation": redo, "sonnet_per_bug": sonnet,
                         "break_even_escalation_rate": break_even}
    print("\nReviewed cascade cost per bug = Haiku + review + escalation rate x main-model redo")
    print(f"  {sum(haiku) / n:.4f} + {sum(review) / n:.4f} + {e:.2f} x {redo:.4f} = "
          f"{fixed + e * redo:.4f}  (Sonnet alone {sonnet:.4f})")
    print(f"  Cheaper than Sonnet only if under {100 * break_even:.0f}% of bugs escalate; here {100 * e:.0f}% do."
          f" A redo costs {redo / sonnet:.1f}x a Sonnet run from scratch.")

    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2))
        print(f"\nSaved to {args.json}")


if __name__ == "__main__":
    main()
