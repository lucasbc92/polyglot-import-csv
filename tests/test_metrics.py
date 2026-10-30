"""MetricsCollector: per-phase records and runner integration."""

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


def test_the_phases_are_the_three_reads():
    assert metrics.PHASES == ("infer", "validate", "write")


def _read_rows(config_path: Path) -> dict:
    c = MetricsCollector()
    run_import(config_path, dry_run=True, collector=c)
    return {m.phase: m.rows for m in c.entries()}


def test_infer_and_validate_count_every_data_row_once_in_both_layouts():
    """A combined CSV is profiled by origin value: each of its rows counts once, so
    both layouts of the same data report the same rows read."""
    multi = sum(
        _data_rows(DATA / f"ecommerce_{src}.csv")
        for src in ("stock", "purchase", "select_product", "add_to_cart")
    )
    assert _data_rows(DATA / "ecommerce_join.csv") == multi
    expected = {"infer": multi, "validate": multi}
    assert _read_rows(CFG) == expected
    assert _read_rows(CFG_COMBINED) == expected


def test_metrics_table_renders_rows():
    c = MetricsCollector()
    c.record("postgres", "items", "write", rows=100, seconds=2.0)
    buf = Console(file=StringIO(), width=120)
    buf.print(metrics_table(c.to_records()))
    text = buf.file.getvalue()
    assert "rows/s" in text and "postgres" in text and "50" in text
