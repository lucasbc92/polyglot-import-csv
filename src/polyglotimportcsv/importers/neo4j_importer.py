"""Import nodes and relationships into Neo4j."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

import pandas as pd
from neo4j import GraphDatabase

from polyglotimportcsv.business_exception import BusinessException
from polyglotimportcsv.entity_utils import output_column_name
from polyglotimportcsv.filter_engine import apply_filters, expand_each
from polyglotimportcsv.materialize import cell_scalar

logger = logging.getLogger(__name__)


def _sanitize_label(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", label)


def run_neo4j_import(
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
    relationships = backend_cfg.get("relationships") or {}
    _ = create_schema

    if dry_run:
        lines.append("[neo4j] dry-run: would MERGE nodes and relationships.")
        for ename, ecfg in entities.items():
            non_each = [f for f in (ecfg.get("filters") or []) if f.get("operator") != "each"]
            dff = apply_filters(df, non_each, column_kinds)
            for part_name, part_df in expand_each(dff, ecfg.get("filters") or [], ename):
                lines.append(f"  label {part_name}: {len(part_df)} row(s)")
        for rname, rspec in (relationships or {}).items():
            lines.append(f"  relationship type {rspec.get('type', rname)}")
        return lines

    uri = conn.get("uri", "bolt://127.0.0.1:7687")
    user = conn.get("user", "neo4j")
    password = conn.get("password", "password")
    database = conn.get("database") or None

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
    except Exception as e:
        raise BusinessException(f"Neo4j connection failed: {e}") from e

    def props_from_row(row: pd.Series, ecfg: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for src, spec in (ecfg.get("columns") or {}).items():
            name = output_column_name(src, spec)
            out[name] = cell_scalar(row[src] if src in row.index else None)
        return out

    with driver.session(database=database) as session:
        for ename, ecfg in entities.items():
            key_cols = [(s, sp) for s, sp in (ecfg.get("columns") or {}).items() if sp.get("is_key")]
            if len(key_cols) != 1:
                raise BusinessException(f"Neo4j entity '{ename}' must have exactly one is_key column.")
            key_src, key_spec = key_cols[0]
            key_name = output_column_name(key_src, key_spec)
            label = _sanitize_label(ename)
            non_each = [f for f in (ecfg.get("filters") or []) if f.get("operator") != "each"]
            dff = apply_filters(df, non_each, column_kinds)
            for part_name, part_df in expand_each(dff, ecfg.get("filters") or [], ename):
                plabel = _sanitize_label(part_name)
                seen = set()
                merged = 0
                for _, row in part_df.iterrows():
                    props = props_from_row(row, ecfg)
                    kid = props.get(key_name)
                    if kid is None or kid in seen:
                        continue
                    seen.add(kid)
                    rest = {k: v for k, v in props.items() if k != key_name}
                    q = f"MERGE (n:{plabel} {{{key_name}: $k}}) SET n += $props"
                    session.run(q, k=kid, props=rest)
                    merged += 1
                lines.append(f"[neo4j] merged {merged} node(s) :{plabel}")

        for rname, rspec in (relationships or {}).items():
            from_label = _sanitize_label(rspec["from"])
            to_label = _sanitize_label(rspec["to"])
            rel_type = _sanitize_label(rspec.get("type") or rname)
            from_ent = entities[rspec["from"]]
            to_ent = entities[rspec["to"]]
            fk_from = [(s, sp) for s, sp in from_ent["columns"].items() if sp.get("is_key")][0]
            fk_to = [(s, sp) for s, sp in to_ent["columns"].items() if sp.get("is_key")][0]
            from_key = output_column_name(fk_from[0], fk_from[1])
            to_key = output_column_name(fk_to[0], fk_to[1])
            rel_cols = rspec.get("columns") or {}
            merge_key_cols = [
                (src, output_column_name(src, spec))
                for src, spec in rel_cols.items()
                if spec.get("is_key")
            ]
            f1 = [x for x in (from_ent.get("filters") or []) if x.get("operator") != "each"]
            dff = apply_filters(df, f1, column_kinds)
            count = 0
            for _, row in dff.iterrows():
                a_id = cell_scalar(row[fk_from[0]] if fk_from[0] in row.index else None)
                b_id = cell_scalar(row[fk_to[0]] if fk_to[0] in row.index else None)
                if a_id is None or b_id is None:
                    continue
                rel_props: Dict[str, Any] = {}
                for src, spec in rel_cols.items():
                    name = output_column_name(src, spec)
                    rel_props[name] = cell_scalar(row[src] if src in row.index else None)
                merge_keys = {db_name: rel_props[db_name] for _, db_name in merge_key_cols}
                rest_props = {k: v for k, v in rel_props.items() if k not in merge_keys}
                if merge_keys:
                    mk_clause = ", ".join(f"{k}: $mk_{k}" for k in merge_keys)
                    mk_params = {f"mk_{k}": v for k, v in merge_keys.items()}
                else:
                    mk_clause = ""
                    mk_params = {}
                mk_block = f" {{{mk_clause}}}" if mk_clause else ""
                q = (
                    f"MATCH (a:{from_label} {{{from_key}: $a_id}}), "
                    f"(b:{to_label} {{{to_key}: $b_id}}) "
                    f"MERGE (a)-[r:{rel_type}{mk_block}]->(b) SET r += $rprops"
                )
                session.run(q, a_id=a_id, b_id=b_id, rprops=rest_props, **mk_params)
                count += 1
            lines.append(f"[neo4j] merged {count} relationship(s) :{rel_type}")

    driver.close()
    return lines
