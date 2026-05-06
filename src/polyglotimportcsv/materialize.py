"""Build per-entity pandas frames from a source DataFrame and entity config."""

from __future__ import annotations

import json
from typing import Any, Dict

import pandas as pd

from polyglotimportcsv.entity_utils import output_column_name


def flatten_entity_dataframe(df: pd.DataFrame, entity_cfg: Dict[str, Any]) -> pd.DataFrame:
    """Select entity columns, rename to db_column/alias, drop duplicate primary keys."""
    cols = list((entity_cfg.get("columns") or {}).keys())
    if not cols:
        raise ValueError("Entity has no columns")
    sub = df.loc[:, cols].copy()
    rename = {src: output_column_name(src, spec) for src, spec in entity_cfg["columns"].items()}
    sub = sub.rename(columns=rename)
    key_outs = [
        output_column_name(src, spec)
        for src, spec in entity_cfg["columns"].items()
        if spec.get("is_key")
    ]
    if key_outs:
        for kc in key_outs:
            sub[kc] = sub[kc].replace("", pd.NA)
        sub = sub.dropna(subset=key_outs, how="any")
        sub = sub.drop_duplicates(subset=key_outs, keep="last")
    return sub


def cell_scalar(val: Any) -> Any:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if hasattr(val, "item"):
        try:
            return val.item()
        except Exception:
            return val
    return val


def mongo_document_from_row(row: pd.Series, entity_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Build one BSON-ready dict from a CSV row for a Mongo entity with optional nested."""
    doc: Dict[str, Any] = {}
    for src, spec in (entity_cfg.get("columns") or {}).items():
        name = output_column_name(src, spec)
        val = cell_scalar(row[src] if src in row.index else None)
        doc[name] = val
    for nest_name, nest_cfg in (entity_cfg.get("nested") or {}).items():
        nest_doc: Dict[str, Any] = {}
        for src, spec in (nest_cfg.get("columns") or {}).items():
            name = output_column_name(src, spec)
            nest_doc[name] = cell_scalar(row[src] if src in row.index else None)
        doc[nest_name] = nest_doc
    return doc


def redis_payload_from_row(row: pd.Series, entity_cfg: Dict[str, Any]) -> tuple[str, str]:
    """Return (redis_key, redis_value_json) for a row; key column must be marked is_key."""
    key_cols = [s for s, sp in entity_cfg["columns"].items() if sp.get("is_key")]
    if len(key_cols) != 1:
        raise ValueError("Redis entity requires exactly one is_key column for the key name")
    k_src = key_cols[0]
    key_val = row[k_src]
    if pd.isna(key_val):
        raise ValueError("Redis key column value is null")
    payload: Dict[str, Any] = {}
    for src, spec in entity_cfg["columns"].items():
        if spec.get("is_key"):
            continue
        name = output_column_name(src, spec)
        payload[name] = cell_scalar(row[src] if src in row.index else None)
    return str(key_val), json.dumps(payload, default=str)
