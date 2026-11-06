class Cart:
    def __init__(self):
        self.lines = []

    def add(self, item, quantity=1):
        self.lines.append((item, quantity))

    def total(self):
        return sum(item.price * quantity for item, quantity in self.lines)
