"""Config loading and JSON Schema validation (split import / SGBD configs)."""

from pathlib import Path

import pytest

from polyglotimportcsv.business_exception import BusinessException
from polyglotimportcsv.config_parser import (
    load_config,
    merge_configs,
    validate_import_config_schema,
    validate_sgbd_config,
)


def test_import_schema_rejects_unknown_top_level_key():
    data = {"sources": {"s": "s.csv"}, "not_a_backend": {}}
    with pytest.raises(BusinessException):
        validate_import_config_schema(data)


def test_import_schema_rejects_connection_block():
    # Connection settings belong in the SGBD config, not the import config.
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


def test_sgbd_schema_rejects_entities_block():
    # Mapping (entities) belongs in the import config, not the SGBD config.
    data = {
        "postgres": {"connection": {"host": "x"}, "entities": {}},
    }
    with pytest.raises(BusinessException):
        validate_sgbd_config(data)


def test_merge_requires_backend_in_sgbd_config():
    import_cfg = {
        "sources": {"s": "s.csv"},
        "redis": {"entities": {"x": {"columns": {"k": {}}}}},
    }
    sgbd_cfg = {"sources": {"s": "s.csv"}, "postgres": {"connection": {}}}
    with pytest.raises(BusinessException, match="not declared in the SGBD config"):
        merge_configs(import_cfg, sgbd_cfg)


def test_load_config_rejects_missing_file():
    missing = Path(__file__).resolve().parents[1] / "data" / "nonexistent_config.json"
    with pytest.raises(BusinessException):
        load_config(missing)


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
    sgbd_cfg = {"postgres": {"connection": {"host": "db"}, "schema": "shop"}}
    merged = merge_configs(import_cfg, sgbd_cfg)
    assert merged["sources"] == {"t": "t.csv"}
    assert "version" not in merged
    assert merged["postgres"]["connection"] == {"host": "db"}
    assert merged["postgres"]["schema"] == "shop"


@pytest.mark.xfail(reason="example migrates in Task 13", strict=False)
def test_load_config_accepts_ecommerce_fixture():
    root = Path(__file__).resolve().parents[1]
    cfg = root / "data" / "ecommerce" / "import_config.json"
    data = load_config(cfg)
    assert "sources" in data and "version" not in data
    assert "postgres" in data
    assert data["postgres"]["connection"]["database"] == "ecommerce"
