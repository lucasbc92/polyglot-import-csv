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


def test_dry_run_all_backends():
    """All 5 backends appear in dry-run output with expected row counts."""
    lines = run_import(CSV, CFG, dry_run=True)
    text = "\n".join(lines)
    assert "entity orders: 8 row(s)" in text
    assert "entity inventory: 8 row(s)" in text
    assert "collection product_catalog: 8 document(s)" in text
    assert "table user_activity_log: 32 row(s)" in text
    assert "entity shopping_cart: 8 row(s)" in text
    assert "entity user_session: 8 row(s)" in text
    assert "label User: 8 row(s)" in text
    assert "label Product: 8 row(s)" in text
    assert "relationship type PURCHASED" in text


def test_invalid_column_raises():
    cfg = load_config(CFG)
    cfg = dict(cfg)
    cfg["postgres"] = dict(cfg["postgres"])
    cfg["postgres"]["entities"] = dict(cfg["postgres"]["entities"])
    cfg["postgres"]["entities"]["bad"] = {"columns": {"no_such_col": {}}, "filters": []}
    df, kinds = load_csv_with_inference(CSV)
    with pytest.raises(BusinessException):
        validate_import_config(cfg, df, kinds)
