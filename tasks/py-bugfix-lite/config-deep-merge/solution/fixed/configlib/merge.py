import copy


def merge(base: dict, override: dict) -> dict:
    """Return a new dict with override applied on top of base.

    Nested dicts are merged recursively; any other value in override replaces the
    value in base. Neither input is modified.
    """
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result
