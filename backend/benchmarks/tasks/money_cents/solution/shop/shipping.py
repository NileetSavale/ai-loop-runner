FLAT_RATE_CENTS = 499
FREE_OVER_CENTS = 5000


def shipping_cents(cart):
    return 0 if cart.total_cents() >= FREE_OVER_CENTS else FLAT_RATE_CENTS
