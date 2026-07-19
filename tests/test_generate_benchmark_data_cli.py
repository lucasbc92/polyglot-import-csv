"""CLI wrapper for the dataset generator."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_benchmark_data.py"


def _load_main():
    spec = importlib.util.spec_from_file_location("generate_benchmark_data", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.main


def test_cli_writes_multi(tmp_path):
    main = _load_main()
    rc = main(["--rows", "20", "--seed", "42", "--out", str(tmp_path), "--mode", "multi"])
    assert rc == 0
    for fname in ("ecommerce_stock.csv", "ecommerce_purchase.csv",
                  "ecommerce_select_product.csv", "ecommerce_add_to_cart.csv"):
        assert (tmp_path / fname).is_file()


def test_cli_writes_both(tmp_path):
    main = _load_main()
    rc = main(["--rows", "20", "--out", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "ecommerce_join.csv").is_file()
