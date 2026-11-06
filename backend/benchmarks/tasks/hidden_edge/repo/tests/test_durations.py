from durations import parse_duration


def test_single_units():
    assert parse_duration("90s") == 90
    assert parse_duration("2m") == 120


def test_hours_and_minutes():
    assert parse_duration("1h30m") == 5400
