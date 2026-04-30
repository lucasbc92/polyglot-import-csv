"""Helpers to traverse entity column definitions (including nested)."""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Tuple


def output_column_name(source_col: str, spec: Dict[str, Any]) -> str:
    """CSV/source column name -> target attribute name."""
    return spec.get("db_column") or spec.get("alias_db") or source_col


def iter_leaf_columns(
    entity_cfg: Dict[str, Any], prefix: Tuple[str, ...] = ()
) -> Iterator[Tuple[str, ...], str, Dict[str, Any]]:
    """
    Yields (nested_path_tuple, source_csv_column, column_spec).
    nested_path_tuple is e.g. () for top-level, ('buyer',) for nested buyer columns.
    """
    cols = entity_cfg.get("columns") or {}
    for src, spec in cols.items():
        yield prefix, src, spec
    nested = entity_cfg.get("nested") or {}
    for nest_name, nest_cfg in nested.items():
        yield from iter_leaf_columns(nest_cfg, prefix + (nest_name,))


def collect_source_columns(entity_cfg: Dict[str, Any]) -> List[str]:
    """All CSV column names referenced by an entity (including nested)."""
    return [src for _, src, _ in iter_leaf_columns(entity_cfg)]


def primary_key_source_columns(entity_cfg: Dict[str, Any]) -> List[str]:
    keys: List[str] = []
    for _, src, spec in iter_leaf_columns(entity_cfg):
        if spec.get("is_key"):
            keys.append(src)
    return keys
