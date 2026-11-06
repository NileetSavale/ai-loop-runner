def loyalty_points(cart):
    """One point per whole dollar spent."""
    return int(cart.total())
