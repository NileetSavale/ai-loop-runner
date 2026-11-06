"""The agent loop, with a scripted model acting on a real repo through the real tools."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import SQLModel, create_engine

import core.agent as agent_module
import database
from core.agent import run_agent
from core.loop import run_loop
from core.tools import MAX_READ_CHARS, MAX_READ_LINES, MAX_READABLE_BYTES, RepoTools
from database import get_session as db_session
from models import Iteration, Session, Task, UsageEvent
from providers.base import LLMProvider, LLMResult, ToolCall, ToolTurn, calculate_cost
from sqlmodel import select

MODEL = "claude-sonnet-4-6"


def turn(*calls, stop="tool_use", text="", in_tokens=100, out_tokens=10, cache_read=0, cache_write=0):
    tool_calls = [ToolCall(f"id{i}", name, args) for i, (name, args) in enumerate(calls)]
    return ToolTurn(text=text, tool_calls=tool_calls, stop_reason=stop if calls else (stop if stop != "tool_use" else "end_turn"),
                    assistant_message={"role": "assistant", "content": f"turn-{text}"},
                    input_tokens=in_tokens, output_tokens=out_tokens, cache_read_tokens=cache_read, cache_write_tokens=cache_write)


class ScriptedModel(LLMProvider):
    supports_tools = True

    def __init__(self, turns):
        super().__init__("k")
        self.turns = list(turns)
        self.seen = []

    async def complete(self, system, prompt, model, on_token=None):
        raise AssertionError("a tool agent must not use the one-shot path")

    async def complete_with_tools(self, system, messages, tools, model, on_token=None):
        self.seen.append(list(messages))
        current = self.turns.pop(0)
        if on_token and current.text:
            await on_token(current.text)
        return current

    def tool_results_message(self, results):
        return {"role": "user", "content": results}


def _go(repo, model, verify="true", tests_added=None, max_cost=float("inf")):
    tools = RepoTools(str(repo), verify, tests_added)
    with patch("core.agent.get_provider", return_value=model):
        return asyncio.run(run_agent("do it", MODEL, tools=tools, max_cost_usd=max_cost))


def _last_results(model):
    return model.seen[-1][-1]["content"]


def test_the_loop_reads_writes_tests_then_stops(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    model = ScriptedModel([
        turn(("list_files", {})),
        turn(("read_file", {"path": "a.py"})),
        turn(("edit_file", {"path": "a.py", "old_text": "x = 1", "new_text": "x = 2"})),
        turn(("run_tests", {})),
        turn(text="Done."),
    ])
    result = _go(tmp_path, model, verify="echo all good")
    assert (tmp_path / "a.py").read_text() == "x = 2\n"
    assert result.applied == ["a.py"] and result.notes == []
    assert "a.py" in model.seen[1][-1]["content"][0]["content"]
    assert "x = 1" in model.seen[2][-1]["content"][0]["content"]
    assert "PASSED" in _last_results(model)[0]["content"] and "all good" in _last_results(model)[0]["content"]
    assert "> edit_file a.py" in result.raw_output and "Done." in result.raw_output
    assert model.turns == []


def test_parallel_calls_answered_together_in_one_message(tmp_path):
    (tmp_path / "a.py").write_text("A")
    (tmp_path / "b.py").write_text("B")
    model = ScriptedModel([turn(("read_file", {"path": "a.py"}), ("read_file", {"path": "b.py"})), turn()])
    _go(tmp_path, model)
    results = _last_results(model)
    assert [(r["id"], r["content"]) for r in results] == [("id0", "A"), ("id1", "B")]


@pytest.mark.parametrize("call,expected", [
    (("read_file", {"path": "../secret.txt"}), "outside the repo"),
    (("write_file", {"path": "../escaped.txt", "content": "x"}), "outside the repo"),
    (("write_file", {"path": "tests/test_old.py", "content": "assert True"}), "read-only"),
    (("edit_file", {"path": "tests/test_old.py", "old_text": "False", "new_text": "True"}), "read-only"),
    (("write_file", {"path": "conftest.py", "content": "x"}), "read-only"),
    (("write_file", {"path": ".git/hooks/pre-commit", "content": "x"}), "read-only"),
    (("read_file", {"path": "missing.py"}), "failed"),
    (("read_file", {"path": 123}), "needs text"),
    (("read_file", {}), "needs text"),
    (("delete_everything", {}), "Unknown tool"),
    (("edit_file", {"path": "a.py", "old_text": "nope", "new_text": "x"}), "appears 0 times"),
    (("edit_file", {"path": "a.py", "old_text": "y", "new_text": "x"}), "appears 2 times"),
    (("edit_file", {"path": "a.py", "old_text": "", "new_text": "x"}), "appears 0 times"),
])
def test_refused_actions_become_errors_the_model_can_read(tmp_path, call, expected):
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_old.py").write_text("assert False")
    (repo / "a.py").write_text("y y")
    (tmp_path / "secret.txt").write_text("hunter2")
    model = ScriptedModel([turn(call), turn()])
    result = _go(repo, model)
    answer = _last_results(model)[0]
    assert answer["is_error"] is True and expected in answer["content"]
    assert "hunter2" not in answer["content"]
    assert (repo / "tests" / "test_old.py").read_text() == "assert False"
    assert (repo / "a.py").read_text() == "y y"
    assert not (tmp_path / "escaped.txt").exists() and not (repo / "conftest.py").exists()
    assert result.applied == []


def test_new_tests_allowed_and_search_finds_text(tmp_path):
    (tmp_path / "a.py").write_text("def Target():\n    pass\n")
    added = set()
    model = ScriptedModel([
        turn(("write_file", {"path": "tests/test_new.py", "content": "ok"})),
        turn(("search_code", {"query": "target"})),
        turn(),
    ])
    result = _go(tmp_path, model, tests_added=added)
    assert added == {"tests/test_new.py"} and result.applied == ["tests/test_new.py"]
    assert "a.py:1: def Target():" in _last_results(model)[0]["content"]


def _read(repo, **args):
    return asyncio.run(RepoTools(str(repo), "true").run("read_file", {"path": "big.py", **args}))


def _numbered(repo, count):
    (repo / "big.py").write_text("".join(f"line {n}\n" for n in range(1, count + 1)))


def test_a_small_file_comes_back_exactly(tmp_path):
    _numbered(tmp_path, 3)
    assert _read(tmp_path) == ("line 1\nline 2\nline 3\n", False)


def test_a_large_file_is_cut_and_says_so(tmp_path):
    _numbered(tmp_path, MAX_READ_LINES + 50)
    content, is_error = _read(tmp_path)
    assert not is_error
    assert f"line {MAX_READ_LINES}\n" in content and f"line {MAX_READ_LINES + 1}\n" not in content
    assert f"(showing lines 1-{MAX_READ_LINES} of {MAX_READ_LINES + 50}." in content


def test_reads_a_line_range(tmp_path):
    _numbered(tmp_path, 100)
    content, _ = _read(tmp_path, start_line=10, end_line=12)
    assert content == "line 10\nline 11\nline 12\n(showing lines 10-12 of 100. Set start_line to read further.)"


def test_range_past_the_end_stops_at_the_end(tmp_path):
    _numbered(tmp_path, 5)
    content, _ = _read(tmp_path, start_line=4, end_line=99)
    assert content.startswith("line 4\nline 5\n(showing lines 4-5 of 5.")


def test_the_character_limit_cuts_at_a_whole_line(tmp_path):
    (tmp_path / "big.py").write_text(("y" * 1000 + "\n") * 50)
    content, _ = _read(tmp_path)
    lines = content.split("\n")
    assert len(content) < MAX_READ_CHARS + 100 and all(len(line) == 1000 for line in lines[:-2])
    assert "(showing lines 1-11 of 50." in content


def test_one_huge_line_is_cut_and_says_so(tmp_path):
    (tmp_path / "big.py").write_text("x" * (MAX_READ_CHARS + 1))
    content, is_error = _read(tmp_path)
    assert not is_error and content.startswith("x" * MAX_READ_CHARS + "\n(line 1 of big.py was cut")


def test_an_empty_file_is_fine(tmp_path):
    (tmp_path / "big.py").write_text("")
    assert _read(tmp_path) == ("", False)


def test_a_huge_file_is_refused(tmp_path):
    (tmp_path / "big.py").write_bytes(b"x" * (MAX_READABLE_BYTES + 1))
    content, is_error = _read(tmp_path)
    assert is_error and "too large" in content


@pytest.mark.parametrize("args,expected", [
    ({"start_line": 99}, "has 3 lines"),
    ({"start_line": 3, "end_line": 2}, "before start_line"),
    ({"start_line": 0}, "whole numbers"),
    ({"start_line": "1"}, "whole numbers"),
    ({"end_line": True}, "whole numbers"),
    ({"start_line": 1.5}, "whole numbers"),
])
def test_bad_ranges_tell_the_model_what_went_wrong(tmp_path, args, expected):
    _numbered(tmp_path, 3)
    content, is_error = _read(tmp_path, **args)
    assert is_error and expected in content


def test_listing_skips_dependencies(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.js").write_text("x")
    (tmp_path / "a.py").write_text("x")
    model = ScriptedModel([turn(("list_files", {})), turn()])
    _go(tmp_path, model)
    assert _last_results(model)[0]["content"] == "a.py"


@pytest.mark.parametrize("stop,note", [("max_tokens", "output limit"), ("refusal", "declined")])
def test_tools_never_run_from_a_cut_off_or_refused_turn(tmp_path, stop, note):
    model = ScriptedModel([turn(("write_file", {"path": "a.py", "content": "half a fi"}), stop=stop)])
    result = _go(tmp_path, model)
    assert not (tmp_path / "a.py").exists()
    assert note in result.notes[0]


def test_budget_stops_the_agent_before_its_next_action(tmp_path):
    expensive = turn(("write_file", {"path": "a.py", "content": "x"}), in_tokens=1_000_000)
    model = ScriptedModel([expensive, turn()])
    result = _go(tmp_path, model, max_cost=1.0)
    assert not (tmp_path / "a.py").exists()
    assert "budget" in result.notes[0]
    assert len(model.turns) == 1


def test_step_limit_ends_a_model_that_never_stops(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_module, "MAX_AGENT_STEPS", 3)
    model = ScriptedModel([turn(("list_files", {})) for _ in range(10)])
    result = _go(tmp_path, model)
    assert "limit of 3 steps" in result.notes[0]
    assert len(model.turns) == 7


def test_cost_and_tokens_add_up_across_turns_including_cache(tmp_path):
    model = ScriptedModel([
        turn(("list_files", {}), in_tokens=100, out_tokens=10, cache_write=1000),
        turn(in_tokens=50, out_tokens=20, cache_read=1000),
    ])
    result = _go(tmp_path, model)
    assert result.cost_usd == pytest.approx(calculate_cost(MODEL, 150, 30, 1000, 1000))
    assert (result.input_tokens, result.output_tokens) == (2150, 30)


def test_cached_tokens_priced_below_normal_and_writes_above():
    plain = calculate_cost(MODEL, 1000, 0)
    assert calculate_cost(MODEL, 0, 0, cache_read_tokens=1000) == pytest.approx(plain * 0.1)
    assert calculate_cost(MODEL, 0, 0, cache_write_tokens=1000) == pytest.approx(plain * 1.25)


class OneShotModel(LLMProvider):
    async def complete(self, system, prompt, model, on_token=None):
        return LLMResult(text='<file path="a.py">one shot</file>', input_tokens=1, output_tokens=1)


def test_provider_without_tools_uses_the_one_shot_path(tmp_path):
    with patch("core.agent.get_provider", return_value=OneShotModel("k")):
        result = asyncio.run(run_agent("do it", MODEL, tools=RepoTools(str(tmp_path), "true")))
    assert result.edits[0].content == "one shot" and result.applied == []


# --- through the outer loop ---

@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)


def _session(repo, command, user_id=None):
    import core.loop as loop
    sid = str(uuid.uuid4())
    with db_session() as s:
        s.add(Session(id=sid, user_id=user_id, name="t", repo_path=str(repo), verify_command=command, model=MODEL, max_iterations=3, status="running"))
        t = Task(id=str(uuid.uuid4()), session_id=sid, title="t", spec="do it")
        t.set_files_context([])
        s.add(t)
        s.commit()
    loop._running[sid] = object()
    return sid


def _loop(sid, model, **kwargs):
    events = []

    async def broadcast(e):
        events.append(e)

    with patch("core.agent.get_provider", return_value=model), patch("core.loop.git_commit", return_value="abc"), \
         patch("core.loop.invalidate_analytics", new_callable=AsyncMock):
        asyncio.run(run_loop(sid, broadcast, **kwargs))
    with db_session() as s:
        return s.get(Session, sid).status, events


def test_outer_loop_judges_for_itself_whatever_the_agent_claims(tmp_path, db):
    (tmp_path / "ok.py").write_text("import sys\nsys.exit(1)\n")
    model = ScriptedModel([
        turn(("write_file", {"path": "a.py", "content": "x"})), turn(text="All tests pass, I promise!"),
        turn(("write_file", {"path": "ok.py", "content": "import sys\nsys.exit(0)\n"})), turn(text="Really fixed."),
    ])
    status, events = _loop(_session(tmp_path, f"{sys.executable} ok.py"), model)
    assert status == "passed"
    assert sum(e["event"] == "iteration_start" for e in events) == 2
    assert model.turns == []


def test_tool_activity_streams_to_the_ui_and_edits_are_recorded(tmp_path, db):
    model = ScriptedModel([turn(("write_file", {"path": "a.py", "content": "x"})), turn(text="Done.")])
    sid = _session(tmp_path, "true", user_id="u1")
    status, events = _loop(sid, model)
    assert status == "passed"
    tokens = "".join(e["data"]["token"] for e in events if e["event"] == "agent_token")
    assert "> write_file a.py" in tokens and "Done." in tokens
    with db_session() as s:
        iteration = s.exec(select(Iteration).where(Iteration.session_id == sid)).first()
        assert '"a.py"' in iteration.files_changed and iteration.cost_usd > 0
        assert s.exec(select(UsageEvent).where(UsageEvent.session_id == sid)).first().cost_usd == iteration.cost_usd


def test_agent_gets_only_the_money_left_in_the_session(tmp_path, db):
    expensive = turn(("write_file", {"path": "a.py", "content": "1"}), in_tokens=100_000)  # $0.30
    model = ScriptedModel([expensive, turn(text="x"), turn(("write_file", {"path": "b.py", "content": "2"}), in_tokens=100_000), turn(text="y")])
    status, events = _loop(_session(tmp_path, f"{sys.executable} -c 'raise SystemExit(1)'"), model, max_cost_usd=0.5)
    assert status == "failed"
    assert not (tmp_path / "b.py").exists()  # the second attempt started with only $0.20, and its first turn spent that
    assert any("limit" in str(e["data"].get("error")) for e in events if e["event"] == "session_complete")


def test_weak_tests_written_through_tools_are_still_rejected(tmp_path, db):
    (tmp_path / "run_tests.py").write_text('import glob, runpy, sys\nsys.path.insert(0, ".")\nfor f in glob.glob("test_*.py"):\n    runpy.run_path(f)\n')
    code = "def is_adult(age):\n    return age >= 18\n"
    model = ScriptedModel([
        turn(("write_file", {"path": "calc.py", "content": code}), ("write_file", {"path": "test_calc.py", "content": "assert True\n"})), turn(),
        turn(("write_file", {"path": "test_calc.py", "content": "from calc import is_adult\nassert is_adult(18) is True\nassert is_adult(17) is False\n"})), turn(),
    ])
    status, _ = _loop(_session(tmp_path, f"{sys.executable} run_tests.py"), model)
    assert status == "passed"
    assert any("too weak" in str(m) for m in model.seen[2])
