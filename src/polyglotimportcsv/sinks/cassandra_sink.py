"""CassandraSink: DbmsSink adapter for Apache Cassandra (spec: streaming import, Task 5).

Reuses the same column-plan/DDL builders (``_cassandra_column_plan``,
``_cassandra_table_ddl``, ``_cassandra_insert_cql``, ``_cassandra_keyspace_ddl``),
row-shaping (``_row_values``), and batched-write helper (``_write_batched`` ->
``execute_concurrent_with_args``, concurrency 64) as the materialize importer
(``importers.cassandra_importer.run_cassandra_import``), so both paths issue
byte-identical DDL/CQL for the same entity config.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pandas as pd

from polyglotimportcsv.business_exception import ImportExecutionError
from polyglotimportcsv.importers.cassandra_importer import (
    _cassandra_column_plan,
    _cassandra_insert_cql,
    _cassandra_keyspace_ddl,
    _cassandra_table_ddl,
    _default_cassandra_session,
    _row_values,
    _write_batched,
)
from polyglotimportcsv.stream_binding import EntityBinding
from polyglotimportcsv.row_view import iter_rows


class CassandraSink:
    """Streams cast batches into Cassandra tables, one table per partition."""

    def __init__(self, backend_cfg: Dict[str, Any], *, session_factory=_default_cassandra_session):
        conn = backend_cfg.get("connection") or {}
        self.keyspace = conn.get("keyspace", "ecommerce")
        try:
            self._cluster, self._session = session_factory(conn)
        except ImportExecutionError:
            raise
        except Exception as e:
            raise ImportExecutionError(f"Cassandra connection failed: {e}") from e
        self._keyspace_ready = False
        # partition_name -> (prepared_stmt, ordered_src, cql_by_src)
        self._tables: Dict[str, Tuple[Any, List[str], Dict[str, str]]] = {}

    def _ensure_keyspace_set(self) -> None:
        if not self._keyspace_ready:
            self._session.set_keyspace(self.keyspace)
            self._keyspace_ready = True

    def create_schema(self) -> None:
        self._session.execute(_cassandra_keyspace_ddl(self.keyspace))
        self._ensure_keyspace_set()

    def ensure_partition(self, partition_name: str, binding: EntityBinding) -> None:
        if partition_name in self._tables:
            return
        self._ensure_keyspace_set()
        # No source-CSV header is available at bind time; declared columns
        # (binding.cfg keys) stand in for it. This resolves correctly for the
        # common case (no `csv_column` override), matching write_batch's
        # column plan below since batches carry the same field-key columns.
        csv_columns = list(binding.cfg.get("columns") or {})
        pmap, ordered_src, ordered_db, cql_by_src, pk_clause = _cassandra_column_plan(
            binding.cfg, binding.kinds, csv_columns
        )
        ddl = _cassandra_table_ddl(partition_name, ordered_src, pmap, cql_by_src, pk_clause)
        self._session.execute(ddl)
        cql = _cassandra_insert_cql(partition_name, ordered_db)
        prepared = self._session.prepare(cql)
        self._tables[partition_name] = (prepared, ordered_src, cql_by_src)

    def write_batch(self, partition_name: str, binding: EntityBinding, batch: pd.DataFrame) -> int:
        prepared, ordered_src, cql_by_src = self._tables[partition_name]
        params_list = [_row_values(row, ordered_src, cql_by_src) for row in iter_rows(batch)]
        if not params_list:
            return 0
        return _write_batched(self._session, prepared, params_list, lambda n: None, concurrency=64)

    def close(self) -> None:
        self._cluster.shutdown()
