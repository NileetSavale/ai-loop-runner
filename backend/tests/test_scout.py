import asyncio
import subprocess
from pathlib import Path
from unittest.mock import patch

import benchmarks.run as bench
from benchmarks.run import BenchTask, RunResult, accepted, changed_functions, run_cascade_arm
from core.loop import _build_guide
from core.scout import SCOUT_SYSTEM_PROMPT, handover, notes_from, run_scout, tried_summary
from core.tools import READ_ONLY_TOOLS, RepoTools
from providers.base import LLMProvider, ToolCall, ToolTurn

NOTES = "## Relevant code\n- a.py::f - adds\n## Relevant tests\n- tests/test_a.py::test_f - checks f\n## Likely cause\nf is off by one."


def _turn(*calls, text=""):
    return ToolTurn(text=text, tool_calls=[ToolCall(f"id{i}", n, a) for i, (n, a) in enumerate(calls)],
                    stop_reason="tool_use" if calls else "end_turn",
                    assistant_message={"role": "assistant", "content": text or "calls"},
                    input_tokens=100, output_tokens=10, cache_read_tokens=0, cache_write_tokens=0)


class _Model(LLMProvider):
    supports_tools = True

    def __init__(self, turns):
        super().__init__("k")
        self.turns, self.systems, self.tools = list(turns), [], []

    async def complete(self, *a, **k):
        raise AssertionError("not used")

    async def complete_with_tools(self, system, messages, tools, model, on_token=None):
        self.systems.append(system)
        self.tools.append([t["name"] for t in tools])
        return self.turns.pop(0)

    def tool_results_message(self, results):
        return {"role": "user", "content": results}


