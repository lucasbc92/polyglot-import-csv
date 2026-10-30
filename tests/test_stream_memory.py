"""Bounded-memory proof.

Checked without any live database: peak memory stays roughly constant as total
row count grows (bounded by one read chunk plus the still-open partition
buffers), by streaming two hand-written CSVs of very different sizes through a
discard sink under ``tracemalloc``. The inference read (``plan_import``) is held to
the same bound.
"""

from __future__ import annotations

import dataclasses
import gc
import tracemalloc
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from polyglotimportcsv import csv_reader
from polyglotimportcsv import stream_runner as sr
from polyglotimportcsv.import_plan import plan_import
from polyglotimportcsv.stream_source import chunk_rows


def _write_csv(path: Path, header: List[str], rows: List[Tuple[Any, ...]]) -> None:
    path.write_text(
        ",".join(header) + "\n"
        + "\n".join(",".join(str(c) for c in r) for r in rows) + "\n",
        encoding="utf-8",
    )


class _NullSink:
    """Discards every batch; used to isolate the orchestrator's own memory footprint."""

    def create_schema(self) -> None:
        pass

    def ensure_partition(self, partition_name, binding) -> None:
        pass

    def write_batch(self, partition_name, binding, batch) -> int:
        return len(batch)

    def close(self) -> None:
        pass


def _write_wide_csv(path: Path, n_rows: int) -> None:
    rows = [(i, f"name{i}", f"note-{i}-{'x' * 20}") for i in range(n_rows)]
    _write_csv(path, ["id", "name", "note"], rows)


# Read-chunk granularity for the memory probe: rows per chunk of every source, set on
# the plan so that both test files below span many chunks and reach the
# orchestrator's steady-state peak quickly, keeping the test fast.
_PROBE_CHUNK = 2048


def _streaming_peak(config: Dict[str, Any], base_dir: Path) -> int:
    """Peak traced memory of the write read alone (the plan is built beforehand)."""
    plan = plan_import(config, base_dir, dbms_names=["redis"])
    plan = dataclasses.replace(plan, rows_per_chunk={n: _PROBE_CHUNK for n in plan.sources_cfg})
    gc.collect()
    tracemalloc.start()
    tracemalloc.reset_peak()
    sr.run_stream_import(plan, sink_factories={"redis": lambda cfg: _NullSink()})
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return peak


def _measure_peak(csv_path: Path, base_dir: Path) -> int:
    config = {
        "sources": {"items": csv_path.name},
        "redis": {
            "entities": {
                "items": {
                    "source": "items",
                    "columns": {"id": {"is_key": True}},
                }
            }
        },
    }
    return _streaming_peak(config, base_dir)


def test_stream_peak_does_not_scale_with_rows(tmp_path):
    # BOTH sizes must exceed the read chunk by several multiples: peak memory is
    # bounded by one read chunk plus sub-chunk partition buffers, so it only
    # settles to its steady-state value once a file spans many chunks. A file
    # smaller than one chunk reads as a single (short) chunk and never reaches
    # that steady state, which would understate the small-file peak and inflate
    # the ratio -- so keep both sizes well above _PROBE_CHUNK.
    small_path = tmp_path / "small.csv"
    large_path = tmp_path / "large.csv"
    _write_wide_csv(small_path, 10_000)
    _write_wide_csv(large_path, 40_000)

    peak_small = _measure_peak(small_path, tmp_path)
    gc.collect()
    peak_large = _measure_peak(large_path, tmp_path)

    # A 4x row increase must NOT produce anywhere near 4x peak memory: the
    # orchestrator only ever holds one read chunk plus small, sub-chunk
    # partition buffers, regardless of total file size. In practice the ratio
    # is ~1.1x; 2.0x leaves generous headroom for allocator/measurement noise
    # while still proving strongly sub-linear (bounded) memory.
    assert peak_large < 2.0 * peak_small, (
        f"peak memory scaled with row count: peak_small={peak_small} "
        f"peak_large={peak_large} (ratio={peak_large / peak_small:.2f})"
    )


