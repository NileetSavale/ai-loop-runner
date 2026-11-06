def money(amount):
    return f"${amount:,.2f}"


def order_line(product, quantity):
    return f"{quantity} x {product.name} @ {money(product.price)}"
