from datetime import date, timedelta


def period_end(year, month):
    """Last day of the pay period."""
    return date(year, month, 1) + timedelta(29)


def daily_rate(monthly_salary, year, month):
    days = (period_end(year, month) - date(year, month, 1)).days + 1
    return round(monthly_salary / days, 2)
