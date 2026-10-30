"""Cassandra helpers shared by ``CassandraSink``: session, DDL/CQL builders and batched write."""

from __future__ import annotations

import logging
import os
import time

from typing import Any, Callable, Dict, List, Tuple

import pandas as pd

try:
    # cassandra.concurrent transitively imports cassandra.cluster, which fails to
    # load on Python 3.12+ without a reactor backend (see the guarded lazy import
    # in _default_cassandra_session below). Guarding this module-level import too
    # keeps the module importable even when the driver/reactor is unavailable —
    # required so fake-session tests can still collect this module.
    from cassandra.concurrent import execute_concurrent_with_args
except Exception:  # pragma: no cover - driver/reactor may be unavailable
    execute_concurrent_with_args = None

from polyglotimportcsv.business_exception import ImportExecutionError
from polyglotimportcsv.entity_utils import (
    flat_leaf_columns,
    resolve_csv_column,
    target_field_name,
)

logger = logging.getLogger(__name__)

#: Client-side request timeout, in seconds. The driver's own default is 10s, which
#: a node busy flushing or compacting a bulk load routinely exceeds — and a single
#: overrun raises OperationTimedOut, aborting the whole import. Override per
#: deployment with ``connection.request_timeout``.
DEFAULT_REQUEST_TIMEOUT = 30.0

#: Retries for rows a concurrent write reported as failed, before giving up.
WRITE_RETRIES = 3

#: Multiplied by the attempt number, so a stalling node gets increasing room.
RETRY_BACKOFF_SECONDS = 2.0


def _request_timeout(conn: Dict[str, Any]) -> float:
    raw = conn.get("request_timeout", DEFAULT_REQUEST_TIMEOUT)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ImportExecutionError(
            f"Cassandra connection.request_timeout must be a positive number of "
            f"seconds, got {raw!r}."
        ) from None
    if value <= 0:
        raise ImportExecutionError(
            f"Cassandra connection.request_timeout must be a positive number of "
            f"seconds, got {raw!r}."
        )
    return value


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


def _cassandra_keyspace_ddl(keyspace: str) -> str:
    """CREATE KEYSPACE DDL."""
    return (
        f"CREATE KEYSPACE IF NOT EXISTS {keyspace} "
        "WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};"
    )


def _cassandra_column_plan(
    ecfg: Dict[str, Any], kinds: Dict[str, str], csv_columns: List[str]
) -> Tuple[Dict[str, str], List[str], List[str], Dict[str, str], str]:
    """Compute the column/PK plan for one entity's Cassandra table.

    Returns ``(pmap, ordered_src, ordered_db, cql_by_src, pk_clause)``:
    ``pmap`` maps source column -> db column name; ``ordered_src``/``ordered_db``
    are the partition+cluster+other columns in insert order (source and db
    names respectively); ``cql_by_src`` is the CQL type per source column;
    ``pk_clause`` is the ``PRIMARY KEY`` clause.
    """
    pmap = _source_to_db_map(ecfg, csv_columns)
    part_src = ecfg.get("cassandra_partition") or []
    clust_src = ecfg.get("cassandra_cluster") or []
    part_db = [pmap[c] for c in part_src]
    clust_db = [pmap[c] for c in clust_src]
    all_src = [
        resolve_csv_column(fk, spec, csv_columns)
        for fk, _, spec in flat_leaf_columns(ecfg)
    ]
    other_src = [s for s in all_src if s not in list(part_src) + list(clust_src)]
    ordered_src = list(part_src) + list(clust_src) + other_src
    ordered_db: List[str] = [pmap[s] for s in ordered_src]
    spec_by_src = {
        resolve_csv_column(fk, spec, csv_columns): spec
        for fk, _, spec in flat_leaf_columns(ecfg)
    }
    pk_clause = _primary_key_clause(part_db, clust_db)
    cql_by_src = {
        src: _cassandra_type_for(spec_by_src[src], kinds.get(src, "string"))
        for src in ordered_src
    }
    return pmap, ordered_src, ordered_db, cql_by_src, pk_clause


def _cassandra_table_ddl(
    table: str,
    ordered_src: List[str],
    pmap: Dict[str, str],
    cql_by_src: Dict[str, str],
    pk_clause: str,
) -> str:
    """CREATE TABLE DDL for one partition."""
    col_defs = [f'"{pmap[src]}" {cql_by_src[src]}' for src in ordered_src]
    return f'CREATE TABLE IF NOT EXISTS "{table}" (' + ", ".join(col_defs) + f", {pk_clause});"


def _cassandra_insert_cql(table: str, ordered_db: List[str]) -> str:
    """INSERT statement (with ``?`` placeholders) for one partition."""
    cols_cql = ", ".join(f'"{c}"' for c in ordered_db)
    placeholders = ", ".join(["?"] * len(ordered_db))
    return f'INSERT INTO "{table}" ({cols_cql}) VALUES ({placeholders})'


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
    session = cluster.connect()
    # Applies to every statement on this session; without it the driver's 10s
    # default governs bulk writes (see DEFAULT_REQUEST_TIMEOUT).
    session.default_timeout = _request_timeout(conn)
    return cluster, session


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


def _write_batched(
    session,
    prepared,
    params_list,
    advance,
    concurrency: int = 64,
    *,
    retries: int = WRITE_RETRIES,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Write rows concurrently, retrying the ones a transient failure hit.

    Collects per-row outcomes instead of aborting on the first error, so only the
    failed rows are resent — resending is safe because a Cassandra INSERT is an
    upsert on the primary key, so a row that actually landed is simply rewritten.
    A node stalling on a flush or compaction under a bulk load would otherwise end
    the whole import (and, in the benchmark matrix, discard the runs still queued).
    """
    if execute_concurrent_with_args is None:
        raise ImportExecutionError(
            "Cassandra driver could not be loaded: cassandra.concurrent is unavailable. "
            "Install the 'pyasyncore' package (pip install pyasyncore) on Python 3.12+; see DataStax docs."
        )
    pending = list(params_list)
    for attempt in range(retries + 1):
        outcomes = execute_concurrent_with_args(
            session, prepared, pending,
            concurrency=concurrency, raise_on_first_error=False,
        )
        # A driver (or stub) that reports nothing is taken at its word: no failures.
        failed = [p for p, outcome in zip(pending, outcomes or []) if not outcome[0]]
        if not failed:
            break
        if attempt == retries:
            raise ImportExecutionError(
                f"Cassandra write failed for {len(failed)} row(s) after "
                f"{attempt + 1} attempt(s): {failed[0] if failed else ''} "
                f"-> {outcomes[0][1] if outcomes else 'unknown error'}. "
                "Raise connection.request_timeout, or give the node more heap, "
                "if this repeats under load."
            )
        logger.warning(
            "cassandra: %d/%d row(s) failed, retrying (attempt %d/%d)",
            len(failed), len(pending), attempt + 1, retries,
        )
        sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
        pending = failed
    advance(len(params_list))
    return len(params_list)
