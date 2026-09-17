class InventoryError(Exception):
    """Base class for inventory errors."""


class OutOfStockError(InventoryError):
    """Raised when removing more units than are in stock."""


class UnknownItemError(InventoryError, KeyError):
    """Raised when a SKU has never been added."""
