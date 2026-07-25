"""Bounded-memory streaming orchestrator (spec: streaming import, Task 3).

Reads every declared source in fixed-size chunks (``stream_source``), binds
each entity lazily from its first chunk (``stream_binding``), applies
row-local filters/casting/each-splitting per chunk (``filter_engine``,
``casting``), and flushes ``batch``-sized row groups to a ``DbmsSink`` per
partition. Peak memory stays ~one read chunk plus the still-open partition
buffers (each smaller than one chunk), regardless of total file size.

The orchestrator is DBMS-agnostic: it never emits SQL/Cypher and never
deduplicates rows. Both are the sink's responsibility, applied inside
``write_batch``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

import pandas as pd

from polyglotimportcsv.business_exception import ImportExecutionError
from polyglotimportcsv.casting import cast_frame
from polyglotimportcsv.dbms_sink import DbmsSink, SinkFactory
from polyglotimportcsv.filter_engine import apply_filters, expand_each
from polyglotimportcsv.stream_binding import EntityBinding, bind_entity_from_sample
from polyglotimportcsv.stream_source import READ_CHUNK, iter_entity_chunks
from polyglotimportcsv.validation import BACKENDS

#: DBMS flush granularity (same constant as redis/neo4j batched writes).
BATCH = 1000


def _dbms_names(config: Dict[str, Any], only: Optional[Iterable[str]]) -> List[str]:
    names = [b for b in BACKENDS if b in config]
    if only is None:
        return names
    only_set = {str(x).strip().lower() for x in only if x and str(x).strip()}
    return [b for b in names if b in only_set]


def _validate_no_union_sources(entities: Dict[str, Any]) -> None:
    for ename, ecfg in entities.items():
        if isinstance((ecfg or {}).get("source"), list):
            raise ImportExecutionError(
                f"streaming does not support union (list) sources: {ename}"
            )


def _matches(ename: str, ecfg: Dict[str, Any], yielded_name: str) -> bool:
    """An entity is fed by a yielded (source_name/origin) chunk when either:

    - its declared ``source`` equals the yielded name (multi source, or the
      source name an explicit ``source:`` points to), or
    - its own name equals the yielded name (combined mode routes by origin
      value, and/or an entity with no declared ``source`` defaults to a
      source named after itself, per ``mapping_resolver.bind_entity_source``).
    """
    return ecfg.get("source") == yielded_name or ename == yielded_name


def _flush_ready(
    partition_name: str,
    buffers: Dict[str, List[pd.DataFrame]],
    partition_binding: Dict[str, EntityBinding],
    seen_partitions: Set[str],
    written: Dict[str, int],
    sink: DbmsSink,
    batch: int,
) -> None:
    """Flush as many full ``batch``-sized groups as are ready; keep the remainder buffered."""
    pending = buffers.get(partition_name) or []
    total = sum(len(d) for d in pending)
    if total < batch:
        return
    combined = pd.concat(pending, ignore_index=True)
    binding = partition_binding[partition_name]
    while len(combined) >= batch:
        to_write = combined.iloc[:batch].reset_index(drop=True)
        if partition_name not in seen_partitions:
            sink.ensure_partition(partition_name, binding)
            seen_partitions.add(partition_name)
        sink.write_batch(partition_name, binding, to_write)
        written[partition_name] = written.get(partition_name, 0) + batch
        combined = combined.iloc[batch:].reset_index(drop=True)
    buffers[partition_name] = [combined] if len(combined) else []


def _flush_remainder(
    partition_name: str,
    buffers: Dict[str, List[pd.DataFrame]],
    partition_binding: Dict[str, EntityBinding],
    seen_partitions: Set[str],
    written: Dict[str, int],
    sink: DbmsSink,
) -> None:
    pending = buffers.get(partition_name) or []
    total = sum(len(d) for d in pending)
    if total == 0:
        return
    combined = pd.concat(pending, ignore_index=True)
    binding = partition_binding[partition_name]
    if partition_name not in seen_partitions:
        sink.ensure_partition(partition_name, binding)
        seen_partitions.add(partition_name)
    sink.write_batch(partition_name, binding, combined)
    written[partition_name] = written.get(partition_name, 0) + len(combined)
    buffers[partition_name] = []


def run_stream_import(
    config: Dict[str, Any],
    base_dir: "str | Path",
    *,
    sink_factories: Dict[str, SinkFactory],
    only: Optional[Iterable[str]] = None,
    create_schema: bool = True,
    source_overrides: Optional[Dict[str, str]] = None,
    chunksize: int = READ_CHUNK,
    batch: int = BATCH,
) -> Dict[str, int]:
    """Stream every configured DBMS's entities through a ``DbmsSink`` in bounded memory.

    Returns ``{partition_name: rows_written}`` aggregated across every
    processed DBMS (a partition name written by more than one DBMS sums its
    counts).
    """
    base_dir = Path(base_dir)
    dbms_names = _dbms_names(config, only)

    # Fail fast, before opening any sink: union (list) sources are out of
    # scope for streaming (see plan Task 3).
    for dbms in dbms_names:
        _validate_no_union_sources((config[dbms].get("entities") or {}))

    written: Dict[str, int] = {}

    for dbms in dbms_names:
        bcfg = config[dbms]
        entities: Dict[str, Any] = bcfg.get("entities") or {}

        sink = sink_factories[dbms](bcfg)
        if create_schema:
            sink.create_schema()

        bindings: Dict[str, EntityBinding] = {}
        buffers: Dict[str, List[pd.DataFrame]] = {}
        partition_binding: Dict[str, EntityBinding] = {}
        seen_partitions: Set[str] = set()

        for yielded_name, chunk in iter_entity_chunks(
            config.get("sources") or {}, base_dir, source_overrides, chunksize
        ):
            targets = [
                (ename, ecfg)
                for ename, ecfg in entities.items()
                if _matches(ename, ecfg, yielded_name)
            ]
            for ename, ecfg in targets:
                if ename not in bindings:
                    bindings[ename] = bind_entity_from_sample(ename, ecfg, chunk, yielded_name)
                binding = bindings[ename]
                filters = binding.cfg.get("filters") or []
                non_each = [f for f in filters if f.get("operator") != "each"]
                filtered = apply_filters(chunk, non_each, binding.kinds)
                casted = cast_frame(filtered, binding.kinds, strategy="optimized")
                for partition_name, part_df in expand_each(casted, filters, ename):
                    buffers.setdefault(partition_name, []).append(part_df)
                    partition_binding[partition_name] = binding
                    _flush_ready(
                        partition_name, buffers, partition_binding,
                        seen_partitions, written, sink, batch,
                    )

        for partition_name in list(buffers.keys()):
            _flush_remainder(
                partition_name, buffers, partition_binding,
                seen_partitions, written, sink,
            )

        sink.close()

    return written
