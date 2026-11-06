from shop.money import format_money


def render(cart):
    lines = [f"{q} x {item.name}: {format_money(item.price_cents * q)}" for item, q in cart.lines]
    lines.append(f"Total: {format_money(cart.total_cents())}")
    return "\n".join(lines)
