"""Bounded-memory streaming engine over the import plan.

Reads the plan's sources in the plan's read blocks (``stream_source``), applies
row-local filters/casting/each-splitting per block (``filter_engine``,
``casting``) to the entities bound in the plan (``import_plan``), and flushes
batch-sized row groups to a ``DbmsSink`` per partition. What the engine holds is
bounded by one read block plus the still-open partition buffers (each smaller than
one block), whatever the size of the file; how large a block is, and so the peak of
an import, is the choice of ``auto_size`` or of ``--chunk-size``.

``DbmsStream`` is one DBMS's share of that work. ``run_single_pass`` feeds every
DBMS of a plan from one read of its sources, for sinks that only check;
``run_stream_import`` runs it once per DBMS, over that DBMS's own sources, with
the sinks that write.

The engine is DBMS-agnostic: it never emits SQL/Cypher and never deduplicates
rows. Both are the sink's responsibility, applied inside ``write_batch``.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, replace
from functools import partial
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple

import pandas as pd

from polyglotimportcsv.business_exception import BusinessException, ImportExecutionError
from polyglotimportcsv.casting import cast_frame
from polyglotimportcsv.dbms_sink import DbmsSink, RowInspector, SinkFactory
from polyglotimportcsv.filter_engine import apply_filters, expand_each
from polyglotimportcsv.import_plan import ImportPlan, dbms_sources, declared_sources
from polyglotimportcsv.metrics import MetricsCollector
from polyglotimportcsv.stream_binding import EntityBinding, entity_source_names
from polyglotimportcsv.stream_source import iter_entity_chunks


logger = logging.getLogger(__name__)


@dataclass
class StreamCounts:
    """Rows per DBMS: written per partition (``":TYPE"`` for relationships), and per
    entity after the filters."""

    written: Dict[str, Dict[str, int]] = field(default_factory=dict)
    entity_rows: Dict[str, Dict[str, int]] = field(default_factory=dict)


def _matches(ename: str, ecfg: Dict[str, Any], yielded_name: str) -> bool:
    """Is a chunk yielded under ``yielded_name`` (a source name or origin value) one of
    the entity's own sources, the ones the plan bound it to (``entity_source_names``)?"""
    return yielded_name in entity_source_names(ename, ecfg)


