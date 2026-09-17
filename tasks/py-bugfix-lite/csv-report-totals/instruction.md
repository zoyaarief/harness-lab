The regional totals printed by `python report.py data/sales.csv` don't match the
finance team's numbers: east should be 350.00, north 120.50 and west 99.50.
Fix the bug in `report.py`.

Also, rows whose `amount` is empty or only whitespace must count as 0 (the region
still appears in the totals).

The project is in /app. Visible tests are in /app/tests; run them with `python -m pytest -q`. Hidden tests will check all of the behavior described above.
