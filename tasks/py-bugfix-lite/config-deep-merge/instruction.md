Loading `config/base.json` and then `config/prod.json` with
`configlib.load_layers` drops nested settings from the base file (for example
`database.pool_size`). Fix `configlib.merge(base, override)` so that:
- nested dicts are merged recursively;
- any non-dict value in `override` replaces the value in `base` (and a dict in
  `override` replaces a non-dict in `base`);
- neither input is modified, and the result shares no nested objects with the inputs.

The project is in /app. Visible tests are in /app/tests; run them with `python -m pytest -q`. Hidden tests will check all of the behavior described above.
