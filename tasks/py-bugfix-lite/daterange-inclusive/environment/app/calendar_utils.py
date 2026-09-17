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
