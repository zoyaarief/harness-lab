from report import load_rows, totals_by_region


def test_sales_totals():
    rows = load_rows("data/sales.csv")
    assert totals_by_region(rows) == {"north": 120.5, "east": 350.0, "west": 99.5}
