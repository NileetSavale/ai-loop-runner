from benchmarks.review_offline import score, select
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


def test_score_counts_catches_and_false_escalations_for_reviewer_rule_and_either():
    reviews = [
        {"hidden_passed": False, "accept": False, "edited_tests": [], "cost_usd": 0.01},
        {"hidden_passed": False, "accept": True, "edited_tests": ["tests/t.py"], "cost_usd": 0.01},
        {"hidden_passed": True, "accept": False, "edited_tests": [], "cost_usd": 0.01},
        {"hidden_passed": True, "accept": True, "edited_tests": [], "cost_usd": 0.01},
    ]
    assert score(reviews) == {
        "reviewed": 4, "hidden_failures": 2, "hidden_passes": 2, "caught": 1, "wrongly_escalated": 1,
        "rule": {"caught": 1, "wrongly_escalated": 0}, "either": {"caught": 2, "wrongly_escalated": 1},
        "cost_usd": 0.04,
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
