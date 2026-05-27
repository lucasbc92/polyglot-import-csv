"""Cross-validate configuration against the loaded CSV."""

from __future__ import annotations

from typing import Any, Dict, List, Set

import pandas as pd

from polyglotimportcsv.business_exception import BusinessException
from polyglotimportcsv.entity_utils import (
    FLAT_BACKENDS,
    collect_source_columns,
    entity_has_nested_branches,
    iter_leaf_columns,
    resolve_csv_column,
)


BACKENDS = ("postgres", "mongodb", "cassandra", "redis", "neo4j")


def _all_entity_configs(backend_cfg: Dict[str, Any]) -> List[tuple[str, Dict[str, Any]]]:
    out: List[tuple[str, Dict[str, Any]]] = []
    entities = backend_cfg.get("entities") or {}
    for name, ecfg in entities.items():
        out.append((name, ecfg))
    return out


def _collect_all_columns_from_entities(
    backend_cfg: Dict[str, Any], csv_column_list: List[str]
) -> Set[str]:
    cols: Set[str] = set()
    for _, ecfg in _all_entity_configs(backend_cfg):
        try:
            cols.update(collect_source_columns(ecfg, csv_column_list))
        except ValueError as e:
            raise BusinessException(str(e)) from e
    return cols


def _validate_filters(filters: List[Dict[str, Any]], csv_columns: Set[str]) -> None:
    for flt in filters or []:
        c = flt.get("column")
        if not c:
            raise BusinessException("Filter missing 'column'.")
        if c not in csv_columns:
            raise BusinessException(f"Filter column not found in CSV: {c}")
        op = flt.get("operator")
        if op not in ("==", "!=", ">", "<", ">=", "<=", "in", "not_in", "each"):
            raise BusinessException(f"Unsupported filter operator: {op}")
        if op in ("in", "not_in") and not isinstance(flt.get("value"), list):
            raise BusinessException(f"Filter '{op}' requires 'value' to be a list.")
        if op == "each":
            continue
        if op not in ("in", "not_in") and "value" not in flt:
            raise BusinessException(f"Filter with operator {op} requires 'value'.")


def _validate_leaf_columns(
    ename: str, backend: str, ecfg: Dict[str, Any], csv_column_list: List[str], csv_columns: Set[str]
) -> None:
    for _, field_key, spec in iter_leaf_columns(ecfg):
        try:
            resolved = resolve_csv_column(field_key, spec, csv_column_list)
        except ValueError as e:
            raise BusinessException(
                f"Entity '{ename}' in '{backend}': {e}"
            ) from e
        if resolved not in csv_columns:
            raise BusinessException(
                f"Entity '{ename}' in '{backend}' references unknown column: {resolved}"
            )


def validate_import_config(config: Dict[str, Any], df: pd.DataFrame, kinds: Dict[str, str]) -> None:
    csv_column_list = list(df.columns)
    csv_columns = set(csv_column_list)
    for backend in BACKENDS:
        if backend not in config:
            continue
        bcfg = config[backend]
        for ename, ecfg in _all_entity_configs(bcfg):
            if backend in FLAT_BACKENDS and entity_has_nested_branches(ecfg):
                raise BusinessException(
                    f"Entity '{ename}' in '{backend}' uses nested columns; "
                    f"only flat column mappings are allowed for this backend."
                )
        referenced = _collect_all_columns_from_entities(bcfg, csv_column_list)
        missing = sorted(referenced - csv_columns)
        if missing:
            raise BusinessException(
                f"Backend '{backend}' references unknown CSV column(s): {', '.join(missing)}"
            )
        for ename, ecfg in _all_entity_configs(bcfg):
            _validate_filters(ecfg.get("filters") or [], csv_columns)
            _validate_leaf_columns(ename, backend, ecfg, csv_column_list, csv_columns)
            for pk in ecfg.get("cassandra_partition") or []:
                if pk not in csv_columns:
                    raise BusinessException(
                        f"Cassandra partition column '{pk}' not in CSV (entity {ename})."
                    )
            for ck in ecfg.get("cassandra_cluster") or []:
                if ck not in csv_columns:
                    raise BusinessException(
                        f"Cassandra cluster column '{ck}' not in CSV (entity {ename})."
                    )

        if backend == "postgres":
            rels = bcfg.get("relationships") or {}
            entities = set((bcfg.get("entities") or {}).keys())
            for rname, rspec in rels.items():
                fr = rspec.get("from")
                to = rspec.get("to")
                if fr not in entities or to not in entities:
                    raise BusinessException(
                        f"Relationship '{rname}' references unknown entity (from={fr}, to={to})."
                    )
                fk = rspec.get("foreign_key")
                refk = rspec.get("references_key") or fk
                if fk not in csv_columns:
                    raise BusinessException(
                        f"Relationship '{rname}' foreign_key '{fk}' not found in CSV columns."
                    )
                to_cols = collect_source_columns(bcfg["entities"][to], csv_column_list)
                if refk not in to_cols:
                    raise BusinessException(
                        f"Relationship '{rname}': references_key '{refk}' not mapped in entity '{to}'."
                    )

        if backend == "neo4j":
            rels = bcfg.get("relationships") or {}
            entities = set((bcfg.get("entities") or {}).keys())
            for rname, rspec in rels.items():
                if rspec.get("from") not in entities or rspec.get("to") not in entities:
                    raise BusinessException(
                        f"Neo4j relationship '{rname}' references unknown node entity."
                    )
                for field_key, spec in (rspec.get("columns") or {}).items():
                    try:
                        resolved = resolve_csv_column(field_key, spec, csv_column_list)
                    except ValueError as e:
                        raise BusinessException(
                            f"Neo4j relationship '{rname}': {e}"
                        ) from e
                    if resolved not in csv_columns:
                        raise BusinessException(
                            f"Neo4j relationship '{rname}' property column '{resolved}' not in CSV."
                        )

    _ = kinds  # reserved for stricter checks later
