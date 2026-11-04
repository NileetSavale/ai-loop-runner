import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.agent import parse_file_blocks
from providers.base import calculate_cost
from types import SimpleNamespace


# --- parse_file_blocks ---

def test_parse_single_file():
    text = '<file path="src/main.py">\nprint("hello")\n</file>'
    edits = parse_file_blocks(text)
    assert len(edits) == 1
    assert edits[0].path == "src/main.py"
    assert edits[0].content == 'print("hello")'


def test_parse_multiple_files():
    text = '''
<file path="a.py">
x = 1
</file>
some text in between
<file path="b.py">
y = 2
</file>
'''
    edits = parse_file_blocks(text)
    assert len(edits) == 2
    assert edits[0].path == "a.py"
    assert edits[1].path == "b.py"


def test_parse_no_files():
    assert parse_file_blocks("No file blocks here.") == []


def test_parse_preserves_multiline_content():
    text = '<file path="x.py">\ndef foo():\n    return 42\n</file>'
    edits = parse_file_blocks(text)
    assert "def foo():" in edits[0].content
    assert "return 42" in edits[0].content


def test_parse_nested_path():
    text = '<file path="src/routes/auth.py">\npass\n</file>'
    assert parse_file_blocks(text)[0].path == "src/routes/auth.py"


# --- calculate_cost ---

def test_cost_sonnet():
    assert calculate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000) == 3.00 + 15.00


def test_cost_haiku_cheap():
    assert calculate_cost("claude-haiku-4-5-20251001", 1_000_000, 1_000_000) == 0.80 + 4.00


def test_cost_zero_tokens():
    assert calculate_cost("claude-sonnet-4-6", 0, 0) == 0.0


def test_cost_unknown_model_falls_back_to_sonnet():
    assert calculate_cost("unknown-model", 1_000_000, 0) == 3.00


def test_cost_small_realistic():
    cost = calculate_cost("claude-sonnet-4-6", 10_000, 2_000)
    assert abs(cost - (0.03 + 0.03)) < 0.001


def test_cost_openai_gpt4o():
    assert calculate_cost("gpt-4o", 1_000_000, 1_000_000) == 2.50 + 10.00


def test_parse_keeps_last_version_of_a_repeated_file():
    text = '<file path="a.py">first</file> wait, let me fix that <file path="a.py">second</file><file path="b.py">b</file>'
    edits = parse_file_blocks(text)
    assert [(e.path, e.content) for e in edits] == [("a.py", "second"), ("b.py", "b")]
