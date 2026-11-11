"""Builds the packet two people label independently: why each test-passing cheap fix fails SWE-bench's hidden tests.

    cd backend && python -m benchmarks.label_packet OUT_DIR RESULTS.json [RESULTS.json ...]

Takes every fix the loop accepted from a cheap model (as review_offline selects them) that fails the hidden tests.
Each case gets one Markdown file: the issue, the cheap model's diff, the official fix and the official tests, and the
hidden tests that failed with an excerpt of their output. Cases are shuffled and numbered; which bug, setup and model
each number is goes in a separate key file, kept from the labellers. sheet.csv is the blank form.
"""
import argparse
import csv
import json
import random
import re
from pathlib import Path

from benchmarks.review_offline import finished_runs, select
from benchmarks.swe_run import MODEL_NAME, SWE_DIR, load_instance

MAX_EXCERPT_LINES = 160
CONTEXT_AFTER = 40


def run_id(results: Path, run: dict) -> str:
    """As swe_run names a run: the results file's stamp, the arm and the bug."""
    stamp = results.name.split("-swe-")[0]
    return f"{stamp}-{run['arm'].removeprefix('swe-')}-{run['task']}"


def failed_tests(report: dict) -> list[str]:
    status = report["tests_status"]
    return status["FAIL_TO_PASS"]["failure"] + status["PASS_TO_PASS"]["failure"]


def excerpt(output: str, tests: list[str]) -> str:
    """The test output from where each failed test is named, plus what follows."""
    lines = output.split(">>>>> Start Test Output")[-1].splitlines()
    names = {re.split(r"[ (\[]", t)[0].split("::")[-1] for t in tests}
    keep: set[int] = set()
    for i, line in enumerate(lines):
        if not any(name and name in line for name in names):
            continue
        # The start of a failure's report: pytest's and sympy's "____ name ____" header, unittest's "FAIL: name"
        if re.match(r"\s*_{3,} ", line) or re.match(r"(FAIL|ERROR): ", line):
            keep.update(range(i, min(i + CONTEXT_AFTER, len(lines))))
        elif re.search(r"FAIL|ERROR", line):
            keep.add(i)
    if not keep:  # the failed tests never ran, e.g. their module didn't import: show the errors instead
        for i, line in enumerate(lines):
            if re.match(r"(ERROR|FAIL)\b|E +\w*Error|\w*Error: ", line):
                keep.update(range(max(0, i - 2), min(i + 10, len(lines))))
    chosen = [lines[i] for i in sorted(keep)][:MAX_EXCERPT_LINES]
    return "\n".join(chosen) or "(no output matched the failed tests' names)"


def case_text(number: int, instance: dict, diff: str, tests: list[str], output: str) -> str:
    return (f"# Case {number}\n\n## The issue\n\n{instance['problem_statement'].strip()}\n\n"
            f"## The cheap model's fix (passed the repository's own tests)\n\n```diff\n{diff.strip()}\n```\n\n"
            f"## The official fix\n\n```diff\n{instance['patch'].strip()}\n```\n\n"
            f"## The official tests added or changed for this issue\n\n```diff\n{instance['test_patch'].strip()}\n```\n\n"
            f"## Hidden tests the cheap fix failed\n\n" + "\n".join(f"- `{t}`" for t in tests) +
            f"\n\n## Test output for those tests (excerpt)\n\n```\n{output}\n```\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("results", nargs="+", type=Path)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    cases = []
    for path in args.results:
        saved = json.loads(path.read_text())
        # Files from before --cheap-model existed all used Haiku
        model = saved["settings"].get("cheap_model", "claude-haiku-5-5")
        cases += [(path, model, run) for run in select(finished_runs(saved), cheap_model=model)
                   if not run["hidden_passed"]]
    random.Random(args.seed).shuffle(cases)

    (args.out / "cases").mkdir(parents=True, exist_ok=True)
    key, rows = [], []
    for number, (path, model, run) in enumerate(cases, start=1):
        instance = load_instance(run["task"])
        logs = SWE_DIR / "logs/evaluation" / run_id(path, run) / MODEL_NAME / run["task"]
        report = json.loads((logs / "report.json").read_text())[run["task"]]
        tests = failed_tests(report)
        output = excerpt((logs / "test_output.txt").read_text(errors="replace"), tests)
        (args.out / "cases" / f"case-{number:02}.md").write_text(case_text(number, instance, run["diff"], tests, output))
        key.append({"case": number, "task": run["task"], "arm": run["arm"], "cheap_model": model, "results": str(path)})
        rows.append({"case": number, "category": "", "sure": "", "note": ""})
        print(f"case {number:02}: {run['task']} ({model}, {run['arm']})", flush=True)

    with open(args.out / "sheet.csv", "w", newline="") as sheet:
        writer = csv.DictWriter(sheet, fieldnames=["case", "category", "sure", "note"])
        writer.writeheader()
        writer.writerows(rows)
    (args.out.parent / f"{args.out.name}-key.json").write_text(json.dumps(key, indent=2))
    print(f"{len(cases)} cases in {args.out}; key in {args.out.name}-key.json beside it")


if __name__ == "__main__":
    main()
