"""Import rows into Apache Cassandra."""

from __future__ import annotations

import logging
import os

from typing import Any, Callable, Dict, List, Tuple

import pandas as pd

from cassandra.concurrent import execute_concurrent_with_args

from polyglotimportcsv import metrics
from polyglotimportcsv.business_exception import ImportExecutionError
from polyglotimportcsv.entity_utils import (
    flat_leaf_columns,
    resolve_csv_column,
    target_field_name,
)
from polyglotimportcsv.filter_engine import apply_filters, expand_each
from polyglotimportcsv.mapping_resolver import BoundEntity
from polyglotimportcsv.reporting import entity_progress

logger = logging.getLogger(__name__)


def _source_to_db_map(ecfg: Dict[str, Any], csv_columns: List[str]) -> Dict[str, str]:
    return {
        resolve_csv_column(fk, spec, csv_columns): target_field_name(fk, spec)
        for fk, _, spec in flat_leaf_columns(ecfg)
    }


_KIND_TO_CQL_TYPE: Dict[str, str] = {
    "integer": "bigint",
    "float": "double",
    "datetime": "timestamp",
    "boolean": "boolean",
}


def _cassandra_type_for(spec: Dict[str, Any], kind: str) -> str:
    db_type = spec.get("db_type")
    if not db_type:
        return _KIND_TO_CQL_TYPE.get(kind, "text")
    t = db_type.upper()
    if t in ("TIMESTAMPTZ", "TIMESTAMP"):
        return "timestamp"
    if t in ("BIGINT", "INT", "INTEGER"):
        return "bigint"
    if t in ("DOUBLE", "FLOAT", "NUMERIC", "DECIMAL"):
        return "double"
    if t in ("BOOLEAN", "BOOL"):
        return "boolean"
    return "text"


def _primary_key_clause(part_db: List[str], clust_db: List[str]) -> str:
    if not part_db:
        raise ValueError("cassandra_partition must name at least one column")
    if len(part_db) == 1 and not clust_db:
        return f"PRIMARY KEY ({part_db[0]})"
    if len(part_db) == 1 and clust_db:
        return f"PRIMARY KEY ({part_db[0]}, {', '.join(clust_db)})"
    inner = ", ".join(part_db)
    if clust_db:
        return f"PRIMARY KEY (({inner}), {', '.join(clust_db)})"
    return "PRIMARY KEY ((" + inner + "))"


def _default_cassandra_session(conn: Dict[str, Any]):
    # Force the driver to bypass compiling or searching for legacy C extensions on Windows
    os.environ["CASS_DRIVER_NO_EXTENSIONS"] = "1"
    try:
        # cassandra.cluster fails to import on Python 3.12+ unless a reactor backend
        # is available (no gevent/eventlet, no compiled libev, and stdlib asyncore was
        # removed). The "pyasyncore" package restores a working asyncore module so the
        # import succeeds; we then switch to AsyncioConnection below instead of the
        # legacy asyncore-based reactor.
        from cassandra.cluster import Cluster
        from cassandra.io.asyncioreactor import AsyncioConnection
    except Exception as e:  # pragma: no cover - environment specific
        raise ImportExecutionError(
            f"Cassandra driver could not be loaded: {e}. "
            "Install the 'pyasyncore' package (pip install pyasyncore) on Python 3.12+; see DataStax docs."
        ) from e
    hosts = conn.get("hosts") or ["127.0.0.1"]
    port = int(conn.get("port", 9042))
    cluster = Cluster(hosts, port=port, connect_timeout=5)
    cluster.connection_class = AsyncioConnection  # <-- Forces the driver to use asyncio instead of deleted asyncore
    return cluster, cluster.connect()


def _row_values(row, ordered_src: List[str], cql_by_src: Dict[str, str]) -> List[Any]:
    values = []
    for src in ordered_src:
        val = row.get(src)
        if pd.isna(val):
            values.append(None)
        elif cql_by_src[src] == "text":
            values.append(str(val))
        else:
            values.append(val)
    return values


def _write_naive(session, prepared, params_list, advance) -> int:
    count = 0
    for values in params_list:
        session.execute(prepared, values)
        count += 1
        advance(1)
    return count


