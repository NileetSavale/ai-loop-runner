from datetime import date

from acme.dates import days_in_month


def period_end(year, month):
    """Last day of the pay period."""
    return date(year, month, days_in_month(year, month))


def daily_rate(monthly_salary, year, month):
    return round(monthly_salary / days_in_month(year, month), 2)
