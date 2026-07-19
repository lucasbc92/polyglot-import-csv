"""Consolidate benchmark runs: median across repetitions + JSON/CSV output (spec §3.4)."""

from __future__ import annotations

import csv
import json
import statistics
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

_RESULT_FIELDS = (
    "timestamp", "size", "mode", "backend", "entity", "phase",
    "rows", "median_seconds", "rows_per_second",
)


def median_results(labeled_runs: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """Median ``seconds`` per ``(size, mode, backend, entity, phase)``.

    ``rows`` is constant across repetitions (same dataset); ``rows_per_second``
    is recomputed from the median.
    """
    groups: Dict[Tuple, Dict[str, object]] = {}
    order: List[Tuple] = []
    for run in labeled_runs:
        for rec in run["records"]:
            key = (run["size"], run["mode"], rec["backend"], rec["entity"], rec["phase"])
            if key not in groups:
                groups[key] = {"rows": rec["rows"], "seconds": []}
                order.append(key)
            groups[key]["seconds"].append(rec["seconds"])

    results: List[Dict[str, object]] = []
    for key in order:
        size, mode, backend, entity, phase = key
        g = groups[key]
        med = statistics.median(g["seconds"])
        rps = (g["rows"] / med) if med > 0 else None
        results.append({
            "size": size, "mode": mode, "backend": backend,
            "entity": entity, "phase": phase, "rows": g["rows"],
            "median_seconds": med, "rows_per_second": rps,
        })
    return results


def write_consolidated(
    results: List[Dict[str, object]],
    metadata: Dict[str, object],
    out_dir: "str | Path" = "benchmarks",
) -> Tuple[Path, Path]:
    """Write ``benchmark_run_<timestamp>.json`` and append ``benchmark_results.csv``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out / f"benchmark_run_{stamp}.json"
    json_path.write_text(
        json.dumps({"metadata": metadata, "results": results}, indent=2, default=str),
        encoding="utf-8",
    )
    csv_path = out / "benchmark_results.csv"
    new_file = not csv_path.exists()
    ts = metadata.get("timestamp", "")
    with csv_path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_RESULT_FIELDS)
        if new_file:
            writer.writeheader()
        for rec in results:
            row = {k: rec[k] for k in _RESULT_FIELDS if k != "timestamp"}
            row["timestamp"] = ts
            writer.writerow(row)
    return json_path, csv_path
