"""Import flattened entities into PostgreSQL."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values

from polyglotimportcsv import metrics
from polyglotimportcsv.business_exception import ImportExecutionError
from polyglotimportcsv.mapping_resolver import BoundEntity
from polyglotimportcsv.filter_engine import apply_filters, expand_each
from polyglotimportcsv.entity_utils import flat_leaf_columns, target_field_name
from polyglotimportcsv.materialize import flatten_entity_dataframe
from polyglotimportcsv.reporting import entity_progress
from polyglotimportcsv.schema_generator import build_postgres_create_tables, build_postgres_foreign_keys

logger = logging.getLogger(__name__)

# Default insert order for the e-commerce demo (FK: products -> categories)
_DEFAULT_INSERT_ORDER = ("categories", "products", "inventory")


def build_insert_sql(schema: str, table: str, cols: List[str], pks: List[str]) -> "sql.Composed":
    """Build the ``INSERT ... VALUES %s [ON CONFLICT (pks) DO NOTHING]`` statement.

    Shared by the materialize importer (``run_postgres_import``) and
    ``PostgresSink.write_batch`` so both paths issue byte-identical SQL.
    """
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


def run_postgres_import(
    backend_cfg: Dict[str, Any],
    entities: Dict[str, "BoundEntity"],
    *,
    dry_run: bool,
    create_schema: bool,
    strategy: str = "optimized",
) -> List[str]:
    """Execute Postgres import; return log lines."""
    lines: List[str] = []
    _ = strategy
    conn_cfg = backend_cfg.get("connection") or {}
    schema = backend_cfg.get("schema") or "public"
    relationships = backend_cfg.get("relationships") or {}
    entity_cfgs = {name: be.cfg for name, be in entities.items()}

    if dry_run:
        lines.append("[postgres] dry-run: would connect and import entities.")
        for ename, be in entities.items():
            non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
            with metrics.timed_phase("postgres", ename, "filter") as t:
                dff = apply_filters(be.df, non_each, be.kinds)
                t.rows = len(dff)
            for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
                mat = flatten_entity_dataframe(part_df, be.cfg)
                lines.append(f"  entity {part_name}: {len(mat)} row(s) after dedupe")
        return lines

    create_stmts = build_postgres_create_tables(schema, entity_cfgs, relationships)
    fk_stmts = build_postgres_foreign_keys(schema, entity_cfgs, relationships)

    try:
        cx = _connect(conn_cfg)
    except Exception as e:
        raise ImportExecutionError(f"PostgreSQL connection failed: {e}") from e

    cx.autocommit = True
    with cx.cursor() as cur:
        if create_schema:
            for stmt in create_stmts:
                logger.debug("[postgres] DDL: %s", stmt)
                cur.execute(stmt)
            for stmt in fk_stmts:
                for sub in stmt.split(";"):
                    sub = sub.strip()
                    if sub:
                        logger.debug("[postgres] DDL: %s;", sub)
                        cur.execute(sub + ";")
        ordered_names = [n for n in _DEFAULT_INSERT_ORDER if n in entities] + [
            n for n in sorted(entities.keys()) if n not in _DEFAULT_INSERT_ORDER
        ]
        for ename in ordered_names:
            be = entities[ename]
            non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
            with metrics.timed_phase("postgres", ename, "filter") as t:
                dff = apply_filters(be.df, non_each, be.kinds)
                t.rows = len(dff)
            for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
                mat = flatten_entity_dataframe(part_df, be.cfg)
                if mat.empty:
                    logger.warning(
                        "[postgres] entity %s has 0 row(s) after filters; nothing to insert",
                        part_name,
                    )
                    continue
                cols = list(mat.columns)
                pks = [
                    target_field_name(fk, spec)
                    for fk, _, spec in flat_leaf_columns(be.cfg)
                    if spec.get("is_key")
                ]
                full = build_insert_sql(schema, part_name, cols, pks)
                tuples = [tuple(row) for row in mat.itertuples(index=False, name=None)]
                logger.debug(
                    "[postgres] SQL: %s (%d row(s), page_size=500)",
                    full.as_string(cx), len(tuples),
                )
                with metrics.timed_phase("postgres", part_name, "write") as tw:
                    with entity_progress(f"postgres · {part_name}", len(tuples)) as advance:
                        for i in range(0, len(tuples), 500):
                            chunk = tuples[i : i + 500]
                            execute_values(cur, full.as_string(cx), chunk, page_size=500)
                            advance(len(chunk))
                    tw.rows = len(tuples)
                lines.append(f"[postgres] inserted {len(tuples)} row(s) into {schema}.{part_name}")
    cx.close()
    return lines
