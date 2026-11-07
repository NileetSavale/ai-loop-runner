"""The benchmark harness, with a scripted model so no tokens are spent."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import json
import shutil
from functools import partial
from unittest.mock import patch

import pytest

from benchmarks.run import (
    BenchTask, RunResult, apply_claude_output, changed_lines, claude_code_command, format_summary, format_table,
    hidden_tests_pass, load_tasks, prepare_repo, run_benchmark, run_loop_arm, run_one, spent_so_far, check_overall_cap, summarize,
)
from benchmarks.swe_run import test_command as swe_test_command, verify_command
from core.agent import run_agent
from core.verifier import run_verify
from providers.base import LLMProvider, LLMResult
from test_tool_agent import ScriptedModel, turn

MODEL = "claude-sonnet-5-5"
TASKS = load_tasks()
OFF_BY_ONE = next(t for t in TASKS if t.name == "off_by_one")
FIXED = (OFF_BY_ONE.path / "solution" / "pagination.py").read_text()
# Passes the one visible test, and nothing else
GAMED = "def paginate(items, page, per_page):\n    return items[:per_page]\n"


def _run(model: ScriptedModel, budget: float = 1.0) -> RunResult:
    async def go():
        with patch("core.agent.get_provider", return_value=model):
            results, _ = await run_benchmark([OFF_BY_ONE], "loop", MODEL, 1, budget, budget)
        return results[0]
    return asyncio.run(go())


def _writes(content: str) -> ScriptedModel:
    return ScriptedModel([turn(("write_file", {"path": "pagination.py", "content": content})), turn(text="Done.")])


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t.name)
def test_every_task_starts_broken_and_its_solution_passes(task: BenchTask, tmp_path):
    """A task that passes untouched, or that nobody can solve, would quietly make the numbers meaningless."""
    repo = tmp_path / "repo"
    prepare_repo(task, repo)

    async def check():
        return (await run_verify(task.verify, str(repo))).passed, await hidden_tests_pass(task, repo)

    # A demo app can pass its own tests on purpose, so that only the hidden checks show what's wrong
    healthy_looking = json.loads((task.path / "task.json").read_text()).get("visible_tests_pass_at_start", False)
    assert asyncio.run(check()) == (healthy_looking, False)
    shutil.copytree(task.path / "solution", repo, dirs_exist_ok=True)
    assert asyncio.run(check()) == (True, True)


def test_a_correct_fix_is_a_success():
    result = _run(_writes(FIXED))
    assert (result.visible_passed, result.hidden_passed, result.agent_status) == (True, True, "passed")
    assert (result.changed_code_lines, result.changed_test_lines) == (4, 0)  # 3 lines added and 1 removed
    assert (result.attempts, result.tool_calls) == (1, 1)
    assert result.tool_result_chars > 0


def test_passing_only_the_visible_tests_is_a_failure():
    result = _run(_writes(GAMED))
    assert (result.visible_passed, result.hidden_passed, result.agent_status) == (True, False, "passed")


def test_logged_usage_adds_up_to_the_session_totals():
    result = _run(ScriptedModel([
        turn(("write_file", {"path": "pagination.py", "content": FIXED}), in_tokens=1000, out_tokens=50, cache_write=2000),
        turn(text="Done.", in_tokens=10, out_tokens=5, cache_read=2500),
    ]))
    assert result.usage_matches is True
    assert (result.input_tokens, result.output_tokens, result.cache_read_tokens, result.cache_write_tokens) == (1010, 55, 2500, 2000)
    assert result.cost_usd > 0


def test_the_run_budget_stops_the_agent():
    model = ScriptedModel([
        turn(("read_file", {"path": "pagination.py"}), out_tokens=1_000_000),  # $10 on one turn
        turn(text="Should never be reached."),
    ])
    result = _run(model, budget=1.0)
    assert result.hidden_passed is False and result.agent_status == "failed"
    assert result.attempts == 1 and len(model.turns) == 1


def test_the_total_budget_stops_runs_it_cant_cover():
    async def fake_arm(task, repo, model, budget, result):
        result.cost_usd = 0.5

    # After $1.00 spent, another run could cost up to $1.00, which the $1.50 total can't cover
    results, skipped = asyncio.run(run_benchmark([OFF_BY_ONE], "loop", MODEL, 4, 1.0, 1.5, arm_fn=fake_arm))
    assert (len(results), skipped) == (2, 2)


def test_changes_count_whether_or_not_they_were_committed(tmp_path):
    repo = tmp_path / "repo"
    base = prepare_repo(OFF_BY_ONE, repo)
    assert changed_lines(repo, base) == (0, 0)
    (repo / "pagination.py").write_text(FIXED)
    (repo / "__pycache__").mkdir()
    (repo / "__pycache__" / "x.pyc").write_bytes(b"\0")
    (repo / "tests" / "test_extra.py").write_text("x = 1\ny = 2\n")
    assert changed_lines(repo, base) == (4, 2)


def test_one_shot_providers_log_usage_too():
    class OneShot(LLMProvider):
        async def complete(self, system, prompt, model, on_token=None):
            return LLMResult(text="", input_tokens=7, output_tokens=3)

    events = []

    async def on_event(kind, data):
        events.append((kind, data))

    with patch("core.agent.get_provider", return_value=OneShot("k")):
        asyncio.run(run_agent("do it", MODEL, on_event=on_event))
    assert [kind for kind, _ in events] == ["usage"]
    assert (events[0][1]["input_tokens"], events[0][1]["output_tokens"]) == (7, 3)


def test_cost_per_success_includes_what_failed_runs_spent():
    runs = [
        RunResult("a", "loop", MODEL, 1, hidden_passed=True, cost_usd=0.10, input_tokens=100, cache_read_tokens=300),
        RunResult("a", "loop", MODEL, 2, hidden_passed=False, cost_usd=0.30),
    ]
    summary = summarize(runs)
    assert summary["cost_per_success_usd"] == pytest.approx(0.40)
    assert summary["pass_rate"] == 0.5
    assert summary["cache_hit_rate"] == 0.75
    assert "$0.4000" in format_summary(summary)
    assert "FAIL" in format_table(runs)


def test_first_runs_and_repeats_are_reported_separately():
    runs = [
        RunResult("a", "loop", MODEL, 1, hidden_passed=True, cost_usd=0.08),
        RunResult("a", "loop", MODEL, 2, hidden_passed=True, cost_usd=0.02),
        RunResult("a", "loop", MODEL, 3, hidden_passed=False, cost_usd=0.04),
    ]
    summary = summarize(runs)
    assert summary["first_runs"] == {"runs": 1, "successes": 1, "cost_per_success_usd": pytest.approx(0.08)}
    assert summary["repeat_runs"] == {"runs": 2, "successes": 1, "cost_per_success_usd": pytest.approx(0.06)}
    assert "First runs:         $0.0800" in format_summary(summary)


def test_no_successes_has_no_cost_per_success():
    summary = summarize([RunResult("a", "loop", MODEL, 1, cost_usd=0.2)])
    assert summary["cost_per_success_usd"] is None
    assert "none succeeded" in format_summary(summary)
    assert summarize([]) == {"runs": 0}


def test_claude_code_only_gets_file_tools_and_the_task_tests():
    command = claude_code_command(OFF_BY_ONE, MODEL, 1.0)
    assert not any("dangerously" in part or "bypass" in part.lower() for part in command)
    assert command[command.index("--permission-mode") + 1] == "dontAsk"
    allowed = command[command.index("--allowedTools") + 1]
    assert allowed == f"Read,Edit,Write,Glob,Grep,Bash({OFF_BY_ONE.verify}),Bash({OFF_BY_ONE.verify} *)"
    assert command[command.index("--max-budget-usd") + 1] == "0.75"
    assert "only shell command" in command[command.index("-p") + 1]


def _tool_use(name, **tool_input):
    return json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": tool_input}]}})


def test_reads_claude_code_usage_and_whether_it_ran_the_tests():
    result = RunResult("a", "claude-code", MODEL, 1)
    stdout = "\n".join([
        json.dumps({"type": "system"}),
        _tool_use("Read", file_path="a.py"),
        _tool_use("Bash", command="python3 -c 'print(1)'"),
        _tool_use("Bash", command="bash verify.sh 2>&1 | tail"),
        json.dumps({
            "type": "result", "is_error": False, "total_cost_usd": 0.12, "result": "Which month do you mean?",
            "usage": {"input_tokens": 5, "output_tokens": 6, "cache_read_input_tokens": 7, "cache_creation_input_tokens": 8},
            "permission_denials": [{"tool_name": "Bash", "tool_input": {"command": "python3 -c 'print(1)'"}}],
        }),
    ])
    apply_claude_output(stdout, result, "bash verify.sh")
    assert (result.cost_usd, result.input_tokens, result.output_tokens, result.cache_read_tokens, result.cache_write_tokens) == (0.12, 5, 6, 7, 8)
    assert result.agent_status == "finished" and result.final_message == "Which month do you mean?"
    assert (result.tool_calls, result.verify_runs) == (3, 1)
    assert result.note == "Denied: python3 -c 'print(1)'"


@pytest.mark.parametrize("stdout", ["not json", "{}", '{"total_cost_usd": 1}'])
def test_unreadable_claude_code_output_is_reported_not_counted_as_zero_cost(stdout):
    result = RunResult("a", "claude-code", MODEL, 1)
    apply_claude_output(stdout, result)
    assert result.agent_status == "unreadable" and "Couldn't read" in result.note


def test_loop_arm_passes_the_tests_setting_through():
    seen = []

    async def fake_loop(*args, **kwargs):
        seen.append(kwargs.get("add_tests"))
    with patch("core.loop.start_loop", side_effect=lambda *a, **k: asyncio.ensure_future(fake_loop(*a, **k))):
        asyncio.run(run_benchmark([OFF_BY_ONE], "loop", MODEL, 1, 1.0, 1.0, arm_fn=partial(run_loop_arm, add_tests=True)))
    assert seen == [True]


def test_swe_verify_command_runs_only_the_test_step_with_no_network():
    script = "git apply - <<'EOF'\nhidden test patch\nEOF\n: '>>>>> Start Test Output'\nbin/test a.py\n: '>>>>> End Test Output'\ngit checkout a.py\n"
    command = swe_test_command("#!/bin/bash\nset -ux\nexport LANG=C\ngit status\npython -m pip install -e .\ngit checkout abc a.py\n" + script)
    assert command == "export LANG=C\nbin/test a.py"
    full = verify_command("img:latest", command)
    assert "--network none" in full and '"$PWD":/testbed' in full and "hidden" not in full
    with pytest.raises(ValueError):
        swe_test_command("no markers")


def test_overall_cap_counts_saved_results_and_refuses_to_go_over(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"runs": [{"cost_usd": 1.5}, {"cost_usd": 0.5}]}))
    (tmp_path / "b.json").write_text(json.dumps({"runs": [{"cost_usd": 3.0}]}))
    assert spent_so_far(tmp_path) == 5.0
    check_overall_cap(5.0, 5.0, 10.0)
    with pytest.raises(SystemExit, match="overall cap"):
        check_overall_cap(5.01, 5.0, 10.0)


def test_labels_already_failing_must_change_and_flaky_tests():
    from benchmarks.swe_label import Run, label
    base = [Run(False, {"old", "flip"}), Run(False, {"old"}), Run(False, {"old", "target"})]
    gold = [Run(False, {"old", "pinned"}), Run(False, {"old", "pinned", "flip"}), Run(False, {"old", "pinned"})]
    assert label(base, gold) == {
        "already_failing": ["old"], "must_change": ["pinned"], "flaky": ["flip", "target"], "fixed_by_gold": [],
    }


def test_finds_test_files_the_hidden_patch_creates():
    from benchmarks.swe_label import new_test_files
    patch = "--- /dev/null\n+++ b/tests/test_new.py\n@@ -0,0 +1 @@\n+x\n--- a/tests/test_old.py\n+++ b/tests/test_old.py\n"
    assert new_test_files(patch) == ["tests/test_new.py"]


def test_token_sources_are_averaged_per_run_and_ranked_by_cost():
    from benchmarks.run import RunResult, format_sources
    runs = [
        RunResult("t", "loop", "m", 1, token_sources={
            "results: read_file": {"written": 4000, "read": 20000, "output": 0, "cost_usd": 0.03},
            "task": {"written": 1000, "read": 5000, "output": 0, "cost_usd": 0.01},
        }),
        RunResult("u", "loop", "m", 1, token_sources={"results: read_file": {"written": 0, "read": 0, "output": 0, "cost_usd": 0.0}}),
    ]
    lines = format_sources(runs).splitlines()
    assert lines[1].startswith("results: read_file") and "$0.0150" in lines[1] and "75%" in lines[1]
    assert format_sources([RunResult("t", "claude-code", "m", 1)]) == ""
