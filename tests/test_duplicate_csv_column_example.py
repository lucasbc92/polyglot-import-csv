"""Smoke test for the shipped duplicate csv_column mapping example (spec §2.4)."""

import re
from pathlib import Path

from polyglotimportcsv.runner import run_import

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data" / "ecommerce" / "import_config_duplicate_csv_column_example.json"
SGBD_CONFIG = ROOT / "data" / "ecommerce" / "sgbd_config.json"


def test_duplicate_csv_column_example_dry_run_succeeds():
    lines = run_import(CONFIG, sgbd_config_path=SGBD_CONFIG, dry_run=True)
    assert any(re.match(r"\s*entity categories: [1-9]\d* row\(s\)", L) for L in lines)
