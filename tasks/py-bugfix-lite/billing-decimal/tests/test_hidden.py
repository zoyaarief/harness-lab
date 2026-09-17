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
