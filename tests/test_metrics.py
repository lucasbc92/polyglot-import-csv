"""MetricsCollector: per-phase records, module-level current, runner integration."""

from io import StringIO
from pathlib import Path

from rich.console import Console

from polyglotimportcsv import metrics
from polyglotimportcsv.metrics import MetricsCollector
from polyglotimportcsv.reporting import metrics_table
from polyglotimportcsv.runner import run_import

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "ecommerce"
CFG = DATA / "import_config.json"
CFG_COMBINED = DATA / "import_config_combined.json"


def _stub(cfg, entities, *, dry_run, create_schema, strategy="optimized"):
    return ["[postgres] stub"]


def _data_rows(path: Path) -> int:
    with open(path, "rb") as fh:
        return sum(1 for _ in fh) - 1  # minus header


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
    c = MetricsCollector()
    run_import(
        CFG, dry_run=True, only=["postgres"], importers={"postgres": _stub}, collector=c
    )
    phases = {(m.backend, m.phase) for m in c.entries()}
    assert ("(sources)", "read") in phases
    assert ("postgres", "map") in phases
    assert metrics.current() is None  # runner must reset after the run


def _read_rows(config_path: Path) -> int:
    c = MetricsCollector()
    run_import(
        config_path, dry_run=True, only=["postgres"],
        importers={"postgres": _stub}, collector=c,
    )
    [read] = [m for m in c.entries() if m.phase == "read"]
    return read.rows


def test_read_rows_counts_multi_sources():
    expected = sum(
        _data_rows(DATA / f"ecommerce_{src}.csv")
        for src in ("stock", "purchase", "select_product", "add_to_cart")
    )
    assert _read_rows(CFG) == expected


def test_read_rows_counts_combined_file_once():
    """A combined CSV also registers one slice per origin value. Those slices are
    the same rows again, so counting the whole source registry would report twice
    the rows read and inflate combined-mode read throughput 2x in the benchmarks."""
    assert _read_rows(CFG_COMBINED) == _data_rows(DATA / "ecommerce_join.csv")


def test_read_rows_match_across_modes():
    # Same underlying dataset in both layouts: the read metric must agree.
    assert _read_rows(CFG_COMBINED) == _read_rows(CFG)


def test_metrics_table_renders_rows():
    c = MetricsCollector()
    c.record("postgres", "items", "write", rows=100, seconds=2.0)
    buf = Console(file=StringIO(), width=120)
    buf.print(metrics_table(c.to_records()))
    text = buf.file.getvalue()
    assert "rows/s" in text and "postgres" in text and "50" in text


def test_metrics_table_omits_filter_phase():
    # The consolidated report already drops `filter`; the terminal table must match.
    c = MetricsCollector()
    c.record("postgres", "items", "filter", rows=100, seconds=1.0)
    c.record("postgres", "items", "write", rows=100, seconds=2.0)
    buf = Console(file=StringIO(), width=120)
    buf.print(metrics_table(c.to_records()))
    text = buf.file.getvalue()
    assert "filter" not in text
    assert "write" in text
