"""Importers record the 'filter' phase in dry-run (no DB connections needed)."""

from pathlib import Path

from polyglotimportcsv.metrics import MetricsCollector
from polyglotimportcsv.runner import run_import

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "data" / "ecommerce" / "import_config.json"


def _filter_phases(only):
    c = MetricsCollector()
    run_import(CFG, dry_run=True, only=[only], collector=c)
    return {(m.backend, m.phase) for m in c.entries()}


def test_postgres_dry_run_records_filter_phase():
    assert ("postgres", "filter") in _filter_phases("postgres")


def test_mongodb_dry_run_records_filter_phase():
    assert ("mongodb", "filter") in _filter_phases("mongodb")


def test_cassandra_dry_run_records_filter_phase():
    assert ("cassandra", "filter") in _filter_phases("cassandra")


def test_redis_dry_run_records_filter_phase():
    assert ("redis", "filter") in _filter_phases("redis")


def test_neo4j_dry_run_records_filter_phase():
    assert ("neo4j", "filter") in _filter_phases("neo4j")
