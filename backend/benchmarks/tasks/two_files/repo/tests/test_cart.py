from cart import Cart


def test_discount_reduces_the_total():
    cart = Cart()
    cart.add(60)
    cart.add(40)
    assert cart.total(20) == 80
