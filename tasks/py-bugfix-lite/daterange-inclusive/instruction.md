The scheduling report is missing the last day of every range and counts Saturdays
as business days. Fix `calendar_utils.py`:
- `daterange(start, end, step_days)` includes `end` when the steps land on it, and
  yields nothing if `start > end`.
- `daterange` raises `ValueError` if `step_days` is not positive.
- `business_days(start, end)` returns only Monday to Friday, inclusive of both ends.

The project is in /app. Visible tests are in /app/tests; run them with `python -m pytest -q`. Hidden tests will check all of the behavior described above.
