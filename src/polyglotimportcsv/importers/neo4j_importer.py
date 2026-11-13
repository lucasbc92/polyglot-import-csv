"""Neo4j helpers shared by ``Neo4jSink``: driver, node/edge shaping and UNWIND writes."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
from neo4j import GraphDatabase

from polyglotimportcsv.entity_utils import (
    flat_leaf_columns,
    is_empty_reference,
    resolve_csv_column,
    target_field_name,
)
from polyglotimportcsv.row_shaping import cell_scalar
from polyglotimportcsv.row_view import iter_rows


def _sanitize_label(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", label)


def _default_neo4j_driver(conn: Dict[str, Any]):
    uri = conn.get("uri", "bolt://127.0.0.1:7687")
    user = conn.get("user", "neo4j")
    password = conn.get("password", "password")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    return driver


#: ``(property name, CSV column)`` of every leaf column of an entity, resolved once
#: against the columns of a batch.
_Plan = List[Tuple[str, str]]


def _node_plan(ecfg: Dict[str, Any], csv_columns) -> _Plan:
    return [
        (target_field_name(field_key, spec), resolve_csv_column(field_key, spec, csv_columns))
        for field_key, _, spec in flat_leaf_columns(ecfg)
    ]


def _props(row, plan: _Plan) -> Dict[str, Any]:
    return {name: cell_scalar(row.get(src)) for name, src in plan}


def props_from_row(row: pd.Series, ecfg: Dict[str, Any]) -> Dict[str, Any]:
    """Build one node's property dict from a CSV row (flat columns only)."""
    return _props(row, _node_plan(ecfg, row.index))


def _dedupe_props(part_df, ecfg, key_name, seen: Optional[Set[Any]] = None):
    """First-wins dedupe by key; returns (list-of-props, skipped_count).

    The entity's columns are resolved once for the batch, and a row whose key was
    already seen is skipped before its properties are built. ``seen`` defaults to a
    fresh set (one call = one dedupe scope). Pass a set kept across calls (as
    ``Neo4jSink.write_batch`` does, keyed per partition) to make first-wins hold
    across a whole streaming pass instead of just within one batch.
    """
    if seen is None:
        seen = set()
    plan = _node_plan(ecfg, part_df.columns)
    key_src = dict(plan).get(key_name)
    out, skipped = [], 0
    if key_src is None:
        return out, skipped
    for row in iter_rows(part_df):
        kid = cell_scalar(row.get(key_src))
        if kid is None:
            continue
        if kid in seen:
            skipped += 1
            continue
        seen.add(kid)
        out.append(_props(row, plan))
    return out, skipped


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


def _rel_rows_for_batch(dff, from_src, to_src, rel_cols, mk_names):
    """Shape rows for UNWIND batching: (a_id, b_id, rest_props, mk_params).

    A row with an empty endpoint (``is_empty_reference``) makes no edge and is left out.
    The edge's columns are resolved once for the batch.
    """
    columns = list(dff.columns)
    merge = set(mk_names)
    plan = [
        (target_field_name(fk, spec), resolve_csv_column(fk, spec, columns))
        for fk, spec in rel_cols.items()
    ]
    mk_plan = [(name, src) for name, src in plan if name in merge]
    rest_plan = [(name, src) for name, src in plan if name not in merge]
    rows: List[Tuple[Any, Any, Dict[str, Any], Dict[str, Any]]] = []
    for row in iter_rows(dff):
        a_id = cell_scalar(row.get(from_src))
        b_id = cell_scalar(row.get(to_src))
        if is_empty_reference(a_id) or is_empty_reference(b_id):
            continue
        rows.append((a_id, b_id, _props(row, rest_plan), _props(row, mk_plan)))
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
