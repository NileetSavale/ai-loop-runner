from billing.plans import PLANS
from billing.proration import upgrade_charge
from billing.tax import tax_rate


def invoice_total(subtotal, discount_percent=0, tax=0.0):
    tax_amount = subtotal * tax
    discounted = subtotal * (100 - discount_percent) / 100
    return round(discounted + tax_amount, 2)


def upgrade_invoice(old_name, new_name, days_remaining, region, discount_percent=0):
    charge = upgrade_charge(PLANS[old_name], PLANS[new_name], days_remaining)
    return invoice_total(charge, discount_percent, tax_rate(region))
