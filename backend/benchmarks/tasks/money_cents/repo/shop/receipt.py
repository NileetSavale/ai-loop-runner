from shop.money import format_money


def render(cart):
    lines = [f"{q} x {item.name}: {format_money(item.price * q)}" for item, q in cart.lines]
    lines.append(f"Total: {format_money(cart.total())}")
    return "\n".join(lines)
