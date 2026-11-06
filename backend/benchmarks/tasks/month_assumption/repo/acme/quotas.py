MONTH = 30


def prorated_quota(quota, year, month, start_day):
    """Share of a monthly quota for someone starting on start_day, rounded down."""
    return quota * (MONTH - start_day + 1) // MONTH
