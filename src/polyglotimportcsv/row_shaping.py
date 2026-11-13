"""Build per-entity pandas frames from a source DataFrame and entity config."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence, Tuple

import pandas as pd

from polyglotimportcsv.entity_utils import (
    flat_leaf_columns,
    is_column_branch,
    is_column_spec,
    resolve_csv_column,
    target_field_name,
)
from polyglotimportcsv.row_view import iter_rows


def flatten_entity_dataframe(df: pd.DataFrame, entity_cfg: Dict[str, Any]) -> pd.DataFrame:
    """Select entity columns, rename to schema targets, drop duplicate primary keys
    (the first row of each key is kept).

    Built per leaf column (not select+rename) so one CSV column mapped to two
    schema_column targets (the duplicate csv_column feature) doesn't collide.
    """
    csv_columns = list(df.columns)
    data: Dict[str, pd.Series] = {}
    key_outs: list[str] = []
    for field_key, _, spec in flat_leaf_columns(entity_cfg):
        src = resolve_csv_column(field_key, spec, csv_columns)
        out = target_field_name(field_key, spec)
        data[out] = df[src].copy()
        if spec.get("is_key"):
            key_outs.append(out)
    if not data:
        raise ValueError("Entity has no columns")
    sub = pd.DataFrame(data, index=df.index)
    if key_outs:
        for kc in key_outs:
            sub[kc] = sub[kc].replace("", pd.NA)
        sub = sub.dropna(subset=key_outs, how="any")
        # The first row of a key wins, as it does between two batches (the INSERT
        # skips a key already in the table): which row is kept does not depend on
        # where the batches are cut.
        sub = sub.drop_duplicates(subset=key_outs, keep="first")
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


#: A document's fields, resolved once per batch: ``(target name, CSV column)`` for a
#: leaf, ``(field name, sub-plan)`` for a nested document.
_DocumentPlan = List[Tuple[str, Any]]


def _document_plan(columns: Dict[str, Any], csv_columns: Sequence[str]) -> _DocumentPlan:
    plan: _DocumentPlan = []
    for field_key, node in (columns or {}).items():
        if is_column_spec(node):
            plan.append(
                (target_field_name(field_key, node), resolve_csv_column(field_key, node, csv_columns))
            )
        elif is_column_branch(node):
            plan.append((field_key, _document_plan(node, csv_columns)))
    return plan


def _document(row: Any, plan: _DocumentPlan) -> Dict[str, Any]:
    return {
        name: _document(row, src) if isinstance(src, list) else cell_scalar(row.get(src))
        for name, src in plan
    }


def mongo_document_from_row(row: pd.Series, entity_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Build one BSON-ready dict from a CSV row (recursive columns)."""
    return _document(row, _document_plan(entity_cfg.get("columns") or {}, row.index))


def mongo_documents(df: pd.DataFrame, entity_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One BSON-ready dict per row of ``df``. The entity's columns are resolved once for
    the batch, not once per row."""
    plan = _document_plan(entity_cfg.get("columns") or {}, df.columns)
    return [_document(row, plan) for row in iter_rows(df)]


def _redis_plan(
    entity_cfg: Dict[str, Any], csv_columns: Sequence[str]
) -> Tuple[str, _DocumentPlan]:
    """``(key column, payload plan)`` of a Redis entity; its key column must be the one
    marked is_key."""
    leaves = [(fk, sp) for fk, _, sp in flat_leaf_columns(entity_cfg)]
    keys = [(fk, sp) for fk, sp in leaves if sp.get("is_key")]
    if len(keys) != 1:
        raise ValueError("Redis entity requires exactly one is_key column for the key name")
    payload = [
        (target_field_name(fk, sp), resolve_csv_column(fk, sp, csv_columns))
        for fk, sp in leaves
        if not sp.get("is_key")
    ]
    return resolve_csv_column(*keys[0], csv_columns), payload


def _redis_payload(row: Any, key_src: str, plan: _DocumentPlan) -> tuple[str, str]:
    key_val = row[key_src]
    if pd.isna(key_val):
        raise ValueError("Redis key column value is null")
    return str(key_val), json.dumps(_document(row, plan), default=str)


def redis_payload_from_row(row: pd.Series, entity_cfg: Dict[str, Any]) -> tuple[str, str]:
    """Return (redis_key, redis_value_json) for a row; key column must be marked is_key."""
    return _redis_payload(row, *_redis_plan(entity_cfg, row.index))


def redis_payloads(df: pd.DataFrame, entity_cfg: Dict[str, Any]) -> List[tuple[str, str]]:
    """``(redis_key, redis_value_json)`` of every row of ``df`` that has a key. The
    entity's columns are resolved once for the batch, not once per row."""
    key_src, plan = _redis_plan(entity_cfg, df.columns)
    pairs = []
    for row in iter_rows(df):
        try:
            pairs.append(_redis_payload(row, key_src, plan))
        except ValueError:
            continue
    return pairs
