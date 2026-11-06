from datetime import timedelta

BILLING_INTERVAL = timedelta(days=30)


def next_renewal(current):
    return current + BILLING_INTERVAL
