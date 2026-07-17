"""Smoke tests: config validation and dry-run pipeline."""

from pathlib import Path

import pytest

from polyglotimportcsv.runner import run_import


ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "ecommerce" / "ecommerce_join.csv"
CFG = ROOT / "data" / "ecommerce" / "import_config.json"


@pytest.mark.xfail(reason="example migrates in Task 13", strict=False)
def test_dry_run_smoke():
    lines = run_import(CSV, CFG, dry_run=True, create_schema=False, only=["postgres"])
    assert any("postgres" in L for L in lines)


@pytest.mark.xfail(reason="example migrates in Task 13", strict=False)
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
