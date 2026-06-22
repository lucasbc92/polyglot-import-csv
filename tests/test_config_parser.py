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
    data = {"version": 1, "not_a_backend": {}}
    with pytest.raises(BusinessException):
        validate_import_config_schema(data)


def test_import_schema_rejects_connection_block():
    # Connection settings belong in the SGBD config, not the import config.
    data = {
        "version": 1,
        "mongodb": {
            "connection": {"uri": "mongodb://localhost", "database": "db"},
            "entities": {"doc": {"columns": {"a": {}}}},
        },
    }
    with pytest.raises(BusinessException):
        validate_import_config_schema(data)


def test_import_schema_rejects_invalid_csv_column_type():
    data = {
        "version": 1,
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
        "version": 1,
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
        "version": 1,
        "postgres": {"connection": {"host": "x"}, "entities": {}},
    }
    with pytest.raises(BusinessException):
        validate_sgbd_config(data)


def test_merge_requires_backend_in_sgbd_config():
    import_cfg = {"version": 1, "redis": {"entities": {"x": {"columns": {"k": {}}}}}}
    sgbd_cfg = {"version": 1, "postgres": {"connection": {}}}
    with pytest.raises(BusinessException, match="not declared in the SGBD config"):
        merge_configs(import_cfg, sgbd_cfg)


def test_merge_injects_connection_and_schema():
    import_cfg = {
        "version": 1,
        "postgres": {"entities": {"t": {"columns": {"id": {"is_key": True}}}}},
    }
    sgbd_cfg = {
        "version": 1,
        "postgres": {"connection": {"host": "db"}, "schema": "shop"},
    }
    merged = merge_configs(import_cfg, sgbd_cfg)
    assert merged["postgres"]["connection"] == {"host": "db"}
    assert merged["postgres"]["schema"] == "shop"
    assert "entities" in merged["postgres"]


def test_load_config_rejects_missing_file():
    missing = Path(__file__).resolve().parents[1] / "data" / "nonexistent_config.json"
    with pytest.raises(BusinessException):
        load_config(missing)


def test_load_config_accepts_ecommerce_fixture():
    root = Path(__file__).resolve().parents[1]
    cfg = root / "data" / "ecommerce" / "import_config.json"
    data = load_config(cfg)
    assert data["version"] == 1
    assert "postgres" in data
    # Connection is merged in from the sibling sgbd_config.json.
    assert data["postgres"]["connection"]["database"] == "ecommerce"
