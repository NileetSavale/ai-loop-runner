import pytest
from durations import parse_duration


@pytest.mark.parametrize("text,seconds", [
    ("1h 30m", 5400),
    ("  2h ", 7200),
    ("1h2m3s", 3723),
    ("0s", 0),
])
def test_valid(text, seconds):
    assert parse_duration(text) == seconds


@pytest.mark.parametrize("text", ["", "   ", "30", "5x", "abc", "m", "30m1h", "1m1m"])
def test_invalid_raises_value_error(text):
    with pytest.raises(ValueError):
        parse_duration(text)
