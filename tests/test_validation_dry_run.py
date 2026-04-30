"""Smoke tests: config validation and dry-run pipeline."""

from pathlib import Path

import pytest

from polyglotimportcsv.business_exception import BusinessException
from polyglotimportcsv.config_parser import load_config
from polyglotimportcsv.csv_reader import load_csv_with_inference
from polyglotimportcsv.runner import run_import
from polyglotimportcsv.validation import validate_import_config


ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "ecommerce" / "ecommerce_join.csv"
CFG = ROOT / "data" / "ecommerce" / "import_config.json"


def test_validate_config_and_csv():
    cfg = load_config(CFG)
    df, kinds = load_csv_with_inference(CSV)
    validate_import_config(cfg, df, kinds)


def test_dry_run_smoke():
    lines = run_import(CSV, CFG, dry_run=True, create_schema=False, only=["postgres"])
    assert any("postgres" in L for L in lines)


def test_invalid_column_raises():
    cfg = load_config(CFG)
    cfg = dict(cfg)
    cfg["postgres"] = dict(cfg["postgres"])
    cfg["postgres"]["entities"] = dict(cfg["postgres"]["entities"])
    cfg["postgres"]["entities"]["bad"] = {"columns": {"no_such_col": {}}, "filters": []}
    df, kinds = load_csv_with_inference(CSV)
    with pytest.raises(BusinessException):
        validate_import_config(cfg, df, kinds)
