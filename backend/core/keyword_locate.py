"""Find the code a task is about by keyword search over every function, with no LLM calls.

Each function and class is a document; the task text is the query (BM25). Files are ranked by their best function.
Offline on 60 SWE-bench Verified bugs (benchmarks/localize_offline.py), a file the official fix changed was in the
top 5 for 77% of bugs, against 2% for locate_issue's name matching.
"""
import ast
import math
import os
import re
from collections import Counter

from core.edits import is_test_path
from core.tools import SKIPPED_DIRS

MAX_PARSED_BYTES = 500_000
FUNCTIONS_PER_FILE = 3
_CODE = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
_STOP = {
    "the", "and", "for", "with", "this", "that", "from", "not", "but", "are", "was", "has", "have", "can", "will",
    "would", "should", "could", "when", "then", "than", "into", "use", "used", "using", "def", "self", "return",
    "import", "class", "none", "true", "false", "if", "else", "elif", "in", "is", "of", "to", "it", "be", "as", "or",
    "on", "an", "at", "by", "we", "you", "my", "so", "do", "does", "there", "which", "what", "also", "one", "get",
}


def tokens(text: str) -> list[str]:
    """Identifiers split at underscores and case changes, so get_unitFormat matches 'unit' and 'format'."""
    out = []
    for ident in _IDENT.findall(text):
        for part in ident.split("_"):
            out += [w.lower() for w in _CAMEL.findall(part)]
    return [w for w in out if len(w) > 1 and w not in _STOP]


class BM25:
    def __init__(self, docs: dict[str, list[str]], k1: float = 1.2, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tf = {d: Counter(t) for d, t in docs.items()}
        self.len = {d: len(t) for d, t in docs.items()}
        self.avg = sum(self.len.values()) / max(len(docs), 1)
        df = Counter(w for c in self.tf.values() for w in c)
        n = len(docs)
        self.idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}

    def scores(self, query: list[str]) -> dict[str, float]:
        q = Counter(query)
        out = {}
        for d, tf in self.tf.items():
            s = 0.0
            norm = self.k1 * (1 - self.b + self.b * self.len[d] / self.avg)
            for w, qn in q.items():
                if w in tf:
                    s += self.idf[w] * tf[w] * (self.k1 + 1) / (tf[w] + norm)
            if s:
                out[d] = s
        return out


def functions(path: str, source: str) -> list[dict]:
    """Every function and class, nested ones included, as path::Qual.name with its line span and text."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    lines = source.splitlines()
    found = []

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}{child.name}"
                end = getattr(child, "end_lineno", child.lineno)
                found.append({"id": f"{path}::{name}", "path": path, "start": child.lineno, "end": end,
                              "text": "\n".join(lines[child.lineno - 1:end]), "name": child.name})
                visit(child, f"{name}.")

    visit(tree, "")
    return found


def code_sources(repo_path: str) -> dict[str, str]:
    """Every non-test code file, with no cap on how many (the repo map stops at 400)."""
    root = os.path.realpath(repo_path)
    sources = {}
    for folder, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIPPED_DIRS and not d.startswith("."))
        for name in sorted(names):
            rel = os.path.relpath(os.path.join(folder, name), root)
            if not name.endswith(_CODE) or is_test_path(rel):
                continue
            try:
                if os.path.getsize(os.path.join(root, rel)) <= MAX_PARSED_BYTES:
                    with open(os.path.join(root, rel), errors="replace") as f:
                        sources[rel] = f.read()
            except OSError:
                pass
    return sources


def rank_functions(sources: dict[str, str], task: str) -> list[str]:
    """Function ids, best first. A file with no parsed functions (or not Python) counts as one document."""
    docs = {}
    for path, source in sources.items():
        found = functions(path, source) if path.endswith(".py") else []
        for f in found:
            docs[f["id"]] = tokens(f["name"]) * 3 + tokens(f["text"])
        if not found:
            docs[f"{path}::"] = tokens(path) * 3 + tokens(source)
    scores = BM25(docs).scores(tokens(task))
    return [d for d, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def locate_by_keywords(repo_path: str, task: str, limit: int) -> list[dict]:
    """The best files, each with the functions that matched, in locate_issue's {"path", "reason"} shape."""
    by_file: dict[str, list[str]] = {}
    for fid in rank_functions(code_sources(repo_path), task):
        path, name = fid.split("::", 1)
        if path not in by_file:
            if len(by_file) == limit:
                continue
            by_file[path] = []
        if name and len(by_file[path]) < FUNCTIONS_PER_FILE:
            by_file[path].append(name)
    return [{"path": p, "reason": f"task words match {', '.join(names)}" if names else "task words match"}
            for p, names in by_file.items()]
