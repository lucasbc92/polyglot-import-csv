"""Cross-validate resolved (bound) entities against their sources.

``validate_headers`` is the header-level check shared by the CLI and the GUI
preflight: it binds every entity to header-only sources and runs
``validate_backend_entities`` over them.
"""

from __future__ import annotations

from typing import Any, Collection, Dict, List, Sequence, Set, Tuple

import pandas as pd

from polyglotimportcsv.business_exception import MappingError
from polyglotimportcsv.entity_utils import (
    FLAT_BACKENDS,
    entity_has_nested_branches,
    iter_leaf_columns,
    resolve_csv_column,
    target_field_name,
)
from polyglotimportcsv.mapping_resolver import (
    BoundEntity,
    bind_entity_source,
    expand_entity_columns,
    union_data_cols,
)
from polyglotimportcsv.sources import SOURCE_COLUMN, SourceData

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


def _key_leaves(cfg: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """``(field_key, spec)`` of every leaf column marked ``is_key``."""
    return [(fk, spec) for _, fk, spec in iter_leaf_columns(cfg) if spec.get("is_key")]


def _check_endpoints_have_no_each(
    label: str, rname: str, rspec: Dict[str, Any], bound: Dict[str, BoundEntity]
) -> None:
    """A relationship cannot point at an entity an ``each`` filter splits in parts."""
    for end in ("from", "to"):
        ename = rspec[end]
        filters = bound[ename].cfg.get("filters") or []
        if any(f.get("operator") == "each" for f in filters):
            raise MappingError(
                f"{label} '{rname}': entity '{ename}' uses an 'each' filter, which splits "
                f"it into several parts; a relationship cannot reference it."
            )


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
        if backend in ("redis", "neo4j") and len(_key_leaves(be.cfg)) != 1:
            raise MappingError(
                f"Entity '{ename}' in '{backend}' must have exactly one is_key column."
            )
        if backend == "cassandra" and not be.cfg.get("cassandra_partition"):
            raise MappingError(
                f"Entity '{ename}' in 'cassandra' must declare a non-empty cassandra_partition."
            )
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
            _check_endpoints_have_no_each("Relationship", rname, rspec, bound)
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
            _check_endpoints_have_no_each("Neo4j relationship", rname, rspec, bound)
            from_be = bound[rspec["from"]]
            cols = list(from_be.df.columns)
            colset = set(cols)
            # Both endpoint keys are read from the `from` entity's source rows.
            for end in ("from", "to"):
                key_field, key_spec = _key_leaves(bound[rspec[end]].cfg)[0]
                try:
                    key_col = resolve_csv_column(key_field, key_spec, cols)
                except ValueError as e:
                    raise MappingError(f"Neo4j relationship '{rname}': {e}") from e
                if key_col not in colset:
                    raise MappingError(
                        f"Neo4j relationship '{rname}': key column '{key_col}' of entity "
                        f"'{rspec[end]}' not in the source of '{rspec['from']}'."
                    )
            for field_key, spec in (rspec.get("columns") or {}).items():
                try:
                    resolved = resolve_csv_column(field_key, spec, cols)
                except ValueError as e:
                    raise MappingError(f"Neo4j relationship '{rname}': {e}") from e
                if resolved not in colset:
                    raise MappingError(
                        f"Neo4j relationship '{rname}' property column '{resolved}' not in source."
                    )


def _header_only(name: str, columns: List[str]) -> SourceData:
    frame = pd.DataFrame({column: pd.Series(dtype=str) for column in columns + [SOURCE_COLUMN]})
    kinds = {column: "string" for column in columns}
    kinds[SOURCE_COLUMN] = "string"
    return SourceData(name=name, df=frame, kinds=kinds, file_header=list(columns))


def validate_headers(
    config: Dict[str, Any],
    headers: Dict[str, List[str]],
    combined: Collection[str],
    dbms_names: Sequence[str],
) -> None:
    """Bind and validate every entity of ``dbms_names`` against header-only sources.

    ``headers`` maps each declared source to its data columns (origin column of a
    combined file already removed); ``combined`` names the combined sources among
    them. No row is needed: a column the configuration names but the header lacks
    fails here with the same message the data pass would give.

    The origin values that name a combined source's slices live in the rows, so a
    name an entity refers to that is not a declared source stands for one such
    slice. It may draw on any combined file, so it gets the union of their headers.
    The declared name of a combined file is no source of an entity (an origin value
    can never equal it), so an entity that names one is rejected.
    """
    registry = {
        name: _header_only(name, header) for name, header in headers.items() if name not in combined
    }
    combined_headers = [header for name, header in headers.items() if name in combined]
    if combined_headers:
        union_header = union_data_cols(combined_headers)
        for dbms in dbms_names:
            for ename, ecfg in (config[dbms].get("entities") or {}).items():
                ref = (ecfg or {}).get("source", ename)
                for name in ref if isinstance(ref, list) else [ref]:
                    if name in combined:
                        raise MappingError(
                            f"Entity '{ename}' ({dbms}): '{name}' is the name of a combined CSV, "
                            "not a source. The entity must use one of the origin values of "
                            "that file as its source."
                        )
                    if name not in registry:
                        registry[name] = _header_only(name, union_header)
    for dbms in dbms_names:
        bound: Dict[str, BoundEntity] = {}
        for ename, ecfg in (config[dbms].get("entities") or {}).items():
            src = bind_entity_source(ename, ecfg, registry)
            cfg = dict(ecfg)
            cfg["columns"] = expand_entity_columns(ename, ecfg, src)
            for key in ("source", "csv_columns", "auto_map"):
                cfg.pop(key, None)
            bound[ename] = BoundEntity(name=ename, cfg=cfg, df=src.df, kinds=src.kinds)
        validate_backend_entities(dbms, config[dbms], bound)
