from ledger.errors import NoRate
from ledger.money import round_money


def rate_on(rates, day):
    """rates is a list of (date, rate)."""
    earlier = [(d, r) for d, r in rates if d < day]
    if not earlier:
        raise NoRate(day)
    return max(earlier)[1]


def convert(amount, rates, day):
    return round_money(amount * rate_on(rates, day))
