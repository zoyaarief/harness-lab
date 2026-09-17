The `retry` decorator in `resilience.py` swallows errors. Make it follow its contract:
- `times` is the total number of attempts; `retry(times=0)` (or less) raises
  `ValueError` immediately.
- Only exceptions matching `exceptions` (including subclasses) are retried; any
  other exception propagates immediately without another attempt.
- If every attempt fails, the last exception is re-raised.
- Between attempts it calls `sleep(delay)`; it never sleeps after the final attempt.
- The wrapper preserves the wrapped function's `__name__` and `__doc__`.

The project is in /app. Visible tests are in /app/tests; run them with `python -m pytest -q`. Hidden tests will check all of the behavior described above.
