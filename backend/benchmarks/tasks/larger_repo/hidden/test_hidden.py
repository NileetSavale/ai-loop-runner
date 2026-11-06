import pytest
from inventory.catalog import Catalog
from inventory.errors import OutOfStock
from inventory.orders import Order
from inventory.stock import receive, release, reserve


@pytest.fixture
def widget():
    return Catalog().add("A1", "Widget", 2.5, on_hand=5)


def test_can_reserve_exactly_what_is_left(widget):
    reserve(widget, 3)
    reserve(widget, 2)
    assert widget.reserved == 5


def test_failed_reservation_changes_nothing(widget):
    reserve(widget, 4)
    with pytest.raises(OutOfStock):
        reserve(widget, 2)
    assert widget.reserved == 4


def test_released_and_received_units_become_available(widget):
    reserve(widget, 5)
    release(widget, 2)
    reserve(widget, 2)
    receive(widget, 1)
    reserve(widget, 1)
    assert widget.reserved == 6


def test_order_total_still_works():
    catalog = Catalog()
    catalog.add("A1", "Widget", 2.5, on_hand=5)
    order = Order(catalog)
    order.add("A1", 2)
    assert order.total() == 5
