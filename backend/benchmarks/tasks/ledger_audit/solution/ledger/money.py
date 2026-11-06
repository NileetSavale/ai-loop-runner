from decimal import Decimal, ROUND_HALF_UP


def round_money(amount):
    # Via repr, so 2.675 means 2.675 and not its nearest binary float
    return float(Decimal(repr(round(float(amount), 10))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
