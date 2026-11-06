from shop.cart import Cart
from shop.items import Item


def test_total_has_no_float_errors():
    cart = Cart()
    cart.add(Item("Tea", 10), 3)
    assert cart.total_cents() == 30
