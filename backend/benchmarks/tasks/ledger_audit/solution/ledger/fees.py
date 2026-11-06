from ledger.money import round_money

RATE = 0.015
MIN_FEE = 0.3
MAX_FEE = 25.0


def fee_for(amount):
    return round_money(max(MIN_FEE, min(abs(amount) * RATE, MAX_FEE)))
