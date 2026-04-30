"""Config loading and JSON Schema validation."""

from pathlib import Path

import pytest

from polyglotimportcsv.business_exception import BusinessException
from polyglotimportcsv.config_parser import load_config, validate_config


def test_validate_config_rejects_unknown_top_level_key():
    data = {"version": 1, "not_a_backend": {}}
    with pytest.raises(BusinessException):
        validate_config(data)


def test_load_config_rejects_missing_file(tmp_path):
    missing = tmp_path / "nope.json"
    with pytest.raises(BusinessException):
        load_config(missing)


def test_load_config_accepts_ecommerce_fixture():
    root = Path(__file__).resolve().parents[1]
    cfg = root / "data" / "ecommerce" / "import_config.json"
    data = load_config(cfg)
    assert data["version"] == 1
    assert "postgres" in data
