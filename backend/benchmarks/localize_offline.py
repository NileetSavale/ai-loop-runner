"""Score ways of finding the code a bug is in, with no model calls, against the files the official fix changed.

    cd backend && python -m benchmarks.localize_offline /Volumes/LoopRunnerDocker/swe/labels.jsonl --out results/x.json

For each bug: copy the buggy code out of its SWE-bench image, rank the repo's non-test Python files (and functions)
from the issue text alone, and check whether the official fix's files and functions are near the top. Tests that
fail before any change aren't used, since most SWE-bench bugs have none (the failing test is hidden).
"""
import argparse
import json
import re
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import core.repo_map as repo_map
from benchmarks.swe_run import checkout, load_instance
from core.edits import is_test_path
from core.keyword_locate import BM25, functions, locate_by_keywords, tokens

TOP_K = (1, 3, 5, 10)
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@", re.M)


def gold_targets(fix: str, sources: dict[str, str]) -> tuple[set[str], set[str]]:
    """Files the official fix changes, and the innermost functions or classes around its changed lines."""
    files, funcs = set(), set()
    for block in re.split(r"^diff --git ", fix, flags=re.M)[1:]:
        path = re.match(r"a/(\S+)", block).group(1)
        files.add(path)
        spans = functions(path, sources.get(path, ""))
        for m in _HUNK.finditer(block):
            start, count = int(m.group(1)), int(m.group(2) or 1)
            body = block[m.end():].split("\n@@", 1)[0].splitlines()[1:]
            line = start
            for row in body:
                if row.startswith(("-", "+")):
                    inside = [s for s in spans if s["start"] <= line <= s["end"]]
                    if inside:
                        funcs.add(min(inside, key=lambda s: s["end"] - s["start"])["id"])
                if not row.startswith("+"):
                    line += 1
    return files, funcs


def ranked(scores: dict[str, float]) -> list[str]:
    return [d for d, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def personalized_pagerank(nodes: list[str], edges: list[tuple[str, str]], seed: dict[str, float],
                          restart: float = 0.3, steps: int = 30) -> dict[str, float]:
    """Random walk over imports in both directions that keeps jumping back to the seed files."""
    total = sum(seed.values())
    if not total:
        return {}
    seed = {n: s / total for n, s in seed.items()}
    nbrs = defaultdict(list)
    for a, b in edges:
        nbrs[a].append(b)
        nbrs[b].append(a)
    rank = dict(seed)
    for _ in range(steps):
        nxt = {n: restart * s for n, s in seed.items()}
        for n, r in rank.items():
            out = nbrs.get(n)
            if out:
                share = (1 - restart) * r / len(out)
                for m in out:
                    nxt[m] = nxt.get(m, 0.0) + share
            else:
                nxt[n] = nxt.get(n, 0.0) + (1 - restart) * r
        rank = nxt
    return rank


def fuse(*rankings: list[str], k: int = 60) -> list[str]:
    """Reciprocal rank fusion: each list adds 1/(k + position) to every item it ranks."""
    score = defaultdict(float)
    for r in rankings:
        for i, d in enumerate(r):
            score[d] += 1 / (k + i + 1)
    return ranked(score)


def localize(repo: Path, issue: str) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, float], dict]:
    """File rankings and function rankings per method, seconds per method, and the sources read."""
    sources = {}
    for p in sorted(repo.rglob("*.py")):
        rel = str(p.relative_to(repo))
        if any(part.startswith(".") or part in repo_map.SKIPPED_DIRS for part in p.relative_to(repo).parts[:-1]):
            continue
        try:
            sources[rel] = p.read_text(errors="replace")
        except OSError:
            pass
    code = {p: s for p, s in sources.items() if not is_test_path(p)}
    query = tokens(issue)
    files, funcs, seconds = {}, {}, {}

    def timed(name, fn):
        started = time.perf_counter()
        result = fn()
        seconds[name] = round(time.perf_counter() - started, 2)
        return result

    def current(max_files):
        with patch.object(repo_map, "MAX_FILES", max_files), patch.object(repo_map, "MAX_FOCUS_FILES", 10):
            graph = repo_map.build_repo_map(str(repo))
            return [f["path"] for f in repo_map.locate_issue(graph, issue, None, [], str(repo))], graph

    files["current map (400 files)"], _ = timed("current map (400 files)", lambda: current(repo_map.MAX_FILES))
    files["current map (all files)"], graph = timed("current map (all files)", lambda: current(10**6))

    bm25_files = timed("bm25 files", lambda: BM25({p: tokens(p) * 3 + tokens(s) for p, s in code.items()}).scores(query))
    files["bm25 files"] = ranked(bm25_files)

    all_funcs = [f for p, s in code.items() for f in functions(p, s)]
    bm25_funcs = timed("bm25 functions", lambda: BM25(
        {f["id"]: tokens(f["name"]) * 3 + tokens(f["text"]) for f in all_funcs}).scores(query))
    funcs["bm25 functions"] = ranked(bm25_funcs)
    by_file = {}
    for fid in funcs["bm25 functions"]:
        by_file.setdefault(fid.split("::")[0], None)
    files["bm25 functions -> files"] = list(by_file)

    trace = []
    for m in repo_map._TRACE_PATH.finditer(issue):
        path = m.group(1).replace("\\", "/").lstrip("./")
        hit = path if path in code else next((p for p in code if p.endswith("/" + path)), None)
        if hit and hit not in trace:
            trace.append(hit)
    files["traceback, then bm25"] = trace + [p for p in files["bm25 files"] if p not in trace]

    nodes = [n["path"] for n in graph["nodes"]]
    edges = [(e["from"], e["to"]) for e in graph["edges"]]
    top = files["bm25 files"][:20]
    seed = {p: bm25_files[p] for p in top}
    for p in trace:
        seed[p] = seed.get(p, 0) + max(bm25_files.values(), default=1)
    ppr = timed("pagerank", lambda: personalized_pagerank(nodes, edges, seed))
    files["pagerank (bm25 + traceback seeds)"] = [p for p in ranked(ppr) if p in code]
    # The loop's own locator (core/keyword_locate.py), which also reads non-Python files: should match the line above
    files["keyword locator (loop)"] = [f["path"] for f in timed("keyword locator (loop)",
                                                                  lambda: locate_by_keywords(str(repo), issue, 10))]
    files["fusion"] = fuse(files["traceback, then bm25"], files["bm25 functions -> files"],
                           files["pagerank (bm25 + traceback seeds)"])
    return files, funcs, seconds, sources


