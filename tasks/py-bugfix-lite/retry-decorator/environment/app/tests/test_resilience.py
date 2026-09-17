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
