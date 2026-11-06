from pricing import apply_discount


class Cart:
    def __init__(self):
        self.prices = []

    def add(self, price):
        self.prices.append(price)

    def total(self, discount_percent=0):
        return apply_discount(sum(self.prices), discount_percent)
