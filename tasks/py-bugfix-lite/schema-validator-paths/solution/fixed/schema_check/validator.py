TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
}


def _matches(value, expected):
    if expected in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, TYPE_MAP[expected])


def validate(value, schema, path="$"):
    """Validate `value` against a small JSON-schema subset.

    Supported keywords: type, required, properties, items, enum.
    Returns a list of error strings such as "$.user.age: expected integer";
    the list is empty when the value is valid.
    """
    errors = []
    expected = schema.get("type")
    if expected and not _matches(value, expected):
        errors.append(f"{path}: expected {expected}")
        return errors
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: must be one of {schema['enum']}")
    if expected == "object":
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required property '{key}'")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                errors.extend(validate(value[key], sub, f"{path}.{key}"))
    if expected == "array":
        for i, item in enumerate(value):
            errors.extend(validate(item, schema.get("items", {}), f"{path}[{i}]"))
    return errors
