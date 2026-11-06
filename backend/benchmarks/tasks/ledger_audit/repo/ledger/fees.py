from ledger.money import round_money

RATE = 0.015
MAX_FEE = 25.0


def fee_for(amount):
    return round_money(min(amount * RATE, MAX_FEE))
