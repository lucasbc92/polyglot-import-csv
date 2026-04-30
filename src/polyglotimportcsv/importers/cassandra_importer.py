"""Import rows into Apache Cassandra."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import pandas as pd

from polyglotimportcsv.business_exception import BusinessException
from polyglotimportcsv.entity_utils import output_column_name
from polyglotimportcsv.filter_engine import apply_filters, expand_each

logger = logging.getLogger(__name__)


def _all_db_columns(ecfg: Dict[str, Any]) -> Dict[str, str]:
    return {src: output_column_name(src, spec) for src, spec in (ecfg.get("columns") or {}).items()}


def _cassandra_type_for(spec: Dict[str, Any]) -> str:
    t = (spec.get("db_type") or "TEXT").upper()
    if t in ("TIMESTAMPTZ", "TIMESTAMP"):
        return "timestamp"
    if t in ("BIGINT", "INT", "INTEGER"):
        return "bigint"
    if t in ("DOUBLE", "FLOAT", "NUMERIC", "DECIMAL"):
        return "double"
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


def run_cassandra_import(
    backend_cfg: Dict[str, Any],
    df: pd.DataFrame,
    column_kinds: Dict[str, str],
    *,
    dry_run: bool,
    create_schema: bool,
) -> List[str]:
    lines: List[str] = []
    conn = backend_cfg.get("connection") or {}
    entities = backend_cfg.get("entities") or {}
    hosts = conn.get("hosts") or ["127.0.0.1"]
    port = int(conn.get("port", 9042))
    keyspace = conn.get("keyspace", "ecommerce")

    if dry_run:
        lines.append("[cassandra] dry-run: would create tables and insert rows.")
        for ename, ecfg in entities.items():
            non_each = [f for f in (ecfg.get("filters") or []) if f.get("operator") != "each"]
            dff = apply_filters(df, non_each, column_kinds)
            for part_name, part_df in expand_each(dff, ecfg.get("filters") or [], ename):
                lines.append(f"  table {part_name}: {len(part_df)} row(s)")
        return lines

    try:
        from cassandra.cluster import Cluster  # lazy: driver has heavy deps / py3.12+ quirks
    except Exception as e:
        raise BusinessException(
            f"Cassandra driver could not be loaded: {e}. "
            "Use --dry-run without the driver, or Python <=3.11 with build deps; see DataStax docs."
        ) from e

    try:
        cluster = Cluster(hosts, port=port, connect_timeout=5)
        session = cluster.connect()
    except Exception as e:
        raise BusinessException(f"Cassandra connection failed: {e}") from e

    session.execute(
        f"""
        CREATE KEYSPACE IF NOT EXISTS {keyspace}
        WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': 1}};
        """
    )
    session.set_keyspace(keyspace)

    for ename, ecfg in entities.items():
        pmap = _all_db_columns(ecfg)
        part_src = ecfg.get("cassandra_partition") or []
        clust_src = ecfg.get("cassandra_cluster") or []
        part_db = [pmap[c] for c in part_src]
        clust_db = [pmap[c] for c in clust_src]
        all_src = list((ecfg.get("columns") or {}).keys())
        other_src = [s for s in all_src if s not in list(part_src) + list(clust_src)]
        ordered_src = list(part_src) + list(clust_src) + other_src
        ordered_db: List[str] = [pmap[s] for s in ordered_src]
        pk_clause = _primary_key_clause(part_db, clust_db)

        non_each = [f for f in (ecfg.get("filters") or []) if f.get("operator") != "each"]
        dff = apply_filters(df, non_each, column_kinds)
        for table, part_df in expand_each(dff, ecfg.get("filters") or [], ename):
            if create_schema:
                col_defs = []
                for src in ordered_src:
                    spec = ecfg["columns"][src]
                    col_defs.append(f'"{pmap[src]}" {_cassandra_type_for(spec)}')
                ddl = f'CREATE TABLE IF NOT EXISTS "{table}" (' + ", ".join(col_defs) + f", {pk_clause});"
                session.execute(ddl)

            cols_cql = ", ".join(f'"{c}"' for c in ordered_db)
            placeholders = ", ".join(["?"] * len(ordered_db))
            cql = f'INSERT INTO "{table}" ({cols_cql}) VALUES ({placeholders})'
            prep = session.prepare(cql)
            count = 0
            for _, row in part_df.iterrows():
                values = []
                for src in ordered_src:
                    val = row.get(src)
                    values.append(None if pd.isna(val) else val)
                session.execute(prep, values)
                count += 1
            lines.append(f"[cassandra] inserted {count} row(s) into {keyspace}.{table}")

    cluster.shutdown()
    return lines
