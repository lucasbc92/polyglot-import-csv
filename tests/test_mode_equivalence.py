"""Multi-CSV mode and combined mode produce identical dry-run counts (spec §7)."""

import re
from pathlib import Path

from polyglotimportcsv.runner import run_import

ROOT = Path(__file__).resolve().parents[1]
MULTI = ROOT / "data" / "ecommerce" / "import_config.json"
COMBINED = ROOT / "data" / "ecommerce" / "import_config_combined.json"

_COUNT_LINE = re.compile(r"^\s*(entity|collection|table|label)\s+(\S+): (\d+)")


def _counts(lines):
    out = {}
    for line in lines:
        m = _COUNT_LINE.match(line)
        if m:
            out[f"{m.group(1)} {m.group(2)}"] = int(m.group(3))
    return out


def test_both_modes_yield_identical_entity_counts():
    multi = _counts(run_import(MULTI, dry_run=True))
    combined = _counts(run_import(COMBINED, dry_run=True))
    assert multi == combined
    assert multi, "expected at least one counted entity"
