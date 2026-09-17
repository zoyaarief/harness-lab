from .models import Item


class Store:
    def __init__(self):
        self._items: dict[str, Item] = {}

    def add(self, sku, name, quantity):
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        item = self._items.get(sku)
        if item is None:
            self._items[sku] = Item(sku, name, quantity)
        else:
            item.quantity += quantity

    def remove(self, sku, quantity):
        item = self._items[sku]
        item.quantity -= quantity
        return item.quantity

    def quantity(self, sku):
        return self._items[sku].quantity
