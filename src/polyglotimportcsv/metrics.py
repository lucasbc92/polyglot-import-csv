"""Per-phase import metrics (spec §4.4).

The runner owns one ``MetricsCollector`` per run and records the three reads of
an import into it: ``infer`` and ``validate`` once each, ``write`` once per DBMS.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from polyglotimportcsv.benchmark_io import write_json_and_csv

PHASES = ("infer", "validate", "write")


@dataclass
class PhaseMetric:
    backend: str
    entity: str
    phase: str
    rows: int
    seconds: float

    @property
    def rows_per_second(self) -> Optional[float]:
        if self.seconds <= 0:
            return None
        return self.rows / self.seconds

    def to_record(self) -> Dict[str, object]:
        return {
            "backend": self.backend,
            "entity": self.entity,
            "phase": self.phase,
            "rows": self.rows,
            "seconds": self.seconds,
            "rows_per_second": self.rows_per_second,
        }


class MetricsCollector:
    def __init__(self) -> None:
        self._entries: List[PhaseMetric] = []

    def record(
        self, backend: str, entity: str, phase: str, *, rows: int, seconds: float
    ) -> None:
        self._entries.append(PhaseMetric(backend, entity, phase, rows, seconds))

    def entries(self) -> List[PhaseMetric]:
        return list(self._entries)

    def to_records(self) -> List[Dict[str, object]]:
        return [m.to_record() for m in self._entries]


_CSV_FIELDS = ("timestamp", "backend", "entity", "phase", "rows", "seconds", "rows_per_second")


def environment_metadata(
    config_path: "str | Path", source_rows: Dict[str, int]
) -> Dict[str, object]:
    """Run metadata stored with each benchmark (spec §4.4)."""
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "config": str(config_path),
        "source_rows": source_rows,
    }


def write_benchmark_files(
    collector: MetricsCollector,
    metadata: Dict[str, object],
    out_dir: "str | Path" = "benchmarks",
) -> Tuple[Path, Path]:
    """Write benchmark_<timestamp>.json and append benchmark_history.csv."""
    return write_json_and_csv(
        out_dir, metadata, collector.to_records(),
        json_prefix="benchmark", csv_name="benchmark_history.csv",
        csv_fields=_CSV_FIELDS, payload_key="metrics",
    )
