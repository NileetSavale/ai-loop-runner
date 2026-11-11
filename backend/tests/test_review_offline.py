from benchmarks.review_offline import UNREADABLE, score, select
from core.fix_review import PROMPTS, code_context, edited_tests, hunk_ranges, parse_verdict, review_prompt

DIFF = """diff --git a/pkg/mod.py b/pkg/mod.py
index 1..2 100644
--- a/pkg/mod.py
+++ b/pkg/mod.py
@@ -100,3 +100,3 @@ def f():
-    return 1
+    return 2
@@ -150,2 +150,3 @@ def g():
+    x = 1
diff --git a/pkg/new.py b/pkg/new.py
new file mode 100644
--- /dev/null
+++ b/pkg/new.py
@@ -0,0 +1 @@
+print()
"""


def run(arm, status="passed", note="", hidden=True, diff=DIFF):
    return {"arm": arm, "agent_status": status, "note": note, "hidden_passed": hidden, "diff": diff}


def test_select_keeps_accepted_cheap_model_fixes_only():
    runs = [
        run("swe-cheap-lean"),
        run("swe-cheap-lean", status="failed"),
        run("swe-cheap-lean", status="failed", note="Stopped: the only failing tests were already failing before any change (x)"),
        run("swe-cascade-notes", note="Solved by claude-haiku-5-5."),
        run("swe-cascade-notes", note="Escalated to claude-sonnet-5-5 after claude-haiku-5-5: failed"),
        run("swe-loop-lean"),
        run("swe-cheap-lean", diff=""),
    ]
    assert [r["arm"] for r in select(runs)] == ["swe-cheap-lean", "swe-cheap-lean", "swe-cascade-notes"]
    assert len(select(runs, everyone=True)) == 5


def test_hunk_ranges_widen_merge_and_skip_new_files():
    assert hunk_ranges(DIFF) == {"pkg/mod.py": [(60, 192)]}


def test_code_context_numbers_original_lines():
    text = code_context(DIFF, lambda path: "\n".join(f"line {n}" for n in range(1, 71)))
    assert "pkg/mod.py, lines 60-192" in text
    assert "   60 line 60" in text and "   70 line 70" in text and "line 71" not in text


def test_parse_verdict_escalates_unless_clearly_accepted():
    assert parse_verdict('{"accept": true, "why": "fine"}') == (True, "fine")
    assert parse_verdict('{"accept": "yes"}')[0] is False
    assert parse_verdict("no json")[0] is False
    reasoned = 'It sets {x} in `f()`.\n```json\n{"accept": false, "why": "misses g"}\n```'
    assert parse_verdict(reasoned) == (False, "misses g")
    quoting_code = '```json\n{"accept": true, "why": "Wraps it in `{\'a\': f(x)}` as the task asks."}\n```'
    assert parse_verdict(quoting_code) == (True, "Wraps it in `{'a': f(x)}` as the task asks.")


def test_score_counts_catches_and_false_escalations_for_reviewer_rule_and_either():
    reviews = [
        {"hidden_passed": False, "accept": False, "edited_tests": [], "cost_usd": 0.01, "why": UNREADABLE},
        {"hidden_passed": False, "accept": True, "edited_tests": ["tests/t.py"], "cost_usd": 0.01},
        {"hidden_passed": True, "accept": False, "edited_tests": [], "cost_usd": 0.01},
        {"hidden_passed": True, "accept": True, "edited_tests": [], "cost_usd": 0.01},
    ]
    reviews = [{"why": "w", **r} for r in reviews]
    assert score(reviews) == {
        "reviewed": 4, "hidden_failures": 2, "hidden_passes": 2, "caught": 1, "wrongly_escalated": 1,
        "rule": {"caught": 1, "wrongly_escalated": 0}, "either": {"caught": 2, "wrongly_escalated": 1},
        "unreadable": {"hidden_failures": 1, "hidden_passes": 0}, "cost_usd": 0.04,
    }


