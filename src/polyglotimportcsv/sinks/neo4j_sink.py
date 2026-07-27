"""Neo4jSink: DbmsSink adapter for Neo4j (spec: streaming import, Task 5).

Writes both nodes (pass 1) and relationships (pass 2, if declared). Relationships
are written by a second pass driven by ``stream_runner`` calling ``write_relationships``.
Relationships need every node set to exist before edge insertion, which requires
two streaming passes over the entity/relationship sources.

Reuses the same props-shaping (``props_from_row``) and batched-write helper
(``_merge_nodes_batched`` -> UNWIND) as the materialize importer
(``importers.neo4j_importer.run_neo4j_import``), but dedupe is tracked
*across* ``write_batch`` calls (one seen-set per partition, kept for the
sink's lifetime) instead of once per call, so first-wins holds for the whole
streaming pass rather than just within one flush.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Set

import pandas as pd

from polyglotimportcsv.business_exception import ImportExecutionError
from polyglotimportcsv.entity_utils import flat_leaf_columns, resolve_csv_column, target_field_name
from polyglotimportcsv.importers.neo4j_importer import (
    _default_neo4j_driver,
    _dedupe_props,
    _merge_nodes_batched,
    _merge_rels_batched,
    _rel_rows_for_batch,
    _sanitize_label,
    props_from_row,
)
from polyglotimportcsv.stream_binding import EntityBinding

logger = logging.getLogger(__name__)


def _single_key(cfg: Dict[str, Any], partition_name: str):
    key_cols = [(fk, sp) for fk, _, sp in flat_leaf_columns(cfg) if sp.get("is_key")]
    if len(key_cols) != 1:
        raise ImportExecutionError(
            f"Neo4j entity '{partition_name}' must have exactly one is_key column."
        )
    return target_field_name(*key_cols[0])


class Neo4jSink:
    """Streams cast batches into Neo4j nodes and relationships, one label/type per partition."""

    def __init__(self, backend_cfg: Dict[str, Any], *, driver_factory=_default_neo4j_driver):
        conn = backend_cfg.get("connection") or {}
        database = conn.get("database") or None
        try:
            driver = driver_factory(conn)
        except ImportExecutionError:
            raise
        except Exception as e:
            raise ImportExecutionError(f"Neo4j connection failed: {e}") from e
        self._driver = driver
        self._session = driver.session(database=database)
        # partition_name -> set of already-merged key values (first-wins,
        # kept across write_batch calls for the sink's whole lifetime).
        self._seen: Dict[str, Set[Any]] = {}

    def create_schema(self) -> None:
        """No-op: per-label uniqueness constraints are created lazily in ensure_partition."""

    def ensure_partition(self, partition_name: str, binding: EntityBinding) -> None:
        key_name = _single_key(binding.cfg, partition_name)
        label = _sanitize_label(partition_name)
        self._session.run(
            f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.{key_name} IS UNIQUE"
        )

    def write_batch(self, partition_name: str, binding: EntityBinding, batch: pd.DataFrame) -> int:
        key_name = _single_key(binding.cfg, partition_name)
        seen = self._seen.setdefault(partition_name, set())
        props_list, skipped = _dedupe_props(batch, binding.cfg, key_name, props_from_row, seen=seen)
        if skipped:
            logger.warning(
                "[neo4j] %s: %d duplicate key value(s) skipped (first MERGE wins)",
                partition_name, skipped,
            )
        if not props_list:
            return 0
        label = _sanitize_label(partition_name)
        return _merge_nodes_batched(self._session, label, key_name, props_list, lambda n: None)

    def write_relationships(
        self,
        rname: str,
        rspec: Dict[str, Any],
        from_binding: EntityBinding,
        to_binding: EntityBinding,
        batch: pd.DataFrame,
    ) -> int:
        """MERGE one chunk of edges; endpoints must already exist (pass 2).

        ``batch`` is the ``from`` entity's cast chunk, which carries both
        foreign keys plus edge props. Rows with a missing endpoint key are
        dropped (by ``_rel_rows_for_batch``) and, if a node is nonetheless
        absent, Cypher ``MATCH`` silently creates no edge -- matching the
        materialize path.
        """
        from_label = _sanitize_label(rspec["from"])
        to_label = _sanitize_label(rspec["to"])
        rel_type = _sanitize_label(rspec.get("type") or rname)
        from_key_col = [(fk, sp) for fk, _, sp in flat_leaf_columns(from_binding.cfg) if sp.get("is_key")][0]
        to_key_col = [(fk, sp) for fk, _, sp in flat_leaf_columns(to_binding.cfg) if sp.get("is_key")][0]
        from_key = target_field_name(*from_key_col)
        to_key = target_field_name(*to_key_col)
        cols = list(batch.columns)
        from_src = resolve_csv_column(from_key_col[0], from_key_col[1], cols)
        to_src = resolve_csv_column(to_key_col[0], to_key_col[1], cols)
        rel_cols = rspec.get("columns") or {}
        mk_names = [target_field_name(fk, spec) for fk, spec in rel_cols.items() if spec.get("is_key")]
        rows = _rel_rows_for_batch(batch, from_src, to_src, rel_cols, mk_names)
        if not rows:
            return 0
        return _merge_rels_batched(
            self._session, from_label, from_key, to_label, to_key,
            rel_type, mk_names, rows, advance=lambda n: None,
        )

    def close(self) -> None:
        self._driver.close()
