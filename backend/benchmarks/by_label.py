"""Solves and cost per arm, split by how misleading each bug's visible tests are.

    cd backend && python -m benchmarks.by_label results/<run>.json /Volumes/LoopRunnerDocker/swe/labels.jsonl

Groups come from the labelling run (benchmarks/swe_label.py): "already failing" (a visible test fails before and
after the official fix), "must change" (the official fix changes an existing test), otherwise "clean".
"""
import json
import sys
from collections import defaultdict


def group(label: dict) -> str:
    if label["already_failing"]:
        return "already failing"
    if label["must_change"]:
        return "must change"
    return "clean"


def main(results_path: str, labels_path: str):
    labels = {(l := json.loads(line))["instance_id"]: group(l) for line in open(labels_path)}
    runs = json.load(open(results_path))["runs"]
    table = defaultdict(lambda: {"runs": 0, "solved": 0, "cost": 0.0, "attempts": 0})
    for r in runs:
        for g in (labels.get(r["task"], "unlabelled"), "all"):
            row = table[(r["arm"], g)]
            row["runs"] += 1
            row["solved"] += bool(r["hidden_passed"])
            row["cost"] += r["cost_usd"]
            row["attempts"] += r["attempts"] or 0
    groups = ["clean", "already failing", "must change", "all"]
    print(f"{'arm':<22}{'group':<17}{'solved':>10}{'cost':>9}{'per bug':>9}{'attempts':>10}")
    for arm in sorted({a for a, _ in table}):
        for g in groups:
            if (row := table.get((arm, g))):
                print(f"{arm:<22}{g:<17}{row['solved']:>5} of {row['runs']:<3}${row['cost']:>7.2f}"
                      f" ${row['cost'] / row['runs']:>7.3f}{row['attempts'] / row['runs']:>10.1f}")
        print()


if __name__ == "__main__":
    main(*sys.argv[1:3])
