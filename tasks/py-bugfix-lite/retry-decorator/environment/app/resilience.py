import time


def retry(times=3, exceptions=(Exception,), delay=0.0, sleep=time.sleep):
    """Retry the wrapped function when it raises one of `exceptions`."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(times):
                try:
                    return func(*args, **kwargs)
                except Exception:
                    sleep(delay)
            return None

        return wrapper

    return decorator
