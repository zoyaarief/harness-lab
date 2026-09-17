import pytest

from inventory import OutOfStockError, Store


def test_remove_reduces_quantity():
    store = Store()
    store.add("A1", "Widget", 5)
    assert store.remove("A1", 2) == 3


def test_cannot_oversell():
    store = Store()
    store.add("A1", "Widget", 2)
    with pytest.raises(OutOfStockError):
        store.remove("A1", 3)
