`python summarize.py` should read `logs/server.log` and write `error_counts.json`
in /app, but it crashes and its counting is wrong. Fix `summarize.py`.

Rules:
- An ERROR entry is a line whose log level (the field right after the timestamp) is
  exactly `ERROR`. Lines at other levels and indented continuation lines (such as
  traceback lines) never count, even if they contain the text `ERROR`.
- Count ERROR entries by the value of their `code=` field. Entries without a
  `code=` field are counted under `UNKNOWN`.
- `summarize(path)` returns `{"total_errors": <int>, "by_code": {<code>: <count>}}`,
  and running the script writes that same object as JSON to `error_counts.json`.

The log file is large; avoid printing all of it.

The project is in /app. Visible tests are in /app/tests; run them with `python -m pytest -q`. Hidden tests will check all of the behavior described above.