def test_stream_union_peak_does_not_scale_with_rows(tmp_path):
    """Union streaming stays bounded: per-chunk reindex never accumulates across chunks."""

    def _write_union_pair(dir_path: Path, n_rows: int) -> None:
        # Disjoint extra columns force a genuine heterogeneous superset.
        _write_csv(
            dir_path / "a.csv", ["id", "a_col"],
            [(i, f"a{i}-{'x' * 12}") for i in range(n_rows)],
        )
        _write_csv(
            dir_path / "b.csv", ["id", "b_col"],
            [(i, f"b{i}-{'y' * 12}") for i in range(n_rows)],
        )

    def _measure(dir_path: Path) -> int:
        config = {
            "sources": {"a": "a.csv", "b": "b.csv"},
            "redis": {
                "entities": {
                    "activity": {"source": ["a", "b"], "columns": {"id": {"is_key": True}}}
                }
            },
        }
        return _streaming_peak(config, dir_path)

    small_dir = tmp_path / "small"
    large_dir = tmp_path / "large"
    small_dir.mkdir()
    large_dir.mkdir()
    _write_union_pair(small_dir, 10_000)
    _write_union_pair(large_dir, 40_000)

    peak_small = _measure(small_dir)
    gc.collect()
    peak_large = _measure(large_dir)

    assert peak_large < 2.0 * peak_small, (
        f"union peak memory scaled with row count: peak_small={peak_small} "
        f"peak_large={peak_large} (ratio={peak_large / peak_small:.2f})"
    )


#: Memory budget of one read block in the inference test: about 700 rows of its file.
_INFERENCE_CHUNK_MB = 0.2


def _inference_peak(base_dir: Path, n_rows: int, reads: List[Tuple[str, Any]]) -> int:
    """Peak traced memory of ``plan_import`` over a file of ``n_rows`` rows.

    ``when`` is dates after a block of junk, 90% dates in all: the blocks disagree on
    it, so its kind is settled by the exact re-read of that column as well. The two wide
    numeric columns make the file big enough for the CSV parser to fill its own buffer.
    """
    junk = n_rows // 10
    minutes = pd.date_range("2023-01-01", periods=100, freq="min").strftime("%Y-%m-%dT%H:%M:%SZ")
    when = ["n/a"] * junk + [minutes[i % 100] for i in range(n_rows - junk)]
    _write_csv(base_dir / "ev.csv", ["id", "when", "a", "b"],
               [(i, w, "1" * 40, "2" * 40) for i, w in enumerate(when)])
    config = {
        "sources": {"ev": "ev.csv"},
        "redis": {"entities": {"ev": {"source": "ev", "columns": {"id": {"is_key": True}}}}},
    }
    assert chunk_rows("ev", base_dir / "ev.csv", _INFERENCE_CHUNK_MB) < n_rows // 4
    reads.clear()
    gc.collect()
    tracemalloc.start()
    tracemalloc.reset_peak()
    plan = plan_import(config, base_dir, dbms_names=["redis"], chunk_mb=_INFERENCE_CHUNK_MB)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert plan.profiles["ev"].kinds["when"] == "datetime"
    assert ("ev.csv", ["when"]) in reads, "the exact re-read did not run"
    return peak


def test_inference_peak_does_not_scale_with_rows(tmp_path, monkeypatch, reads):
    # Probe rounds of 10 distinct values, so that the early stop bites on blocks this small.
    monkeypatch.setattr(csv_reader, "_DATETIME_PROBE_CHUNK", 10)
    (tmp_path / "small").mkdir()
    (tmp_path / "large").mkdir()
    small = _inference_peak(tmp_path / "small", 4_000, reads)
    gc.collect()
    large = _inference_peak(tmp_path / "large", 16_000, reads)
    assert large < 1.5 * small, f"peak {small} -> {large} ({large / small:.2f}x)"
