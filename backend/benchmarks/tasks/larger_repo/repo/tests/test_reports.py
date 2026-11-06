from inventory.catalog import Catalog
from inventory.reports import low_stock, stock_value


def test_reports():
    catalog = Catalog()
    catalog.add("A1", "Widget", 2.5, on_hand=2)
    catalog.add("B2", "Gadget", 10, on_hand=20)
    assert low_stock(catalog) == ["A1"]
    assert stock_value(catalog) == 205