def _write_batched(session, prepared, params_list, advance, concurrency: int = 64) -> int:
    execute_concurrent_with_args(session, prepared, params_list, concurrency=concurrency)
    advance(len(params_list))
    return len(params_list)


def run_cassandra_import(
    backend_cfg: Dict[str, Any],
    entities: Dict[str, "BoundEntity"],
    *,
    dry_run: bool,
    create_schema: bool,
    strategy: str = "optimized",
    session_factory: Callable[[Dict[str, Any]], Tuple[Any, Any]] = _default_cassandra_session,
) -> List[str]:
    lines: List[str] = []
    conn = backend_cfg.get("connection") or {}
    keyspace = conn.get("keyspace", "ecommerce")

    if dry_run:
        lines.append("[cassandra] dry-run: would create tables and insert rows.")
        for ename, be in entities.items():
            non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
            with metrics.timed_phase("cassandra", ename, "filter") as t:
                dff = apply_filters(be.df, non_each, be.kinds)
                t.rows = len(dff)
            for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
                lines.append(f"  table {part_name}: {len(part_df)} row(s)")
        return lines

    try:
        cluster, session = session_factory(conn)
    except ImportExecutionError:
        raise
    except Exception as e:
        raise ImportExecutionError(f"Cassandra connection failed: {e}") from e

    if create_schema:
        keyspace_ddl = (
            f"CREATE KEYSPACE IF NOT EXISTS {keyspace} "
            "WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};"
        )
        logger.debug("[cassandra] DDL: %s", keyspace_ddl)
        session.execute(keyspace_ddl)
    session.set_keyspace(keyspace)

    for ename, be in entities.items():
        csv_columns = list(be.df.columns)
        pmap = _source_to_db_map(be.cfg, csv_columns)
        part_src = be.cfg.get("cassandra_partition") or []
        clust_src = be.cfg.get("cassandra_cluster") or []
        part_db = [pmap[c] for c in part_src]
        clust_db = [pmap[c] for c in clust_src]
        all_src = [
            resolve_csv_column(fk, spec, csv_columns)
            for fk, _, spec in flat_leaf_columns(be.cfg)
        ]
        other_src = [s for s in all_src if s not in list(part_src) + list(clust_src)]
        ordered_src = list(part_src) + list(clust_src) + other_src
        ordered_db: List[str] = [pmap[s] for s in ordered_src]
        spec_by_src = {
            resolve_csv_column(fk, spec, csv_columns): spec
            for fk, _, spec in flat_leaf_columns(be.cfg)
        }
        pk_clause = _primary_key_clause(part_db, clust_db)
        cql_by_src = {
            src: _cassandra_type_for(spec_by_src[src], be.kinds.get(src, "string"))
            for src in ordered_src
        }

        non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
        with metrics.timed_phase("cassandra", ename, "filter") as t:
            dff = apply_filters(be.df, non_each, be.kinds)
            t.rows = len(dff)
        for table, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
            if create_schema:
                col_defs = []
                for src in ordered_src:
                    col_defs.append(f'"{pmap[src]}" {cql_by_src[src]}')
                ddl = f'CREATE TABLE IF NOT EXISTS "{table}" (' + ", ".join(col_defs) + f", {pk_clause});"
                logger.debug("[cassandra] DDL: %s", ddl)
                session.execute(ddl)

            cols_cql = ", ".join(f'"{c}"' for c in ordered_db)
            placeholders = ", ".join(["?"] * len(ordered_db))
            cql = f'INSERT INTO "{table}" ({cols_cql}) VALUES ({placeholders})'
            logger.debug("[cassandra] CQL: %s (%d row(s))", cql, len(part_df))
            prep = session.prepare(cql)
            if part_df.empty:
                logger.warning("[cassandra] table %s has 0 row(s) after filters", table)
            params_list = [_row_values(row, ordered_src, cql_by_src)
                           for _, row in part_df.iterrows()]
            writer = _write_naive if strategy == "naive" else _write_batched
            with metrics.timed_phase("cassandra", table, "write") as tw:
                with entity_progress(f"cassandra · {table}", len(params_list)) as advance:
                    count = writer(session, prep, params_list, advance)
                tw.rows = count
            lines.append(f"[cassandra] inserted {count} row(s) into {keyspace}.{table}")

    cluster.shutdown()
    return lines
