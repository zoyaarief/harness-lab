Add options to the `wordfreq.py` command-line tool (`python wordfreq.py PATH`):
- `--top N`: print only the N most frequent words (default: all).
- `--min-length L`: ignore words shorter than L characters, apostrophes included
  (default: 1).
- `--stopwords FILE`: ignore the words listed in FILE (one per line, case-insensitive).

Output lines are `word<TAB>count`, ordered by count (highest first) and then
alphabetically. Leading and trailing apostrophes are not part of a word (`'quoted'`
counts as `quoted`, while `don't` stays `don't`); `count_words(text)` must apply
this rule too. `main(argv)` takes the argument list, as it does now.

The project is in /app. Visible tests are in /app/tests; run them with `python -m pytest -q`. Hidden tests will check all of the behavior described above.
