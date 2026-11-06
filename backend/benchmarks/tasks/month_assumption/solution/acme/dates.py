from calendar import monthrange
from datetime import date, timedelta


def days_in_month(year, month):
    return monthrange(year, month)[1]


def month_bounds(year, month):
    """(first day, first day after the month)."""
    start = date(year, month, 1)
    return start, start + timedelta(days=days_in_month(year, month))
