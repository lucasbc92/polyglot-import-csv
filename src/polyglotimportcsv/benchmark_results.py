"""Consolidate benchmark runs: median across repetitions + JSON/CSV output (spec §3.4)."""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Dict, List, Tuple

from polyglotimportcsv.benchmark_io import write_json_and_csv

_RESULT_FIELDS = (
    "timestamp", "size", "mode", "strategy", "execution", "backend", "entity",
    "phase", "rows", "median_seconds", "rows_per_second", "peak_memory_mb",
)


def median_results(labeled_runs: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """Median ``seconds`` per ``(size, mode, strategy, execution, backend, entity, phase)``.

    ``rows`` is constant across repetitions (same dataset); ``rows_per_second``
    is recomputed from the median. ``peak_memory_mb`` is a per-import (whole
    process) measurement carried on the labeled run, so each repetition
    contributes one value to the group; the median across repetitions is
    reported (``None`` if no run supplied a peak).
    """
    groups: Dict[Tuple, Dict[str, object]] = {}
    order: List[Tuple] = []
    for run in labeled_runs:
        for rec in run["records"]:
            key = (run["size"], run["mode"], run["strategy"], run["execution"],
                   rec["backend"], rec["entity"], rec["phase"])
            if key not in groups:
                groups[key] = {"rows": rec["rows"], "seconds": [], "peak": []}
                order.append(key)
            groups[key]["seconds"].append(rec["seconds"])
            groups[key]["peak"].append(run.get("peak_memory_mb"))

    results: List[Dict[str, object]] = []
    for key in order:
        size, mode, strategy, execution, backend, entity, phase = key
        g = groups[key]
        med = statistics.median(g["seconds"])
        rps = (g["rows"] / med) if med > 0 else None
        peaks = [p for p in g["peak"] if p is not None]
        peak = statistics.median(peaks) if peaks else None
        results.append({
            "size": size, "mode": mode, "strategy": strategy, "execution": execution,
            "backend": backend, "entity": entity, "phase": phase,
            "rows": g["rows"], "median_seconds": med, "rows_per_second": rps,
            "peak_memory_mb": peak,
        })
    return results


def write_consolidated(
    results: List[Dict[str, object]],
    metadata: Dict[str, object],
    out_dir: "str | Path" = "benchmarks",
) -> Tuple[Path, Path]:
    """Write ``benchmark_run_<timestamp>.json`` and append ``benchmark_results.csv``."""
    return write_json_and_csv(
        out_dir, metadata, results,
        json_prefix="benchmark_run", csv_name="benchmark_results.csv",
        csv_fields=_RESULT_FIELDS, payload_key="results",
    )
