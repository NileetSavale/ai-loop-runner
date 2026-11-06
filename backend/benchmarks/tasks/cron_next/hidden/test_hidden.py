from datetime import datetime as dt

import pytest
from cron import next_run


@pytest.mark.parametrize("expression,after,expected", [
    ("* * * * *", dt(2025, 1, 1, 0, 0, 30), dt(2025, 1, 1, 0, 1)),
    ("0 12 * * *", dt(2025, 1, 1, 12, 0), dt(2025, 1, 2, 12, 0)),
    ("30 9 * * 1-5", dt(2025, 1, 3, 10, 0), dt(2025, 1, 6, 9, 30)),
    ("0 0 1 * *", dt(2025, 1, 31, 12, 0), dt(2025, 2, 1)),
    ("0 0 1 1 *", dt(2025, 12, 31, 23, 59), dt(2026, 1, 1)),
    ("0 0 29 2 *", dt(2025, 3, 1), dt(2028, 2, 29)),
    ("*/15 * * * *", dt(2025, 1, 1, 10, 7), dt(2025, 1, 1, 10, 15)),
    ("0 */6 * * *", dt(2025, 1, 1, 5, 59), dt(2025, 1, 1, 6, 0)),
    ("5,10-12 0 * * *", dt(2025, 1, 1, 0, 10), dt(2025, 1, 1, 0, 11)),
    ("5,10-12 0 * * *", dt(2025, 1, 1, 0, 12), dt(2025, 1, 2, 0, 5)),
    ("10-20/5 * * * *", dt(2025, 1, 1, 10, 10), dt(2025, 1, 1, 10, 15)),
    ("10-20/5 * * * *", dt(2025, 1, 1, 10, 20), dt(2025, 1, 1, 11, 10)),
    ("0 0 * * 0", dt(2025, 1, 1), dt(2025, 1, 5)),
    ("0 0 * * 7", dt(2025, 1, 1), dt(2025, 1, 5)),
    ("0 0 * * 6-7", dt(2025, 1, 5), dt(2025, 1, 11)),
    ("0 0 13 * 5", dt(2025, 1, 1), dt(2025, 1, 3)),
    ("0 0 13 * 5", dt(2025, 1, 10), dt(2025, 1, 13)),
    ("0 0 */2 * 5", dt(2025, 1, 1), dt(2025, 1, 3)),
    ("0 0 */2 * 5", dt(2025, 1, 3), dt(2025, 1, 17)),
])
def test_next_run(expression, after, expected):
    assert next_run(expression, after) == expected


@pytest.mark.parametrize("expression", [
    "", "* * * *", "* * * * * *", "60 * * * *", "* 24 * * *", "* * 0 * *", "* * 32 * *", "* * * 0 *", "* * * 13 *",
    "* * * * 8", "*/0 * * * *", "1-5/0 * * * *", "5-1 * * * *", "a * * * *", "1, * * * *", ",1 * * * *", "1-* * * * *",
    "*/ * * * *", "-1 * * * *", "1-2-3 * * * *", "1/2/3 * * * *",
])
def test_malformed(expression):
    with pytest.raises(ValueError):
        next_run(expression, dt(2025, 1, 1))


@pytest.mark.parametrize("expression", ["0 0 30 2 *", "0 0 31 4 *"])
def test_impossible_dates(expression):
    with pytest.raises(ValueError):
        next_run(expression, dt(2025, 1, 1))
