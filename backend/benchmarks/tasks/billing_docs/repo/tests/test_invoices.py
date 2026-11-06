from billing.invoices import upgrade_invoice


def test_annual_upgrade_uses_the_annual_rate():
    # (600 - 300) / 365 x 73 days = 60.00, plus 20% tax
    assert upgrade_invoice("annual_basic", "annual_pro", 73, "uk") == 72.0


def test_monthly_upgrade():
    assert upgrade_invoice("monthly_basic", "monthly_pro", 10, "uk") == 12.0
