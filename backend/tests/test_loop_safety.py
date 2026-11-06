"""Tests for the limits the loop enforces in code rather than asking the model to respect."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import subprocess
import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import SQLModel, create_engine

import core.loop as loop
import database
from agents.test_gen import apply_tests
from core.agent import AgentResult, FileEdit
from core.loop import build_file_context, filter_edits, is_locked_path, is_test_path, run_loop
from core.mutation import apply_mutant, changed_lines, check_test_strength, list_mutants
from core.verifier import VerifyResult, run_verify
from database import get_session as db_session
from models import Session, Task


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)


FAIL = VerifyResult(passed=False, output="1 failed in 0.01s", exit_code=1)
PASS = VerifyResult(passed=True, output="ok", exit_code=0)


def _agent(*edits, cost=0.01):
    return AgentResult(raw_output="", edits=list(edits), input_tokens=1, output_tokens=1, cost_usd=cost)


def _run(repo, agent, verify, max_iterations=5, require_failing=False, command="true", max_cost_usd=None, use_map=False):
    sid = str(uuid.uuid4())
    with db_session() as db:
        db.add(Session(id=sid, name="t", repo_path=str(repo), verify_command=command,
                       model="claude-sonnet-4-6", max_iterations=max_iterations, status="running"))
        t = Task(id=str(uuid.uuid4()), session_id=sid, title="t", spec="do it")
        t.set_files_context([])
        db.add(t)
        db.commit()
    loop._running[sid] = object()
    events = []

    async def broadcast(e):
        events.append(e)

    with patch("core.loop.run_agent", agent), patch("core.loop.run_verify", verify), \
         patch("core.loop.git_commit", return_value="abc"), \
         patch("core.loop.invalidate_analytics", new_callable=AsyncMock):
        asyncio.run(run_loop(sid, broadcast, require_failing=require_failing, max_cost_usd=max_cost_usd, use_map=use_map))
    with db_session() as db:
        status = db.get(Session, sid).status
    return status, events[-1]["data"], events


@pytest.mark.parametrize("path", [
    "tests/test_a.py", "test/a.py", "src/__tests__/a.ts", "src/test_a.py", "src/a_test.go", "src/a.test.ts",
    "src/a.spec.js", "TESTS/a.py",
])
def test_test_paths(path):
    assert is_test_path(path)


@pytest.mark.parametrize("path", ["conftest.py", "tests/conftest.py", "pytest.ini", "vitest.config.ts", ".git/hooks/pre-commit"])
def test_locked_paths(path):
    assert is_locked_path(path)


@pytest.mark.parametrize("path", ["src/rate_limiter.py", "latest.py", "src/contest.py", "app/attest/a.py", "README.md"])
def test_ordinary_paths_are_neither(path):
    assert not is_test_path(path) and not is_locked_path(path)


def test_filter_rejects_escapes_existing_tests_config_and_symlinks(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("assert False")
    os.symlink(tmp_path / "tests", tmp_path / "innocent")
    outside = tmp_path.parent / "abs.txt"
    edits = [FileEdit(p, "x") for p in [
        "src/ok.py", "../up.txt", str(outside), "tests/test_a.py", "src/../tests/test_a.py", "innocent/test_a.py",
        "tests/conftest.py", "pytest.ini", ".git/config",
    ]]
    allowed, rejected = filter_edits(edits, str(tmp_path))
    assert [e.path for e in allowed] == ["src/ok.py"]
    assert len(rejected) == 8


def test_new_tests_allowed_and_agent_can_improve_only_its_own(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_old.py").write_text("assert False")
    added = set()
    allowed, _ = filter_edits([FileEdit("tests/test_new.py", "x")], str(tmp_path), added)
    assert len(allowed) == 1 and added == {"tests/test_new.py"}
    (tmp_path / "tests" / "test_new.py").write_text("x")
    edits = [FileEdit("tests/test_new.py", "y"), FileEdit("tests/test_old.py", "y")]
    allowed, rejected = filter_edits(edits, str(tmp_path), added)
    assert [e.path for e in allowed] == ["tests/test_new.py"]
    assert "test_old.py" in rejected[0]


def test_context_will_not_read_outside_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (tmp_path / ".env").write_text("SECRET=hunter2")
    assert "hunter2" not in build_file_context(["../.env"], str(repo))


def test_apply_tests_writes_nothing_if_any_path_escapes(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    files = [{"path": "tests/a.py", "content": "x"}, {"path": "../b.py", "content": "x"}]
    with pytest.raises(ValueError):
        asyncio.run(apply_tests(str(repo), files))
    assert not (repo / "tests").exists() and not (tmp_path / "b.py").exists()


def test_tampered_test_is_kept_and_agent_is_told(tmp_path):
    (tmp_path / "tests").mkdir()
    test_file = tmp_path / "tests" / "test_a.py"
    test_file.write_text("assert False")
    agent = AsyncMock(side_effect=[
        _agent(FileEdit("tests/test_a.py", "assert True"), FileEdit("a.py", "1")),
        _agent(FileEdit("a.py", "2")),
    ])
    status, _, _ = _run(tmp_path, agent, AsyncMock(side_effect=[FAIL, PASS]))
    assert status == "passed"
    assert test_file.read_text() == "assert False"
    assert "REJECTED tests/test_a.py" in agent.call_args_list[1].args[0]


def test_only_editing_existing_tests_cannot_pass_even_if_verify_would(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("assert False")
    verify = AsyncMock(return_value=PASS)
    agent = AsyncMock(return_value=_agent(FileEdit("tests/test_a.py", "assert True")))
    status, _, _ = _run(tmp_path, agent, verify, max_iterations=2)
    assert status == "failed"
    verify.assert_not_called()


def test_only_adding_tests_with_no_code_to_check_cannot_pass(tmp_path):
    agent = AsyncMock(return_value=_agent(FileEdit("tests/test_new.py", "assert True")))
    status, _, _ = _run(tmp_path, agent, AsyncMock(return_value=PASS), max_iterations=2)
    assert status == "failed"
    assert "nothing shows" in agent.call_args_list[1].args[0]


def test_no_edits_tells_agent_and_cannot_pass(tmp_path):
    agent = AsyncMock(side_effect=[_agent(), _agent(FileEdit("a.py", "1"))])
    status, _, _ = _run(tmp_path, agent, AsyncMock(return_value=PASS))
    assert status == "passed"
    assert "No edits were applied" in agent.call_args_list[1].args[0]


def test_tests_already_green_stops_before_spending(tmp_path):
    agent = AsyncMock()
    status, data, events = _run(tmp_path, agent, AsyncMock(return_value=PASS), require_failing=True)
    assert status == "failed" and "already pass" in data["error"]
    assert any(e["event"] == "verify_output" and "already pass" in e["data"]["output"] for e in events)
    agent.assert_not_called()


def test_tests_failing_first_lets_loop_run(tmp_path):
    _repo(tmp_path, impl="def is_adult(age):\n    return None\n", test=STRONG_TEST)
    agent = AsyncMock(return_value=_agent(FileEdit("calc.py", IMPL)))
    status, _, _ = _run(tmp_path, agent, run_verify, require_failing=True, command=VERIFY)
    assert status == "passed"
    agent.assert_called_once()


def test_cost_limit_stops_loop(tmp_path, monkeypatch):
    monkeypatch.setattr(loop, "MAX_SESSION_COST_USD", 1.0)
    agent = AsyncMock(return_value=_agent(FileEdit("a.py", "1"), cost=0.6))
    verify = AsyncMock(side_effect=[
        VerifyResult(False, "first problem", 1), VerifyResult(False, "other problem", 1), PASS,
    ])
    status, data, _ = _run(tmp_path, agent, verify)
    assert status == "failed" and "limit" in data["error"]
    assert agent.call_count == 2


def test_same_failure_three_times_stops_ignoring_timings(tmp_path):
    outputs = ["1 failed in 0.01s", "1 failed in 0.57s", "1 failed in 12.30s"]
    verify = AsyncMock(side_effect=[VerifyResult(False, o, 1) for o in outputs])
    agent = AsyncMock(return_value=_agent(FileEdit("a.py", "1")))
    status, data, _ = _run(tmp_path, agent, verify, max_iterations=10)
    assert status == "failed" and "repeated 3 times" in data["error"]
    assert agent.call_count == 3


def test_different_failures_keep_going_to_max_iterations(tmp_path):
    verify = AsyncMock(side_effect=[VerifyResult(False, c, 1) for c in "abcd"])
    agent = AsyncMock(return_value=_agent(FileEdit("a.py", "1")))
    status, _, _ = _run(tmp_path, agent, verify, max_iterations=4)
    assert status == "failed"
    assert agent.call_count == 4


def _failed(*names, note=""):
    return VerifyResult(False, "".join(f"FAILED tests/test_a.py::{n} - boom {note}\n" for n in names), 1)


def test_stops_when_only_tests_that_already_failed_still_fail(tmp_path):
    verify = AsyncMock(side_effect=[_failed("test_old"), _failed("test_old", note="0.1s"), _failed("test_old", note="9.9s"), PASS])
    agent = AsyncMock(return_value=_agent(FileEdit("a.py", "1")))
    status, data, _ = _run(tmp_path, agent, verify, max_iterations=10, use_map=True)
    assert status == "failed" and "already failing before any change" in data["error"]
    assert agent.call_count == 2
    assert "already failing before your changes: tests/test_a.py::test_old" in agent.call_args_list[1].args[0]


def test_a_new_failure_alongside_old_ones_keeps_going(tmp_path):
    verify = AsyncMock(side_effect=[_failed("test_old"), _failed("test_old", "test_new"), _failed("test_old"), PASS])
    agent = AsyncMock(return_value=_agent(FileEdit("a.py", "1")))
    status, _, _ = _run(tmp_path, agent, verify, max_iterations=10, use_map=True)
    assert status == "passed" and agent.call_count == 3


def test_failing_tests_are_the_job_when_the_task_is_to_fix_them(tmp_path):
    verify = AsyncMock(side_effect=[_failed("test_x"), _failed("test_x", note="1"), _failed("test_x", note="2"), PASS])
    agent = AsyncMock(return_value=_agent(FileEdit("a.py", "1")))
    status, _, _ = _run(tmp_path, agent, verify, max_iterations=10, require_failing=True)
    assert status == "passed" and agent.call_count == 3


def test_per_session_cost_limit_overrides_default(tmp_path):
    agent = AsyncMock(return_value=_agent(FileEdit("a.py", "1"), cost=0.6))
    verify = AsyncMock(side_effect=[VerifyResult(False, c, 1) for c in "abc"] + [PASS])
    status, data, _ = _run(tmp_path, agent, verify, max_cost_usd=0.5)
    assert status == "failed" and "$0.50" in data["error"]
    agent.assert_called_once()


def test_verify_timeout_kills_child_processes(tmp_path, monkeypatch):
    import core.verifier as verifier
    monkeypatch.setattr(verifier, "MAX_TIMEOUT", 1)
    marker = tmp_path / "survived"
    result = asyncio.run(run_verify(f"(sleep 2; touch {marker}) & wait", str(tmp_path)))
    assert "TIMEOUT" in result.output
    time.sleep(2.5)
    assert not marker.exists()


# --- mutation check: real files and real test runs, no mocks ---

IMPL = "def is_adult(age):\n    return age >= 18\n"
WEAK_TEST = "assert True\n"
STRONG_TEST = (
    "from calc import is_adult\n"
    "assert is_adult(18) is True\n"
    "assert is_adult(17) is False\n"
    "assert is_adult(19) is True\n"
)
RUNNER = 'import glob, runpy, sys\nsys.path.insert(0, ".")\nfor f in glob.glob("test_*.py"):\n    runpy.run_path(f)\n'
VERIFY = f"{sys.executable} run_tests.py"


def _repo(tmp_path, impl=IMPL, test=None):
    (tmp_path / "run_tests.py").write_text(RUNNER)
    (tmp_path / "calc.py").write_text(impl)
    if test:
        (tmp_path / "test_calc.py").write_text(test)
    return tmp_path


def test_each_mutant_changes_behaviour_of_the_source():
    assert len(list_mutants(IMPL)) == 3  # >= to <, 18 to 19, return None
    assert "age < 18" in apply_mutant(IMPL, [i for i, d in list_mutants(IMPL) if "GtE" in d][0])


def test_weak_tests_catch_nothing(tmp_path):
    result = asyncio.run(check_test_strength(str(_repo(tmp_path, test=WEAK_TEST)), VERIFY, ["calc.py"]))
    assert result.tested == 3 and result.caught == 0 and len(result.survivors) == 3


def test_strong_tests_catch_everything(tmp_path):
    result = asyncio.run(check_test_strength(str(_repo(tmp_path, test=STRONG_TEST)), VERIFY, ["calc.py"]))
    assert result.tested == 3 and result.caught == 3 and not result.survivors


def test_mutation_never_touches_the_real_repo(tmp_path):
    asyncio.run(check_test_strength(str(_repo(tmp_path, test=WEAK_TEST)), VERIFY, ["calc.py"]))
    assert (tmp_path / "calc.py").read_text() == IMPL


def test_mutant_that_loops_forever_counts_as_caught_and_does_not_hang(tmp_path, monkeypatch):
    import core.verifier as verifier
    monkeypatch.setattr(verifier, "MAX_TIMEOUT", 2)
    impl = "def stop():\n    while False:\n        pass\n    return 1\n"
    test = "from calc import stop\nassert stop() == 1\n"
    result = asyncio.run(check_test_strength(str(_repo(tmp_path, impl, test)), VERIFY, ["calc.py"]))
    assert result.tested == 3 and result.caught == 3


def test_mutation_skips_when_repo_does_not_pass_in_a_copy(tmp_path):
    result = asyncio.run(check_test_strength(str(_repo(tmp_path, test=WEAK_TEST)), "exit 1", ["calc.py"]))
    assert result.skipped_reason and result.tested == 0


def test_loop_rejects_easy_tests_then_accepts_real_ones(tmp_path):
    _repo(tmp_path, impl="def is_adult(age):\n    return False\n")
    agent = AsyncMock(side_effect=[
        _agent(FileEdit("calc.py", IMPL), FileEdit("test_calc.py", WEAK_TEST)),
        _agent(FileEdit("test_calc.py", STRONG_TEST)),
    ])
    status, _, events = _run(tmp_path, agent, run_verify, command=VERIFY)
    assert status == "passed"
    assert agent.call_count == 2
    second_prompt = agent.call_args_list[1].args[0]
    assert "too weak" in second_prompt and "calc.py line" in second_prompt
    assert "test_calc.py" in second_prompt  # it can see its own test to improve it
    assert events[-2]["data"]["output"].endswith("Tests caught 3 of 3 deliberately planted bugs.")


def test_loop_keeps_failing_if_tests_stay_easy(tmp_path):
    _repo(tmp_path)
    agent = AsyncMock(return_value=_agent(FileEdit("calc.py", IMPL), FileEdit("test_calc.py", WEAK_TEST)))
    status, data, _ = _run(tmp_path, agent, run_verify, command=VERIFY, max_iterations=10)
    assert status == "failed" and "repeated 3 times" in data["error"]


def test_non_python_code_passes_but_says_strength_was_not_checked(tmp_path):
    (tmp_path / "ok.sh").write_text("exit 0\n")
    agent = AsyncMock(return_value=_agent(FileEdit("app.js", "1"), FileEdit("app.test.js", "ok")))
    status, _, events = _run(tmp_path, agent, run_verify, command="sh ok.sh")
    assert status == "passed"
    assert "NOT checked" in events[-2]["data"]["output"]


TWO_FUNCTIONS = "def changed(x):\n    return x + 1\n\n\ndef untouched(x):\n    return x * 2\n"
TESTS_CHANGED_ONLY = "from calc import changed\n\n\ndef test_changed():\n    assert changed(1) == 2\n"
PYTEST = f"{sys.executable} -m pytest -q"


def _committed_repo(tmp_path):
    (tmp_path / "calc.py").write_text(TWO_FUNCTIONS)
    (tmp_path / "test_calc.py").write_text(TESTS_CHANGED_ONLY)
    subprocess.run("git init -q && git add -A && git -c user.name=t -c user.email=t@t.co commit -qm base", shell=True, cwd=tmp_path, check=True)
    return tmp_path


def test_untouched_code_is_not_held_against_the_tests(tmp_path):
    repo = _committed_repo(tmp_path)
    (repo / "calc.py").write_text(TWO_FUNCTIONS.replace("x + 1", "x + 1  # fixed"))
    result = asyncio.run(check_test_strength(str(repo), PYTEST, ["calc.py"]))
    assert result.tested == 3 and result.caught == 3  # return None, + to -, 1 to 2, all on the changed line
    assert result.survivors == []


def test_weak_tests_on_changed_lines_are_still_caught(tmp_path):
    repo = _committed_repo(tmp_path)
    (repo / "calc.py").write_text(TWO_FUNCTIONS.replace("x * 2", "x * 3"))
    result = asyncio.run(check_test_strength(str(repo), PYTEST, ["calc.py"]))
    assert result.tested == 3 and result.caught == 0
    assert all("line 6" in survivor for survivor in result.survivors)


def test_a_file_with_no_changes_has_nothing_to_check(tmp_path):
    result = asyncio.run(check_test_strength(str(_committed_repo(tmp_path)), PYTEST, ["calc.py"]))
    assert result.skipped_reason and result.tested == 0


def test_a_new_file_counts_as_all_changed(tmp_path):
    repo = _committed_repo(tmp_path)
    (repo / "extra.py").write_text("def a():\n    return 1\n")
    assert changed_lines(str(repo), "extra.py") is None
    assert changed_lines(str(repo), "calc.py") == set()


def test_no_git_history_counts_as_all_changed(tmp_path):
    (tmp_path / "calc.py").write_text(TWO_FUNCTIONS)
    assert changed_lines(str(tmp_path), "calc.py") is None


def test_diff_ranges_cover_every_added_line(tmp_path):
    repo = _committed_repo(tmp_path)
    (repo / "calc.py").write_text(TWO_FUNCTIONS.replace("    return x + 1\n", "    y = x\n    z = y\n    return z + 1\n"))
    assert changed_lines(str(repo), "calc.py") == {2, 3, 4}


def test_cut_off_reply_is_explained_to_the_agent(tmp_path):
    cut_off = AgentResult(raw_output="", edits=[], input_tokens=1, output_tokens=1, cost_usd=0.01, truncated=True)
    agent = AsyncMock(side_effect=[cut_off, _agent(FileEdit("a.py", "1"))])
    status, _, _ = _run(tmp_path, agent, AsyncMock(return_value=PASS))
    assert status == "passed"
    assert "hit the output limit" in agent.call_args_list[1].args[0]


STRINGY = '''"""Docstring."""
import re

def slugify(text):
    """Docstring."""
    if not isinstance(text, str):
        raise TypeError("needs a string")
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")

if __name__ == "__main__":
    print(slugify("A b"))
'''


def test_string_and_not_mutants_exist_but_docstrings_errors_and_main_guard_are_ignored():
    found = [description for _, description in list_mutants(STRINGY)]
    assert any("not" in d for d in found)
    assert any("[^a-z0-9]+" in d for d in found) and any("'-'" in d for d in found)
    assert not any("Docstring" in d or "needs a string" in d or "__main__" in d for d in found)


def test_vague_test_on_string_code_no_longer_clears_the_bar(tmp_path):
    weak = "from calc import slugify\nassert slugify('x') is not None\n"
    result = asyncio.run(check_test_strength(str(_repo(tmp_path, STRINGY, weak)), VERIFY, ["calc.py"]))
    assert result.tested >= 3
    assert result.caught / result.tested < loop.MIN_MUTATION_SCORE
