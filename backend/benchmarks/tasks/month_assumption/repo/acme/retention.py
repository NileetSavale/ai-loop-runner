from datetime import timedelta

# The contract says exactly 30 days, whatever the month
RETENTION = timedelta(days=30)


def purge_before(today):
    return today - RETENTION
