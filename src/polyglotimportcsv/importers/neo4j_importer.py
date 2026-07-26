"""Import nodes and relationships into Neo4j."""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import pandas as pd
from neo4j import GraphDatabase

from polyglotimportcsv import metrics
from polyglotimportcsv.business_exception import ImportExecutionError
from polyglotimportcsv.entity_utils import (
    flat_leaf_columns,
    resolve_csv_column,
    target_field_name,
)
from polyglotimportcsv.filter_engine import apply_filters, expand_each
from polyglotimportcsv.mapping_resolver import BoundEntity
from polyglotimportcsv.materialize import cell_scalar
from polyglotimportcsv.reporting import entity_progress

logger = logging.getLogger(__name__)


def _sanitize_label(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", label)


def _default_neo4j_driver(conn: Dict[str, Any]):
    uri = conn.get("uri", "bolt://127.0.0.1:7687")
    user = conn.get("user", "neo4j")
    password = conn.get("password", "password")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    return driver


def props_from_row(row: pd.Series, ecfg: Dict[str, Any]) -> Dict[str, Any]:
    """Build one node's property dict from a CSV row (flat columns only)."""
    csv_columns = list(row.index)
    out: Dict[str, Any] = {}
    for field_key, _, spec in flat_leaf_columns(ecfg):
        name = target_field_name(field_key, spec)
        src = resolve_csv_column(field_key, spec, csv_columns)
        out[name] = cell_scalar(row[src] if src in row.index else None)
    return out


def _dedupe_props(part_df, ecfg, key_name, props_from_row, seen: Optional[Set[Any]] = None):
    """First-wins dedupe by key; returns (list-of-props, skipped_count).

    ``seen`` defaults to a fresh set (one call = one dedupe scope, as used by
    the materialize importer). Pass a set kept across calls (as
    ``Neo4jSink.write_batch`` does, keyed per partition) to make first-wins
    hold across a whole streaming pass instead of just within one batch.
    """
    if seen is None:
        seen = set()
    out, skipped = [], 0
    for _, row in part_df.iterrows():
        props = props_from_row(row, ecfg)
        kid = props.get(key_name)
        if kid is None:
            continue
        if kid in seen:
            skipped += 1
            continue
        seen.add(kid)
        out.append(props)
    return out, skipped


def _merge_nodes_naive(session, plabel, key_name, props_list, advance) -> int:
    q = f"MERGE (n:{plabel} {{{key_name}: $k}}) SET n += $props"
    merged = 0
    for props in props_list:
        kid = props[key_name]
        rest = {k: v for k, v in props.items() if k != key_name}
        session.run(q, k=kid, props=rest)
        merged += 1
        advance(1)
    return merged


def _merge_nodes_batched(session, plabel, key_name, props_list, advance, batch: int = 1000) -> int:
    q = (f"UNWIND $batch AS row "
         f"MERGE (n:{plabel} {{{key_name}: row.k}}) SET n += row.props")
    merged = 0
    for i in range(0, len(props_list), batch):
        chunk = props_list[i : i + batch]
        payload = [{"k": p[key_name],
                    "props": {k: v for k, v in p.items() if k != key_name}}
                   for p in chunk]
        session.execute_write(lambda tx, q=q, payload=payload: tx.run(q, batch=payload))
        merged += len(chunk)
        advance(len(chunk))
    return merged


def _merge_rels_naive(session, q, dff, from_src, to_src, rel_cols, mk_names, advance) -> int:
    """Issue one MERGE per row, exactly as the original (pre-batching) code did."""
    count = 0
    for _, row in dff.iterrows():
        a_id = cell_scalar(row[from_src] if from_src in row.index else None)
        b_id = cell_scalar(row[to_src] if to_src in row.index else None)
        if a_id is None or b_id is None:
            advance(1)
            continue
        rel_props: Dict[str, Any] = {}
        csv_columns = list(row.index)
        for field_key, spec in rel_cols.items():
            name = target_field_name(field_key, spec)
            src = resolve_csv_column(field_key, spec, csv_columns)
            rel_props[name] = cell_scalar(row[src] if src in row.index else None)
        mk_params = {f"mk_{k}": rel_props[k] for k in mk_names}
        rest_props = {k: v for k, v in rel_props.items() if k not in mk_names}
        session.run(q, a_id=a_id, b_id=b_id, rprops=rest_props, **mk_params)
        count += 1
        advance(1)
    return count


def _rel_rows_for_batch(dff, from_src, to_src, rel_cols, mk_names):
    """Shape rows for UNWIND batching: (a_id, b_id, rest_props, mk_params)."""
    rows: List[Tuple[Any, Any, Dict[str, Any], Dict[str, Any]]] = []
    for _, row in dff.iterrows():
        a_id = cell_scalar(row[from_src] if from_src in row.index else None)
        b_id = cell_scalar(row[to_src] if to_src in row.index else None)
        if a_id is None or b_id is None:
            continue
        rel_props: Dict[str, Any] = {}
        csv_columns = list(row.index)
        for field_key, spec in rel_cols.items():
            name = target_field_name(field_key, spec)
            src = resolve_csv_column(field_key, spec, csv_columns)
            rel_props[name] = cell_scalar(row[src] if src in row.index else None)
        mk_params = {k: rel_props[k] for k in mk_names}
        rest_props = {k: v for k, v in rel_props.items() if k not in mk_names}
        rows.append((a_id, b_id, rest_props, mk_params))
    return rows


def _merge_rels_batched(
    session, from_label, from_key, to_label, to_key, rel_type, mk_names, rows, advance,
    batch: int = 1000,
) -> int:
    mk_clause = ", ".join(f"{k}: row.mk.{k}" for k in mk_names)
    mk_block = f" {{{mk_clause}}}" if mk_clause else ""
    q = (
        f"UNWIND $batch AS row "
        f"MATCH (a:{from_label} {{{from_key}: row.a_id}}), "
        f"(b:{to_label} {{{to_key}: row.b_id}}) "
        f"MERGE (a)-[r:{rel_type}{mk_block}]->(b) SET r += row.rprops"
    )
    count = 0
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        payload = [
            {"a_id": a_id, "b_id": b_id, "rprops": rest_props, "mk": mk_params}
            for a_id, b_id, rest_props, mk_params in chunk
        ]
        session.execute_write(lambda tx, q=q, payload=payload: tx.run(q, batch=payload))
        count += len(chunk)
        advance(len(chunk))
    return count


def run_neo4j_import(
    backend_cfg: Dict[str, Any],
    entities: Dict[str, "BoundEntity"],
    *,
    dry_run: bool,
    create_schema: bool,
    strategy: str = "optimized",
    driver_factory: Callable[[Dict[str, Any]], Any] = _default_neo4j_driver,
) -> List[str]:
    lines: List[str] = []
    conn = backend_cfg.get("connection") or {}
    relationships = backend_cfg.get("relationships") or {}

    if dry_run:
        lines.append("[neo4j] dry-run: would MERGE nodes and relationships.")
        for ename, be in entities.items():
            non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
            with metrics.timed_phase("neo4j", ename, "filter") as t:
                dff = apply_filters(be.df, non_each, be.kinds)
                t.rows = len(dff)
            for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
                lines.append(f"  label {part_name}: {len(part_df)} row(s)")
        for rname, rspec in (relationships or {}).items():
            lines.append(f"  relationship type {rspec.get('type', rname)}")
        return lines

    database = conn.get("database") or None

    try:
        driver = driver_factory(conn)
    except ImportExecutionError:
        raise
    except Exception as e:
        raise ImportExecutionError(f"Neo4j connection failed: {e}") from e

    with driver.session(database=database) as session:
        if create_schema:
            for ename, be in entities.items():
                key_cols = [(fk, sp) for fk, _, sp in flat_leaf_columns(be.cfg) if sp.get("is_key")]
                if len(key_cols) == 1:
                    kn = target_field_name(*key_cols[0])
                    lbl = _sanitize_label(ename)
                    session.run(
                        f"CREATE CONSTRAINT IF NOT EXISTS "
                        f"FOR (n:{lbl}) REQUIRE n.{kn} IS UNIQUE"
                    )

        for ename, be in entities.items():
            key_cols = [
                (fk, sp) for fk, _, sp in flat_leaf_columns(be.cfg) if sp.get("is_key")
            ]
            if len(key_cols) != 1:
                raise ImportExecutionError(f"Neo4j entity '{ename}' must have exactly one is_key column.")
            key_field, key_spec = key_cols[0]
            key_name = target_field_name(key_field, key_spec)
            key_src = resolve_csv_column(key_field, key_spec, list(be.df.columns))
            label = _sanitize_label(ename)
            non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
            with metrics.timed_phase("neo4j", ename, "filter") as t:
                dff = apply_filters(be.df, non_each, be.kinds)
                t.rows = len(dff)
            for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
                plabel = _sanitize_label(part_name)
                logger.debug("[neo4j] MERGE label %s (%d row(s))", plabel, len(part_df))
                if part_df.empty:
                    logger.warning("[neo4j] label %s has 0 row(s) after filters", part_name)
                with metrics.timed_phase("neo4j", part_name, "write") as tw:
                    props_list, skipped = _dedupe_props(part_df, be.cfg, key_name, props_from_row)
                    with entity_progress(f"neo4j · {part_name}", len(props_list)) as advance:
                        if strategy == "naive":
                            merged = _merge_nodes_naive(session, plabel, key_name, props_list, advance)
                        else:
                            merged = _merge_nodes_batched(session, plabel, key_name, props_list, advance)
                    tw.rows = merged
                if skipped:
                    logger.warning(
                        "[neo4j] %s: %d duplicate key value(s) skipped (first MERGE wins)",
                        part_name, skipped,
                    )
                lines.append(f"[neo4j] merged {merged} node(s) :{plabel}")

        for rname, rspec in (relationships or {}).items():
            from_label = _sanitize_label(rspec["from"])
            to_label = _sanitize_label(rspec["to"])
            rel_type = _sanitize_label(rspec.get("type") or rname)
            from_be = entities[rspec["from"]]
            to_be = entities[rspec["to"]]
            fk_from = [(fk, sp) for fk, _, sp in flat_leaf_columns(from_be.cfg) if sp.get("is_key")][0]
            fk_to = [(fk, sp) for fk, _, sp in flat_leaf_columns(to_be.cfg) if sp.get("is_key")][0]
            from_key = target_field_name(fk_from[0], fk_from[1])
            to_key = target_field_name(fk_to[0], fk_to[1])
            from_src = resolve_csv_column(fk_from[0], fk_from[1], list(from_be.df.columns))
            to_src = resolve_csv_column(fk_to[0], fk_to[1], list(from_be.df.columns))
            rel_cols = rspec.get("columns") or {}
            mk_names = [
                target_field_name(fk, spec)
                for fk, spec in rel_cols.items()
                if spec.get("is_key")
            ]
            f1 = [x for x in (from_be.cfg.get("filters") or []) if x.get("operator") != "each"]
            dff = apply_filters(from_be.df, f1, from_be.kinds)
            with metrics.timed_phase("neo4j", f"rel:{rel_type}", "write") as tw:
                if strategy == "naive":
                    mk_clause = ", ".join(f"{k}: $mk_{k}" for k in mk_names)
                    mk_block = f" {{{mk_clause}}}" if mk_clause else ""
                    q = (
                        f"MATCH (a:{from_label} {{{from_key}: $a_id}}), "
                        f"(b:{to_label} {{{to_key}: $b_id}}) "
                        f"MERGE (a)-[r:{rel_type}{mk_block}]->(b) SET r += $rprops"
                    )
                    logger.debug("[neo4j] Cypher: %s", q)
                    with entity_progress(f"neo4j · :{rel_type}", len(dff)) as advance:
                        count = _merge_rels_naive(
                            session, q, dff, from_src, to_src, rel_cols, mk_names, advance
                        )
                else:
                    rows = _rel_rows_for_batch(dff, from_src, to_src, rel_cols, mk_names)
                    with entity_progress(f"neo4j · :{rel_type}", len(rows)) as advance:
                        count = _merge_rels_batched(
                            session, from_label, from_key, to_label, to_key, rel_type,
                            mk_names, rows, advance,
                        )
                tw.rows = count
            lines.append(f"[neo4j] merged {count} relationship(s) :{rel_type}")

    driver.close()
    return lines