def hit_at(ranking: list[str], gold: set[str], k: int) -> bool:
    return bool(gold & set(ranking[:k]))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("labels", help="labels.jsonl; its instance ids are the bugs scored")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    ids = [json.loads(line)["instance_id"] for line in open(args.labels)]
    rows = []
    for n, instance_id in enumerate(ids, 1):
        instance = load_instance(instance_id)
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            checkout(f"swebench/sweb.eval.x86_64.{instance_id.replace('__', '_1776_').lower()}:latest", repo)
            files, funcs, seconds, sources = localize(repo, instance["problem_statement"])
        gold_files, gold_funcs = gold_targets(instance["patch"], sources)
        row = {"instance_id": instance_id, "gold_files": sorted(gold_files), "gold_functions": sorted(gold_funcs),
               "code_files": sum(1 for p in sources if not is_test_path(p)), "seconds": seconds,
               "files": {m: {"top10": r[:10], **{f"hit@{k}": hit_at(r, gold_files, k) for k in TOP_K}}
                         for m, r in files.items()},
               "functions": {m: {"top10": r[:10], **{f"hit@{k}": hit_at(r, gold_funcs, k) for k in TOP_K}}
                             for m, r in funcs.items()}}
        rows.append(row)
        # "runs" stays empty: the overall spending cap sums cost over every results file's runs, and this costs nothing
        args.out.write_text(json.dumps({"settings": {"kind": "offline localization, no model calls"}, "runs": [],
                                        "bugs": rows}, indent=1))
        best = ", ".join(f"{m}: {'yes' if v['hit@5'] else 'no'}" for m, v in row["files"].items())
        print(f"[{n}/{len(ids)}] {instance_id} ({row['code_files']} files) top 5 has a fixed file? {best}", flush=True)
    print(summary(rows))


def summary(rows: list[dict]) -> str:
    out = [f"{len(rows)} bugs. Share where a file (or function) the official fix changed is in the top k:", ""]
    for level in ("files", "functions"):
        methods = list(rows[0][level])
        out.append(f"{level:<36}" + "".join(f"{'top ' + str(k):>8}" for k in TOP_K))
        for m in methods:
            out.append(f"{m:<36}" + "".join(f"{sum(r[level][m][f'hit@{k}'] for r in rows) / len(rows):>8.0%}" for k in TOP_K))
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    main()
