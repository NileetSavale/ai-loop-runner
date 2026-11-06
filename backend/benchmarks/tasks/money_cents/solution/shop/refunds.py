def refund_cents(cart, percent):
    return (cart.total_cents() * percent + 50) // 100
