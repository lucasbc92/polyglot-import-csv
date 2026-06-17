"""Helpers to traverse entity column definitions (including nested)."""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Sequence, Tuple

COLUMN_SPEC_KEYS = frozenset(
    {"is_key", "db_type", "csv_column", "schema_column"}
)

FLAT_BACKENDS = frozenset({"postgres", "redis", "cassandra", "neo4j"})


def is_column_spec(node: Any) -> bool:
    """True when *node* is a leaf columnSpec (not a nested branch)."""
    return isinstance(node, dict) and all(k in COLUMN_SPEC_KEYS for k in node)


def is_column_branch(node: Any) -> bool:
    return isinstance(node, dict) and not is_column_spec(node) and len(node) > 0


def target_field_name(field_key: str, spec: Dict[str, Any]) -> str:
    """JSON field key -> target attribute name in the destination store."""
    return spec.get("schema_column") or field_key


def output_column_name(source_col: str, spec: Dict[str, Any]) -> str:
    """Backward-compatible alias for target_field_name (first arg is the field key)."""
    return target_field_name(source_col, spec)


def resolve_csv_column(
    field_key: str, spec: Dict[str, Any], csv_columns: Sequence[str]
) -> str:
    """Resolve csv_column (name or 0-based index) to the actual CSV header."""
    csv = spec.get("csv_column")
    if isinstance(csv, int):
        if csv < 0 or csv >= len(csv_columns):
            raise ValueError(
                f"csv_column index {csv} out of range (CSV has {len(csv_columns)} column(s))."
            )
        return csv_columns[csv]
    if isinstance(csv, str):
        return csv
    return field_key


def iter_column_tree(
    columns: Dict[str, Any], prefix: Tuple[str, ...] = ()
) -> Iterator[Tuple[Tuple[str, ...], str, Dict[str, Any]]]:
    """
    Walk a recursive ``columns`` map.

    Yields (nested_path_tuple, field_key, column_spec) for each leaf.
    """
    for field_key, node in (columns or {}).items():
        if is_column_spec(node):
            yield prefix, field_key, node
        elif is_column_branch(node):
            yield from iter_column_tree(node, prefix + (field_key,))


def iter_leaf_columns(
    entity_cfg: Dict[str, Any], prefix: Tuple[str, ...] = ()
) -> Iterator[Tuple[Tuple[str, ...], str, Dict[str, Any]]]:
    """
    Yields (nested_path_tuple, field_key, column_spec) for all leaves of the
    recursive ``columns`` map.
    """
    yield from iter_column_tree(entity_cfg.get("columns") or {}, prefix)


def entity_has_nested_branches(entity_cfg: Dict[str, Any]) -> bool:
    """True when ``columns`` contains nested objects (MongoDB subdocuments)."""
    for node in (entity_cfg.get("columns") or {}).values():
        if is_column_branch(node):
            return True
    return False


def collect_source_columns(
    entity_cfg: Dict[str, Any], csv_columns: Sequence[str] | None = None
) -> List[str]:
    """All CSV column names referenced by an entity (including nested)."""
    out: List[str] = []
    for _, field_key, spec in iter_leaf_columns(entity_cfg):
        if csv_columns is not None:
            out.append(resolve_csv_column(field_key, spec, csv_columns))
        else:
            csv = spec.get("csv_column")
            if isinstance(csv, int):
                out.append(str(csv))
            elif isinstance(csv, str):
                out.append(csv)
            else:
                out.append(field_key)
    return out


def primary_key_source_columns(
    entity_cfg: Dict[str, Any], csv_columns: Sequence[str] | None = None
) -> List[str]:
    keys: List[str] = []
    for _, field_key, spec in iter_leaf_columns(entity_cfg):
        if spec.get("is_key"):
            if csv_columns is not None:
                keys.append(resolve_csv_column(field_key, spec, csv_columns))
            else:
                keys.append(field_key)
    return keys


def flat_leaf_columns(
    entity_cfg: Dict[str, Any],
) -> Iterator[Tuple[str, str, Dict[str, Any]]]:
    """
    Yields (field_key, resolved_source_placeholder, spec) for top-level leaves only.
    Used by flat backends after validation ensures no nesting.
    """
    for field_key, node in (entity_cfg.get("columns") or {}).items():
        if is_column_spec(node):
            yield field_key, field_key, node
