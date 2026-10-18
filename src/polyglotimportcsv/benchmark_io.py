"""Shared JSON+CSV writer for benchmark output (spec §3.4, §4.4).

Leaf module: stdlib only, no imports from other polyglotimportcsv modules,
so it can be used by both ``metrics.write_benchmark_files`` and
``benchmark_results.write_consolidated`` without creating a cycle.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


def check_csv_header(csv_path: "str | Path", csv_fields: Tuple[str, ...]) -> None:
    """Raise ``ValueError`` if ``csv_path`` exists with a header other than ``csv_fields``."""
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        existing = fh.readline().rstrip("\n\r")
    if existing and existing != ",".join(csv_fields):
        raise ValueError(
            f"CSV header mismatch in {csv_path}: file has {existing!r} but "
            f"this run writes {','.join(csv_fields)!r}. Move or rename the old "
            "file (its columns changed)."
        )


def write_json_and_csv(
    out_dir: "str | Path",
    metadata: Dict[str, object],
    records: List[Dict[str, object]],
    *,
    json_prefix: str,
    csv_name: str,
    csv_fields: Tuple[str, ...],
    payload_key: str,
) -> Tuple[Path, Path]:
    """Write ``<json_prefix>_<timestamp>.json`` ({"metadata":..., payload_key: records})
    and append ``csv_name`` (header written only when the file is new; each row's
    ``timestamp`` column comes from ``metadata['timestamp']``)."""
    out = Path(out_dir)
    csv_path = out / csv_name
    # Before the JSON is written, so a refused CSV leaves no stray run file.
    check_csv_header(csv_path, csv_fields)
    new_file = not csv_path.exists()
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out / f"{json_prefix}_{stamp}.json"
    json_path.write_text(
        json.dumps({"metadata": metadata, payload_key: records}, indent=2, default=str),
        encoding="utf-8",
    )
    ts = metadata.get("timestamp", "")
    with csv_path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=csv_fields)
        if new_file:
            writer.writeheader()
        for rec in records:
            row = {k: rec[k] for k in csv_fields if k != "timestamp"}
            row["timestamp"] = ts
            writer.writerow(row)
    return json_path, csv_path
