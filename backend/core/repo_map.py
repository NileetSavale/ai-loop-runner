"""A map of a repo, computed from the code itself with no LLM calls.

The website draws it. The agent gets a compact version, plus the files the failing tests point at, so it spends
fewer tokens finding its way around.
"""
import ast
import os
import re

from core.edits import is_test_path
from core.tools import SKIPPED_DIRS

MAX_FILES = 400
MAX_PARSED_BYTES = 500_000
MAX_FOCUS_FILES = 6
MAX_PROMPT_MAP_CHARS = 800  # measured: a 3,000 character map gave up most of the saving
_CODE = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs")
_JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", "/index.ts", "/index.tsx", "/index.js")
_JS_IMPORT = re.compile(r"""(?:from\s+|import\s*\(?\s*|require\(\s*)['"]([^'"]+)['"]""")
_JS_SYMBOL = re.compile(r"^export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|interface|type)\s+(\w+)", re.M)
_TRACE_PATH = re.compile(r"([\w./\\-]+\.(?:py|tsx?|jsx?|mjs))(?::(\d+)|\", line (\d+))?")
_STOP_WORDS = {
    "that", "this", "with", "from", "have", "should", "would", "could", "make", "when", "then", "than", "them", "there",
    "file", "files", "code", "test", "tests", "pass", "fail", "failing", "fix", "issue", "problem", "project", "repo",
    "find", "need", "needed", "what", "where", "which", "does", "work", "working", "implement", "yourself", "finish",
}