def test_edited_tests_flags_changed_or_deleted_lines_in_existing_tests_only():
    diff = """diff --git a/lib/tests/test_dates.py b/lib/tests/test_dates.py
--- a/lib/tests/test_dates.py
+++ b/lib/tests/test_dates.py
@@ -10,1 +10,1 @@ def test_offset():
-    assert offset == ''
+    assert offset == '1997'
diff --git a/lib/tests/test_more.py b/lib/tests/test_more.py
--- a/lib/tests/test_more.py
+++ b/lib/tests/test_more.py
@@ -5,0 +6,2 @@ def test_x():
+def test_new():
+    assert f()
diff --git a/lib/tests/test_brand_new.py b/lib/tests/test_brand_new.py
new file mode 100644
--- /dev/null
+++ b/lib/tests/test_brand_new.py
@@ -0,0 +1 @@
+def test_y(): pass
diff --git a/lib/dates.py b/lib/dates.py
--- a/lib/dates.py
+++ b/lib/dates.py
@@ -3,1 +3,1 @@
-    level < 2
+    level < 1
"""
    assert edited_tests(diff) == ["lib/tests/test_dates.py"]


def test_v1_prompt_is_unchanged_and_v2_adds_the_sibling_and_test_checks():
    assert "sibling" not in PROMPTS["v1"] and "sibling" in PROMPTS["v2"]
    assert PROMPTS["v2"].startswith(PROMPTS["v1"].split("\n\nReply")[0])
    assert PROMPTS["v2"].rstrip().endswith('"why": "one or two sentences"}')
    assert "existing tests: a/t.py" in review_prompt("task", "diff", "", "", ["a/t.py"])
    assert "changes or deletes" not in review_prompt("task", "diff", "", "")


