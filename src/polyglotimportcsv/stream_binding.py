"""Bind a streamed entity from the profiles of its sources.

Binds each entity with the pieces of ``mapping_resolver`` (``bind_entity_source``,
``expand_entity_columns``), over a header-only ``SourceData`` registry built from the
source profiles; the kinds are those of the whole file.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Tuple

import pandas as pd

from polyglotimportcsv.business_exception import MappingError
from polyglotimportcsv.casting import declared_kind
from polyglotimportcsv.entity_utils import iter_leaf_columns, resolve_csv_column
from polyglotimportcsv.mapping_resolver import bind_entity_source, expand_entity_columns
from polyglotimportcsv.source_profile import SourceProfile, union_kinds
from polyglotimportcsv.sources import SOURCE_COLUMN, SourceData


@dataclass
class EntityBinding:
    """An entity bound once, before any row is written: expanded cfg + column kinds.

    ``kinds`` are those the rows are cast to and filtered by: inferred from the whole
    file, except where a column declares a ``db_type`` (``casting.declared_kind``).
    ``cast_columns`` are the columns anything reads cast (``None``: every column).
    """

    cfg: Dict[str, Any]
    kinds: Dict[str, str]
    source_name: str
    cast_columns: Optional[FrozenSet[str]] = None


def _declared_kinds(ename: str, cfg: Dict[str, Any], kinds: Dict[str, str]) -> Dict[str, str]:
    """``kinds`` with the kind of every column that declares a ``db_type`` set by it.

    ``MappingError`` when one CSV column is mapped twice with declared types of
    different kinds: its rows are cast once, so they cannot be both.
    """
    columns = list(kinds)
    out = dict(kinds)
    chosen: Dict[str, str] = {}
    for _, field_key, spec in iter_leaf_columns(cfg):
        db_type = spec.get("db_type")
        col = resolve_csv_column(field_key, spec, columns)
        if not db_type or col not in kinds:
            continue
        kind = declared_kind(db_type, kinds[col])
        if chosen.setdefault(col, kind) != kind:
            raise MappingError(
                f"Entity '{ename}': CSV column '{col}' is mapped with db_types of different "
                f"kinds ({chosen[col]} and {kind}); its values can be cast to only one."
            )
        out[col] = kind
    return out


def _bind_from_source(
    ename: str,
    ecfg: Dict[str, Any],
    src: SourceData,
    source_name: str,
) -> EntityBinding:
    """Expand ``ename``'s columns against its resolved source ``src``."""
    cfg = dict(ecfg)
    cfg["columns"] = expand_entity_columns(ename, ecfg, src)
    cfg.pop("source", None)
    cfg.pop("csv_columns", None)
    cfg.pop("auto_map", None)
    return EntityBinding(
        cfg=cfg, kinds=_declared_kinds(ename, cfg, src.kinds), source_name=source_name
    )


def _key_leaves(cfg: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    return [(fk, spec) for _, fk, spec in iter_leaf_columns(cfg) if spec.get("is_key")]


def entity_cast_columns(
    binding: EntityBinding, relationships: Iterable[Tuple[Dict[str, Any], EntityBinding]] = ()
) -> FrozenSet[str]:
    """The columns of its source an entity needs cast.

    Its mapped columns, those of its filters, and its Cassandra partition and cluster
    columns. ``relationships`` are the ``(rspec, to_binding)`` of every relationship it
    is the ``from`` entity of: an edge is built from this entity's rows, so they also
    need the column holding the ``to`` key (named as the ``to`` entity names its key)
    and the edge's own columns.
    """
    columns = list(binding.kinds)
    leaves = [(fk, spec) for _, fk, spec in iter_leaf_columns(binding.cfg)]
    for rspec, to_binding in relationships:
        leaves += _key_leaves(to_binding.cfg) + list((rspec.get("columns") or {}).items())
    needed = {resolve_csv_column(fk, spec, columns) for fk, spec in leaves}
    needed.update(f["column"] for f in binding.cfg.get("filters") or [])
    needed.update(binding.cfg.get("cassandra_partition") or [])
    needed.update(binding.cfg.get("cassandra_cluster") or [])
    return frozenset(needed)


def set_cast_columns(dbms_cfg: Dict[str, Any], bindings: Dict[str, EntityBinding]) -> None:
    """Set ``cast_columns`` on every binding of one DBMS (``entity_cast_columns``)."""
    relationships = (dbms_cfg.get("relationships") or {}).values()
    for ename, binding in bindings.items():
        binding.cast_columns = entity_cast_columns(binding, [
            (rspec, bindings[rspec["to"]])
            for rspec in relationships
            if rspec.get("from") == ename and rspec.get("to") in bindings
        ])


def entity_source_names(ename: str, ecfg: Dict[str, Any]) -> List[str]:
    """Names of the sources an entity reads: its ``source`` (one name, or a union list),
    or the entity's own name when it declares none."""
    ref = ecfg.get("source")
    if ref is None:
        return [ename]
    return list(ref) if isinstance(ref, list) else [ref]


def _header_only(profile: SourceProfile) -> SourceData:
    """A ``SourceData`` with the profile's columns and whole-file kinds, and no rows."""
    kinds = dict(profile.kinds)
    kinds[SOURCE_COLUMN] = "string"
    frame = pd.DataFrame(columns=profile.header + [SOURCE_COLUMN])
    return SourceData(name=profile.name, df=frame, kinds=kinds, file_header=list(profile.header))


def bind_entity(
    ename: str, ecfg: Dict[str, Any], profiles: Dict[str, SourceProfile]
) -> EntityBinding:
    """Bind ``ename`` to the profiles of its sources, with the kinds of the whole files.

    The source is resolved by ``mapping_resolver.bind_entity_source`` over a registry
    holding each profile's header, so that rule lives in one place. A union's kinds
    are then those of its sources' stats merged (``union_kinds``) over the superset
    columns, in the order the resolver gave them.
    """
    names = entity_source_names(ename, ecfg)
    registry = {n: _header_only(profiles[n]) for n in names if n in profiles}
    src = bind_entity_source(ename, ecfg, registry)
    if isinstance(ecfg.get("source"), list):
        kinds = union_kinds([profiles[n] for n in names], src.file_header)
        kinds[SOURCE_COLUMN] = "string"
        src = replace(src, kinds=kinds)
    return _bind_from_source(ename, ecfg, src, "+".join(names))