def _python_details(source: str) -> tuple[list[dict], list[tuple[str, int]]]:
    tree = ast.parse(source)
    symbols = [
        {"name": n.name, "line": n.lineno}
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    imports = []  # (module, relative level)
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imports += [(a.name, 0) for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            base = n.module or ""
            imports.append((base, n.level))
            imports += [(f"{base}.{a.name}" if base else a.name, n.level) for a in n.names]
    return symbols, imports


def _resolve_python(importer: str, module: str, level: int, files: set[str]) -> str | None:
    folder = os.path.dirname(importer)
    path = module.replace(".", "/")
    if level:
        for _ in range(level - 1):
            folder = os.path.dirname(folder)
        roots = [folder]
    else:
        # Absolute imports resolve from wherever the code runs, so try each folder from here up to the repo root
        roots = []
        while True:
            roots.append(folder)
            if not folder:
                break
            folder = os.path.dirname(folder)
    for root in roots:
        for candidate in (f"{path}.py", f"{path}/__init__.py"):
            full = os.path.normpath(os.path.join(root, candidate))
            if full in files:
                return full
    return None


def _resolve_js(importer: str, target: str, files: set[str]) -> str | None:
    folder = os.path.dirname(importer)
    if target.startswith("."):
        roots = [folder]
    elif target.startswith("@/"):  # the usual alias for the project root
        target, roots = target[2:], []
        while True:
            roots.append(folder)
            if not folder:
                break
            folder = os.path.dirname(folder)
    else:
        return None  # a package
    for root in roots:
        base = os.path.normpath(os.path.join(root, target))
        for candidate in (base, *(base + e for e in _JS_EXTENSIONS)):
            if candidate in files:
                return candidate
    return None


def _group_layers(nodes: list[dict], edges: list[dict]) -> dict[str, int]:
    """Column for each folder, so that code sits to the left of what it depends on."""
    group_of = {n["path"]: n["group"] for n in nodes}
    groups = sorted(set(group_of.values()))
    links = {(group_of[e["from"]], group_of[e["to"]]) for e in edges} - {(g, g) for g in groups}
    layer = dict.fromkeys(groups, 0)
    for _ in groups:  # at most this many passes, which also ends the loop on circular imports
        for source, target in sorted(links):
            layer[target] = max(layer[target], layer[source] + 1)
    used = sorted(set(layer.values()))
    return {g: used.index(v) for g, v in layer.items()}


def build_repo_map(repo_path: str) -> dict:
    root = os.path.realpath(repo_path)
    paths = []
    for folder, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIPPED_DIRS and not d.startswith("."))
        paths += [os.path.relpath(os.path.join(folder, n), root) for n in sorted(names) if n.endswith(_CODE)]
    truncated = len(paths) > MAX_FILES
    paths = sorted(paths)[:MAX_FILES]
    known = set(paths)

    nodes, edges = [], set()
    for path in paths:
        full = os.path.join(root, path)
        symbols = []
        try:
            size = os.path.getsize(full)
            with open(full) as f:
                source = f.read() if size <= MAX_PARSED_BYTES else ""
        except (OSError, UnicodeDecodeError):
            size, source = 0, ""
        if path.endswith(".py"):
            try:
                symbols, imports = _python_details(source)
            except (SyntaxError, ValueError):
                imports = []  # code the agent is about to fix can be broken: keep the file on the map
            targets = {_resolve_python(path, module, level, known) for module, level in imports}
        else:
            symbols = [
                {"name": m.group(1), "line": source.count("\n", 0, m.start()) + 1} for m in _JS_SYMBOL.finditer(source)
            ]
            targets = {_resolve_js(path, m.group(1), known) for m in _JS_IMPORT.finditer(source)}
        edges |= {(path, t) for t in targets if t and t != path}
        nodes.append({
            "path": path,
            "group": os.path.dirname(path) or ".",
            "is_test": is_test_path(path),
            "size": size,
            "symbols": symbols,
        })

    edge_list = [{"from": a, "to": b} for a, b in sorted(edges)]
    return {"nodes": nodes, "edges": edge_list, "layers": _group_layers(nodes, edge_list), "truncated": truncated}


def locate_issue(repo_map: dict, spec: str, verify_output: str | None, selected: list[str], root: str = "") -> list[dict]:
    """The files most likely involved, best first, each with the reason it was picked.

    This is a starting point for the agent rather than an answer, which is why it comes with its reasons.
    """
    nodes = {n["path"]: n for n in repo_map["nodes"]}
    found: dict[str, str] = {}

    def add(path: str, reason: str):
        if path in nodes:
            found.setdefault(path, reason)

    for path in selected:
        add(path, "you selected this")

    code_hits, test_hits = [], []
    real_root = os.path.realpath(root) if root else ""
    for match in _TRACE_PATH.finditer(verify_output or ""):
        path = match.group(1).replace("\\", "/")
        if real_root and path.startswith(real_root):
            path = os.path.relpath(path, real_root)
        path = os.path.normpath(path)
        if path not in nodes:  # a library file, or a path in a message
            path = next((p for p in nodes if p.endswith(f"/{path}")), path)
        if path in nodes:
            line = match.group(2) or match.group(3)
            (test_hits if nodes[path]["is_test"] else code_hits).append((path, line))

    # Where the trace points in real code comes first. Tests usually just fail at an assert, so what they import is next.
    for path, line in code_hits:
        add(path, f"in the test failure at line {line}" if line else "named in the test failure")
    for path, _ in test_hits:
        for edge in repo_map["edges"]:
            if edge["from"] == path and not nodes[edge["to"]]["is_test"]:
                add(edge["to"], f"imported by failing test {path}")
    for path, line in test_hits:
        add(path, f"failing test, line {line}" if line else "failing test")

    words = {w for w in re.findall(r"[a-z_]{4,}", spec.lower()) if w not in _STOP_WORDS}
    for path, node in nodes.items():
        if node["is_test"]:
            continue  # a task about agents doesn't make every test with "agent" in its name a suspect
        names = {os.path.splitext(os.path.basename(path))[0].lower(), *(s["name"].lower() for s in node["symbols"])}
        for word in sorted(words):
            hit = next((n for n in sorted(names) if word in n), None)
            if hit:
                add(path, f"matches '{word}' in the task")
                break

    return [{"path": p, "reason": r} for p, r in list(found.items())[:MAX_FOCUS_FILES]]


def map_for_prompt(repo_map: dict, focus: list[dict]) -> str:
    """A compact outline for the agent, most relevant files first, within a fixed size."""
    nodes = {n["path"]: n for n in repo_map["nodes"]}
    focus_paths = [f["path"] for f in focus]
    lines = []
    for path in focus_paths + [p for p in nodes if p not in focus_paths]:
        symbols = ", ".join(s["name"] for s in nodes[path]["symbols"][:8]) if path in nodes else ""  # past the cap
        lines.append(f"{path}: {symbols}" if symbols else path)
    outline, used = [], 0
    for line in lines:
        if used + len(line) > MAX_PROMPT_MAP_CHARS:
            outline.append(f"(+{len(lines) - len(outline)} more files, use list_files to see them)")
            break
        outline.append(line)
        used += len(line) + 1
    return "\n".join(outline)
