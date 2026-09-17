import pytest

from lru import LRUCache


def test_basic_eviction_order():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    assert "a" not in cache
    assert cache.get("b") == 2 and cache.get("c") == 3


def test_get_refreshes_recency():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1
    cache.put("c", 3)
    assert "b" not in cache and cache.get("a") == 1


def test_put_existing_refreshes_and_updates():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("a", 10)
    cache.put("c", 3)
    assert "b" not in cache and cache.get("a") == 10
    assert len(cache) == 2


def test_contains_does_not_refresh():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert "a" in cache
    cache.put("c", 3)
    assert "a" not in cache


def test_get_missing_returns_default():
    cache = LRUCache(1)
    assert cache.get("x") is None and cache.get("x", 5) == 5


def test_capacity_one():
    cache = LRUCache(1)
    cache.put("a", 1)
    cache.put("b", 2)
    assert "a" not in cache and cache.get("b") == 2


def test_invalid_capacity():
    with pytest.raises(ValueError):
        LRUCache(0)
