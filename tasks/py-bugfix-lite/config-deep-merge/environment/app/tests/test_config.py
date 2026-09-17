from configlib import load_layers


def test_prod_keeps_base_database_settings():
    cfg = load_layers("config/base.json", "config/prod.json")
    assert cfg["database"]["host"] == "db.internal"
    assert cfg["database"]["pool_size"] == 5
