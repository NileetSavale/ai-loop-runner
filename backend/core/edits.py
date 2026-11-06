"""What an agent may change in a repo. Every write, by any agent or tool, goes through here."""
import difflib
import os
import re
from dataclasses import dataclass

# ponytail: name patterns, so the agent can still weaken tests through pyproject.toml or package.json.
# Hash the verify setup before each run if a real tamper proof is needed.
_TEST_DIRS = {"tests", "test", "__tests__", "spec", "specs"}
_TEST_FILES = re.compile(r"test_.*|.*_test\..+|.*\.(test|spec)\..+", re.IGNORECASE)
_LOCKED_FILES = re.compile(r"conftest\.py|pytest\.ini|tox\.ini|(jest|vitest)\.config\..+", re.IGNORECASE)


MAX_DIFF_LINES = 400


@dataclass
class FileEdit:
    path: str
    content: str


def resolve_in_repo(repo_path: str, rel_path: str) -> str:
    """Absolute path of rel_path, or ValueError if it escapes repo_path (symlinks included)."""
    root = os.path.realpath(repo_path)
    path = os.path.realpath(os.path.join(root, rel_path))
    if path == root or os.path.commonpath([root, path]) != root:
        raise ValueError(f"path is outside the repo: {rel_path}")
    return path


def is_test_path(rel_path: str) -> bool:
    *dirs, name = rel_path.replace(os.sep, "/").split("/")
    return any(d.lower() in _TEST_DIRS for d in dirs) or bool(_TEST_FILES.fullmatch(name))


def is_locked_path(rel_path: str) -> bool:
    """Never editable. A new conftest.py or pytest.ini could make every test pass without touching a test."""
    *dirs, name = rel_path.replace(os.sep, "/").split("/")
    return any(d.lower() == ".git" for d in dirs) or bool(_LOCKED_FILES.fullmatch(name))


def filter_edits(edits, repo_path: str, added_tests: set[str] | None = None) -> tuple[list, list[str]]:
    """Split edits into those allowed and notes telling the agent what was refused and why.

    added_tests holds the test files this session created. The agent may keep improving those, and any
    new ones it writes are added to the set.
    """
    added_tests = set() if added_tests is None else added_tests
    allowed, rejected = [], []
    for edit in edits:
        try:
            real_path = resolve_in_repo(repo_path, edit.path)
        except ValueError:
            rejected.append(f"REJECTED {edit.path}: outside the repo.")
            continue
        rel = os.path.relpath(real_path, os.path.realpath(repo_path))
        if is_locked_path(rel):
            rejected.append(f"REJECTED {edit.path}: test config and git files are read-only.")
        elif is_test_path(rel) and rel not in added_tests and os.path.exists(real_path):
            rejected.append(f"REJECTED {edit.path}: existing tests are read-only. Add a new test file instead.")
        else:
            if is_test_path(rel):
                added_tests.add(rel)
            allowed.append(edit)
    return allowed, rejected


def apply_edits(edits, repo_path: str) -> list[str]:
    changed = []
    for edit in edits:
        path = resolve_in_repo(repo_path, edit.path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").write(edit.content)
        changed.append(edit.path)
    return changed


def read_current(repo_path: str, rel_path: str) -> str:
    """A file's text, or empty if it doesn't exist or isn't text, for diffing against."""
    try:
        with open(resolve_in_repo(repo_path, rel_path)) as f:
            return f.read()
    except (OSError, UnicodeDecodeError, ValueError):
        return ""


def describe_change(path: str, before: str, after: str) -> dict:
    """What the website shows for one changed file."""
    lines = list(difflib.unified_diff(before.splitlines(), after.splitlines(), f"a/{path}", f"b/{path}", lineterm=""))
    return {
        "path": path,
        "is_new": before == "",
        "added": sum(1 for l in lines if l.startswith("+") and not l.startswith("+++")),
        "removed": sum(1 for l in lines if l.startswith("-") and not l.startswith("---")),
        "diff": "\n".join(lines[:MAX_DIFF_LINES]),
        "diff_cut_off": len(lines) > MAX_DIFF_LINES,
    }
