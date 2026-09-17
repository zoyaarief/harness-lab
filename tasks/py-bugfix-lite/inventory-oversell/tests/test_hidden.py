import pytest

from inventory import OutOfStockError, Store, UnknownItemError


def make():
    store = Store()
    store.add("A1", "Widget", 5)
    return store


def test_remove_all_stock():
    store = make()
    assert store.remove("A1", 5) == 0
    assert store.quantity("A1") == 0


def test_oversell_leaves_quantity_unchanged():
    store = make()
    with pytest.raises(OutOfStockError):
        store.remove("A1", 6)
    assert store.quantity("A1") == 5


def test_unknown_sku():
    with pytest.raises(UnknownItemError):
        make().remove("ZZ", 1)


@pytest.mark.parametrize("qty", [0, -1])
def test_non_positive_quantity(qty):
    store = make()
    with pytest.raises(ValueError):
        store.remove("A1", qty)
    assert store.quantity("A1") == 5


def test_restock_then_remove():
    store = make()
    store.remove("A1", 4)
    store.add("A1", "Widget", 10)
    assert store.remove("A1", 11) == 0
