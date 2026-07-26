"""Bounded-memory proof + stream/materialize equivalence (spec: streaming import, Task 6).

Two properties are checked without any live database:

1. ``test_stream_peak_does_not_scale_with_rows`` proves peak memory stays
   roughly constant as total row count grows (bounded by one read chunk plus
   the still-open partition buffers), by streaming two hand-written CSVs of
   very different sizes through a discard sink under ``tracemalloc``.
2. ``test_stream_matches_materialize_rows`` proves the streaming path
   produces the same rows, per partition, as the existing materialize path
   for the committed 1000-row reference dataset and the real ecommerce
   config -- same partitions, same row counts, same key/data values.
"""

from __future__ import annotations

import gc
import json
import tracemalloc
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from polyglotimportcsv import stream_runner as sr
from polyglotimportcsv.filter_engine import apply_filters, expand_each
from polyglotimportcsv.mapping_resolver import resolve_backend_entities
from polyglotimportcsv.sources import load_sources

REPO_ROOT = Path(__file__).resolve().parents[1]


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


# Read-chunk granularity for the memory probe. Deliberately smaller than the
# production READ_CHUNK (8192) so that both test files below span many chunks
# and reach the orchestrator's steady-state peak quickly, keeping the test fast.
_PROBE_CHUNK = 2048


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
    gc.collect()
    tracemalloc.start()
    tracemalloc.reset_peak()
    sr.run_stream_import(
        config,
        base_dir,
        sink_factories={"redis": lambda cfg: _NullSink()},
        only=["redis"],
        chunksize=_PROBE_CHUNK,
    )
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return peak


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


class _RecordingSink:
    """Records every batch it receives, per partition, without touching a real DB."""

    def __init__(self) -> None:
        self.batches: Dict[str, List[pd.DataFrame]] = {}

    def create_schema(self) -> None:
        pass

    def ensure_partition(self, partition_name, binding) -> None:
        pass

    def write_batch(self, partition_name, binding, batch: pd.DataFrame) -> int:
        self.batches.setdefault(partition_name, []).append(batch.copy())
        return len(batch)

    def close(self) -> None:
        pass


def _compare_columns(df: pd.DataFrame, key_cols: List[str]) -> List[Tuple[str, ...]]:
    """Sorted list of (stringified) tuples over the given columns, order-independent."""
    return sorted(tuple("" if pd.isna(v) else str(v) for v in row) for row in df[key_cols].itertuples(index=False))


def test_stream_matches_materialize_rows():
    """Redis entities from the ecommerce config, streamed vs. materialized over
    the committed data/benchmark/ reference dataset, must yield identical rows."""
    config_path = REPO_ROOT / "data" / "ecommerce" / "import_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    base_dir = config_path.parent

    bench_dir = REPO_ROOT / "data" / "benchmark"
    overrides = {
        "stock": str(bench_dir / "ecommerce_stock.csv"),
        "purchase": str(bench_dir / "ecommerce_purchase.csv"),
        "select_product": str(bench_dir / "ecommerce_select_product.csv"),
        "add_to_cart": str(bench_dir / "ecommerce_add_to_cart.csv"),
    }

    dbms = "redis"

    # --- Stream path: record every batch the sink receives ---
    sink = _RecordingSink()
    sr.run_stream_import(
        config,
        base_dir,
        sink_factories={dbms: lambda cfg: sink},
        only=[dbms],
        source_overrides=overrides,
        chunksize=8192,
    )
    stream_rows: Dict[str, pd.DataFrame] = {
        partition: pd.concat(dfs, ignore_index=True)
        for partition, dfs in sink.batches.items()
    }

    # --- Materialize path: reproduce what run_import would deliver, DB-free ---
    sources = load_sources(config["sources"], base_dir, overrides)
    bound = resolve_backend_entities(config[dbms], sources, {}, strategy="optimized")
    mat_rows: Dict[str, pd.DataFrame] = {}
    for ename, be in bound.items():
        filters = be.cfg.get("filters") or []
        non_each = [f for f in filters if f.get("operator") != "each"]
        dff = apply_filters(be.df, non_each, be.kinds)
        for part_name, part_df in expand_each(dff, filters, ename):
            mat_rows[part_name] = part_df

    assert set(stream_rows) == set(mat_rows) == {"shopping_cart", "user_session"}

    # Per-partition key/data columns to compare (robust to row order and to
    # the '_source' column, which stream/materialize may populate identically
    # but which is not the point of this comparison).
    compare_cols = {
        "shopping_cart": ["shopping_cart_id", "user_id", "cart_product_id", "cart_quantity"],
        "user_session": ["user_id", "user_name", "user_email"],
    }

    for partition, cols in compare_cols.items():
        s_df = stream_rows[partition]
        m_df = mat_rows[partition]
        assert len(s_df) == len(m_df) > 0, f"{partition}: row count mismatch"
        assert _compare_columns(s_df, cols) == _compare_columns(m_df, cols), (
            f"{partition}: row contents differ between stream and materialize paths"
        )
