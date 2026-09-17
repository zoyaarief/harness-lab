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
