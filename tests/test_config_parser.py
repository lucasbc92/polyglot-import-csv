"""Config loading and JSON Schema validation (split import / DBMS configs)."""

from pathlib import Path

import pytest

from polyglotimportcsv.business_exception import BusinessException, ConfigError
from polyglotimportcsv.config_parser import (
    load_config,
    load_dbms_config,
    merge_configs,
    resolve_dbms_config_path,
    validate_import_config_schema,
    validate_dbms_config,
)


def test_import_schema_rejects_unknown_top_level_key():
    data = {"sources": {"s": "s.csv"}, "not_a_backend": {}}
    with pytest.raises(BusinessException):
        validate_import_config_schema(data)


def test_import_schema_rejects_connection_block():
    # Connection settings belong in the DBMS config, not the import config.
    data = {
        "sources": {"s": "s.csv"},
        "mongodb": {
            "connection": {"uri": "mongodb://localhost", "database": "db"},
            "entities": {"doc": {"columns": {"a": {}}}},
        },
    }
    with pytest.raises(BusinessException):
        validate_import_config_schema(data)


def test_import_schema_rejects_invalid_csv_column_type():
    data = {
        "sources": {"s": "s.csv"},
        "redis": {
            "entities": {
                "x": {
                    "columns": {"k": {"csv_column": -1, "is_key": True}},
                    "filters": [],
                }
            }
        },
    }
    with pytest.raises(BusinessException):
        validate_import_config_schema(data)


def test_import_schema_accepts_nested_columns_mongodb():
    data = {
        "sources": {"s": "s.csv"},
        "mongodb": {
            "entities": {
                "doc": {
                    "columns": {
                        "a": {},
                        "sub": {"b": {}},
                    },
                    "filters": [],
                }
            },
        },
    }
    validate_import_config_schema(data)


def test_dbms_schema_rejects_entities_block():
    # Mapping (entities) belongs in the import config, not the DBMS config.
    data = {
        "postgres": {"connection": {"host": "x"}, "entities": {}},
    }
    with pytest.raises(BusinessException):
        validate_dbms_config(data)


def test_merge_requires_backend_in_dbms_config():
    import_cfg = {
        "sources": {"s": "s.csv"},
        "redis": {"entities": {"x": {"columns": {"k": {}}}}},
    }
    dbms_cfg = {"sources": {"s": "s.csv"}, "postgres": {"connection": {}}}
    with pytest.raises(BusinessException, match="not declared in the DBMS config"):
        merge_configs(import_cfg, dbms_cfg)


def test_load_config_rejects_missing_file():
    missing = Path(__file__).resolve().parents[1] / "data" / "nonexistent_config.json"
    with pytest.raises(BusinessException):
        load_config(missing)


def test_load_dbms_config_hints_at_the_1_1_0_rename(tmp_path):
    (tmp_path / "sgbd_config.json").write_text("{}", encoding="utf-8")
    missing = tmp_path / "dbms_config.json"
    with pytest.raises(ConfigError, match=r"sgbd_config\.json was renamed to dbms_config\.json in 1\.1\.0"):
        load_dbms_config(missing)


def test_load_dbms_config_missing_without_legacy_file_has_no_hint(tmp_path):
    missing = tmp_path / "dbms_config.json"
    with pytest.raises(ConfigError, match="not found") as excinfo:
        load_dbms_config(missing)
    assert "sgbd_config.json" not in str(excinfo.value)


def test_import_schema_rejects_version_field():
    data = {"sources": {"s": "s.csv"}}
    validate_import_config_schema(data)  # baseline OK
    with pytest.raises(BusinessException):
        validate_import_config_schema({"version": 1, "sources": {"s": "s.csv"}})


def test_import_schema_requires_sources():
    with pytest.raises(BusinessException):
        validate_import_config_schema({"redis": {"entities": {"x": {}}}})


