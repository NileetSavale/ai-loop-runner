"""Tests for deciding when an agent may change an existing test."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from unittest.mock import AsyncMock

import pytest

from core.test_changes import check_test_change, parse_review
from core.tools import RepoTools

OLD = "def test_min():\n    raises(ValueError, lambda: Min())\n    assert Min(1) == 1\n"


@pytest.mark.parametrize("after, verdict", [
    (OLD + "\n\ndef test_min_empty():\n    assert Min() == oo\n", "allow"),
    (OLD.replace("    raises(ValueError, lambda: Min())\n", "    assert Min() == oo\n"), "review"),
    ("@pytest.mark.skip\n" + OLD, "block"),
    ("import pytest\n", "block"),
    ("", "block"),
])
def test_sorts_test_changes_by_what_fixed_rules_can_decide(after, verdict):
    assert check_test_change(OLD, after).verdict == verdict


def test_renaming_a_test_counts_as_deleting_it():
    check = check_test_change(OLD, OLD.replace("test_min", "check_min"))
    assert check.verdict == "block" and "test_min" in check.reason


@pytest.mark.parametrize("text, approved", [
    ('{"approve": true, "why": "The task asks Min() to return oo."}', True),
    ('Sure.\n{"approve": false, "why": "Loosens the check."}', False),
    ('{"approve": "yes"}', False),
    ("not json", False),
    ("[1]", False),
])
def test_only_a_clear_approval_counts(text, approved):
    assert parse_review(text)[0] is approved


def _repo(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_min.py").write_text(OLD)
    (tmp_path / "conftest.py").write_text("")
    return tmp_path


def _change(tools, old, new, path="tests/test_min.py"):
    return asyncio.run(tools.run("change_existing_test", {"path": path, "old_text": old, "new_text": new, "reason": "task says so"}))


def test_changing_what_a_test_checks_needs_the_reviewer_and_applies_only_if_approved(tmp_path):
    repo = _repo(tmp_path)
    old, new = "raises(ValueError, lambda: Min())", "assert Min() == oo"
    refuse = AsyncMock(return_value=(False, "The task doesn't ask for this."))
    message, is_error = _change(RepoTools(str(repo), "true", review_test_change=refuse), old, new)
    assert is_error and "refused" in message and "doesn't ask" in message
    assert (repo / "tests/test_min.py").read_text() == OLD
    path, diff, reason = refuse.call_args.args
    assert path == "tests/test_min.py" and "-    raises(ValueError" in diff and reason == "task says so"

    approve = AsyncMock(return_value=(True, "The task asks for it."))
    tools = RepoTools(str(repo), "true", review_test_change=approve)
    message, is_error = _change(tools, old, new)
    assert not is_error and "approved" in message
    assert "assert Min() == oo" in (repo / "tests/test_min.py").read_text()
    assert tools.changed == ["tests/test_min.py"]


def test_adding_to_an_existing_test_skips_the_reviewer(tmp_path):
    repo = _repo(tmp_path)
    reviewer = AsyncMock()
    tools = RepoTools(str(repo), "true", review_test_change=reviewer)
    _, is_error = _change(tools, "    assert Min(1) == 1\n", "    assert Min(1) == 1\n    assert Min(2) == 2\n")
    assert not is_error
    reviewer.assert_not_called()


@pytest.mark.parametrize("old, new, path, expected", [
    ("def test_min():", "@pytest.mark.skip\ndef test_min():", "tests/test_min.py", "never allowed"),
    ("", "x = 1", "conftest.py", "always read-only"),
])
def test_skips_and_test_config_are_refused_without_review(tmp_path, old, new, path, expected):
    repo = _repo(tmp_path)
    reviewer = AsyncMock(return_value=(True, "fine"))
    message, is_error = _change(RepoTools(str(repo), "true", review_test_change=reviewer), old, new, path)
    assert is_error and expected in message
    reviewer.assert_not_called()


def test_without_a_reviewer_existing_tests_stay_read_only(tmp_path):
    repo = _repo(tmp_path)
    message, is_error = _change(RepoTools(str(repo), "true"), "Min(1) == 1", "Min(1) == 2")
    assert is_error and "isn't enabled" in message


def test_edit_file_on_an_existing_test_points_to_the_new_tool(tmp_path):
    repo = _repo(tmp_path)
    tools = RepoTools(str(repo), "true", review_test_change=AsyncMock())
    message, is_error = asyncio.run(tools.run("edit_file", {"path": "tests/test_min.py", "old_text": "Min(1)", "new_text": "Min(2)"}))
    assert is_error and "change_existing_test" in message
