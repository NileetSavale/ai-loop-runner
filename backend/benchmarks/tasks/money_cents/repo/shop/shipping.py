FLAT_RATE = 4.99
FREE_OVER = 50.0


def shipping_cost(cart):
    return 0.0 if cart.total() >= FREE_OVER else FLAT_RATE
