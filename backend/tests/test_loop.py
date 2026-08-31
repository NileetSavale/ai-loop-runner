import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.loop import build_file_context, build_prompt, apply_edits
from core.agent import FileEdit


# --- build_file_context ---

def test_reads_file_contents(tmp_path):
    f = tmp_path / "main.py"
    f.write_text("x = 1")
    ctx = build_file_context(["main.py"], str(tmp_path))
    assert "main.py" in ctx
    assert "x = 1" in ctx


def test_missing_file_noted(tmp_path):
    ctx = build_file_context(["does_not_exist.py"], str(tmp_path))
    assert "not found" in ctx


def test_multiple_files(tmp_path):
    (tmp_path / "a.py").write_text("a = 1")
    (tmp_path / "b.py").write_text("b = 2")
    ctx = build_file_context(["a.py", "b.py"], str(tmp_path))
    assert "a = 1" in ctx
    assert "b = 2" in ctx


# --- build_prompt ---

def test_prompt_contains_spec():
    prompt = build_prompt("do the thing", "file contents", 1)
    assert "do the thing" in prompt


def test_prompt_iteration_1_no_retry_note():
    prompt = build_prompt("spec", "ctx", 1)
    assert "attempt" not in prompt.lower()


def test_prompt_iteration_2_has_retry_note():
    prompt = build_prompt("spec", "ctx", 2)
    assert "attempt #2" in prompt


# --- apply_edits ---

def test_apply_writes_file(tmp_path):
    edits = [FileEdit(path="src/foo.py", content="x = 42")]
    apply_edits(edits, str(tmp_path))
    assert (tmp_path / "src" / "foo.py").read_text() == "x = 42"


def test_apply_creates_missing_dirs(tmp_path):
    edits = [FileEdit(path="a/b/c/deep.py", content="pass")]
    apply_edits(edits, str(tmp_path))
    assert (tmp_path / "a" / "b" / "c" / "deep.py").exists()


def test_apply_returns_changed_paths(tmp_path):
    edits = [FileEdit(path="x.py", content=""), FileEdit(path="y.py", content="")]
    changed = apply_edits(edits, str(tmp_path))
    assert set(changed) == {"x.py", "y.py"}


def test_apply_overwrites_existing(tmp_path):
    f = tmp_path / "f.py"
    f.write_text("old")
    apply_edits([FileEdit(path="f.py", content="new")], str(tmp_path))
    assert f.read_text() == "new"
