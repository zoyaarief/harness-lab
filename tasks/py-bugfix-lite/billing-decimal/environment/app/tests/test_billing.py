from billing import split_bill


def test_split_adds_up():
    assert split_bill("100.00", 3) == ["33.34", "33.33", "33.33"]
