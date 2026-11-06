from inventory.stock import available


def low_stock(catalog, threshold=5):
    return sorted(p.sku for p in catalog.all() if available(p) < threshold)


def stock_value(catalog):
    return round(sum(p.price * p.on_hand for p in catalog.all()), 2)
