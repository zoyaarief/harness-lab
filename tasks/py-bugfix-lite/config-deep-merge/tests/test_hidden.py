import copy

from configlib import load_layers, merge


def test_full_merge():
    cfg = load_layers("config/base.json", "config/prod.json")
    assert cfg == {
        "app": {"name": "orders", "debug": False},
        "database": {
            "host": "db.internal",
            "port": 5432,
            "pool_size": 5,
            "options": {"sslmode": "require", "timeout": 30},
        },
        "features": ["search"],
    }


def test_inputs_not_modified():
    base = {"a": {"b": {"c": 1}}, "x": [1, 2]}
    override = {"a": {"b": {"d": 2}}, "y": 3}
    base_copy, override_copy = copy.deepcopy(base), copy.deepcopy(override)
    assert merge(base, override) == {"a": {"b": {"c": 1, "d": 2}}, "x": [1, 2], "y": 3}
    assert base == base_copy and override == override_copy


def test_result_does_not_share_nested_objects():
    base = {"a": {"b": 1}, "items": [1]}
    result = merge(base, {})
    result["a"]["b"] = 99
    result["items"].append(2)
    assert base == {"a": {"b": 1}, "items": [1]}


def test_type_changes():
    assert merge({"a": {"b": 1}}, {"a": 5}) == {"a": 5}
    assert merge({"a": 5}, {"a": {"b": 1}}) == {"a": {"b": 1}}


def test_three_layers():
    assert merge(merge({"a": {"x": 1}}, {"a": {"y": 2}}), {"a": {"x": 3}}) == {"a": {"x": 3, "y": 2}}
