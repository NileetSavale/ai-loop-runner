"""Score each run of a demo task check by check: which hidden tests pass, not just whether all of them do.

    cd backend && python -m benchmarks.demo_score benchmarks/results/<file>.json [more files]

Each run's saved diff is applied to a fresh copy of the task's repo, then the hidden tests and the repo's own tests run
with one result line per test. No model calls.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from benchmarks.run import load_tasks, prepare_repo


def check_results(task, diff: str) -> dict[str, bool]:
    with tempfile.TemporaryDirectory() as folder:
        repo = Path(folder) / "repo"
        prepare_repo(task, repo)
        if diff.strip():
            # Diffs saved before the harness stopped stripping them can lose a final blank context line, which git
            # apply refuses. patch tolerates it, as SWE-bench's own fallback does.
            applied = subprocess.run(["git", "apply", "-"], input=diff.rstrip("\n") + "\n", cwd=repo, text=True, capture_output=True)
            if applied.returncode:
                subprocess.run(["patch", "--batch", "-p1", "--fuzz=5"], input=diff, cwd=repo, text=True, check=True, capture_output=True)
        # Separate runs, since an agent's test file can share a name with a hidden one, and pytest won't load both
        out = "".join(subprocess.run(
            [sys.executable, "-m", "pytest", "-rA", "-q", "-p", "no:cacheprovider", folder],
            cwd=repo, capture_output=True, text=True, env={"PYTHONPATH": str(repo), "PATH": "/usr/bin:/bin"},
        ).stdout for folder in ("tests", str(task.path / "hidden")))
    return {m.group(2).split("::")[-1]: m.group(1) == "PASSED" for m in re.finditer(r"^(PASSED|FAILED|ERROR) (\S+)", out, re.M)}


def main():
    runs = [r for f in sys.argv[1:] for r in json.loads(Path(f).read_text())["runs"]]
    tasks = {t.name: t for t in load_tasks(sorted({r["task"] for r in runs}))}
    scored = [(r, check_results(tasks[r["task"]], r["diff"])) for r in runs]
    names = sorted({n for _, checks in scored for n in checks})
    print("check".ljust(52) + "".join(f"{r['arm'].removeprefix('swe-')[:12]}#{r['repeat']}".rjust(16) for r, _ in scored))
    for name in names:
        cells = ("-" if name not in checks else "pass" if checks[name] else "FAIL" for _, checks in scored)  # - : not in that run
        print(name[:52].ljust(52) + "".join(c.rjust(16) for c in cells))
    print("cost".ljust(52) + "".join(f"${r['cost_usd']:.3f}".rjust(16) for r, _ in scored))


if __name__ == "__main__":
    main()
