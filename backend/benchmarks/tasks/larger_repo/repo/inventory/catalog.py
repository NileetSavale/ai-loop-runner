from inventory.errors import UnknownProduct
from inventory.models import Product


class Catalog:
    def __init__(self):
        self._products = {}

    def add(self, sku, name, price, on_hand=0):
        self._products[sku] = Product(sku, name, price, on_hand)
        return self._products[sku]

    def get(self, sku):
        if sku not in self._products:
            raise UnknownProduct(sku)
        return self._products[sku]

    def all(self):
        return list(self._products.values())
