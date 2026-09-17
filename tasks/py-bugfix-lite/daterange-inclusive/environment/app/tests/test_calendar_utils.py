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
