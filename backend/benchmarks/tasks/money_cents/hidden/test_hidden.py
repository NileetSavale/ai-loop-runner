import pytest
from shop.cart import Cart
from shop.items import Item
from shop.loyalty import loyalty_points
from shop.money import format_money
from shop.receipt import render
from shop.refunds import refund_cents
from shop.shipping import shipping_cents


def cart_of(cents, quantity=1):
    cart = Cart()
    cart.add(Item("Tea", cents), quantity)
    return cart


def test_item_has_price_cents():
    assert Item("Tea", 120).price_cents == 120
    with pytest.raises(TypeError):
        Item(name="Tea", price=1.2)


def test_totals_are_ints():
    total = cart_of(199, 3).total_cents()
    assert total == 597 and isinstance(total, int)


@pytest.mark.parametrize("cents,text", [(120, "$1.20"), (5, "$0.05"), (0, "$0.00"), (123456, "$1,234.56"), (-120, "-$1.20")])
def test_format_money(cents, text):
    assert format_money(cents) == text


def test_receipt_text_is_unchanged():
    assert render(cart_of(60, 2)) == "2 x Tea: $1.20\nTotal: $1.20"


@pytest.mark.parametrize("cents,percent,expected", [(1000, 50, 500), (101, 50, 51), (125, 10, 13), (333, 100, 333), (5, 0, 0)])
def test_refund_rounds_halves_up(cents, percent, expected):
    refund = refund_cents(cart_of(cents), percent)
    assert refund == expected and isinstance(refund, int)


@pytest.mark.parametrize("cents,points", [(199, 1), (200, 2), (99, 0)])
def test_one_point_per_whole_dollar(cents, points):
    assert loyalty_points(cart_of(cents)) == points


@pytest.mark.parametrize("cents,expected", [(4999, 499), (5000, 0), (5001, 0)])
def test_shipping(cents, expected):
    assert shipping_cents(cart_of(cents)) == expected
