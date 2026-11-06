from decimal import Decimal, ROUND_HALF_UP

from billing.plans import PLANS
from billing.proration import upgrade_charge
from billing.tax import tax_rate


def invoice_total(subtotal, discount_percent=0, tax=0.0):
    # Via repr, so a value like 2.675 means 2.675 and not its nearest binary float. Long fractions are rounded
    # to 10 places first, so float noise such as 53.54999999999 can't change the result.
    amount = Decimal(repr(round(float(subtotal), 10)))
    amount = amount * (100 - Decimal(repr(discount_percent))) / 100
    amount = amount * (1 + Decimal(repr(tax)))
    return float(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def upgrade_invoice(old_name, new_name, days_remaining, region, discount_percent=0):
    charge = upgrade_charge(PLANS[old_name], PLANS[new_name], days_remaining)
    return invoice_total(charge, discount_percent, tax_rate(region))
