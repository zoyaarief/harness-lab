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
