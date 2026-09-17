Customers were able to order more units than we have in stock. In the `inventory`
package, `Store.remove(sku, quantity)` must:
- raise `OutOfStockError` (from `inventory.errors`) when asked to remove more units
  than are in stock, leaving the quantity unchanged;
- raise `UnknownItemError` when the SKU was never added;
- raise `ValueError` when `quantity` is not positive;
- otherwise subtract the quantity and return the remaining stock.

The project is in /app. Visible tests are in /app/tests; run them with `python -m pytest -q`. Hidden tests will check all of the behavior described above.
