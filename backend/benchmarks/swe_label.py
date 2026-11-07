"""Label the tests an agent sees on SWE-bench Verified bugs, to measure how often failures aren't the agent's fault.

    cd backend && python -m benchmarks.swe_label --sample 60 --seed 2026 --reps 3

No model calls, so no API cost. For each bug in a random sample it runs the visible tests (the ones swe_run's agents
check their work with) several times on the original code and several times with the official fix, then labels:
- already failing: fail every time, before and after the official fix, so no correct fix can make them pass
- must change: pass before, fail every time after the official fix, so the fix needs an existing test updated
- flaky: pass in some runs and fail in others under the same code
Results go to one JSON line per bug, and a rerun skips bugs already written.
"""
import argparse
import asyncio
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
# Some suites take minutes, and a timeout would look like a failure
os.environ.setdefault("MAX_VERIFY_TIMEOUT_SECONDS", "900")

from benchmarks.run import _git
from benchmarks.swe_run import DATASET, SWE_DIR, checkout, test_command, verify_command
from core.verifier import failing_tests, run_verify

# The bugs the pilot already used, kept out so the sample is fresh
PILOT = {
    "pytest-dev__pytest-10356", "django__django-10880", "django__django-11299", "django__django-11999",
    "astropy__astropy-13398", "pydata__xarray-6992", "sympy__sympy-13615", "sympy__sympy-15809",
    "pytest-dev__pytest-7432", "astropy__astropy-13579",
}

_LOAD_ALL = """
import json, sys
from swebench.harness.utils import load_swebench_dataset
keep = ("instance_id", "image", "eval_script", "patch", "test_patch")
print(json.dumps([{k: row[k] for k in keep} for row in load_swebench_dataset(sys.argv[1], "test")]))
"""


@dataclass
class Run:
    passed: bool
    failing: set[str]
    unrecognised: bool = False  # failed, but no test names could be read from the output


@dataclass
class Labels:
    instance_id: str
    gold_resolved: bool | None = None
    base_passed: list[bool] = field(default_factory=list)
    gold_passed: list[bool] = field(default_factory=list)
    already_failing: list[str] = field(default_factory=list)
    must_change: list[str] = field(default_factory=list)
    flaky: list[str] = field(default_factory=list)
    fixed_by_gold: list[str] = field(default_factory=list)
    unrecognised_runs: int = 0
    new_test_files: list[str] = field(default_factory=list)
    error: str = ""


def label(base: list[Run], gold: list[Run]) -> dict[str, list[str]]:
    """Sort test names by how they behave across repeated runs before and after the official fix."""
    def always(runs):
        return set.intersection(*(r.failing for r in runs)) if runs else set()

    def ever(runs):
        return set().union(*(r.failing for r in runs))

    flaky = (ever(base) - always(base)) | (ever(gold) - always(gold))
    return {
        "already_failing": sorted(always(base) & always(gold) - flaky),
        "must_change": sorted(always(gold) - ever(base) - flaky),
        "flaky": sorted(flaky),
        "fixed_by_gold": sorted(always(base) - ever(gold) - flaky),
    }


def new_test_files(test_patch: str) -> list[str]:
    """Test files the hidden test patch creates. The visible command names them, but they don't exist yet."""
    return re.findall(r"^--- /dev/null\n\+\+\+ b/(\S+)", test_patch, re.M)


async def _runs(command: str, repo: Path, reps: int) -> list[Run]:
    runs = []
    for _ in range(reps):
        result = await run_verify(command, str(repo))
        names = failing_tests(result.output)
        runs.append(Run(result.passed, names, not result.passed and not names))
    return runs


def label_instance(row: dict, reps: int, gold_resolved: bool | None) -> Labels:
    labels = Labels(row["instance_id"], gold_resolved, new_test_files=new_test_files(row["test_patch"]))
    command = verify_command(row["image"], test_command(row["eval_script"]))
    with tempfile.TemporaryDirectory() as folder:
        repo = Path(folder) / "repo"
        checkout(row["image"], repo)
        base = asyncio.run(_runs(command, repo, reps))
        subprocess.run(["git", "apply", "-"], input=row["patch"], cwd=repo, text=True, check=True, capture_output=True)
        gold = asyncio.run(_runs(command, repo, reps))
    labels.base_passed = [r.passed for r in base]
    labels.gold_passed = [r.passed for r in gold]
    labels.unrecognised_runs = sum(r.unrecognised for r in base + gold)
    for name, tests in label(base, gold).items():
        setattr(labels, name, tests)
    return labels