def _flush_ready(
    partition_name: str,
    buffers: Dict[str, List[pd.DataFrame]],
    partition_binding: Dict[str, EntityBinding],
    seen_partitions: Set[str],
    written: Dict[str, int],
    sink: DbmsSink,
    batch: int,
    notify: Optional[Callable[[str, pd.DataFrame], None]] = None,
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
        if notify is not None:
            notify(partition_name, to_write)
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
    notify: Optional[Callable[[str, pd.DataFrame], None]] = None,
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
    if notify is not None:
        notify(partition_name, combined)
    written[partition_name] = written.get(partition_name, 0) + len(combined)
    buffers[partition_name] = []


def _process_chunk(
    chunk: pd.DataFrame,
    ecfg: Dict[str, Any],
    binding: EntityBinding,
    source: str,
) -> Tuple[pd.DataFrame, pd.DataFrame, List[Dict[str, Any]]]:
    """Run one chunk of ``source`` through the shared per-entity pipeline.

    Union entities are widened to the binding's superset (data_cols + _source,
    missing filled ""); then non-`each` filters and the vectorized cast are
    applied, the cast to the binding's ``cast_columns`` only. Returns (filtered raw rows, cast rows, filters) so the node loop can
    `expand_each` on the same filters. Both frames keep the chunk's index, the
    position of each data row in its file. Reused by the node loop and the
    relationship pass so both shape rows identically.
    """
    working = chunk
    if isinstance(ecfg.get("source"), list):
        working = chunk.reindex(columns=list(binding.kinds.keys()), fill_value="")
    filters = binding.cfg.get("filters") or []
    non_each = [f for f in filters if f.get("operator") != "each"]
    filtered = apply_filters(working, non_each, binding.kinds)
    casted = cast_frame(filtered, binding.kinds, source, binding.cast_columns)
    return filtered, casted, filters


def _dropped_by_split(casted: pd.DataFrame, parts: List[Tuple[str, pd.DataFrame]]) -> pd.Index:
    """The rows of ``casted`` that are in none of the ``expand_each`` parts."""
    if sum(len(part) for _, part in parts) == len(casted):
        return casted.index[:0]
    kept = casted.index[:0].append([part.index for _, part in parts])
    return casted.index[~casted.index.isin(kept)]


class DbmsStream:
    """One DBMS's entities fed chunk by chunk into its sink.

    Nodes first (``feed`` for every chunk, then ``finish_nodes``), then the
    relationships (``feed_relationships`` for every chunk of
    ``relationship_sources()``). ``written`` and ``entity_rows`` count as it goes.

    ``inspector``, when given, sees the rows before they are written
    (``dbms_sink.RowInspector``). A sink writes relationships when it has a
    ``write_relationships(rname, rspec, from_binding, to_binding, batch)`` method.

    The plan's config must have passed ``validation.validate_headers``: the engine
    does not check again, for instance, that a relationship names declared entities.
    """

    def __init__(
        self,
        dbms: str,
        plan: ImportPlan,
        sink: DbmsSink,
        on_batch: Optional[Callable[[str, str, pd.DataFrame], None]] = None,
        inspector: Optional[RowInspector] = None,
    ) -> None:
        self.dbms = dbms
        self.plan = plan
        self.sink = sink
        self._entities: Dict[str, Any] = plan.config[dbms].get("entities") or {}
        self._bindings = plan.bindings[dbms]
        self._batch = {ename: plan.entity_batch(dbms, ename) for ename in self._entities}
        self._notify = partial(on_batch, dbms) if on_batch is not None else None
        self._inspector = inspector
        self.written: Dict[str, int] = {}
        self.entity_rows: Dict[str, int] = {ename: 0 for ename in self._entities}
        self._buffers: Dict[str, List[pd.DataFrame]] = {}
        self._partition_binding: Dict[str, EntityBinding] = {}
        self._seen_partitions: Set[str] = set()

        # from-entity -> its relationships (drive each from its source once)
        self._write_rels = getattr(sink, "write_relationships", None)
        self._from_rels: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
        if self._write_rels is not None:
            for rname, rspec in (plan.config[dbms].get("relationships") or {}).items():
                self._from_rels.setdefault(rspec.get("from"), []).append((rname, rspec))

    def feed(self, source: str, chunk: pd.DataFrame) -> None:
        """Pass one chunk of ``source`` (a source name or origin value) to its entities."""
        for ename, ecfg in self._entities.items():
            if not _matches(ename, ecfg, source):
                continue
            binding = self._bindings[ename]
            raw, casted, filters = _process_chunk(chunk, ecfg, binding, source)
            parts = expand_each(casted, filters, ename)
            if self._inspector is not None:
                dropped = _dropped_by_split(casted, parts)
                if len(dropped):
                    self._inspector.inspect_unpartitioned_rows(
                        source, binding, raw.loc[dropped], casted.loc[dropped]
                    )
            for partition_name, part_df in parts:
                self.entity_rows[ename] += len(part_df)
                if self._inspector is not None:
                    part_raw = raw.loc[part_df.index]
                    self._inspector.inspect_rows(
                        source, partition_name, binding, part_raw, part_df
                    )
                self._buffers.setdefault(partition_name, []).append(part_df)
                self._partition_binding[partition_name] = binding
                _flush_ready(
                    partition_name, self._buffers, self._partition_binding,
                    self._seen_partitions, self.written, self.sink, self._batch[ename],
                    notify=self._notify,
                )

    def finish_nodes(self) -> None:
        """Write what is left in the partition buffers, then create the partition of
        every entity a relationship links that got no row.

        Any other entity without rows gets no partition. A linked one needs it: the
        foreign key PostgreSQL adds at ``close()`` names both tables. (A relationship
        never links an entity split by an ``each`` filter.)
        """
        for partition_name in list(self._buffers.keys()):
            _flush_remainder(
                partition_name, self._buffers, self._partition_binding,
                self._seen_partitions, self.written, self.sink,
                notify=self._notify,
            )
        relationships = (self.plan.config[self.dbms].get("relationships") or {}).values()
        linked = {rspec.get(end) for rspec in relationships for end in ("from", "to")}
        for ename, binding in self._bindings.items():
            if ename in linked and ename not in self._seen_partitions:
                self.sink.ensure_partition(ename, binding)
                self._seen_partitions.add(ename)

    def relationship_sources(self) -> Dict[str, Any]:
        """The declared sources the relationship pass reads; ``{}`` when the sink writes
        no relationships or the DBMS declares none."""
        if not self._from_rels:
            return {}
        names = [n for e in self._from_rels for n in entity_source_names(e, self._entities[e])]
        return declared_sources(self.plan.sources_cfg, names)

    def relationship_columns(self) -> Dict[str, Optional[Set[str]]]:
        """Declared source -> the columns the relationship pass needs of it: those the
        `from` entities reading it have cast (``EntityBinding.cast_columns``), which
        hold everything an edge is built from. ``None`` for a source to read whole."""
        wanted: Dict[str, Optional[Set[str]]] = {}
        for from_e in self._from_rels:
            needed = self._bindings[from_e].cast_columns
            for name in entity_source_names(from_e, self._entities[from_e]):
                profile = self.plan.profiles[name]
                columns = None if needed is None else needed & set(profile.header)
                if not columns or wanted.get(profile.declared, set()) is None:
                    wanted[profile.declared] = None
                else:
                    wanted.setdefault(profile.declared, set()).update(columns)
        return wanted

    def feed_relationships(self, source: str, chunk: pd.DataFrame) -> None:
        """Write the relationships driven by one chunk of their `from` entity's source,
        in batches of the `from` entity's write batch."""
        for from_e, rlist in self._from_rels.items():
            ecfg = self._entities[from_e]
            if not _matches(from_e, ecfg, source):
                continue
            from_binding = self._bindings[from_e]
            _, casted, _ = _process_chunk(chunk, ecfg, from_binding, source)
            batch = self._batch[from_e]
            for rname, rspec in rlist:
                to_binding = self._bindings[rspec["to"]]
                if self._inspector is not None:
                    self._inspector.inspect_relationship_rows(
                        source, rname, rspec, from_binding, to_binding, casted
                    )
                # In write batches, as the nodes are: a read block can hold far more
                # rows than one write should send.
                n = 0
                for start in range(0, len(casted), batch):
                    n += self._write_rels(
                        rname, rspec, from_binding, to_binding, casted.iloc[start:start + batch]
                    )
                key = f":{rspec.get('type') or rname}"
                self.written[key] = self.written.get(key, 0) + n


def _read(
    plan: ImportPlan,
    sources_cfg: Dict[str, Any],
    only_columns: Optional[Dict[str, List[str]]] = None,
) -> Iterator[Tuple[str, pd.DataFrame]]:
    """The chunks of ``sources_cfg``, cut in the plan's read blocks."""
    return iter_entity_chunks(
        sources_cfg, plan.base_dir, plan.overrides, rows_per_chunk=plan.rows_per_chunk,
        only_columns=only_columns,
    )


def _relationship_read_columns(streams: List[DbmsStream]) -> Dict[str, List[str]]:
    """Declared source -> the columns the relationship pass reads of it, for every
    source no stream needs whole."""
    merged: Dict[str, Optional[Set[str]]] = {}
    for stream in streams:
        for declared, columns in stream.relationship_columns().items():
            if columns is None or merged.get(declared, set()) is None:
                merged[declared] = None
            else:
                merged.setdefault(declared, set()).update(columns)
    return {declared: sorted(cols) for declared, cols in merged.items() if cols}


def _abort_quietly(sink: DbmsSink) -> None:
    """``sink.abort()``; a failure of it is logged and dropped, so that it never hides
    the error that made the load stop."""
    try:
        sink.abort()
    except Exception:
        logger.debug("abort of %s failed", type(sink).__name__, exc_info=True)


def run_single_pass(
    plan: ImportPlan,
    sinks: Dict[str, DbmsSink],
    *,
    on_batch: Optional[Callable[[str, str, pd.DataFrame], None]] = None,
    inspectors: Optional[Dict[str, RowInspector]] = None,
) -> StreamCounts:
    """Feed every DBMS of the plan from one read of the sources.

    One read of ``plan.sources_cfg`` feeds the nodes of every DBMS; then one read of
    the sources any of them needs for relationships, limited to the columns an edge is
    built from, feeds those; then every sink is closed. ``create_schema`` is not called. ``on_batch(dbms, partition, frame)`` is
    called after every node batch is written.

    ``inspectors`` maps a DBMS to what sees its rows before they are written.

    The plan's config must have passed ``validation.validate_headers``. The sinks are
    closed on success; when anything raises, each one is aborted instead
    (``DbmsSink.abort``) and the exception goes on.
    """
    inspectors = inspectors or {}
    streams = [
        DbmsStream(dbms, plan, sinks[dbms], on_batch, inspectors.get(dbms))
        for dbms in plan.dbms_names
    ]
    try:
        for source, chunk in _read(plan, plan.sources_cfg):
            for stream in streams:
                stream.feed(source, chunk)
        for stream in streams:
            stream.finish_nodes()
        needed = {name for stream in streams for name in stream.relationship_sources()}
        if needed:
            rel_sources = {k: v for k, v in plan.sources_cfg.items() if k in needed}
            for source, chunk in _read(plan, rel_sources, _relationship_read_columns(streams)):
                for stream in streams:
                    stream.feed_relationships(source, chunk)
        for stream in streams:
            stream.sink.close()
    except BaseException:
        for stream in streams:
            _abort_quietly(stream.sink)
        raise
    return StreamCounts(
        written={s.dbms: s.written for s in streams},
        entity_rows={s.dbms: s.entity_rows for s in streams},
    )


def run_stream_import(
    plan: ImportPlan,
    *,
    sink_factories: Dict[str, SinkFactory],
    on_batch: Optional[Callable[[str, str, pd.DataFrame], None]] = None,
    collector: Optional[MetricsCollector] = None,
) -> StreamCounts:
    """Write every DBMS of the plan through its sink, one DBMS at a time.

    Each DBMS, in ``plan.dbms_names`` order, gets its sink from ``sink_factories``,
    then ``create_schema()``, then a ``run_single_pass`` of its own over
    the sources its entities and relationships read (``dbms_sources``), which writes
    and closes the sink. ``on_batch(dbms, partition, frame)`` is called after every
    node batch is written; the data display (``data_preview``) hangs off it. With
    ``collector``, records one ``(dbms, "*", "write")`` metric per DBMS, with every
    row it wrote.

    A failure of a DBMS that is not already a ``BusinessException`` (a driver error, say)
    becomes an ``ImportExecutionError`` naming that DBMS and those written before it.

    The plan's config must have passed ``validation.validate_headers``. A sink is
    closed when its DBMS is written, and aborted (``DbmsSink.abort``) when it fails.
    """
    counts = StreamCounts()
    for dbms in plan.dbms_names:
        start = time.perf_counter()
        try:
            sink = sink_factories[dbms](plan.config[dbms])
            try:
                sink.create_schema()
            except BaseException:
                _abort_quietly(sink)
                raise
            own = replace(
                plan, dbms_names=[dbms], sources_cfg=dbms_sources(plan.config, [dbms])
            )
            one = run_single_pass(own, {dbms: sink}, on_batch=on_batch)
        except BusinessException:
            raise
        except Exception as exc:
            raise ImportExecutionError(
                f"Write to {dbms} failed ({type(exc).__name__}: {exc}); already written: "
                f"{', '.join(counts.written) or 'none'}; {dbms} may be partly written."
            ) from exc
        counts.written.update(one.written)
        counts.entity_rows.update(one.entity_rows)
        if collector is not None:
            collector.record(
                dbms, "*", "write",
                rows=sum(one.written[dbms].values()),
                seconds=time.perf_counter() - start,
            )
    return counts
