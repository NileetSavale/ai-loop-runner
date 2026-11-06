from inventory.stock import reserve


class Order:
    def __init__(self, catalog):
        self.catalog = catalog
        self.lines = []

    def add(self, sku, quantity):
        product = self.catalog.get(sku)
        reserve(product, quantity)
        self.lines.append((product, quantity))

    def total(self):
        return round(sum(p.price * q for p, q in self.lines), 2)
