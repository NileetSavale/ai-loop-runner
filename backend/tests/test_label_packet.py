from benchmarks.label_packet import excerpt

PYTEST = """>>>>> Start Test Output
____ test_polyval[timedelta-False] ____
    assert actual == expected
E   NameError: name 'x' is not defined
FAILED xarray/tests/test_computation.py::test_polyval[timedelta-False] - NameError
=== 1 failed ==="""

UNITTEST = """>>>>> Start Test Output
test_ok (a.B) ... ok
======================================================================
FAIL: test_simplify_regex (admin_docs.test_views.AdminDocViewFunctionsTests)
AssertionError: '/<a>' != '/<a>/'"""


def test_excerpt_starts_at_each_failed_tests_report():
    text = excerpt(PYTEST, ["xarray/tests/test_computation.py::test_polyval[timedelta-False]"])
    assert text.startswith("____ test_polyval") and "NameError: name 'x'" in text
    text = excerpt(UNITTEST, ["test_simplify_regex (admin_docs.test_views.AdminDocViewFunctionsTests)"])
    assert text.startswith("FAIL: test_simplify_regex") and "AssertionError" in text and "test_ok" not in text


def test_excerpt_shows_the_errors_when_the_failed_tests_never_ran():
    output = ">>>>> Start Test Output\ntests/t.py:32: in <module>\nE   ImportError: cannot import name 'f'\n"
    assert "ImportError" in excerpt(output, ["tests/t.py::test_dot_files[x]"])
