"""MetricsCollector: per-phase records, module-level current, runner integration."""

from io import StringIO
from pathlib import Path

from rich.console import Console

from polyglotimportcsv import metrics
from polyglotimportcsv.metrics import MetricsCollector
from polyglotimportcsv.reporting import metrics_table
from polyglotimportcsv.runner import run_import

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "data" / "ecommerce" / "import_config.json"


def test_collector_records_and_computes_rate():
    c = MetricsCollector()
    c.record("postgres", "items", "write", rows=100, seconds=2.0)
    [m] = c.entries()
    assert m.rows_per_second == 50.0
    rec = m.to_record()
    assert rec["backend"] == "postgres" and rec["phase"] == "write"


def test_zero_seconds_has_no_rate():
    c = MetricsCollector()
    c.record("postgres", "items", "write", rows=10, seconds=0.0)
    assert c.entries()[0].rows_per_second is None


def test_timed_phase_is_noop_without_current():
    metrics.set_current(None)
    with metrics.timed_phase("postgres", "items", "filter") as t:
        t.rows = 3  # must not raise
    assert metrics.current() is None  # nothing was implicitly created


def test_timed_phase_records_into_current():
    c = MetricsCollector()
    metrics.set_current(c)
    try:
        with metrics.timed_phase("postgres", "items", "filter") as t:
            t.rows = 7
    finally:
        metrics.set_current(None)
    [m] = c.entries()
    assert (m.backend, m.entity, m.phase, m.rows) == ("postgres", "items", "filter", 7)
    assert m.seconds >= 0


def test_run_import_records_read_and_map_phases():
    def stub(cfg, entities, *, dry_run, create_schema, strategy="optimized"):
        return ["[postgres] stub"]

    c = MetricsCollector()
    run_import(
        CFG, dry_run=True, only=["postgres"], importers={"postgres": stub}, collector=c
    )
    phases = {(m.backend, m.phase) for m in c.entries()}
    assert ("(sources)", "read") in phases
    assert ("postgres", "map") in phases
    assert metrics.current() is None  # runner must reset after the run


def test_metrics_table_renders_rows():
    c = MetricsCollector()
    c.record("postgres", "items", "write", rows=100, seconds=2.0)
    buf = Console(file=StringIO(), width=120)
    buf.print(metrics_table(c.to_records()))
    text = buf.file.getvalue()
    assert "rows/s" in text and "postgres" in text and "50" in text
