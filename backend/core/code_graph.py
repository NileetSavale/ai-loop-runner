"""A graph of the repo the coder can query, with what earlier tasks learned attached to it.

Nodes are Python functions and classes. Edges computed from the code each task, so always current and free: calls
(a call to a name, matched to definitions of that name in the same file or the files it imports) and tests (test
functions that call it). Edges learned from agents: files earlier tasks read together. Notes on nodes come from
core/repo_memory.py, shown only while the code they describe is unchanged.

The coder pulls from it with the lookup_code tool rather than having it pushed into the prompt, so a bigger repo
doesn't mean a bigger prompt. Finding where to start is left to keyword search (core/keyword_locate.py), which beat
an import graph at that offline.
"""
import ast
import os
import textwrap
from collections import defaultdict

from core.edits import is_test_path
from core.keyword_locate import BM25, functions, tokens
from core.repo_map import _python_details, _resolve_python
from core.repo_memory import RepoMemory, code_hash
from core.tools import SKIPPED_DIRS

MAX_PARSED_BYTES = 500_000
MAX_MATCHES = 4
MAX_NEIGHBOURS = 8
MAX_LOOKUP_CHARS = 3000


def _called_names(tree: ast.Module) -> set[str]:
    """Names called in a function or class, leaving out the functions and classes inside it: they're nodes too."""
    names, todo = set(), list(ast.iter_child_nodes(tree.body[0])) if tree.body else []
    while todo:
        n = todo.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        todo += ast.iter_child_nodes(n)
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                names.add(f.id)
            elif isinstance(f, ast.Attribute):
                names.add(f.attr)
    return names


class CodeGraph:
    def __init__(self, repo_path: str, memory: RepoMemory | None = None):
        self.repo_path = repo_path
        self.memory = memory
        self.sources: dict[str, str] = {}
        root = os.path.realpath(repo_path)
        for folder, dirs, names in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in SKIPPED_DIRS and not d.startswith("."))
            for name in sorted(names):
                full = os.path.join(folder, name)
                if name.endswith(".py") and os.path.getsize(full) <= MAX_PARSED_BYTES:
                    try:
                        with open(full, errors="replace") as f:
                            self.sources[os.path.relpath(full, root)] = f.read()
                    except OSError:
                        pass
        files = set(self.sources)
        self.nodes: dict[str, dict] = {}  # id -> {"path", "name", "start", "end", "text"}
        by_name: dict[str, list[str]] = defaultdict(list)
        imports: dict[str, set[str]] = {}
        trees = {}
        for path, source in self.sources.items():
            try:
                trees[path] = ast.parse(source)
                _, mods = _python_details(source)
            except (SyntaxError, ValueError):
                continue
            imports[path] = {r for m, lvl in mods if (r := _resolve_python(path, m, lvl, files))}
            for f in functions(path, source):
                self.nodes[f["id"]] = f
                by_name[f["name"]].append(f["id"])
        self.callees: dict[str, set[str]] = defaultdict(set)
        self.callers: dict[str, set[str]] = defaultdict(set)
        self.tests: dict[str, set[str]] = defaultdict(set)
        for fid, f in self.nodes.items():
            try:
                body = ast.parse(textwrap.dedent(f["text"]))
            except (SyntaxError, ValueError):
                continue
            near = {f["path"]} | imports.get(f["path"], set())
            test = is_test_path(f["path"])
            for name in _called_names(body) - {f["name"]}:
                for target in by_name.get(name, ()):
                    if target != fid and self.nodes[target]["path"] in near and not is_test_path(self.nodes[target]["path"]):
                        (self.tests if test else self.callers)[target].add(fid)
                        if not test:
                            self.callees[fid].add(target)
        self._index = None

    def _search(self, query: str) -> list[str]:
        if self._index is None:
            self._index = BM25({i: tokens(n["name"]) * 3 + tokens(n["text"]) for i, n in self.nodes.items()
                                if not is_test_path(n["path"])})
        scores = self._index.scores(tokens(query))
        return sorted(scores, key=lambda i: (-scores[i], i))[:MAX_MATCHES]

    def find(self, query: str) -> list[str]:
        """Node ids for a query: an exact id, a path, a qualified or plain name, else keyword search."""
        query = query.strip().strip("`")
        if query in self.nodes:
            return [query]
        if query in self.sources:
            return [i for i in self.nodes if i.startswith(f"{query}::") and "." not in i.split("::")[1]][:MAX_MATCHES * 3]
        named = [i for i in self.nodes if i.split("::")[1] == query or i.split("::")[1].endswith(f".{query}")]
        return sorted(named, key=lambda i: (is_test_path(i), i))[:MAX_MATCHES] if named else self._search(query)

    def _note(self, path: str, name: str) -> str | None:
        if not self.memory:
            return None
        entry = self.memory.notes.get(f"{path}::{name}")
        if entry and code_hash(self.sources.get(path), path, name) == entry["hash"]:
            return entry["note"]
        return None

    def lookup(self, query: str) -> str:
        found = self.find(query)
        if not found:
            return f"Nothing in the code graph matches {query!r}. Try search_code."
        parts = []
        for fid in found:
            n = self.nodes[fid]
            lines = [f"{fid} (lines {n['start']}-{n['end']})"]
            if note := self._note(n["path"], fid.split("::")[1]):
                lines.append(f"  teammate's note: {note}")
            for label, ids in (("calls", self.callees[fid]), ("called by", self.callers[fid]), ("tested by", self.tests[fid])):
                if ids:
                    shown = sorted(ids)[:MAX_NEIGHBOURS]
                    more = f" (+{len(ids) - len(shown)} more)" if len(ids) > len(shown) else ""
                    lines.append(f"  {label}: {', '.join(shown)}{more}")
            if self.memory and (together := self.memory.read_together(n["path"])):
                lines.append(f"  earlier tasks that read this file also read: {', '.join(together)}")
            if file_note := self._note(n["path"], ""):
                lines.append(f"  note on {n['path']}: {file_note}")
            parts.append("\n".join(lines))
        text = "\n\n".join(parts)
        return text if len(text) <= MAX_LOOKUP_CHARS else text[:MAX_LOOKUP_CHARS] + "\n(cut: ask for one name)"
