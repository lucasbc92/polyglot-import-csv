"""Config loading and JSON Schema validation."""

from pathlib import Path

import pytest

from polyglotimportcsv.business_exception import BusinessException
from polyglotimportcsv.config_parser import load_config, validate_config


def test_validate_config_rejects_unknown_top_level_key():
    data = {"version": 1, "not_a_backend": {}}
    with pytest.raises(BusinessException):
        validate_config(data)


def test_validate_config_rejects_invalid_csv_column_type():
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
        validate_config(data)


def test_validate_config_accepts_nested_columns_mongodb():
    data = {
        "version": 1,
        "mongodb": {
            "connection": {"uri": "mongodb://localhost", "database": "db"},
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
    validate_config(data)


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


def test_validate_config_with_csv_column_index():
    cfg = {
        "version": 1,
        "redis": {
            "entities": {
                "sess": {
                    "columns": {"key": {"csv_column": 0, "is_key": True}, "val": {"csv_column": 1}},
                    "filters": [],
                }
            }
        },
    }
    validate_config(cfg)
