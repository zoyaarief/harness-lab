import csv

from report import load_rows, totals_by_region


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "region", "amount"])
        writer.writerows(rows)


def test_sales_file():
    assert totals_by_region(load_rows("data/sales.csv")) == {"north": 120.5, "east": 350.0, "west": 99.5}


def test_single_row(tmp_path):
    path = tmp_path / "one.csv"
    write_csv(path, [["2026-01-01", "south", "5.25"]])
    assert totals_by_region(load_rows(path)) == {"south": 5.25}


def test_empty_amount_counts_as_zero(tmp_path):
    path = tmp_path / "blank.csv"
    write_csv(path, [["2026-01-01", "south", ""], ["2026-01-02", "north", "3"], ["2026-01-03", "south", "  "]])
    assert totals_by_region(load_rows(path)) == {"south": 0.0, "north": 3.0}


def test_no_rows(tmp_path):
    path = tmp_path / "none.csv"
    write_csv(path, [])
    assert totals_by_region(load_rows(path)) == {}
