"""Generate the py-bugfix-lite Harbor dataset in tasks/py-bugfix-lite/.

Each task is a small Python project with a bug or a missing feature. The agent sees
the project and its visible tests in /app. The verifier runs hidden tests from /tests.
Every task image starts from the same two layers, so the dataset costs little disk.

    uv run python scripts/make_py_bugfix_lite.py
    uv run python scripts/check_tasks.py      # buggy code fails, reference fix passes
"""

import shutil
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "tasks" / "py-bugfix-lite"


def D(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


DOCKERFILE = D("""
    FROM python:3.12-slim
    RUN pip install --no-cache-dir pytest==8.4.1
    WORKDIR /app
    COPY app/ /app/
    """)

PYTEST_INI = D("""
    [pytest]
    pythonpath = .
    testpaths = tests
    addopts = -p no:cacheprovider
    """)

TEST_SH = D("""
    #!/bin/bash
    # Hidden tests run from /app so relative data paths resolve.
    mkdir -p /logs/verifier
    cd /app
    PYTHONPATH=/app python -m pytest -q -p no:cacheprovider /tests/test_hidden.py
    if [ $? -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
    """)

SOLVE_SH = D("""
    #!/bin/bash
    # Reference solution: copy the fixed files over the project.
    set -e
    cp -r "$(dirname "$0")/fixed/." /app/
    """)

TASK_TOML = D("""
    schema_version = "1.4"
    artifacts = []

    [metadata]
    difficulty = "{difficulty}"
    category = "{category}"

    [verifier]
    timeout_sec = 180.0
    collect = []

    [verifier.env]

    [agent]
    timeout_sec = 3600.0

    [environment]
    network_mode = "public"
    build_timeout_sec = 600.0
    os = "linux"
    cpus = 1
    memory_mb = 1024
    mcp_servers = []

    [environment.env]

    [solution.env]
    """)

INSTRUCTION_FOOTER = (
    "\n\nThe project is in /app. Visible tests are in /app/tests; run them with "
    "`python -m pytest -q`. Hidden tests will check all of the behavior described above.\n"
)

TASKS: list[dict] = []


def task(name, *, difficulty, category, instruction, files, fixed, hidden, build=None):
    TASKS.append(
        dict(
            name=name,
            difficulty=difficulty,
            category=category,
            instruction=D(instruction).strip(),
            files={k: D(v) for k, v in files.items()},
            fixed={k: D(v) for k, v in fixed.items()},
            hidden=D(hidden),
            build=D(build) if build else None,
        )
    )


# ---------------------------------------------------------------------------
task(
    "csv-report-totals",
    difficulty="easy",
    category="bugfix",
    instruction="""
        The regional totals printed by `python report.py data/sales.csv` don't match the
        finance team's numbers: east should be 350.00, north 120.50 and west 99.50.
        Fix the bug in `report.py`.

        Also, rows whose `amount` is empty or only whitespace must count as 0 (the region
        still appears in the totals).
        """,
    files={
        "report.py": r'''
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
            ''',
        "data/sales.csv": """
            date,region,amount
            2026-01-02,north,100.00
            2026-01-02,east,200.00
            2026-01-03,west,99.50
            2026-01-04,north,20.50
            2026-01-05,east,150.00
            """,
        "tests/test_report.py": r'''
            from report import load_rows, totals_by_region


            def test_sales_totals():
                rows = load_rows("data/sales.csv")
                assert totals_by_region(rows) == {"north": 120.5, "east": 350.0, "west": 99.5}
            ''',
    },
    fixed={
        "report.py": r'''
            import csv
            from collections import defaultdict


            def load_rows(path):
                with open(path, newline="") as f:
                    return list(csv.DictReader(f))


            def totals_by_region(rows):
                totals = defaultdict(float)
                for row in rows:
                    amount = row["amount"].strip()
                    totals[row["region"]] += float(amount) if amount else 0.0
                return dict(totals)


            def main(path):
                rows = load_rows(path)
                for region, total in sorted(totals_by_region(rows).items()):
                    print(f"{region}: {total:.2f}")


            if __name__ == "__main__":
                import sys

                main(sys.argv[1])
            ''',
    },
    hidden=r'''
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
        ''',
)

# ---------------------------------------------------------------------------
task(
    "slugify-rules",
    difficulty="easy",
    category="bugfix",
    instruction="""
        `slugify` in `text_utils.py` produces broken URL slugs. For example,
        `slugify("  Hello,  World!! ")` should return `hello-world`.

        Requirements:
        - Slugs contain only lowercase ASCII letters, digits and single hyphens.
        - Slugs never start or end with a hyphen.
        - Accented letters become their base letter (`é` -> `e`, `Ç` -> `c`); other
          non-ASCII characters are dropped.
        - The result is at most `max_length` characters and must not end with a hyphen
          after truncation.
        """,
    files={
        "text_utils.py": r'''
            import re
            import unicodedata


            def slugify(text: str, max_length: int = 50) -> str:
                """Convert text to a URL slug: lowercase ASCII words joined by single hyphens."""
                text = unicodedata.normalize("NFKD", text)
                text = text.lower()
                text = re.sub(r"[^a-z0-9]", "-", text)
                return text[:max_length]
            ''',
        "tests/test_text_utils.py": r'''
            from text_utils import slugify


            def test_basic_title():
                assert slugify("Hello World") == "hello-world"


            def test_punctuation_and_spaces():
                assert slugify("  Hello,  World!! ") == "hello-world"
            ''',
    },
    fixed={
        "text_utils.py": r'''
            import re
            import unicodedata


            def slugify(text: str, max_length: int = 50) -> str:
                """Convert text to a URL slug: lowercase ASCII words joined by single hyphens."""
                text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
                text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
                return text[:max_length].rstrip("-")
            ''',
    },
    hidden=r'''
        import pytest

        from text_utils import slugify


        @pytest.mark.parametrize(
            "text,expected",
            [
                ("Hello World", "hello-world"),
                ("  Héllo,  World!! ", "hello-world"),
                ("Crème brûlée", "creme-brulee"),
                ("Python 3.12 Release", "python-3-12-release"),
                ("---", ""),
                ("", ""),
                ("ÅNGSTRÖM units", "angstrom-units"),
                ("Ça va? Oui — très bien! 100%", "ca-va-oui-tres-bien-100"),
            ],
        )
        def test_slugify(text, expected):
            assert slugify(text) == expected


        def test_max_length():
            assert slugify("a" * 60) == "a" * 50


        def test_no_trailing_hyphen_after_truncation():
            assert slugify("hello world foo", max_length=6) == "hello"
        ''',
)

# ---------------------------------------------------------------------------
task(
    "inventory-oversell",
    difficulty="medium",
    category="bugfix",
    instruction="""
        Customers were able to order more units than we have in stock. In the `inventory`
        package, `Store.remove(sku, quantity)` must:
        - raise `OutOfStockError` (from `inventory.errors`) when asked to remove more units
          than are in stock, leaving the quantity unchanged;
        - raise `UnknownItemError` when the SKU was never added;
        - raise `ValueError` when `quantity` is not positive;
        - otherwise subtract the quantity and return the remaining stock.
        """,
    files={
        "inventory/__init__.py": r'''
            from .errors import OutOfStockError, UnknownItemError
            from .store import Store

            __all__ = ["Store", "OutOfStockError", "UnknownItemError"]
            ''',
        "inventory/errors.py": r'''
            class InventoryError(Exception):
                """Base class for inventory errors."""


            class OutOfStockError(InventoryError):
                """Raised when removing more units than are in stock."""


            class UnknownItemError(InventoryError, KeyError):
                """Raised when a SKU has never been added."""
            ''',
        "inventory/models.py": r'''
            from dataclasses import dataclass


            @dataclass
            class Item:
                sku: str
                name: str
                quantity: int = 0
            ''',
        "inventory/store.py": r'''
            from .models import Item


            class Store:
                def __init__(self):
                    self._items: dict[str, Item] = {}

                def add(self, sku, name, quantity):
                    if quantity <= 0:
                        raise ValueError("quantity must be positive")
                    item = self._items.get(sku)
                    if item is None:
                        self._items[sku] = Item(sku, name, quantity)
                    else:
                        item.quantity += quantity

                def remove(self, sku, quantity):
                    item = self._items[sku]
                    item.quantity -= quantity
                    return item.quantity

                def quantity(self, sku):
                    return self._items[sku].quantity
            ''',
        "tests/test_store.py": r'''
            import pytest

            from inventory import OutOfStockError, Store


            def test_remove_reduces_quantity():
                store = Store()
                store.add("A1", "Widget", 5)
                assert store.remove("A1", 2) == 3


            def test_cannot_oversell():
                store = Store()
                store.add("A1", "Widget", 2)
                with pytest.raises(OutOfStockError):
                    store.remove("A1", 3)
            ''',
    },
    fixed={
        "inventory/store.py": r'''
            from .errors import OutOfStockError, UnknownItemError
            from .models import Item


            class Store:
                def __init__(self):
                    self._items: dict[str, Item] = {}

                def add(self, sku, name, quantity):
                    if quantity <= 0:
                        raise ValueError("quantity must be positive")
                    item = self._items.get(sku)
                    if item is None:
                        self._items[sku] = Item(sku, name, quantity)
                    else:
                        item.quantity += quantity

                def remove(self, sku, quantity):
                    if quantity <= 0:
                        raise ValueError("quantity must be positive")
                    item = self._items.get(sku)
                    if item is None:
                        raise UnknownItemError(sku)
                    if quantity > item.quantity:
                        raise OutOfStockError(f"{sku}: requested {quantity}, have {item.quantity}")
                    item.quantity -= quantity
                    return item.quantity

                def quantity(self, sku):
                    return self._items[sku].quantity
            ''',
    },
    hidden=r'''
        import pytest

        from inventory import OutOfStockError, Store, UnknownItemError


        def make():
            store = Store()
            store.add("A1", "Widget", 5)
            return store


        def test_remove_all_stock():
            store = make()
            assert store.remove("A1", 5) == 0
            assert store.quantity("A1") == 0


        def test_oversell_leaves_quantity_unchanged():
            store = make()
            with pytest.raises(OutOfStockError):
                store.remove("A1", 6)
            assert store.quantity("A1") == 5


        def test_unknown_sku():
            with pytest.raises(UnknownItemError):
                make().remove("ZZ", 1)


        @pytest.mark.parametrize("qty", [0, -1])
        def test_non_positive_quantity(qty):
            store = make()
            with pytest.raises(ValueError):
                store.remove("A1", qty)
            assert store.quantity("A1") == 5


        def test_restock_then_remove():
            store = make()
            store.remove("A1", 4)
            store.add("A1", "Widget", 10)
            assert store.remove("A1", 11) == 0
        ''',
)

# ---------------------------------------------------------------------------
task(
    "daterange-inclusive",
    difficulty="easy",
    category="bugfix",
    instruction="""
        The scheduling report is missing the last day of every range and counts Saturdays
        as business days. Fix `calendar_utils.py`:
        - `daterange(start, end, step_days)` includes `end` when the steps land on it, and
          yields nothing if `start > end`.
        - `daterange` raises `ValueError` if `step_days` is not positive.
        - `business_days(start, end)` returns only Monday to Friday, inclusive of both ends.
        """,
    files={
        "calendar_utils.py": r'''
            from datetime import date, timedelta


            def daterange(start: date, end: date, step_days: int = 1):
                """Yield dates from start to end, inclusive, stepping by step_days."""
                current = start
                while current < end:
                    yield current
                    current += timedelta(days=step_days)


            def business_days(start: date, end: date):
                """Return the weekdays (Mon-Fri) between start and end, inclusive."""
                return [d for d in daterange(start, end) if d.weekday() < 6]
            ''',
        "tests/test_calendar_utils.py": r'''
            from datetime import date

            from calendar_utils import business_days, daterange


            def test_daterange_includes_end():
                days = list(daterange(date(2026, 3, 1), date(2026, 3, 3)))
                assert days == [date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3)]


            def test_business_days_week():
                # 2026-03-02 is a Monday
                days = business_days(date(2026, 3, 2), date(2026, 3, 8))
                assert [d.isoformat() for d in days] == [
                    "2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06",
                ]
            ''',
    },
    fixed={
        "calendar_utils.py": r'''
            from datetime import date, timedelta


            def daterange(start: date, end: date, step_days: int = 1):
                """Yield dates from start to end, inclusive, stepping by step_days."""
                if step_days <= 0:
                    raise ValueError("step_days must be positive")
                current = start
                while current <= end:
                    yield current
                    current += timedelta(days=step_days)


            def business_days(start: date, end: date):
                """Return the weekdays (Mon-Fri) between start and end, inclusive."""
                return [d for d in daterange(start, end) if d.weekday() < 5]
            ''',
    },
    hidden=r'''
        from datetime import date

        import pytest

        from calendar_utils import business_days, daterange


        def test_single_day():
            assert list(daterange(date(2026, 3, 5), date(2026, 3, 5))) == [date(2026, 3, 5)]


        def test_start_after_end_is_empty():
            assert list(daterange(date(2026, 3, 5), date(2026, 3, 1))) == []


        def test_step_days():
            got = list(daterange(date(2026, 3, 1), date(2026, 3, 10), step_days=3))
            assert got == [date(2026, 3, 1), date(2026, 3, 4), date(2026, 3, 7), date(2026, 3, 10)]


        @pytest.mark.parametrize("step", [0, -2])
        def test_bad_step(step):
            with pytest.raises(ValueError):
                next(iter(daterange(date(2026, 3, 1), date(2026, 3, 2), step_days=step)))


        def test_business_days_across_weekend():
            # Friday to Monday
            assert business_days(date(2026, 3, 6), date(2026, 3, 9)) == [date(2026, 3, 6), date(2026, 3, 9)]


        def test_business_days_in_march_2026():
            assert len(business_days(date(2026, 3, 1), date(2026, 3, 31))) == 22
        ''',
)

# ---------------------------------------------------------------------------
task(
    "lru-cache-recency",
    difficulty="medium",
    category="bugfix",
    instruction="""
        `LRUCache` in `lru.py` does not behave like a least-recently-used cache: hot keys get
        evicted. Fix it so that:
        - reading a key with `get` marks it as most recently used;
        - `put` on an existing key updates the value and marks it as most recently used;
        - when the cache goes over capacity, the least recently used key is evicted;
        - `key in cache` does not change recency.
        """,
    files={
        "lru.py": r'''
            from collections import OrderedDict


            class LRUCache:
                def __init__(self, capacity: int):
                    if capacity <= 0:
                        raise ValueError("capacity must be positive")
                    self.capacity = capacity
                    self._data = OrderedDict()

                def get(self, key, default=None):
                    return self._data.get(key, default)

                def put(self, key, value):
                    self._data[key] = value
                    if len(self._data) > self.capacity:
                        self._data.popitem(last=True)

                def __len__(self):
                    return len(self._data)

                def __contains__(self, key):
                    return key in self._data
            ''',
        "tests/test_lru.py": r'''
            from lru import LRUCache


            def test_evicts_least_recently_used():
                cache = LRUCache(2)
                cache.put("a", 1)
                cache.put("b", 2)
                cache.get("a")
                cache.put("c", 3)
                assert "a" in cache and "c" in cache and "b" not in cache
            ''',
    },
    fixed={
        "lru.py": r'''
            from collections import OrderedDict


            class LRUCache:
                def __init__(self, capacity: int):
                    if capacity <= 0:
                        raise ValueError("capacity must be positive")
                    self.capacity = capacity
                    self._data = OrderedDict()

                def get(self, key, default=None):
                    if key not in self._data:
                        return default
                    self._data.move_to_end(key)
                    return self._data[key]

                def put(self, key, value):
                    if key in self._data:
                        self._data.move_to_end(key)
                    self._data[key] = value
                    if len(self._data) > self.capacity:
                        self._data.popitem(last=False)

                def __len__(self):
                    return len(self._data)

                def __contains__(self, key):
                    return key in self._data
            ''',
    },
    hidden=r'''
        import pytest

        from lru import LRUCache


        def test_basic_eviction_order():
            cache = LRUCache(2)
            cache.put("a", 1)
            cache.put("b", 2)
            cache.put("c", 3)
            assert "a" not in cache
            assert cache.get("b") == 2 and cache.get("c") == 3


        def test_get_refreshes_recency():
            cache = LRUCache(2)
            cache.put("a", 1)
            cache.put("b", 2)
            assert cache.get("a") == 1
            cache.put("c", 3)
            assert "b" not in cache and cache.get("a") == 1


        def test_put_existing_refreshes_and_updates():
            cache = LRUCache(2)
            cache.put("a", 1)
            cache.put("b", 2)
            cache.put("a", 10)
            cache.put("c", 3)
            assert "b" not in cache and cache.get("a") == 10
            assert len(cache) == 2


        def test_contains_does_not_refresh():
            cache = LRUCache(2)
            cache.put("a", 1)
            cache.put("b", 2)
            assert "a" in cache
            cache.put("c", 3)
            assert "a" not in cache


        def test_get_missing_returns_default():
            cache = LRUCache(1)
            assert cache.get("x") is None and cache.get("x", 5) == 5


        def test_capacity_one():
            cache = LRUCache(1)
            cache.put("a", 1)
            cache.put("b", 2)
            assert "a" not in cache and cache.get("b") == 2


        def test_invalid_capacity():
            with pytest.raises(ValueError):
                LRUCache(0)
        ''',
)

# ---------------------------------------------------------------------------
task(
    "config-deep-merge",
    difficulty="medium",
    category="bugfix",
    instruction="""
        Loading `config/base.json` and then `config/prod.json` with
        `configlib.load_layers` drops nested settings from the base file (for example
        `database.pool_size`). Fix `configlib.merge(base, override)` so that:
        - nested dicts are merged recursively;
        - any non-dict value in `override` replaces the value in `base` (and a dict in
          `override` replaces a non-dict in `base`);
        - neither input is modified, and the result shares no nested objects with the inputs.
        """,
    files={
        "configlib/__init__.py": r'''
            from .loader import load_layers
            from .merge import merge

            __all__ = ["load_layers", "merge"]
            ''',
        "configlib/merge.py": r'''
            def merge(base: dict, override: dict) -> dict:
                """Return a new dict with override applied on top of base.

                Nested dicts are merged recursively; any other value in override replaces the
                value in base. Neither input is modified.
                """
                result = base
                result.update(override)
                return result
            ''',
        "configlib/loader.py": r'''
            import json
            from functools import reduce

            from .merge import merge


            def load_layers(*paths):
                """Load JSON config files and merge them in order (later files win)."""
                layers = []
                for path in paths:
                    with open(path) as f:
                        layers.append(json.load(f))
                return reduce(merge, layers, {})
            ''',
        "config/base.json": """
            {
              "app": {"name": "orders", "debug": true},
              "database": {
                "host": "localhost",
                "port": 5432,
                "pool_size": 5,
                "options": {"sslmode": "disable", "timeout": 30}
              },
              "features": ["search", "export"]
            }
            """,
        "config/prod.json": """
            {
              "app": {"debug": false},
              "database": {"host": "db.internal", "options": {"sslmode": "require"}},
              "features": ["search"]
            }
            """,
        "tests/test_config.py": r'''
            from configlib import load_layers


            def test_prod_keeps_base_database_settings():
                cfg = load_layers("config/base.json", "config/prod.json")
                assert cfg["database"]["host"] == "db.internal"
                assert cfg["database"]["pool_size"] == 5
            ''',
    },
    fixed={
        "configlib/merge.py": r'''
            import copy


            def merge(base: dict, override: dict) -> dict:
                """Return a new dict with override applied on top of base.

                Nested dicts are merged recursively; any other value in override replaces the
                value in base. Neither input is modified.
                """
                result = copy.deepcopy(base)
                for key, value in override.items():
                    if isinstance(value, dict) and isinstance(result.get(key), dict):
                        result[key] = merge(result[key], value)
                    else:
                        result[key] = copy.deepcopy(value)
                return result
            ''',
    },
    hidden=r'''
        import copy

        from configlib import load_layers, merge


        def test_full_merge():
            cfg = load_layers("config/base.json", "config/prod.json")
            assert cfg == {
                "app": {"name": "orders", "debug": False},
                "database": {
                    "host": "db.internal",
                    "port": 5432,
                    "pool_size": 5,
                    "options": {"sslmode": "require", "timeout": 30},
                },
                "features": ["search"],
            }


        def test_inputs_not_modified():
            base = {"a": {"b": {"c": 1}}, "x": [1, 2]}
            override = {"a": {"b": {"d": 2}}, "y": 3}
            base_copy, override_copy = copy.deepcopy(base), copy.deepcopy(override)
            assert merge(base, override) == {"a": {"b": {"c": 1, "d": 2}}, "x": [1, 2], "y": 3}
            assert base == base_copy and override == override_copy


        def test_result_does_not_share_nested_objects():
            base = {"a": {"b": 1}, "items": [1]}
            result = merge(base, {})
            result["a"]["b"] = 99
            result["items"].append(2)
            assert base == {"a": {"b": 1}, "items": [1]}


        def test_type_changes():
            assert merge({"a": {"b": 1}}, {"a": 5}) == {"a": 5}
            assert merge({"a": 5}, {"a": {"b": 1}}) == {"a": {"b": 1}}


        def test_three_layers():
            assert merge(merge({"a": {"x": 1}}, {"a": {"y": 2}}), {"a": {"x": 3}}) == {"a": {"x": 3, "y": 2}}
        ''',
)

# ---------------------------------------------------------------------------
task(
    "log-error-summary",
    difficulty="hard",
    category="bugfix",
    instruction="""
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
        """,
    files={
        "summarize.py": r'''
            import json
            from collections import Counter


            def summarize(path):
                counts = Counter()
                with open(path) as f:
                    for line in f:
                        if "ERROR" in line:
                            code = line.split("code=")[1].split()[0]
                            counts[code] += 1
                return dict(counts)


            if __name__ == "__main__":
                counts = summarize("logs/server.log")
                with open("error_counts.json", "w") as f:
                    json.dump(counts, f)
            ''',
        "_build.py": r'''
            import os
            import random
            from datetime import datetime, timedelta

            rng = random.Random(7)
            paths = ["/api/users", "/api/orders", "/api/payments", "/health", "/api/search"]
            codes = ["E_DB_TIMEOUT", "E_UPSTREAM_502", "E_VALIDATION", "E_AUTH_EXPIRED", "E_RATE_LIMIT"]
            t = datetime(2026, 3, 1, 12, 0, 0)
            lines = []
            for _ in range(4000):
                t += timedelta(milliseconds=rng.randint(5, 900))
                ts = t.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
                rid = f"{rng.getrandbits(32):08x}"
                path = rng.choice(paths)
                r = rng.random()
                if r < 0.78:
                    msg = rng.choice(["ok", "cache hit", "no ERROR here", "served"])
                    lines.append(
                        f'{ts} INFO  request_id={rid} path={path} status=200 '
                        f'latency_ms={rng.randint(2, 400)} msg="{msg}"'
                    )
                elif r < 0.88:
                    lines.append(
                        f'{ts} WARN  request_id={rid} path={path} status=200 code=W_SLOW '
                        f'latency_ms={rng.randint(800, 3000)} msg="slow request, ERROR budget at risk"'
                    )
                elif r < 0.985:
                    code = rng.choice(codes)
                    lines.append(f'{ts} ERROR request_id={rid} path={path} status=500 code={code} msg="request failed"')
                    if code == "E_DB_TIMEOUT":
                        lines.append("    Traceback (most recent call last):")
                        lines.append('      File "db/pool.py", line 88, in acquire')
                        lines.append("    TimeoutError: ERROR acquiring connection code=E_POOL")
                else:
                    lines.append(f'{ts} ERROR request_id={rid} path={path} status=500 msg="unhandled exception"')

            os.makedirs("logs", exist_ok=True)
            with open("logs/server.log", "w") as f:
                f.write("\n".join(lines) + "\n")
            ''',
        "tests/test_summarize.py": r'''
            from summarize import summarize


            def test_small_sample(tmp_path):
                path = tmp_path / "sample.log"
                path.write_text(
                    '2026-01-01T00:00:00Z ERROR request_id=1 code=E_X msg="boom"\n'
                    '2026-01-01T00:00:01Z INFO  request_id=2 msg="fine"\n'
                )
                assert summarize(path) == {"total_errors": 1, "by_code": {"E_X": 1}}
            ''',
    },
    build="RUN python _build.py && rm _build.py\n",
    fixed={
        "summarize.py": r'''
            import json
            import re
            from collections import Counter

            CODE_RE = re.compile(r"\bcode=(\S+)")


            def summarize(path):
                counts = Counter()
                with open(path) as f:
                    for line in f:
                        if line[:1].isspace():
                            continue
                        fields = line.split()
                        if len(fields) < 2 or fields[1] != "ERROR":
                            continue
                        match = CODE_RE.search(line)
                        counts[match.group(1) if match else "UNKNOWN"] += 1
                return {"total_errors": sum(counts.values()), "by_code": dict(sorted(counts.items()))}


            if __name__ == "__main__":
                summary = summarize("logs/server.log")
                with open("error_counts.json", "w") as f:
                    json.dump(summary, f, indent=2)
            ''',
    },
    hidden=r'''
        import json
        import re
        import subprocess
        import sys
        from collections import Counter

        from summarize import summarize


        def reference(path):
            counts = Counter()
            with open(path) as f:
                for line in f:
                    if line[:1].isspace():
                        continue
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] == "ERROR":
                        match = re.search(r"\bcode=(\S+)", line)
                        counts[match.group(1) if match else "UNKNOWN"] += 1
            return {"total_errors": sum(counts.values()), "by_code": dict(counts)}


        def test_function_matches_reference():
            assert summarize("logs/server.log") == reference("logs/server.log")


        def test_script_writes_json():
            subprocess.run([sys.executable, "summarize.py"], check=True, timeout=60)
            with open("error_counts.json") as f:
                assert json.load(f) == reference("logs/server.log")


        def test_tricky_lines(tmp_path):
            path = tmp_path / "tricky.log"
            path.write_text(
                '2026-01-01T00:00:00Z ERROR request_id=1 code=E_X msg="a"\n'
                "    at something code=E_TRACE ERROR\n"
                '2026-01-01T00:00:01Z INFO  request_id=2 msg="ERROR code=E_FAKE"\n'
                '2026-01-01T00:00:02Z ERROR request_id=3 msg="no code"\n'
                "2026-01-01T00:00:03Z ERROR request_id=4 code=E_X\n"
            )
            assert summarize(path) == {"total_errors": 3, "by_code": {"E_X": 2, "UNKNOWN": 1}}
        ''',
)

# ---------------------------------------------------------------------------
task(
    "billing-decimal",
    difficulty="medium",
    category="bugfix",
    instruction="""
        Customers are charged amounts that don't add up. Fix `billing.py` using exact
        decimal arithmetic:
        - `split_bill(total, people)` returns `people` amounts as strings with two decimals
          that add up exactly to `total`. Leftover cents go to the first people in the list,
          one cent each: `split_bill("100.00", 3)` returns `["33.34", "33.33", "33.33"]`.
          It raises `ValueError` if `people` is less than 1.
        - `apply_tax(amount, rate)` returns `amount * (1 + rate)` rounded half-up to cents,
          as a string: `apply_tax("1.005", "0")` returns `"1.01"`.
        """,
    files={
        "billing.py": r'''
            def split_bill(total, people):
                """Split `total` (a string like "100.00") among `people`.

                Returns a list of amounts as strings with two decimals.
                """
                share = round(float(total) / people, 2)
                return [f"{share:.2f}"] * people


            def apply_tax(amount, rate):
                """Return amount * (1 + rate) rounded to cents, as a string."""
                return f"{round(float(amount) * (1 + float(rate)), 2):.2f}"
            ''',
        "tests/test_billing.py": r'''
            from billing import split_bill


            def test_split_adds_up():
                assert split_bill("100.00", 3) == ["33.34", "33.33", "33.33"]
            ''',
    },
    fixed={
        "billing.py": r'''
            from decimal import ROUND_HALF_UP, Decimal

            CENT = Decimal("0.01")


            def split_bill(total, people):
                """Split `total` (a string like "100.00") among `people`.

                Returns a list of amounts as strings with two decimals.
                """
                if people < 1:
                    raise ValueError("people must be at least 1")
                cents = int((Decimal(str(total)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                base, extra = divmod(cents, people)
                return [f"{Decimal(base + (1 if i < extra else 0)) / 100:.2f}" for i in range(people)]


            def apply_tax(amount, rate):
                """Return amount * (1 + rate) rounded to cents, as a string."""
                value = Decimal(str(amount)) * (1 + Decimal(str(rate)))
                return f"{value.quantize(CENT, rounding=ROUND_HALF_UP):.2f}"
            ''',
    },
    hidden=r'''
        from decimal import Decimal

        import pytest

        from billing import apply_tax, split_bill


        @pytest.mark.parametrize(
            "total,people,expected",
            [
                ("100.00", 3, ["33.34", "33.33", "33.33"]),
                ("10.00", 4, ["2.50", "2.50", "2.50", "2.50"]),
                ("0.05", 3, ["0.02", "0.02", "0.01"]),
                ("7", 1, ["7.00"]),
                ("0.00", 2, ["0.00", "0.00"]),
            ],
        )
        def test_split(total, people, expected):
            assert split_bill(total, people) == expected


        def test_split_always_sums_to_total():
            for cents in range(0, 2000, 7):
                total = f"{cents // 100}.{cents % 100:02d}"
                for people in range(1, 8):
                    shares = split_bill(total, people)
                    assert len(shares) == people
                    assert sum(Decimal(s) for s in shares) == Decimal(total)


        @pytest.mark.parametrize("people", [0, -3])
        def test_split_invalid_people(people):
            with pytest.raises(ValueError):
                split_bill("10.00", people)


        @pytest.mark.parametrize(
            "amount,rate,expected",
            [
                ("1.005", "0", "1.01"),
                ("2.675", "0", "2.68"),
                ("10.00", "0.0825", "10.83"),
                ("19.99", "0.07", "21.39"),
                ("0.00", "0.5", "0.00"),
            ],
        )
        def test_apply_tax_rounds_half_up(amount, rate, expected):
            assert apply_tax(amount, rate) == expected
        ''',
)

# ---------------------------------------------------------------------------
task(
    "retry-decorator",
    difficulty="medium",
    category="bugfix",
    instruction="""
        The `retry` decorator in `resilience.py` swallows errors. Make it follow its contract:
        - `times` is the total number of attempts; `retry(times=0)` (or less) raises
          `ValueError` immediately.
        - Only exceptions matching `exceptions` (including subclasses) are retried; any
          other exception propagates immediately without another attempt.
        - If every attempt fails, the last exception is re-raised.
        - Between attempts it calls `sleep(delay)`; it never sleeps after the final attempt.
        - The wrapper preserves the wrapped function's `__name__` and `__doc__`.
        """,
    files={
        "resilience.py": r'''
            import time


            def retry(times=3, exceptions=(Exception,), delay=0.0, sleep=time.sleep):
                """Retry the wrapped function when it raises one of `exceptions`."""

                def decorator(func):
                    def wrapper(*args, **kwargs):
                        for attempt in range(times):
                            try:
                                return func(*args, **kwargs)
                            except Exception:
                                sleep(delay)
                        return None

                    return wrapper

                return decorator
            ''',
        "tests/test_resilience.py": r'''
            import pytest

            from resilience import retry


            def test_reraises_after_last_attempt():
                calls = []

                @retry(times=3, exceptions=(ConnectionError,), sleep=lambda s: None)
                def flaky():
                    calls.append(1)
                    raise ConnectionError("down")

                with pytest.raises(ConnectionError):
                    flaky()
                assert len(calls) == 3
            ''',
    },
    fixed={
        "resilience.py": r'''
            import functools
            import time


            def retry(times=3, exceptions=(Exception,), delay=0.0, sleep=time.sleep):
                """Retry the wrapped function when it raises one of `exceptions`."""
                if times < 1:
                    raise ValueError("times must be at least 1")

                def decorator(func):
                    @functools.wraps(func)
                    def wrapper(*args, **kwargs):
                        for attempt in range(1, times + 1):
                            try:
                                return func(*args, **kwargs)
                            except exceptions:
                                if attempt == times:
                                    raise
                                sleep(delay)

                    return wrapper

                return decorator
            ''',
    },
    hidden=r'''
        import pytest

        from resilience import retry


        class Clock:
            def __init__(self):
                self.sleeps = []

            def __call__(self, seconds):
                self.sleeps.append(seconds)


        def test_succeeds_after_failures():
            clock, calls = Clock(), []

            @retry(times=4, exceptions=(TimeoutError,), delay=0.5, sleep=clock)
            def double(x):
                calls.append(x)
                if len(calls) < 3:
                    raise TimeoutError()
                return x * 2

            assert double(21) == 42
            assert len(calls) == 3
            assert clock.sleeps == [0.5, 0.5]


        def test_other_exceptions_propagate_immediately():
            calls = []

            @retry(times=5, exceptions=(TimeoutError,), sleep=lambda s: None)
            def broken():
                calls.append(1)
                raise KeyError("x")

            with pytest.raises(KeyError):
                broken()
            assert calls == [1]


        def test_last_exception_reraised_without_final_sleep():
            clock, calls = Clock(), []

            @retry(times=3, exceptions=(ValueError,), delay=1.0, sleep=clock)
            def always_fails():
                calls.append(1)
                raise ValueError(f"attempt {len(calls)}")

            with pytest.raises(ValueError, match="attempt 3"):
                always_fails()
            assert clock.sleeps == [1.0, 1.0]


        def test_preserves_metadata():
            @retry()
            def documented():
                """Docs here."""

            assert documented.__name__ == "documented"
            assert documented.__doc__ == "Docs here."


        def test_subclasses_are_retried():
            calls = []

            @retry(times=2, exceptions=(OSError,), sleep=lambda s: None)
            def once():
                calls.append(1)
                if len(calls) == 1:
                    raise ConnectionError()
                return "ok"

            assert once() == "ok"


        def test_invalid_times():
            with pytest.raises(ValueError):
                retry(times=0)
        ''',
)

# ---------------------------------------------------------------------------
_PAGINATION_VISIBLE = r'''
    import math

    import pytest

    from pagination import paginate

    CASES = [(n, per_page, page) for n in range(0, 41) for per_page in (1, 3, 7, 10) for page in range(1, 4)]


    @pytest.mark.parametrize("n,per_page,page", CASES)
    def test_page_contents(n, per_page, page):
        items = list(range(n))
        total_pages = math.ceil(n / per_page)
        if page > max(total_pages, 1):
            with pytest.raises(ValueError):
                paginate(items, page, per_page)
            return
        result = paginate(items, page, per_page)
        assert result["items"] == items[(page - 1) * per_page : page * per_page]
        assert result["total_pages"] == total_pages
    '''

task(
    "pagination-pages",
    difficulty="easy",
    category="bugfix",
    instruction="""
        `paginate` in `pagination.py` returns the wrong items and page counts: users report
        that the first page is skipped and the last partial page is missing. Fix it.
        - Pages are 1-indexed.
        - `total_pages` is the number of pages needed to show every item (0 for an empty list).
        - Raise `ValueError` when `per_page < 1`, when `page < 1`, or when `page` is past the
          last page. Page 1 of an empty list is valid and returns no items.
        - `has_next` / `has_prev` say whether a following / preceding page exists.

        The visible test suite is large and prints a lot on failure.
        """,
    files={
        "pagination.py": r'''
            def paginate(items, page, per_page=10):
                """Return a dict describing one page of `items` (pages are 1-indexed)."""
                total_pages = len(items) // per_page
                start = page * per_page
                end = start + per_page
                return {
                    "page": page,
                    "per_page": per_page,
                    "total_items": len(items),
                    "total_pages": total_pages,
                    "items": items[start:end],
                    "has_next": page < total_pages,
                    "has_prev": page > 1,
                }
            ''',
        "tests/test_pagination.py": _PAGINATION_VISIBLE,
    },
    fixed={
        "pagination.py": r'''
            import math


            def paginate(items, page, per_page=10):
                """Return a dict describing one page of `items` (pages are 1-indexed)."""
                if per_page < 1:
                    raise ValueError("per_page must be at least 1")
                total_pages = math.ceil(len(items) / per_page)
                last_page = max(total_pages, 1)
                if page < 1 or page > last_page:
                    raise ValueError(f"page {page} is out of range 1..{last_page}")
                start = (page - 1) * per_page
                return {
                    "page": page,
                    "per_page": per_page,
                    "total_items": len(items),
                    "total_pages": total_pages,
                    "items": items[start : start + per_page],
                    "has_next": page < total_pages,
                    "has_prev": page > 1,
                }
            ''',
    },
    hidden=r'''
        import pytest

        from pagination import paginate


        def test_middle_page():
            assert paginate(list(range(25)), 2, 10) == {
                "page": 2,
                "per_page": 10,
                "total_items": 25,
                "total_pages": 3,
                "items": list(range(10, 20)),
                "has_next": True,
                "has_prev": True,
            }


        def test_last_partial_page():
            result = paginate(list(range(25)), 3, 10)
            assert result["items"] == [20, 21, 22, 23, 24]
            assert result["has_next"] is False and result["has_prev"] is True


        def test_exact_multiple():
            result = paginate(list(range(20)), 2, 10)
            assert result["total_pages"] == 2 and result["has_next"] is False


        def test_empty_list():
            result = paginate([], 1, 10)
            assert result["items"] == [] and result["total_pages"] == 0
            assert result["has_next"] is False and result["has_prev"] is False


        @pytest.mark.parametrize("page", [0, -1, 4])
        def test_out_of_range(page):
            with pytest.raises(ValueError):
                paginate(list(range(25)), page, 10)


        def test_empty_list_page_two():
            with pytest.raises(ValueError):
                paginate([], 2, 10)


        @pytest.mark.parametrize("per_page", [0, -5])
        def test_bad_per_page(per_page):
            with pytest.raises(ValueError):
                paginate([1, 2], 1, per_page)


        def test_first_page():
            result = paginate(["a", "b", "c"], 1, 2)
            assert result["items"] == ["a", "b"]
            assert result["has_prev"] is False and result["has_next"] is True
        ''',
)

# ---------------------------------------------------------------------------
task(
    "wordfreq-cli-options",
    difficulty="medium",
    category="feature",
    instruction="""
        Add options to the `wordfreq.py` command-line tool (`python wordfreq.py PATH`):
        - `--top N`: print only the N most frequent words (default: all).
        - `--min-length L`: ignore words shorter than L characters, apostrophes included
          (default: 1).
        - `--stopwords FILE`: ignore the words listed in FILE (one per line, case-insensitive).

        Output lines are `word<TAB>count`, ordered by count (highest first) and then
        alphabetically. Leading and trailing apostrophes are not part of a word (`'quoted'`
        counts as `quoted`, while `don't` stays `don't`); `count_words(text)` must apply
        this rule too. `main(argv)` takes the argument list, as it does now.
        """,
    files={
        "wordfreq.py": r'''
            import argparse
            import re
            from collections import Counter

            WORD_RE = re.compile(r"[a-z']+")


            def count_words(text):
                return Counter(WORD_RE.findall(text.lower()))


            def main(argv=None):
                parser = argparse.ArgumentParser(description="Count word frequencies in a text file.")
                parser.add_argument("path")
                args = parser.parse_args(argv)
                with open(args.path) as f:
                    counts = count_words(f.read())
                for word, n in counts.most_common():
                    print(f"{word}\t{n}")


            if __name__ == "__main__":
                main()
            ''',
        "data/sample.txt": """
            The cat and the hat. The cat's hat is red; the dog's hat is blue.
            'Quoted' words and don't forget: a cat, a hat, a bat!
            """,
        "data/stopwords.txt": """
            the
            A
            and
            is
            """,
        "tests/test_wordfreq.py": r'''
            from wordfreq import main


            def test_top_option(capsys):
                main(["data/sample.txt", "--top", "2"])
                assert capsys.readouterr().out.strip().splitlines() == ["hat\t4", "the\t4"]
            ''',
    },
    fixed={
        "wordfreq.py": r'''
            import argparse
            import re
            from collections import Counter

            WORD_RE = re.compile(r"[a-z']+")


            def count_words(text, min_length=1, stopwords=frozenset()):
                counts = Counter()
                for raw in WORD_RE.findall(text.lower()):
                    word = raw.strip("'")
                    if word and len(word) >= min_length and word not in stopwords:
                        counts[word] += 1
                return counts


            def load_stopwords(path):
                with open(path) as f:
                    return {line.strip().lower() for line in f if line.strip()}


            def main(argv=None):
                parser = argparse.ArgumentParser(description="Count word frequencies in a text file.")
                parser.add_argument("path")
                parser.add_argument("--top", type=int, default=None)
                parser.add_argument("--min-length", type=int, default=1)
                parser.add_argument("--stopwords")
                args = parser.parse_args(argv)
                stopwords = load_stopwords(args.stopwords) if args.stopwords else frozenset()
                with open(args.path) as f:
                    counts = count_words(f.read(), args.min_length, stopwords)
                ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
                if args.top is not None:
                    ranked = ranked[: max(args.top, 0)]
                for word, n in ranked:
                    print(f"{word}\t{n}")


            if __name__ == "__main__":
                main()
            ''',
    },
    hidden=r'''
        from wordfreq import count_words, main


        def run(capsys, *args):
            main(list(args))
            return capsys.readouterr().out.strip().splitlines()


        def test_full_output_sorted(capsys):
            assert run(capsys, "data/sample.txt") == [
                "hat\t4", "the\t4", "a\t3", "and\t2", "cat\t2", "is\t2",
                "bat\t1", "blue\t1", "cat's\t1", "dog's\t1", "don't\t1",
                "forget\t1", "quoted\t1", "red\t1", "words\t1",
            ]


        def test_top(capsys):
            assert run(capsys, "data/sample.txt", "--top", "3") == ["hat\t4", "the\t4", "a\t3"]


        def test_top_zero(capsys):
            assert run(capsys, "data/sample.txt", "--top", "0") == []


        def test_min_length(capsys):
            got = run(capsys, "data/sample.txt", "--min-length", "4", "--top", "3")
            assert got == ["blue\t1", "cat's\t1", "dog's\t1"]


        def test_stopwords(capsys):
            got = run(capsys, "data/sample.txt", "--stopwords", "data/stopwords.txt", "--top", "3")
            assert got == ["hat\t4", "cat\t2", "bat\t1"]


        def test_apostrophes_in_count_words():
            assert count_words("'hello' ''world'' it's") == {"hello": 1, "world": 1, "it's": 1}
        ''',
)

# ---------------------------------------------------------------------------
task(
    "schema-validator-paths",
    difficulty="hard",
    category="bugfix",
    instruction="""
        `schema_check.validate` reports errors at the wrong location: every nested error says
        `$` instead of its real path. It also accepts booleans where an integer or number is
        expected. Fix it so that:
        - error paths look like `$.owner.email` for object properties and `$.tags[2]` for
          array elements, and they combine (`$.owner.roles[1]`);
        - `true` / `false` are rejected for `integer` and `number` but still accepted for
          `boolean`.
        Keep the existing error message formats and error order.
        """,
    files={
        "schema_check/__init__.py": r'''
            from .validator import validate

            __all__ = ["validate"]
            ''',
        "schema_check/validator.py": r'''
            TYPE_MAP = {
                "string": str,
                "integer": int,
                "number": (int, float),
                "boolean": bool,
                "object": dict,
                "array": list,
            }


            def validate(value, schema, path="$"):
                """Validate `value` against a small JSON-schema subset.

                Supported keywords: type, required, properties, items, enum.
                Returns a list of error strings such as "$.user.age: expected integer";
                the list is empty when the value is valid.
                """
                errors = []
                expected = schema.get("type")
                if expected and not isinstance(value, TYPE_MAP[expected]):
                    errors.append(f"{path}: expected {expected}")
                    return errors
                if "enum" in schema and value not in schema["enum"]:
                    errors.append(f"{path}: must be one of {schema['enum']}")
                if expected == "object":
                    for key in schema.get("required", []):
                        if key not in value:
                            errors.append(f"{path}: missing required property '{key}'")
                    for key, sub in schema.get("properties", {}).items():
                        if key in value:
                            errors.extend(validate(value[key], sub))
                if expected == "array":
                    for i, item in enumerate(value):
                        errors.extend(validate(item, schema.get("items", {}), path))
                return errors
            ''',
        "tests/test_validator.py": r'''
            from schema_check import validate

            SCHEMA = {
                "type": "object",
                "required": ["user"],
                "properties": {
                    "user": {
                        "type": "object",
                        "required": ["name", "age"],
                        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
                    }
                },
            }


            def test_nested_error_path():
                errors = validate({"user": {"name": "Ada", "age": "36"}}, SCHEMA)
                assert errors == ["$.user.age: expected integer"]
            ''',
    },
    fixed={
        "schema_check/validator.py": r'''
            TYPE_MAP = {
                "string": str,
                "integer": int,
                "number": (int, float),
                "boolean": bool,
                "object": dict,
                "array": list,
            }


            def _matches(value, expected):
                if expected in ("integer", "number") and isinstance(value, bool):
                    return False
                return isinstance(value, TYPE_MAP[expected])


            def validate(value, schema, path="$"):
                """Validate `value` against a small JSON-schema subset.

                Supported keywords: type, required, properties, items, enum.
                Returns a list of error strings such as "$.user.age: expected integer";
                the list is empty when the value is valid.
                """
                errors = []
                expected = schema.get("type")
                if expected and not _matches(value, expected):
                    errors.append(f"{path}: expected {expected}")
                    return errors
                if "enum" in schema and value not in schema["enum"]:
                    errors.append(f"{path}: must be one of {schema['enum']}")
                if expected == "object":
                    for key in schema.get("required", []):
                        if key not in value:
                            errors.append(f"{path}: missing required property '{key}'")
                    for key, sub in schema.get("properties", {}).items():
                        if key in value:
                            errors.extend(validate(value[key], sub, f"{path}.{key}"))
                if expected == "array":
                    for i, item in enumerate(value):
                        errors.extend(validate(item, schema.get("items", {}), f"{path}[{i}]"))
                return errors
            ''',
    },
    hidden=r'''
        from schema_check import validate

        SCHEMA = {
            "type": "object",
            "required": ["id", "tags", "owner"],
            "properties": {
                "id": {"type": "integer"},
                "active": {"type": "boolean"},
                "score": {"type": "number"},
                "status": {"type": "string", "enum": ["open", "closed"]},
                "tags": {"type": "array", "items": {"type": "string"}},
                "owner": {
                    "type": "object",
                    "required": ["email"],
                    "properties": {
                        "email": {"type": "string"},
                        "roles": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["name"],
                                "properties": {"name": {"type": "string"}},
                            },
                        },
                    },
                },
            },
        }

        VALID = {
            "id": 1,
            "active": True,
            "score": 2.5,
            "status": "open",
            "tags": ["a"],
            "owner": {"email": "x@y.z", "roles": [{"name": "admin"}]},
        }


        def test_valid_document():
            assert validate(VALID, SCHEMA) == []


        def test_missing_nested_required():
            assert validate({**VALID, "owner": {}}, SCHEMA) == ["$.owner: missing required property 'email'"]


        def test_array_item_paths():
            doc = {**VALID, "tags": ["a", 3, "c", None]}
            assert validate(doc, SCHEMA) == ["$.tags[1]: expected string", "$.tags[3]: expected string"]


        def test_deep_array_object_path():
            doc = {**VALID, "owner": {"email": "x@y.z", "roles": [{"name": "a"}, {}]}}
            assert validate(doc, SCHEMA) == ["$.owner.roles[1]: missing required property 'name'"]


        def test_boolean_is_not_integer_or_number():
            doc = {**VALID, "id": True, "score": False}
            assert validate(doc, SCHEMA) == ["$.id: expected integer", "$.score: expected number"]


        def test_integer_is_a_number_and_bools_are_booleans():
            assert validate({**VALID, "score": 3, "active": False}, SCHEMA) == []


        def test_enum_path():
            assert validate({**VALID, "status": "pending"}, SCHEMA) == [
                "$.status: must be one of ['open', 'closed']"
            ]


        def test_top_level_type():
            assert validate([], SCHEMA) == ["$: expected object"]
        ''',
)


def write(path: Path, content: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    if executable:
        path.chmod(0o755)


def main() -> None:
    if ROOT.exists():
        shutil.rmtree(ROOT)
    for t in TASKS:
        d = ROOT / t["name"]
        write(d / "instruction.md", t["instruction"] + INSTRUCTION_FOOTER)
        write(d / "task.toml", TASK_TOML.format(difficulty=t["difficulty"], category=t["category"]))
        write(d / "README.md", f"# {t['name']}\n\nPart of py-bugfix-lite ({t['difficulty']}, {t['category']}).\n")
        write(d / "environment" / "Dockerfile", DOCKERFILE + (t["build"] or ""))
        app = d / "environment" / "app"
        write(app / "pytest.ini", PYTEST_INI)
        for rel, content in t["files"].items():
            write(app / rel, content)
        for rel, content in t["fixed"].items():
            write(d / "solution" / "fixed" / rel, content)
        write(d / "solution" / "solve.sh", SOLVE_SH, executable=True)
        write(d / "tests" / "test.sh", TEST_SH, executable=True)
        write(d / "tests" / "test_hidden.py", t["hidden"])
    print(f"Wrote {len(TASKS)} tasks to {ROOT}")


if __name__ == "__main__":
    main()
