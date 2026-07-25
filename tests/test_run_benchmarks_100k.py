import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_benchmarks_100k as r100  # noqa: E402


def test_estimate_scales_with_total_rows():
    # Reference point is 8000 total rows; 80000 rows must be ~10x the effort.
    est_8k = r100.estimate_seconds(["postgres"], size=8_000, runs=1)["postgres"]
    est_80k = r100.estimate_seconds(["postgres"], size=80_000, runs=1)["postgres"]
    assert abs(est_80k / est_8k - 10.0) < 0.01


def test_reference_total_rows_is_8000():
    assert r100._REFERENCE_TOTAL_ROWS == 8_000
