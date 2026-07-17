"""Smoke tests: v2 config dry-run pipeline over the e-commerce example."""

from pathlib import Path

import pytest

from polyglotimportcsv.business_exception import MappingError, SourceError
from polyglotimportcsv.runner import run_import

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "data" / "ecommerce" / "import_config.json"


def test_dry_run_smoke():
    lines = run_import(CFG, dry_run=True, create_schema=False, only=["postgres"])
    assert any("postgres" in L for L in lines)


def test_dry_run_all_backends():
    """All 5 backends appear in dry-run output with expected row counts."""
    lines = run_import(CFG, dry_run=True)
    text = "\n".join(lines)
    assert "entity orders: 8 row(s)" in text
    assert "entity inventory: 8 row(s)" in text
    assert "entity categories: 8 row(s)" in text
    assert "entity products: 8 row(s)" in text
    assert "collection product_catalog: 8 document(s)" in text
    assert "table user_activity_log: 32 row(s)" in text
    assert "entity shopping_cart: 8 row(s)" in text
    assert "entity user_session: 8 row(s)" in text
    assert "label User: 8 row(s)" in text
    assert "label Product: 8 row(s)" in text
    assert "relationship type PURCHASED" in text


def test_unknown_source_raises(tmp_path):
    cfg = tmp_path / "cfg.json"
    cfg.write_text(
        '{"sources": {"s": "missing.csv"}, "redis": {"entities": {"x": {}}}}',
        encoding="utf-8",
    )
    (tmp_path / "sgbd_config.json").write_text(
        '{"version": 1, "redis": {"connection": {"host": "h"}}}', encoding="utf-8"
    )
    with pytest.raises(SourceError):
        run_import(cfg, dry_run=True)


def test_unresolvable_entity_raises(tmp_path):
    src = tmp_path / "s.csv"
    src.write_text("a\n1\n", encoding="utf-8")
    cfg = tmp_path / "cfg.json"
    cfg.write_text(
        '{"sources": {"s": "s.csv"}, "redis": {"entities": {"nomatch": {}}}}',
        encoding="utf-8",
    )
    (tmp_path / "sgbd_config.json").write_text(
        '{"version": 1, "redis": {"connection": {"host": "h"}}}', encoding="utf-8"
    )
    with pytest.raises(MappingError):
        run_import(cfg, dry_run=True)
