class Cart:
    def __init__(self):
        self.lines = []

    def add(self, item, quantity=1):
        self.lines.append((item, quantity))

    def total_cents(self):
        return sum(item.price_cents * quantity for item, quantity in self.lines)
