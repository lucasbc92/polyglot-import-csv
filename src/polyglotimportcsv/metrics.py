"""Per-phase import metrics: collector + module-level current instance (spec §4.4).

The runner owns one ``MetricsCollector`` per run and publishes it via
``set_current``; importers record through ``timed_phase`` without any change
to their frozen signature. Phases: read, filter, map, write.
"""

from __future__ import annotations

import platform
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from polyglotimportcsv.benchmark_io import write_json_and_csv

PHASES = ("read", "filter", "map", "write")


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


class _Timed:
    """Mutable row counter handed out by ``timed``/``timed_phase``."""

    def __init__(self) -> None:
        self.rows = 0


class MetricsCollector:
    def __init__(self) -> None:
        self._entries: List[PhaseMetric] = []

    def record(
        self, backend: str, entity: str, phase: str, *, rows: int, seconds: float
    ) -> None:
        self._entries.append(PhaseMetric(backend, entity, phase, rows, seconds))

    @contextmanager
    def timed(self, backend: str, entity: str, phase: str) -> Iterator[_Timed]:
        t = _Timed()
        start = time.perf_counter()
        try:
            yield t
        finally:
            self.record(
                backend, entity, phase, rows=t.rows, seconds=time.perf_counter() - start
            )

    def entries(self) -> List[PhaseMetric]:
        return list(self._entries)

    def to_records(self) -> List[Dict[str, object]]:
        return [m.to_record() for m in self._entries]


_current: Optional[MetricsCollector] = None


def set_current(collector: Optional[MetricsCollector]) -> None:
    global _current
    _current = collector


def current() -> Optional[MetricsCollector]:
    return _current


@contextmanager
def timed_phase(backend: str, entity: str, phase: str) -> Iterator[_Timed]:
    """Record into the current collector; harmless no-op when none is active."""
    if _current is None:
        yield _Timed()
        return
    with _current.timed(backend, entity, phase) as t:
        yield t


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
