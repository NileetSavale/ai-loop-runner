"""Measure the agent on a real bug from SWE-bench Verified, scored by SWE-bench's own hidden tests.

    cd backend && python -m benchmarks.swe_run --instance sympy__sympy-20590 --model claude-sonnet-5-5 --max-run-usd 2

Spends real money. The agent edits a checkout on this machine through its file tools, and its code only runs inside
the bug's Docker image, with no network. The agent sees the issue and the existing tests in the files the fix's tests
touch. Published SWE-bench agents get the issue alone, so these results aren't directly comparable with theirs.
"""
import argparse
import asyncio
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

if __name__ == "__main__":
    # Before the imports below, because providers read their keys on import
    from dotenv import load_dotenv
    load_dotenv(BACKEND / ".env")

from benchmarks.run import (
    OVERALL_CAP_USD, RESULTS_DIR, BenchTask, RunResult, _code_version, _git, changed_lines, check_overall_cap,
    format_summary, format_table, run_loop_arm, spent_so_far, summarize, temp_database,
)
from core.verifier import run_verify

SWE_DIR = Path(os.getenv("SWEBENCH_DIR", "/Volumes/LoopRunnerDocker/swe"))
DATASET = "SWE-bench/SWE-bench_Verified"
MODEL_NAME = "loop-runner"

_LOAD_INSTANCE = """
import json, sys
from swebench.harness.utils import load_swebench_dataset
print(json.dumps(load_swebench_dataset(sys.argv[1], "test", [sys.argv[2]])[0]))
"""


def load_instance(instance_id: str) -> dict:
    """Runs in SWE-bench's own environment, whose dependencies stay out of the backend's."""
    output = subprocess.run(
        [str(SWE_DIR / "venv/bin/python"), "-c", _LOAD_INSTANCE, DATASET, instance_id],
        check=True, capture_output=True, text=True,
    ).stdout
    return json.loads(output.splitlines()[-1])


def test_command(eval_script: str) -> str:
    """The command SWE-bench itself runs. Hidden tests are added by the script before it, not by this command."""
    match = re.search(r">>>>> Start Test Output'\n(.*?)\n: '>>>>> End Test Output'", eval_script, re.DOTALL)
    if not match:
        raise ValueError("Couldn't find the test command in the eval script")
    return match.group(1)


def verify_command(image: str, command: str) -> str:
    """$PWD rather than a fixed path, so it tests whichever copy of the repo it runs in."""
    inner = f"source /opt/miniconda3/bin/activate && conda activate testbed && {command}"
    return (
        f'docker run --rm --network none --platform linux/amd64 -e PYTHONDONTWRITEBYTECODE=1 -v "$PWD":/testbed '
        f"-w /testbed {shlex.quote(image)} bash -c {shlex.quote(inner)}"
    )


def checkout(image: str, dest: Path) -> str:
    """Copy the buggy code out of the image, returning the commit that changes are measured against."""
    def docker(*args: str) -> str:
        return subprocess.run(["docker", *args], check=True, capture_output=True, text=True).stdout.strip()

    container = docker("create", "--platform", "linux/amd64", image)
    try:
        docker("cp", f"{container}:/testbed", str(dest))
    finally:
        docker("rm", container)
    _git(dest, "config", "core.fileMode", "false")
    _git(dest, "config", "user.name", "benchmark")
    _git(dest, "config", "user.email", "benchmark@example.com")
    with open(dest / ".git" / "info" / "exclude", "a") as f:
        f.write("__pycache__/\n.pytest_cache/\n*.egg-info/\n")
    return _git(dest, "rev-parse", "HEAD")


def score(instance_id: str, patch: str, run_id: str) -> tuple[bool, str]:
    """Whether SWE-bench counts the patch as resolving the bug, and why not if it doesn't."""
    if not patch.strip():
        return False, "The agent changed nothing, so there was nothing to score."
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl") as predictions:
        predictions.write(json.dumps({"instance_id": instance_id, "model_name_or_path": MODEL_NAME, "model_patch": patch}))
        predictions.flush()
        # Absolute, because this runs from SWE_DIR and logs go there
        evaluated = subprocess.run(
            [str(SWE_DIR / "venv/bin/swebench"), "eval", "verified", "-p", predictions.name, "-i", instance_id,
             "--run-id", run_id, "--task-repo", "./swe-bench-tasks", "-j", "1"],
            cwd=SWE_DIR, capture_output=True, text=True,
        )
    report = SWE_DIR / "logs/evaluation" / run_id / MODEL_NAME / instance_id / "report.json"
    if not report.exists():
        return False, f"SWE-bench produced no report (exit {evaluated.returncode}): {evaluated.stderr[-300:]}"
    return bool(json.loads(report.read_text())[instance_id]["resolved"]), ""


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--max-run-usd", type=float, required=True)
    parser.add_argument("--yes", action="store_true", help="Skip the spending confirmation.")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY isn't set.")
    spent = spent_so_far()
    check_overall_cap(args.max_run_usd, spent, OVERALL_CAP_USD)
    print(f"{args.instance} on {args.model}: up to ${args.max_run_usd:.2f}. Overall: ${spent:.2f} spent of the ${OVERALL_CAP_USD:.2f} cap.")
    if not args.yes and input("Continue? [y/N] ").strip().lower() != "y":
        raise SystemExit("Stopped. Nothing was spent.")

    # ponytail: needs the image built already (swebench eval --gold builds it). Build here when the pilot needs it.
    instance = load_instance(args.instance)
    image = instance["image"]
    task = BenchTask(
        args.instance, Path(), f"Fix this issue in the repo.\n\n{instance['problem_statement']}",
        verify_command(image, test_command(instance["eval_script"])),
    )
    result = RunResult(task=args.instance, arm="loop-swe", model=args.model, repeat=1)

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = RESULTS_DIR / f"{stamp}-swe-{args.instance}-{args.model}.json"

    def save():
        path.write_text(json.dumps({
            "settings": vars(args), "code": _code_version(), "summary": summarize([result]), "runs": [asdict(result)],
        }, indent=2))

    with tempfile.TemporaryDirectory() as folder, temp_database():
        repo = Path(folder) / "repo"
        base = checkout(image, repo)
        started = time.monotonic()
        asyncio.run(run_loop_arm(task, repo, args.model, args.max_run_usd, result))
        result.duration_seconds = round(time.monotonic() - started, 1)
        result.changed_code_lines, result.changed_test_lines = changed_lines(repo, base)
        result.diff = _git(repo, "diff", "--cached", base) + "\n"  # git apply refuses a patch with no final newline
        save()  # before scoring, so a scoring failure doesn't lose what was paid for
        result.visible_passed = asyncio.run(run_verify(task.verify, str(repo))).passed
        result.hidden_passed, note = score(args.instance, result.diff, f"loop-{stamp}")
        result.note = result.note or note
        save()

    print(f"\n{format_table([result])}\n\n{format_summary(summarize([result]))}\nSaved to {path}")


if __name__ == "__main__":
    main()
