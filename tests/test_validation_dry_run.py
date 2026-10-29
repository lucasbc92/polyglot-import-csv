"""Smoke tests: the dry-run (headers, inference and validation reads) over the e-commerce example."""

from pathlib import Path

import pytest

from polyglotimportcsv.business_exception import MappingError, SourceError
from polyglotimportcsv.runner import run_import

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "data" / "ecommerce" / "import_config.json"


def test_dry_run_smoke():
    lines = run_import(CFG, dry_run=True, create_schema=False, only=["postgres"])
    assert lines and all(line.startswith("[postgres] ") for line in lines)


@pytest.mark.parametrize("cfg_name", ["import_config.json", "import_config_combined.json"])
def test_dry_run_counts_every_dbms(cfg_name):
    """The validation read's counts, per DBMS and partition; both layouts of the
    example hold the same rows, so they give the same counts."""
    assert run_import(CFG.with_name(cfg_name), dry_run=True) == [
        "[postgres] categories: 8 row(s)",
        "[postgres] inventory: 8 row(s)",
        "[postgres] orders: 8 row(s)",
        "[postgres] products: 8 row(s)",
        "[mongodb] product_catalog: 8 row(s)",
        "[cassandra] user_activity_log: 32 row(s)",
        "[redis] shopping_cart: 8 row(s)",
        "[redis] user_session: 8 row(s)",
        "[neo4j] :PURCHASED: 8 row(s)",
        "[neo4j] Product: 8 row(s)",
        "[neo4j] User: 8 row(s)",
    ]


def test_unknown_source_raises(tmp_path):
    cfg = tmp_path / "cfg.json"
    cfg.write_text(
        '{"sources": {"s": "missing.csv"}, "redis": {"entities": {"x": {}}}}',
        encoding="utf-8",
    )
    (tmp_path / "dbms_config.json").write_text(
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
    (tmp_path / "dbms_config.json").write_text(
        '{"version": 1, "redis": {"connection": {"host": "h"}}}', encoding="utf-8"
    )
    with pytest.raises(MappingError):
        run_import(cfg, dry_run=True)
