from benchmarks.review_offline import code_context, hunk_ranges, parse_verdict, score, select

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
    text = code_context(DIFF, read=lambda image, path: "\n".join(f"line {n}" for n in range(1, 71)))
    assert "pkg/mod.py, lines 60-192" in text
    assert "   60 line 60" in text and "   70 line 70" in text and "line 71" not in text


def test_parse_verdict_escalates_unless_clearly_accepted():
    assert parse_verdict('{"accept": true, "why": "fine"}') == (True, "fine")
    assert parse_verdict('{"accept": "yes"}')[0] is False
    assert parse_verdict("no json")[0] is False
    reasoned = 'It sets {x} in `f()`.\n```json\n{"accept": false, "why": "misses g"}\n```'
    assert parse_verdict(reasoned) == (False, "misses g")


def test_score_counts_catches_and_false_escalations():
    reviews = [
        {"hidden_passed": False, "accept": False, "cost_usd": 0.01},
        {"hidden_passed": False, "accept": True, "cost_usd": 0.01},
        {"hidden_passed": True, "accept": False, "cost_usd": 0.01},
        {"hidden_passed": True, "accept": True, "cost_usd": 0.01},
    ]
    assert score(reviews) == {"reviewed": 4, "hidden_failures": 2, "caught": 1, "hidden_passes": 2,
                              "wrongly_escalated": 1, "cost_usd": 0.04}
