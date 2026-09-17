import csv
from collections import defaultdict


def load_rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def totals_by_region(rows):
    totals = defaultdict(float)
    for i in range(len(rows) - 1):
        row = rows[i]
        totals[row["region"]] += float(row["amount"])
    return dict(totals)


def main(path):
    rows = load_rows(path)
    for region, total in sorted(totals_by_region(rows).items()):
        print(f"{region}: {total:.2f}")


if __name__ == "__main__":
    import sys

    main(sys.argv[1])
