from csv_parser import parse_csv


def test_plain_rows():
    assert parse_csv("a,b\nc,d\n") == [["a", "b"], ["c", "d"]]


def test_quoted_comma():
    assert parse_csv('"a,b",c') == [["a,b", "c"]]
