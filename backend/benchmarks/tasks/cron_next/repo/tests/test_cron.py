from datetime import datetime

from cron import next_run


def test_every_minute():
    assert next_run("* * * * *", datetime(2025, 1, 1, 0, 0)) == datetime(2025, 1, 1, 0, 1)


def test_daily():
    assert next_run("30 9 * * *", datetime(2025, 1, 1, 10, 0)) == datetime(2025, 1, 2, 9, 30)
