import pytest
from billing.invoices import invoice_total, upgrade_invoice
from billing.plans import PLANS
from billing.proration import upgrade_charge
from billing.tax import tax_rate


def test_tax_is_calculated_after_the_discount():
    assert invoice_total(100, 10, 0.2) == 108.0


@pytest.mark.parametrize("subtotal,expected", [(0.125, 0.13), (2.675, 2.68), (1.005, 1.01)])
def test_halves_round_up(subtotal, expected):
    assert invoice_total(subtotal) == expected


def test_no_rounding_before_the_last_step():
    assert invoice_total(0.33, 50, 0.5) == 0.25  # 0.165 x 1.5 = 0.2475


def test_plans_with_different_periods_are_refused():
    with pytest.raises(ValueError):
        upgrade_charge(PLANS["monthly_basic"], PLANS["annual_pro"], 10)
    with pytest.raises(ValueError):
        upgrade_invoice("monthly_basic", "annual_pro", 10, "uk")


def test_unknown_region_is_an_error():
    with pytest.raises((KeyError, ValueError)):
        tax_rate("mars")
    with pytest.raises((KeyError, ValueError)):
        upgrade_invoice("annual_basic", "annual_pro", 73, "mars")


def test_known_rates_still_work():
    assert tax_rate("de") == 0.19


def test_full_upgrade_with_discount():
    # 60.00, less 25% = 45.00, plus 19% tax
    assert upgrade_invoice("annual_basic", "annual_pro", 73, "de", 25) == 53.55
