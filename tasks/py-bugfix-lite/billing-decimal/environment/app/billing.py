def split_bill(total, people):
    """Split `total` (a string like "100.00") among `people`.

    Returns a list of amounts as strings with two decimals.
    """
    share = round(float(total) / people, 2)
    return [f"{share:.2f}"] * people


def apply_tax(amount, rate):
    """Return amount * (1 + rate) rounded to cents, as a string."""
    return f"{round(float(amount) * (1 + float(rate)), 2):.2f}"
