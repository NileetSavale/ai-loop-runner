from acme.dates import days_in_month


def prorated_quota(quota, year, month, start_day):
    """Share of a monthly quota for someone starting on start_day, rounded down."""
    days = days_in_month(year, month)
    return quota * (days - start_day + 1) // days