def build_and_check_gold(ids: list[str], run_id: str) -> dict[str, bool | None]:
    """Builds the images and records whether SWE-bench itself counts the official fix as resolving each bug."""
    subprocess.run(
        [str(SWE_DIR / "venv/bin/swebench"), "eval", "verified", "--gold", *[a for i in ids for a in ("-i", i)],
         "--run-id", run_id, "--task-repo", "./swe-bench-tasks", "-j", "2"],
        cwd=SWE_DIR, env={**os.environ, "DOCKER_DEFAULT_PLATFORM": "linux/amd64"},
    )
    resolved = {}
    for i in ids:
        report = SWE_DIR / "logs/evaluation" / run_id / "gold" / i / "report.json"
        resolved[i] = bool(json.loads(report.read_text())[i]["resolved"]) if report.exists() else None
    return resolved


def summarize(rows: list[dict]) -> str:
    done = [r for r in rows if not r["error"]]
    n = len(done) or 1

    def share(test):
        count = sum(1 for r in done if test(r))
        return f"{count} of {len(done)} ({count / n:.0%})"
    return "\n".join([
        f"Bugs labelled:                  {len(done)} ({len(rows) - len(done)} errors)",
        f"Official fix not resolved:      {share(lambda r: r['gold_resolved'] is False)}",
        f"Some test already failing:      {share(lambda r: r['already_failing'])}",
        f"Some existing test must change: {share(lambda r: r['must_change'])}",
        f"Some test flaky:                {share(lambda r: r['flaky'])}",
        f"Visible tests name a new file: {share(lambda r: r['new_test_files'])}",
        f"Any of the above:               {share(lambda r: r['already_failing'] or r['must_change'] or r['flaky'] or r['new_test_files'])}",
        f"Unreadable failing output:      {share(lambda r: r['unrecognised_runs'])}",
    ])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample", type=int, default=60)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--out", type=Path, default=SWE_DIR / "labels.jsonl")
    args = parser.parse_args()

    dataset = json.loads(subprocess.run(
        [str(SWE_DIR / "venv/bin/python"), "-c", _LOAD_ALL, DATASET], check=True, capture_output=True, text=True,
    ).stdout.splitlines()[-1])
    rows = {r["instance_id"]: r for r in dataset}
    # Chosen before seeing any results, from a fixed seed, so the sample can't favour any kind of bug
    sample = random.Random(args.seed).sample(sorted(set(rows) - PILOT), args.sample)

    done = {json.loads(line)["instance_id"] for line in args.out.read_text().splitlines()} if args.out.exists() else set()
    todo = [i for i in sample if i not in done]
    print(f"{len(sample)} bugs sampled (seed {args.seed}), {len(todo)} still to label, {args.reps} runs each way.", flush=True)

    gold = build_and_check_gold(todo, f"label-gold-{args.seed}") if todo else {}
    for i, instance_id in enumerate(todo, 1):
        try:
            labels = label_instance(rows[instance_id], args.reps, gold.get(instance_id))
        except Exception as e:  # one broken image shouldn't lose the rest
            labels = Labels(instance_id, gold.get(instance_id), error=repr(e)[:300])
        with args.out.open("a") as f:
            f.write(json.dumps(asdict(labels)) + "\n")
        flags = [k for k in ("already_failing", "must_change", "flaky", "new_test_files") if getattr(labels, k)]
        print(f"[{i}/{len(todo)}] {instance_id}: {', '.join(flags) or labels.error or 'clean'}", flush=True)

    results = [json.loads(line) for line in args.out.read_text().splitlines()]
    print(summarize([r for r in results if r["instance_id"] in set(sample)]))


if __name__ == "__main__":
    main()
