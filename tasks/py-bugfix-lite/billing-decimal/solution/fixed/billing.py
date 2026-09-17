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
