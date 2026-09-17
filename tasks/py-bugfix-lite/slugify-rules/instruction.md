`slugify` in `text_utils.py` produces broken URL slugs. For example,
`slugify("  Hello,  World!! ")` should return `hello-world`.

Requirements:
- Slugs contain only lowercase ASCII letters, digits and single hyphens.
- Slugs never start or end with a hyphen.
- Accented letters become their base letter (`é` -> `e`, `Ç` -> `c`); other
  non-ASCII characters are dropped.
- The result is at most `max_length` characters and must not end with a hyphen
  after truncation.

The project is in /app. Visible tests are in /app/tests; run them with `python -m pytest -q`. Hidden tests will check all of the behavior described above.
