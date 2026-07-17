"""Cross-validate resolved (bound) entities against their sources."""

from __future__ import annotations

from typing import Any, Dict, List, Set

from polyglotimportcsv.business_exception import MappingError
from polyglotimportcsv.entity_utils import (
    FLAT_BACKENDS,
    entity_has_nested_branches,
    iter_leaf_columns,
    resolve_csv_column,
    target_field_name,
)
from polyglotimportcsv.mapping_resolver import BoundEntity

BACKENDS = ("postgres", "mongodb", "cassandra", "redis", "neo4j")


def _validate_filters(
    ename: str, backend: str, filters: List[Dict[str, Any]], columns: Set[str]
) -> None:
    for flt in filters or []:
        c = flt.get("column")
        if not c:
            raise MappingError(f"Entity '{ename}' in '{backend}': filter missing 'column'.")
        if c not in columns:
            raise MappingError(
                f"Entity '{ename}' in '{backend}': Filter column not found in source: {c}"
            )
        op = flt.get("operator")
        if op not in ("==", "!=", ">", "<", ">=", "<=", "in", "not_in", "each"):
            raise MappingError(f"Unsupported filter operator: {op}")
        if op in ("in", "not_in") and not isinstance(flt.get("value"), list):
            raise MappingError(f"Filter '{op}' requires 'value' to be a list.")
        if op == "each":
            continue
        if op not in ("in", "not_in") and "value" not in flt:
            raise MappingError(f"Filter with operator {op} requires 'value'.")


def _entity_targets(cfg: Dict[str, Any]) -> Set[str]:
    return {target_field_name(fk, spec) for _, fk, spec in iter_leaf_columns(cfg)}


def validate_backend_entities(
    backend: str, backend_cfg: Dict[str, Any], bound: Dict[str, BoundEntity]
) -> None:
    """Validate every bound entity (and relationships) of one backend."""
    for ename, be in bound.items():
        cols = list(be.df.columns)
        colset = set(cols)
        if backend in FLAT_BACKENDS and entity_has_nested_branches(be.cfg):
            raise MappingError(
                f"Entity '{ename}' in '{backend}' uses nested columns; "
                f"only flat column mappings are allowed for this backend."
            )
        for _, field_key, spec in iter_leaf_columns(be.cfg):
            try:
                resolved = resolve_csv_column(field_key, spec, cols)
            except ValueError as e:
                raise MappingError(f"Entity '{ename}' in '{backend}': {e}") from e
            if resolved not in colset:
                raise MappingError(
                    f"Entity '{ename}' in '{backend}' references unknown column: {resolved}"
                )
        _validate_filters(ename, backend, be.cfg.get("filters") or [], colset)
        for pk in be.cfg.get("cassandra_partition") or []:
            if pk not in colset:
                raise MappingError(
                    f"Cassandra partition column '{pk}' not in source (entity {ename})."
                )
        for ck in be.cfg.get("cassandra_cluster") or []:
            if ck not in colset:
                raise MappingError(
                    f"Cassandra cluster column '{ck}' not in source (entity {ename})."
                )

    if backend == "postgres":
        for rname, rspec in (backend_cfg.get("relationships") or {}).items():
            fr, to = rspec.get("from"), rspec.get("to")
            if fr not in bound or to not in bound:
                raise MappingError(
                    f"Relationship '{rname}' references unknown entity (from={fr}, to={to})."
                )
            fk = rspec.get("foreign_key")
            refk = rspec.get("references_key") or fk
            if fk not in _entity_targets(bound[fr].cfg):
                raise MappingError(
                    f"Relationship '{rname}': foreign_key '{fk}' not mapped in entity '{fr}'."
                )
            if refk not in _entity_targets(bound[to].cfg):
                raise MappingError(
                    f"Relationship '{rname}': references_key '{refk}' not mapped in entity '{to}'."
                )

    if backend == "neo4j":
        for rname, rspec in (backend_cfg.get("relationships") or {}).items():
            if rspec.get("from") not in bound or rspec.get("to") not in bound:
                raise MappingError(
                    f"Neo4j relationship '{rname}' references unknown node entity."
                )
            from_be = bound[rspec["from"]]
            cols = list(from_be.df.columns)
            colset = set(cols)
            for field_key, spec in (rspec.get("columns") or {}).items():
                try:
                    resolved = resolve_csv_column(field_key, spec, cols)
                except ValueError as e:
                    raise MappingError(f"Neo4j relationship '{rname}': {e}") from e
                if resolved not in colset:
                    raise MappingError(
                        f"Neo4j relationship '{rname}' property column '{resolved}' not in source."
                    )
