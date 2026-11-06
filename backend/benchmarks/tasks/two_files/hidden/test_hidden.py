import pytest
from cart import Cart
from pricing import apply_discount


def test_no_discount_keeps_the_total():
    cart = Cart()
    cart.add(10)
    assert cart.total() == 10


def test_full_discount_is_free():
    assert apply_discount(50, 100) == 0


def test_rounds_to_two_places():
    assert apply_discount(9.99, 33) == 6.69


@pytest.mark.parametrize("percent", [-1, 101])
def test_invalid_percent_raises(percent):
    with pytest.raises(ValueError):
        apply_discount(10, percent)
