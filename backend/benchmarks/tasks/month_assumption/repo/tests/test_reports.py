from datetime import date

from acme.reports import monthly_total


def test_january_includes_the_31st():
    assert monthly_total([(date(2025, 1, 31), 5), (date(2025, 2, 1), 7)], 2025, 1) == 5
