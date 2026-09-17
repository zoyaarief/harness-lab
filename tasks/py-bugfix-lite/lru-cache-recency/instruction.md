`LRUCache` in `lru.py` does not behave like a least-recently-used cache: hot keys get
evicted. Fix it so that:
- reading a key with `get` marks it as most recently used;
- `put` on an existing key updates the value and marks it as most recently used;
- when the cache goes over capacity, the least recently used key is evicted;
- `key in cache` does not change recency.

The project is in /app. Visible tests are in /app/tests; run them with `python -m pytest -q`. Hidden tests will check all of the behavior described above.
