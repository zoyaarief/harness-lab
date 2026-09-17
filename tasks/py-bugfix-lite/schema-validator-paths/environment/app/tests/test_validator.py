from schema_check import validate

SCHEMA = {
    "type": "object",
    "required": ["user"],
    "properties": {
        "user": {
            "type": "object",
            "required": ["name", "age"],
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        }
    },
}


def test_nested_error_path():
    errors = validate({"user": {"name": "Ada", "age": "36"}}, SCHEMA)
    assert errors == ["$.user.age: expected integer"]
