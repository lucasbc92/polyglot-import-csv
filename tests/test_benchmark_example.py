"""The committed reference dataset drives dry-run smoke + mode-equivalence."""

from pathlib import Path

from polyglotimportcsv import benchmark_data as bd
from polyglotimportcsv.metrics import MetricsCollector
from polyglotimportcsv.runner import run_import

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "data" / "benchmark"
ECOM = ROOT / "data" / "ecommerce"


def test_reference_dataset_committed_and_1k():
    # The committed dataset is generated at --rows 1000 --seed 42 (total rows),
    # split ~1:3:2:2 with seeded jitter. Assert against that split, not fixed
    # numbers, so it tracks the generator.
    split = bd._split_rows(1000, 42)

    def n(fname):
        with open(BENCH / fname, encoding="utf-8") as fh:
            return sum(1 for _ in fh) - 1
    assert n("ecommerce_stock.csv") == split["stock"]
    assert n("ecommerce_purchase.csv") == split["purchase"]
    assert n("ecommerce_select_product.csv") == split["select_product"]
    assert n("ecommerce_add_to_cart.csv") == split["add_to_cart"]
    assert n("ecommerce_join.csv") == 1000  # sum of the four sources


def _filter_rows(config, overrides):
    c = MetricsCollector()
    run_import(config, dry_run=True, collector=c, source_overrides=overrides)
    return {(m.entity): m.rows for m in c.entries() if m.phase == "filter"}


def test_dry_run_smoke_on_reference():
    overrides = {src: str(BENCH / fname) for src, fname in bd.SOURCE_FILES.items()}
    lines = run_import(ECOM / "import_config.json", dry_run=True, source_overrides=overrides)
    assert lines  # produced output, no exception


def test_mode_equivalence_entity_counts():
    multi = _filter_rows(
        ECOM / "import_config.json",
        {src: str(BENCH / fname) for src, fname in bd.SOURCE_FILES.items()},
    )
    combined = _filter_rows(
        ECOM / "import_config_combined.json",
        {"ecommerce": str(BENCH / bd.JOIN_FILE)},
    )
    assert multi == combined
