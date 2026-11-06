from datetime import date

from acme.dates import days_in_month


def next_renewal(current):
    year, month = (current.year + 1, 1) if current.month == 12 else (current.year, current.month + 1)
    return date(year, month, min(current.day, days_in_month(year, month)))
