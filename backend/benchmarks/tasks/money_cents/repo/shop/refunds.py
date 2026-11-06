def refund_amount(cart, percent):
    return round(cart.total() * percent / 100, 2)
