def merge(base: dict, override: dict) -> dict:
    """Return a new dict with override applied on top of base.

    Nested dicts are merged recursively; any other value in override replaces the
    value in base. Neither input is modified.
    """
    result = base
    result.update(override)
    return result
