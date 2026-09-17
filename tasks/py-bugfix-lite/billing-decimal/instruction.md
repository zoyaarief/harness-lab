Customers are charged amounts that don't add up. Fix `billing.py` using exact
decimal arithmetic:
- `split_bill(total, people)` returns `people` amounts as strings with two decimals
  that add up exactly to `total`. Leftover cents go to the first people in the list,
  one cent each: `split_bill("100.00", 3)` returns `["33.34", "33.33", "33.33"]`.
  It raises `ValueError` if `people` is less than 1.
- `apply_tax(amount, rate)` returns `amount * (1 + rate)` rounded half-up to cents,
  as a string: `apply_tax("1.005", "0")` returns `"1.01"`.

The project is in /app. Visible tests are in /app/tests; run them with `python -m pytest -q`. Hidden tests will check all of the behavior described above.
