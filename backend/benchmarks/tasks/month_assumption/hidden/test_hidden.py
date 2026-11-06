from datetime import date

import pytest
from acme.aging import whole_months_between
from acme.dates import month_bounds
from acme.payroll import daily_rate, period_end
from acme.quotas import prorated_quota
from acme.reports import monthly_total
from acme.retention import purge_before
from acme.subscriptions import next_renewal


@pytest.mark.parametrize("year,month,end", [
    (2025, 1, date(2025, 2, 1)), (2025, 2, date(2025, 3, 1)), (2024, 2, date(2024, 3, 1)),
    (2025, 4, date(2025, 5, 1)), (2025, 12, date(2026, 1, 1)),
])
def test_month_bounds(year, month, end):
    assert month_bounds(year, month) == (date(year, month, 1), end)


def test_february_report_leaves_out_march():
    assert monthly_total([(date(2025, 2, 28), 1), (date(2025, 3, 1), 2)], 2025, 2) == 1


@pytest.mark.parametrize("year,month,end", [(2025, 1, 31), (2025, 2, 28), (2024, 2, 29), (2025, 12, 31)])
def test_period_end(year, month, end):
    assert period_end(year, month) == date(year, month, end)


def test_daily_rate_uses_the_real_month():
    assert daily_rate(3100, 2025, 1) == 100.0
    assert daily_rate(2800, 2025, 2) == 100.0


@pytest.mark.parametrize("current,expected", [
    (date(2025, 1, 15), date(2025, 2, 15)), (date(2025, 1, 31), date(2025, 2, 28)),
    (date(2024, 1, 31), date(2024, 2, 29)), (date(2025, 3, 31), date(2025, 4, 30)),
    (date(2025, 12, 31), date(2026, 1, 31)), (date(2025, 2, 28), date(2025, 3, 28)),
])
def test_next_renewal(current, expected):
    assert next_renewal(current) == expected


@pytest.mark.parametrize("quota,year,month,start,expected", [
    (310, 2025, 1, 1, 310), (310, 2025, 1, 31, 10), (280, 2025, 2, 15, 140), (290, 2024, 2, 29, 10),
])
def test_prorated_quota(quota, year, month, start, expected):
    assert prorated_quota(quota, year, month, start) == expected


@pytest.mark.parametrize("start,end,months", [
    (date(2025, 1, 15), date(2025, 2, 15), 1), (date(2025, 1, 15), date(2025, 2, 14), 0),
    (date(2025, 1, 1), date(2025, 3, 1), 2), (date(2024, 12, 20), date(2025, 1, 20), 1),
    (date(2025, 1, 1), date(2025, 1, 31), 0),
])
def test_whole_months(start, end, months):
    assert whole_months_between(start, end) == months


def test_the_contractual_30_days_did_not_change():
    assert purge_before(date(2025, 3, 31)) == date(2025, 3, 1)
