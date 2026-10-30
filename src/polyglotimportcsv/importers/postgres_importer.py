"""PostgreSQL helpers shared by ``PostgresSink``: connection and INSERT statement."""

from __future__ import annotations

from typing import Any, Dict, List

import psycopg2
from psycopg2 import sql


def build_insert_sql(schema: str, table: str, cols: List[str], pks: List[str]) -> "sql.Composed":
    """Build the ``INSERT ... VALUES %s [ON CONFLICT (pks) DO NOTHING]`` statement."""
    fq = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(table))
    col_sql = sql.SQL(", ").join(map(sql.Identifier, cols))
    base = sql.SQL("INSERT INTO {} ({}) VALUES %s").format(fq, col_sql)
    if pks:
        return base + sql.SQL(" ON CONFLICT ({}) DO NOTHING").format(
            sql.SQL(", ").join(map(sql.Identifier, pks))
        )
    return base


def _connect(conn: Dict[str, Any]):
    return psycopg2.connect(
        host=conn.get("host", "127.0.0.1"),
        port=int(conn.get("port", 5432)),
        dbname=conn.get("database", "postgres"),
        user=conn.get("user", "postgres"),
        password=conn.get("password", ""),
    )
