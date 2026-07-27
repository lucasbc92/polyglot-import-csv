"""PostgresSink: DbmsSink adapter for PostgreSQL (spec: streaming import, Task 4).

Reuses the same row-shaping (``flatten_entity_dataframe``) and batched-write
(``build_insert_sql`` + ``execute_values``) helpers as the materialize
importer (``importers.postgres_importer.run_postgres_import``), so both
paths issue byte-identical SQL for the same entity config.
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd
from psycopg2.extras import execute_values

from polyglotimportcsv.entity_utils import flat_leaf_columns, target_field_name
from polyglotimportcsv.importers.postgres_importer import _connect, build_insert_sql
from polyglotimportcsv.materialize import flatten_entity_dataframe
from polyglotimportcsv.schema_generator import (
    build_postgres_create_tables,
    build_postgres_drop_foreign_keys,
    build_postgres_foreign_keys,
)
from polyglotimportcsv.stream_binding import EntityBinding


class PostgresSink:
    """Streams cast batches into PostgreSQL tables, one table per partition."""

    def __init__(self, backend_cfg: Dict[str, Any], *, connection_factory=None):
        self.schema = backend_cfg.get("schema") or "public"
        self.relationships = backend_cfg.get("relationships") or {}
        factory = connection_factory or _connect
        self._cx = factory(backend_cfg.get("connection") or {})
        self._cx.autocommit = True
        self._cur = self._cx.cursor()
        # partition_name -> binding.cfg, kept for building FKs once every
        # partition table has been created (see close()).
        self._created: Dict[str, dict] = {}

    def create_schema(self) -> None:
        """Drop the foreign keys this load will re-add at ``close()``.

        Table DDL is created lazily per partition (``ensure_partition``) and
        foreign keys are added at ``close()``, once every referenced table exists
        and is populated -- the streaming writer emits partitions in buffer order,
        so a child table's batch routinely lands before its parent's. That is safe
        only while the tables carry no constraints. Constraints added by a previous
        run do survive into this one (``CREATE TABLE IF NOT EXISTS`` keeps the
        table, and cleaning by ``TRUNCATE`` keeps its constraints), so they have to
        be dropped up front or the re-run aborts on a foreign key violation.
        """
        for stmt in build_postgres_drop_foreign_keys(self.schema, self.relationships):
            self._cur.execute(stmt)

    def ensure_partition(self, partition_name: str, binding: EntityBinding) -> None:
        stmts = build_postgres_create_tables(self.schema, {partition_name: binding.cfg}, {})
        for stmt in stmts:
            self._cur.execute(stmt)
        self._created[partition_name] = binding.cfg

    def write_batch(self, partition_name: str, binding: EntityBinding, batch: pd.DataFrame) -> int:
        mat = flatten_entity_dataframe(batch, binding.cfg)
        if mat.empty:
            return 0
        cols = list(mat.columns)
        pks = [
            target_field_name(fk, spec)
            for fk, _, spec in flat_leaf_columns(binding.cfg)
            if spec.get("is_key")
        ]
        stmt = build_insert_sql(self.schema, partition_name, cols, pks)
        tuples = [tuple(row) for row in mat.itertuples(index=False, name=None)]
        # Pass the Composed statement straight through: execute_values already
        # knows how to stringify a psycopg2.sql.Composable via `cur` itself
        # (it calls stmt.as_string(cur) internally), which keeps this call
        # DB-free-testable (a fake cursor never needs to satisfy psycopg2's
        # C-level "must be a real connection/cursor" check for Identifier
        # quoting) while producing byte-identical SQL against a real cursor.
        execute_values(self._cur, stmt, tuples, page_size=500)
        return len(tuples)

    def close(self) -> None:
        if self.relationships and self._created:
            fk_stmts = build_postgres_foreign_keys(self.schema, self._created, self.relationships)
            for stmt in fk_stmts:
                for sub in stmt.split(";"):
                    sub = sub.strip()
                    if sub:
                        self._cur.execute(sub + ";")
        self._cx.close()