def test_read_only_tools_refuse_changes_and_test_runs(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    tools = RepoTools(str(tmp_path), "true", read_only=True)
    out, err = asyncio.run(tools.run("edit_file", {"path": "a.py", "old_text": "1", "new_text": "2"}))
    assert err and "only read" in out and (tmp_path / "a.py").read_text() == "x = 1\n"
    assert asyncio.run(tools.run("run_tests", {}))[1]
    assert not asyncio.run(tools.run("read_file", {"path": "a.py"}))[1]


def test_scout_reads_only_and_returns_its_notes(tmp_path):
    (tmp_path / "a.py").write_text("def f(x):\n    return x + 2\n")
    model = _Model([_turn(("read_file", {"path": "a.py"})), _turn(text="I looked around.\n\n" + NOTES)])
    with patch("core.agent.get_provider", return_value=model):
        notes, result = asyncio.run(run_scout("f adds wrong", str(tmp_path), "claude-haiku-5-5", 1.0))
    assert notes == NOTES and result.actions == ["read_file a.py"]
    assert model.systems[0] == SCOUT_SYSTEM_PROMPT
    assert set(model.tools[0]) == set(READ_ONLY_TOOLS)


def test_notes_fall_back_to_the_reply_when_the_format_is_ignored():
    assert notes_from("just some text") == "just some text"


def test_handover_passes_findings_and_facts_but_not_a_verdict():
    tried = tried_summary({"a.py": ["f"]}, ["tests/test_a.py::test_f", "tests/test_b.py::test_old"],
                          ["tests/test_a.py::test_f"], "AssertionError: 3 != 2", "I changed the +2 to +1.")
    text = handover("Fix f.", NOTES, tried)
    assert text.startswith("Fix f.") and NOTES in text
    assert "- a.py (f)" in text and "I changed the +2 to +1." in text
    assert "passed before it and failed after: tests/test_a.py::test_f" in text
    assert "Other tests still failing: tests/test_b.py::test_old" in text
    assert "is for you to judge" in text
    assert "earlier attempt" not in handover("Fix f.", NOTES)


def test_changed_functions_reads_hunk_headers():
    diff = ("diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@ def f(x):\n-    return x + 2\n+    return x + 1\n"
            "diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n@@ -5 +5 @@ class Thing:\n-a\n+b\n")
    assert changed_functions(diff) == {"a.py": ["f"], "b.py": ["Thing"]}


def test_attribution_accepts_a_stop_on_old_failures():
    def run(status, note=""):
        return RunResult("t", "a", "m", 1, agent_status=status, note=note)
    assert accepted(run("passed"))
    assert accepted(run("failed", "Stopped: the only failing tests were already failing before any change (x)."))
    assert not accepted(run("failed", "Stopped: the same failure repeated 3 times in a row."))


BASE = "def f(x):\n" + "".join(f"    step{i} = x\n" for i in range(6)) + "    return x + 2\n"


def _repo(tmp_path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text(BASE)
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base"]):
        subprocess.run(["git", *args], cwd=repo, check=True)
    return repo


def _cascade(tmp_path, cheap_status, cheap_note="", tell_tried=False, **options):
    repo = _repo(tmp_path)
    calls, scouts = [], []

    async def fake_loop(task, repo_path, model, budget, result, **settings):
        calls.append((model, task.prompt, (repo_path / "a.py").read_text(), settings.get("coder_effort")))
        result.cost_usd += 0.01
        if len(calls) == 1:
            (repo_path / "a.py").write_text(BASE.replace("x + 2", "x + 1  # cheap attempt"))
            (repo_path / "new.py").write_text("junk\n")
            result.agent_status, result.note = cheap_status, cheap_note
            return {"verify_output": "AssertionError", "failing": ["t::x"], "broken": ["t::x"], "final_text": "tried +1"}
        result.agent_status = "passed"
        return {"verify_output": "", "failing": [], "broken": [], "final_text": ""}

    async def fake_scout(prompt, repo_path, model, budget, effort=None):
        scouts.append((model, effort))

        class R:
            cost_usd, input_tokens, output_tokens, actions = 0.001, 10, 5, ["read_file a.py"]
        return NOTES, R()

    result = RunResult("t", "cascade", "claude-sonnet-5-5", 1)
    with patch.object(bench, "run_loop_arm", fake_loop), patch.object(bench, "run_scout", fake_scout):
        asyncio.run(run_cascade_arm(BenchTask("t", repo, "Fix f.", "true"), repo, "claude-sonnet-5-5", 1.0, result,
                                    tell_tried=tell_tried, **options))
    result.scouts = scouts
    return repo, calls, result


def test_cascade_stops_when_the_cheap_model_solves_it(tmp_path):
    _, calls, result = _cascade(tmp_path, "passed")
    assert [c[0] for c in calls] == [bench.CHEAP_MODEL] and NOTES in calls[0][1]
    assert result.note.startswith("Solved by") and abs(result.cost_usd - 0.011) < 1e-9


def test_cascade_keeps_a_cheap_attempt_stopped_on_old_failures(tmp_path):
    _, calls, result = _cascade(tmp_path, "failed", "Stopped: the only failing tests were already failing before any change (x).")
    assert len(calls) == 1 and result.note.startswith("Solved by")


def test_escalation_undoes_the_cheap_attempt_and_hands_over_notes_only(tmp_path):
    repo, calls, result = _cascade(tmp_path, "failed", "Stopped: the same failure repeated 3 times in a row.")
    model, prompt, code_seen, _ = calls[1]
    assert model == "claude-sonnet-5-5" and code_seen == BASE
    assert not (repo / "new.py").exists()
    assert NOTES in prompt and "earlier attempt" not in prompt and "cheap attempt" not in prompt
    assert result.note.startswith("Escalated") and result.agent_status == "passed"


def test_escalation_can_say_what_was_tried_without_the_diff(tmp_path):
    _, calls, _ = _cascade(tmp_path, "failed", "Stopped: the same failure repeated 3 times in a row.", tell_tried=True)
    prompt = calls[1][1]
    assert "earlier attempt" in prompt and "- a.py (f)" in prompt and "tried +1" in prompt
    assert "passed before it and failed after: t::x" in prompt
    assert "x + 1" not in prompt  # the failed change itself is never passed on


def test_guide_can_leave_the_map_out():
    repo_map = {"nodes": [{"path": "a.py", "symbols": [{"name": "f"}]}], "edges": []}
    focus = [{"path": "a.py", "reason": "matches"}]
    assert "Repo map" in _build_guide(repo_map, focus, None)
    without = _build_guide(repo_map, focus, None, {"t::old"}, include_map=False)
    assert "Repo map" not in without and "Likely places" not in without and "t::old" in without


def test_effort_cascade_escalates_to_more_thinking_on_the_same_model(tmp_path):
    _, calls, result = _cascade(tmp_path, "failed", "Stopped: the same failure repeated 3 times in a row.",
                                cheap_effort="low")
    assert result.scouts == [("claude-sonnet-5-5", "low")]
    assert [(c[0], c[3]) for c in calls] == [("claude-sonnet-5-5", "low"), ("claude-sonnet-5-5", None)]
    assert "at low effort" in result.note


def test_effort_reaches_the_provider_only_when_set(tmp_path):
    seen = []

    class Model(_Model):
        async def complete_with_tools(self, system, messages, tools, model, on_token=None, **kw):
            seen.append(kw)
            return await super().complete_with_tools(system, messages, tools, model, on_token)

    (tmp_path / "a.py").write_text("x = 1\n")
    for effort in ("low", None):
        with patch("core.agent.get_provider", return_value=Model([_turn(text=NOTES)])):
            asyncio.run(run_scout("f", str(tmp_path), "claude-sonnet-5-5", 1.0, effort=effort))
    assert seen == [{"effort": "low"}, {}]
