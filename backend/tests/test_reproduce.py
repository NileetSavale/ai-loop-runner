import subprocess

from core.edits import FileEdit, filter_edits
from core.reproduce import FAILURE_NAME, SCRIPT_PATH, fails_for_the_bug, script_from, with_reproduction
from core.verifier import failing_tests


def test_only_a_failure_that_can_be_the_bug_counts():
    assert fails_for_the_bug(1, "AssertionError: expected 2")
    assert fails_for_the_bug(1, "ValueError: bad unit")  # the error the task describes
    assert not fails_for_the_bug(0, "")  # doesn't reproduce anything
    assert not fails_for_the_bug(1, "ModuleNotFoundError: No module named 'pkg'")
    assert not fails_for_the_bug(1, "  File \"x\", line 3\nSyntaxError: invalid syntax")


def test_the_script_is_read_from_the_reply():
    assert script_from(f'<file path="{SCRIPT_PATH}">\nassert 1 == 2\n</file>') == "assert 1 == 2\n"
    assert script_from('<file path="other.py">x</file>') is None


def _run(command, cwd):
    return subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True)


def test_combined_check_passes_only_when_tests_and_script_both_pass(tmp_path):
    (tmp_path / SCRIPT_PATH).write_text("assert 1 == 2\n")
    failing_script = _run(with_reproduction("echo tests ok", f"python3 {SCRIPT_PATH}"), tmp_path)
    assert failing_script.returncode != 0 and failing_tests(failing_script.stdout) == {FAILURE_NAME}
    (tmp_path / SCRIPT_PATH).write_text("assert 1 == 1\n")
    assert _run(with_reproduction("echo tests ok", f"python3 {SCRIPT_PATH}"), tmp_path).returncode == 0
    assert _run(with_reproduction("exit 1", f"python3 {SCRIPT_PATH}"), tmp_path).returncode != 0


def test_the_coder_cannot_change_the_script(tmp_path):
    (tmp_path / SCRIPT_PATH).write_text("assert 1 == 2\n")
    allowed, rejected = filter_edits([FileEdit(SCRIPT_PATH, "pass\n")], str(tmp_path), set())
    assert not allowed and "reproduction script are read-only" in rejected[0]
