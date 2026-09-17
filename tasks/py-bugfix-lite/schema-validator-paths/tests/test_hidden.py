from schema_check import validate

SCHEMA = {
    "type": "object",
    "required": ["id", "tags", "owner"],
    "properties": {
        "id": {"type": "integer"},
        "active": {"type": "boolean"},
        "score": {"type": "number"},
        "status": {"type": "string", "enum": ["open", "closed"]},
        "tags": {"type": "array", "items": {"type": "string"}},
        "owner": {
            "type": "object",
            "required": ["email"],
            "properties": {
                "email": {"type": "string"},
                "roles": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name"],
                        "properties": {"name": {"type": "string"}},
                    },
                },
            },
        },
    },
}

VALID = {
    "id": 1,
    "active": True,
    "score": 2.5,
    "status": "open",
    "tags": ["a"],
    "owner": {"email": "x@y.z", "roles": [{"name": "admin"}]},
}


def test_valid_document():
    assert validate(VALID, SCHEMA) == []


def test_missing_nested_required():
    assert validate({**VALID, "owner": {}}, SCHEMA) == ["$.owner: missing required property 'email'"]


def test_array_item_paths():
    doc = {**VALID, "tags": ["a", 3, "c", None]}
    assert validate(doc, SCHEMA) == ["$.tags[1]: expected string", "$.tags[3]: expected string"]


def test_deep_array_object_path():
    doc = {**VALID, "owner": {"email": "x@y.z", "roles": [{"name": "a"}, {}]}}
    assert validate(doc, SCHEMA) == ["$.owner.roles[1]: missing required property 'name'"]


def test_boolean_is_not_integer_or_number():
    doc = {**VALID, "id": True, "score": False}
    assert validate(doc, SCHEMA) == ["$.id: expected integer", "$.score: expected number"]


def test_integer_is_a_number_and_bools_are_booleans():
    assert validate({**VALID, "score": 3, "active": False}, SCHEMA) == []


def test_enum_path():
    assert validate({**VALID, "status": "pending"}, SCHEMA) == [
        "$.status: must be one of ['open', 'closed']"
    ]


def test_top_level_type():
    assert validate([], SCHEMA) == ["$: expected object"]
