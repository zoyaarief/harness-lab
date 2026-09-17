`schema_check.validate` reports errors at the wrong location: every nested error says
`$` instead of its real path. It also accepts booleans where an integer or number is
expected. Fix it so that:
- error paths look like `$.owner.email` for object properties and `$.tags[2]` for
  array elements, and they combine (`$.owner.roles[1]`);
- `true` / `false` are rejected for `integer` and `number` but still accepted for
  `boolean`.
Keep the existing error message formats and error order.

The project is in /app. Visible tests are in /app/tests; run them with `python -m pytest -q`. Hidden tests will check all of the behavior described above.
