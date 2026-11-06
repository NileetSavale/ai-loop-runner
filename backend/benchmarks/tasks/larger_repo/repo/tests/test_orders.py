import pytest
from inventory.catalog import Catalog
from inventory.errors import OutOfStock
from inventory.orders import Order


def test_second_order_cannot_take_reserved_units():
    catalog = Catalog()
    catalog.add("A1", "Widget", 2.5, on_hand=5)
    Order(catalog).add("A1", 4)
    with pytest.raises(OutOfStock):
        Order(catalog).add("A1", 2)
