def loyalty_points(cart):
    """One point per whole dollar spent."""
    return cart.total_cents() // 100
