from inventory.errors import OutOfStock


def available(product):
    return product.on_hand - product.reserved


def reserve(product, quantity):
    if quantity > available(product):
        raise OutOfStock(product.sku)
    product.reserved += quantity


def release(product, quantity):
    product.reserved = max(0, product.reserved - quantity)


def receive(product, quantity):
    product.on_hand += quantity