def _replay(tmp_path, monkeypatch, review_fix, resume=None, cap="9", extra=()):
    """Runs review_offline's main on one saved file of two accepted Haiku fixes, with the reviewer faked."""
    import asyncio, json, sys
    import benchmarks.review_offline as offline
    saved = tmp_path / "runs.json"
    saved.write_text(json.dumps({"runs": [{**run("swe-cheap-lean"), "task": t} for t in ("a", "b")]}))
    monkeypatch.setattr(offline, "review_fix", review_fix)
    monkeypatch.setattr(offline, "RETRY_WAITS_SECONDS", (0, 0))
    monkeypatch.setattr(offline, "load_instance", lambda task: {"problem_statement": "spec"})
    monkeypatch.setattr(offline, "original_file", lambda instance, path: "")
    monkeypatch.setattr(offline, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(offline, "check_caps", lambda worst, models: "fine")
    monkeypatch.setattr(sys, "argv", ["x", str(saved), "--max-total-usd", cap, *extra] + (["--resume", str(resume)] if resume else []))
    asyncio.run(offline.main())
    out = resume or next(p for p in tmp_path.glob("*-review-offline.json"))
    return json.loads(out.read_text())


VERDICT = {"accept": False, "why": "w", "cost_usd": 0.01, "input_tokens": 1, "output_tokens": 1}


def test_replay_retries_a_dropped_review_and_skips_one_that_keeps_failing(tmp_path, monkeypatch):
    calls = []

    async def flaky(spec, diff, read, note, prompt, model, effort):
        calls.append(spec)
        if len(calls) == 1 or read is None:
            raise ConnectionError("dropped")
        return VERDICT

    saved = _replay(tmp_path, monkeypatch, flaky)
    assert sorted(r["task"] for r in saved["runs"]) == ["a", "b"] and saved["summary"]["skipped"] == 0

    async def down(*args):
        raise ConnectionError("dropped")

    for p in tmp_path.glob("*-review-offline.json"):
        p.unlink()
    saved = _replay(tmp_path, monkeypatch, down)
    assert saved["runs"] == [] and saved["summary"]["skipped"] == 2


def test_replay_resumes_a_stopped_file_without_reviewing_its_fixes_again(tmp_path, monkeypatch):
    import json
    stopped = tmp_path / "stopped-review-offline.json"
    stopped.write_text(json.dumps({"runs": [{"task": "a", "arm": "review:swe-cheap-lean", "source_arm": "swe-cheap-lean",
                                             "hidden_passed": True, "edited_tests": [], **VERDICT}]}))
    seen = []

    async def reviewer(spec, diff, read, note, prompt, model, effort):
        seen.append(1)
        return VERDICT

    saved = _replay(tmp_path, monkeypatch, reviewer, resume=stopped)
    assert len(seen) == 1 and sorted(r["task"] for r in saved["runs"]) == ["a", "b"]
    assert saved["summary"]["overall"]["reviewed"] == 2


def test_replay_stops_starting_reviews_at_the_cap_counting_resumed_ones(tmp_path, monkeypatch):
    import json
    import benchmarks.review_offline as offline
    monkeypatch.setattr(offline, "calculate_cost", lambda model, i, o: 1.0)  # each review could cost $1
    stopped = tmp_path / "stopped-review-offline.json"
    stopped.write_text(json.dumps({"runs": [{"task": "a", "arm": "review:swe-cheap-lean", "source_arm": "swe-cheap-lean",
                                             "hidden_passed": True, "edited_tests": [], **VERDICT, "cost_usd": 1.5}]}))

    async def reviewer(*args):
        return VERDICT

    saved = _replay(tmp_path, monkeypatch, reviewer, resume=stopped, cap="2")
    assert [r["task"] for r in saved["runs"]] == ["a"] and saved["summary"]["not_reviewed_at_cap"] == 1
    saved = _replay(tmp_path, monkeypatch, reviewer, resume=stopped, cap="3")
    assert sorted(r["task"] for r in saved["runs"]) == ["a", "b"]


def test_runs_still_going_when_a_batch_stopped_are_not_reviewed():
    from benchmarks.review_offline import finished_runs
    saved = {"runs": [{"task": "a", "arm": "swe-cheap-lean"}, {"task": "b", "arm": "swe-cheap-lean"}],
             "running": [["b", "swe-cheap-lean"]]}
    assert finished_runs(saved) == [{"task": "a", "arm": "swe-cheap-lean"}]


def test_redo_unreadable_reviews_again_only_the_replies_that_werent_cut_off(tmp_path, monkeypatch):
    import json
    from benchmarks.review_offline import UNREADABLE
    stopped = tmp_path / "stopped-review-offline.json"
    common = {"arm": "review:swe-cheap-lean", "source_arm": "swe-cheap-lean", "hidden_passed": True, "edited_tests": []}
    stopped.write_text(json.dumps({"runs": [{**common, "task": "a", **VERDICT, "why": UNREADABLE, "output_tokens": 900},
                                            {**common, "task": "b", **VERDICT, "why": UNREADABLE, "output_tokens": 16000}]}))
    seen = []

    async def reviewer(spec, diff, read, note, prompt, model, effort):
        seen.append(1)
        return VERDICT

    saved = _replay(tmp_path, monkeypatch, reviewer, resume=stopped, extra=["--redo-unreadable"])
    assert len(seen) == 1 and sorted((r["task"], r["why"]) for r in saved["runs"]) == [("a", "w"), ("b", UNREADABLE)]


def test_original_file_falls_back_to_github_at_the_base_commit(monkeypatch):
    """Without the bug's image (deleted after its batch), the file comes from GitHub at the base commit."""
    import io, subprocess, urllib.request
    import benchmarks.review_offline as offline
    monkeypatch.setattr(offline.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1))
    asked = []

    def urlopen(url, timeout):
        asked.append(url)
        return io.BytesIO(b"code\n")
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    instance = {"instance_id": "o__r-1", "repo": "o/r", "base_commit": "abc"}
    assert offline.original_file(instance, "pkg/m.py") == "code\n"
    assert asked == ["https://raw.githubusercontent.com/o/r/abc/pkg/m.py"]


def test_original_file_is_empty_for_a_file_the_fix_creates(monkeypatch):
    import subprocess, urllib.error, urllib.request
    import benchmarks.review_offline as offline
    monkeypatch.setattr(offline.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1))

    def urlopen(url, timeout):
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert offline.original_file({"instance_id": "o__r-1", "repo": "o/r", "base_commit": "abc"}, "new.py") == ""
