`paginate` in `pagination.py` returns the wrong items and page counts: users report
that the first page is skipped and the last partial page is missing. Fix it.
- Pages are 1-indexed.
- `total_pages` is the number of pages needed to show every item (0 for an empty list).
- Raise `ValueError` when `per_page < 1`, when `page < 1`, or when `page` is past the
  last page. Page 1 of an empty list is valid and returns no items.
- `has_next` / `has_prev` say whether a following / preceding page exists.

The visible test suite is large and prints a lot on failure.

The project is in /app. Visible tests are in /app/tests; run them with `python -m pytest -q`. Hidden tests will check all of the behavior described above.
