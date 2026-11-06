from pathlib import Path

import pytest
import csv_parser
from csv_parser import parse_csv


def test_does_not_use_the_csv_module():
    source = Path(csv_parser.__file__).read_text()
    assert "import csv" not in source and "from csv" not in source


@pytest.mark.parametrize("text,rows", [
    ("", []),
    ("a", [["a"]]),
    ("a\n", [["a"]]),
    ("a\r\nb\r\n", [["a"], ["b"]]),
    ("a\n\nb", [["a"], [""], ["b"]]),
    ("\n", [[""]]),
    (",", [["", ""]]),
    ("a,\n", [["a", ""]]),
    ('"say ""hi"""', [['say "hi"']]),
    ('""', [[""]]),
    ('"",""', [["", ""]]),
    ('"line1\nline2",x', [["line1\nline2", "x"]]),
    ('"line1\r\nline2"\r\ny', [["line1\r\nline2"], ["y"]]),
    ('a"b,c"', [['a"b', 'c"']]),
    (" a , b ", [[" a ", " b "]]),
    ('"a",b\n"c,d"\n', [["a", "b"], ["c,d"]]),
])
def test_valid(text, rows):
    assert parse_csv(text) == rows


@pytest.mark.parametrize("text", ['"abc', 'a,"b', '"a"b', '"a" ,b', '"a""'])
def test_malformed_raises(text):
    with pytest.raises(ValueError):
        parse_csv(text)
