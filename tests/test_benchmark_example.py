"""The committed reference dataset drives the dry-run smoke, in both layouts."""

from pathlib import Path

import pytest

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


@pytest.mark.parametrize("mode", ["multi", "combined"])
def test_dry_run_smoke_on_reference(mode):
    cfg_name = "import_config.json" if mode == "multi" else "import_config_combined.json"
    overrides = (
        {src: str(BENCH / fname) for src, fname in bd.SOURCE_FILES.items()}
        if mode == "multi" else {"ecommerce": str(BENCH / bd.JOIN_FILE)}
    )
    c = MetricsCollector()
    lines = run_import(ECOM / cfg_name, dry_run=True, source_overrides=overrides, collector=c)
    assert any(line.startswith("[neo4j] :PURCHASED: ") for line in lines)
    # every one of the 1000 rows is read by the inference and by the validation
    assert {m.phase: m.rows for m in c.entries()} == {"infer": 1000, "validate": 1000}
