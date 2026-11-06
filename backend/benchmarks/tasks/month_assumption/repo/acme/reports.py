from acme.dates import month_bounds


def monthly_total(transactions, year, month):
    start, end = month_bounds(year, month)
    return sum(amount for day, amount in transactions if start <= day < end)