def test_merge_injects_connection_and_schema_and_sources():
    import_cfg = {
        "sources": {"t": "t.csv"},
        "postgres": {"entities": {"t": {"columns": {"id": {"is_key": True}}}}},
    }
    dbms_cfg = {"postgres": {"connection": {"host": "db"}, "schema": "shop"}}
    merged = merge_configs(import_cfg, dbms_cfg)
    assert merged["sources"] == {"t": "t.csv"}
    assert "version" not in merged
    assert merged["postgres"]["connection"] == {"host": "db"}
    assert merged["postgres"]["schema"] == "shop"


def test_load_config_accepts_ecommerce_fixture():
    root = Path(__file__).resolve().parents[1]
    cfg = root / "data" / "ecommerce" / "import_config.json"
    data = load_config(cfg)
    assert "sources" in data and "version" not in data
    assert "postgres" in data
    assert data["postgres"]["connection"]["database"] == "ecommerce"


ECOMMERCE = Path(__file__).resolve().parents[1] / "data" / "ecommerce"
DBMS_NAMES = ("postgres", "mongodb", "cassandra", "redis", "neo4j")


def _postgres_with(start):
    return {"version": 1, "postgres": {"connection": {"host": "h"}, "start": start}}


@pytest.mark.parametrize("start", [
    {"command": "net start postgresql-x64-16"},
    {"compose": {"file": "../../docker-compose.yml", "service": "postgres"}},
])
def test_dbms_schema_accepts_each_start_form(start):
    validate_dbms_config(_postgres_with(start))


@pytest.mark.parametrize("start", [
    {"command": "x", "compose": {"file": "f", "service": "s"}},  # both forms
    {"command": ""},
    {"command": "x", "sudo": True},
    {"compose": {"file": "f"}},
    {"compose": {"file": "f", "service": "s", "profile": "p"}},
    {},
])
def test_dbms_schema_rejects_a_malformed_start(start):
    with pytest.raises(BusinessException):
        validate_dbms_config(_postgres_with(start))


@pytest.mark.parametrize("name", [
    "dbms_config.json", "dbms_config_windows.json", "dbms_config_linux.json",
])
def test_example_dbms_configs_are_valid_and_declare_start_everywhere(name):
    cfg = load_dbms_config(ECOMMERCE / name)
    for dbms in DBMS_NAMES:
        assert "start" in cfg[dbms], (name, dbms)


def test_example_dbms_configs_share_the_same_connections():
    base = load_dbms_config(ECOMMERCE / "dbms_config.json")
    for name in ("dbms_config_windows.json", "dbms_config_linux.json"):
        other = load_dbms_config(ECOMMERCE / name)
        for dbms in DBMS_NAMES:
            assert other[dbms]["connection"] == base[dbms]["connection"], (name, dbms)
        assert other["postgres"]["schema"] == base["postgres"]["schema"]


def test_example_compose_references_point_at_the_repository_compose_file():
    for name in ("dbms_config.json", "dbms_config_windows.json"):
        cfg = load_dbms_config(ECOMMERCE / name)
        for dbms in DBMS_NAMES:
            compose = cfg[dbms]["start"].get("compose")
            if compose:
                assert (ECOMMERCE / compose["file"]).resolve().is_file(), (name, dbms)


def test_merge_does_not_carry_start_into_the_import_structure():
    import_cfg = {"sources": {"s": "s.csv"}, "postgres": {"entities": {}}}
    dbms_cfg = {"version": 1, "postgres": {"connection": {"host": "h"},
                                           "start": {"command": "x"}}}
    merged = merge_configs(import_cfg, dbms_cfg)
    assert "start" not in merged["postgres"]
    assert merged["postgres"]["connection"] == {"host": "h"}


def test_resolve_dbms_config_path_defaults_next_to_the_import_config(tmp_path):
    cfg = tmp_path / "import_config.json"
    assert resolve_dbms_config_path(cfg) == tmp_path / "dbms_config.json"
    assert resolve_dbms_config_path(cfg, "other.json") == Path("other.json")
