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
