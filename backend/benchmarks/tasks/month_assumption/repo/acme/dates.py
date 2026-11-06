from datetime import date, timedelta


def month_bounds(year, month):
    """(first day, first day after the month)."""
    start = date(year, month, 1)
    return start, start + timedelta(days=30)
