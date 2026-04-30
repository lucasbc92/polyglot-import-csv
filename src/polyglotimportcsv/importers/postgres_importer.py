"""Import flattened entities into PostgreSQL."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

import pandas as pd
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values

from polyglotimportcsv.business_exception import BusinessException
from polyglotimportcsv.filter_engine import apply_filters, expand_each
from polyglotimportcsv.entity_utils import output_column_name
from polyglotimportcsv.materialize import flatten_entity_dataframe
from polyglotimportcsv.schema_generator import build_postgres_create_tables, build_postgres_foreign_keys

logger = logging.getLogger(__name__)

# Default insert order for the e-commerce demo (FK: products -> categories)
_DEFAULT_INSERT_ORDER = ("categories", "products", "inventory")


def _connect(conn: Dict[str, Any]):
    return psycopg2.connect(
        host=conn.get("host", "127.0.0.1"),
        port=int(conn.get("port", 5432)),
        dbname=conn.get("database", "postgres"),
        user=conn.get("user", "postgres"),
        password=conn.get("password", ""),
    )


def run_postgres_import(
    backend_cfg: Dict[str, Any],
    df: pd.DataFrame,
    column_kinds: Dict[str, str],
    *,
    dry_run: bool,
    create_schema: bool,
) -> List[str]:
    """Execute Postgres import; return log lines."""
    lines: List[str] = []
    conn_cfg = backend_cfg.get("connection") or {}
    schema = backend_cfg.get("schema") or "public"
    entities = backend_cfg.get("entities") or {}
    relationships = backend_cfg.get("relationships") or {}

    if dry_run:
        lines.append("[postgres] dry-run: would connect and import entities.")
        for ename, ecfg in entities.items():
            non_each = [f for f in (ecfg.get("filters") or []) if f.get("operator") != "each"]
            dff = apply_filters(df, non_each, column_kinds)
            for part_name, part_df in expand_each(dff, ecfg.get("filters") or [], ename):
                mat = flatten_entity_dataframe(part_df, ecfg)
                lines.append(f"  entity {part_name}: {len(mat)} row(s) after dedupe")
        return lines

    create_stmts = build_postgres_create_tables(schema, entities, relationships)
    fk_stmts = build_postgres_foreign_keys(schema, entities, relationships)

    try:
        cx = _connect(conn_cfg)
    except Exception as e:
        raise BusinessException(f"PostgreSQL connection failed: {e}") from e

    cx.autocommit = True
    with cx.cursor() as cur:
        if create_schema:
            for stmt in create_stmts:
                cur.execute(stmt)
            for stmt in fk_stmts:
                for sub in stmt.split(";"):
                    sub = sub.strip()
                    if sub:
                        cur.execute(sub + ";")
        # Insert order
        ordered_names = [n for n in _DEFAULT_INSERT_ORDER if n in entities] + [
            n for n in sorted(entities.keys()) if n not in _DEFAULT_INSERT_ORDER
        ]
        for ename in ordered_names:
            ecfg = entities[ename]
            non_each = [f for f in (ecfg.get("filters") or []) if f.get("operator") != "each"]
            dff = apply_filters(df, non_each, column_kinds)
            for part_name, part_df in expand_each(dff, ecfg.get("filters") or [], ename):
                mat = flatten_entity_dataframe(part_df, ecfg)
                if mat.empty:
                    continue
                cols = list(mat.columns)
                fq = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(part_name))
                col_sql = sql.SQL(", ").join(map(sql.Identifier, cols))
                pks = [
                    output_column_name(src, spec)
                    for src, spec in ecfg["columns"].items()
                    if spec.get("is_key")
                ]
                base = sql.SQL("INSERT INTO {} ({}) VALUES %s").format(fq, col_sql)
                if pks:
                    full = base + sql.SQL(" ON CONFLICT ({}) DO NOTHING").format(
                        sql.SQL(", ").join(map(sql.Identifier, pks))
                    )
                else:
                    full = base
                tuples = [tuple(row) for row in mat.itertuples(index=False, name=None)]
                execute_values(cur, full.as_string(cx), tuples, page_size=500)
                lines.append(f"[postgres] inserted {len(tuples)} row(s) into {schema}.{part_name}")
    cx.close()
    return lines
