"""Build per-entity pandas frames from a source DataFrame and entity config."""

from __future__ import annotations

import json
from typing import Any, Dict

import pandas as pd

from polyglotimportcsv.entity_utils import (
    flat_leaf_columns,
    is_column_branch,
    is_column_spec,
    resolve_csv_column,
    target_field_name,
)


def _row_cell(row: pd.Series, field_key: str, spec: Dict[str, Any]) -> Any:
    src = resolve_csv_column(field_key, spec, list(row.index))
    val = row[src] if src in row.index else None
    return cell_scalar(val)


def flatten_entity_dataframe(df: pd.DataFrame, entity_cfg: Dict[str, Any]) -> pd.DataFrame:
    """Select entity columns, rename to schema targets, drop duplicate primary keys."""
    csv_columns = list(df.columns)
    src_cols: list[str] = []
    rename: Dict[str, str] = {}
    key_outs: list[str] = []
    for field_key, _, spec in flat_leaf_columns(entity_cfg):
        src = resolve_csv_column(field_key, spec, csv_columns)
        src_cols.append(src)
        out = target_field_name(field_key, spec)
        rename[src] = out
        if spec.get("is_key"):
            key_outs.append(out)
    if not src_cols:
        raise ValueError("Entity has no columns")
    sub = df.loc[:, src_cols].copy()
    sub = sub.rename(columns=rename)
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


def _build_document_from_columns(row: pd.Series, columns: Dict[str, Any]) -> Dict[str, Any]:
    doc: Dict[str, Any] = {}
    for field_key, node in (columns or {}).items():
        if is_column_spec(node):
            doc[target_field_name(field_key, node)] = _row_cell(row, field_key, node)
        elif is_column_branch(node):
            doc[field_key] = _build_document_from_columns(row, node)
    return doc


def mongo_document_from_row(row: pd.Series, entity_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Build one BSON-ready dict from a CSV row (recursive columns + legacy nested)."""
    doc = _build_document_from_columns(row, entity_cfg.get("columns") or {})
    for nest_name, nest_cfg in (entity_cfg.get("nested") or {}).items():
        nest_columns = nest_cfg.get("columns") if isinstance(nest_cfg, dict) else {}
        doc[nest_name] = _build_document_from_columns(row, nest_columns or {})
    return doc


def redis_payload_from_row(row: pd.Series, entity_cfg: Dict[str, Any]) -> tuple[str, str]:
    """Return (redis_key, redis_value_json) for a row; key column must be marked is_key."""
    csv_columns = list(row.index)
    key_entries = [
        (fk, sp)
        for fk, _, sp in flat_leaf_columns(entity_cfg)
        if sp.get("is_key")
    ]
    if len(key_entries) != 1:
        raise ValueError("Redis entity requires exactly one is_key column for the key name")
    key_field, key_spec = key_entries[0]
    key_src = resolve_csv_column(key_field, key_spec, csv_columns)
    key_val = row[key_src]
    if pd.isna(key_val):
        raise ValueError("Redis key column value is null")
    payload: Dict[str, Any] = {}
    for field_key, _, spec in flat_leaf_columns(entity_cfg):
        if spec.get("is_key"):
            continue
        name = target_field_name(field_key, spec)
        payload[name] = _row_cell(row, field_key, spec)
    return str(key_val), json.dumps(payload, default=str)
