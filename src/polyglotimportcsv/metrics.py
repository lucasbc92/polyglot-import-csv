"""Per-phase import metrics: collector + module-level current instance (spec §4.4).

The runner owns one ``MetricsCollector`` per run and publishes it via
``set_current``; importers record through ``timed_phase`` without any change
to their frozen signature. Phases: read, filter, map, write.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional

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
