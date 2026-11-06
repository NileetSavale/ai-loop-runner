"""Mutation check: are the tests strong enough to notice a broken implementation?

Plants small bugs in a throwaway copy of the repo and re-runs the verify command. Good tests fail
for each bug. Tests like `assert True` catch none, so they can't be used to clear the bar.
"""
import ast
import asyncio
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field

import git

from core.agent import resolve_in_repo
from core.verifier import run_verify

MAX_MUTANTS = 10
MAX_SECONDS = 300

_SWAPS = {
    ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Gt: ast.LtE, ast.LtE: ast.Gt,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.In: ast.NotIn, ast.NotIn: ast.In,
    ast.Is: ast.IsNot, ast.IsNot: ast.Is,
    ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Add, ast.Div: ast.Mult,
    ast.And: ast.Or, ast.Or: ast.And,
}


@dataclass
class MutationResult:
    tested: int = 0
    caught: int = 0
    survivors: list[str] = field(default_factory=list)
    skipped_reason: str | None = None


def _mutation_for(node: ast.AST):
    """(description, apply) for a bug we can plant at this node, or None."""
    if isinstance(node, ast.Compare) and type(node.ops[0]) in _SWAPS:
        new = _SWAPS[type(node.ops[0])]
        return f"{type(node.ops[0]).__name__} changed to {new.__name__}", lambda: node.ops.__setitem__(0, new())
    if isinstance(node, (ast.BinOp, ast.BoolOp)) and type(node.op) in _SWAPS:
        new = _SWAPS[type(node.op)]
        return f"{type(node.op).__name__} changed to {new.__name__}", lambda: setattr(node, "op", new())
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return f"{node.value} changed to {not node.value}", lambda: setattr(node, "value", not node.value)
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return f"{node.value} changed to {node.value + 1}", lambda: setattr(node, "value", node.value + 1)
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and not node.value.startswith("__"):
        return f"string {node.value[:30]!r} altered", lambda: setattr(node, "value", node.value + "X")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return "'not' removed", lambda: setattr(node, "operand", ast.UnaryOp(ast.Not(), node.operand))
    if isinstance(node, ast.Return) and node.value is not None:
        return "return value replaced with None", lambda: setattr(node, "value", ast.Constant(None))
    return None


def _sites(tree: ast.AST) -> list[tuple[ast.AST, tuple]]:
    # Docstrings and error messages can change without the code being wrong, so a miss there means nothing
    ignored = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr):
            ignored.add(id(node.value))
        elif isinstance(node, ast.Raise):
            ignored.update(id(n) for n in ast.walk(node))
    return [(n, m) for n in ast.walk(tree) if id(n) not in ignored and (m := _mutation_for(n))]


def list_mutants(source: str, lines: set[int] | None = None) -> list[tuple[int, str]]:
    """(apply_mutant index, description) per plantable bug, only on the given lines if there are any."""
    return [
        (index, f"line {node.lineno}: {mutation[0]}")
        for index, (node, mutation) in enumerate(_sites(ast.parse(source)))
        if lines is None or node.lineno in lines
    ]


def changed_lines(repo_path: str, rel_path: str) -> set[int] | None:
    """Lines that differ from the last commit, so tests are only judged on what this work changed.

    None means all of them: the file is new, or there's no git history to compare with.
    """
    try:
        repo = git.Repo(repo_path)
        if not repo.git.ls_files("--", rel_path):
            return None
        diff = repo.git.diff("HEAD", "--unified=0", "--", rel_path)
    except (git.GitError, ValueError):
        return None
    lines = set()
    for start, count in re.findall(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", diff, re.M):
        lines.update(range(int(start), int(start) + int(count or 1)))
    return lines


def apply_mutant(source: str, index: int) -> str:
    tree = ast.parse(source)
    _sites(tree)[index][1][1]()
    return ast.unparse(tree)


# ponytail: Python only, a stdlib ast mutator rather than mutmut or Stryker. Add those per language when needed.
# Copies the whole repo minus these folders, so a huge repo is slow to check.
_NOT_COPIED = shutil.ignore_patterns(".git", "node_modules", "__pycache__", ".venv", "venv", ".next", "dist", "build")


async def check_test_strength(repo_path: str, verify_command: str, files: list[str]) -> MutationResult:
    mutants = []  # (rel_path, index, description)
    for rel in files:
        try:
            with open(resolve_in_repo(repo_path, rel)) as f:
                mutants += [(rel, i, d) for i, d in list_mutants(f.read(), changed_lines(repo_path, rel))]
        except (OSError, ValueError, SyntaxError):
            continue
    if not mutants:
        return MutationResult(skipped_reason="the changed code has nothing to mutate")
    if len(mutants) > MAX_MUTANTS:
        mutants = [mutants[i * len(mutants) // MAX_MUTANTS] for i in range(MAX_MUTANTS)]

    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "repo")
        await asyncio.to_thread(shutil.copytree, repo_path, copy, ignore=_NOT_COPIED, symlinks=True)
        if not (await run_verify(verify_command, copy)).passed:
            return MutationResult(skipped_reason="the tests don't pass in a copy of the repo without .git or virtualenvs")

        result = MutationResult()
        deadline = time.monotonic() + MAX_SECONDS
        for rel, index, description in mutants:
            if time.monotonic() > deadline:
                break
            path = resolve_in_repo(copy, rel)
            with open(path) as f:
                original = f.read()
            with open(path, "w") as f:
                f.write(apply_mutant(original, index))
            outcome = await run_verify(verify_command, copy)
            with open(path, "w") as f:
                f.write(original)
            result.tested += 1
            if outcome.passed:
                result.survivors.append(f"{rel} {description}")
            else:
                result.caught += 1
        return result
