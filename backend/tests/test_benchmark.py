"""The benchmark harness, with a scripted model so no tokens are spent."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import json
import shutil
from unittest.mock import patch

import pytest

from benchmarks.run import (
    BenchTask, RunResult, apply_claude_output, changed_lines, claude_code_command, format_summary, format_table,
    hidden_tests_pass, load_tasks, prepare_repo, run_benchmark, run_one, summarize,
)
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

    assert asyncio.run(check()) == (False, False)
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


def test_reads_claude_code_usage():
    result = RunResult("a", "claude-code", MODEL, 1)
    apply_claude_output(json.dumps({
        "is_error": False, "total_cost_usd": 0.12,
        "usage": {"input_tokens": 5, "output_tokens": 6, "cache_read_input_tokens": 7, "cache_creation_input_tokens": 8},
    }), result)
    assert (result.cost_usd, result.input_tokens, result.output_tokens, result.cache_read_tokens, result.cache_write_tokens) == (0.12, 5, 6, 7, 8)
    assert result.agent_status == "finished"


@pytest.mark.parametrize("stdout", ["not json", "{}", '{"total_cost_usd": 1}'])
def test_unreadable_claude_code_output_is_reported_not_counted_as_zero_cost(stdout):
    result = RunResult("a", "claude-code", MODEL, 1)
    apply_claude_output(stdout, result)
    assert result.agent_status == "unreadable" and "Couldn't read" in result.note
