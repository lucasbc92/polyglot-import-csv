"""Bind a streamed entity from the profiles of its sources (spec: streaming import).

Reuses the existing binding pieces from ``mapping_resolver`` so the streaming path
binds each entity exactly the way ``resolve_backend_entities`` does for the
materialize path, just without a pre-loaded ``SourceData`` registry: a header-only
registry built from the source profiles stands in for it, and the kinds are those of
the whole file.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, List

import pandas as pd

from polyglotimportcsv.mapping_resolver import bind_entity_source, expand_entity_columns
from polyglotimportcsv.source_profile import SourceProfile, union_kinds
from polyglotimportcsv.sources import SOURCE_COLUMN, SourceData


@dataclass
class EntityBinding:
    """An entity bound once, before any row is written: expanded cfg + inferred kinds."""

    cfg: Dict[str, Any]
    kinds: Dict[str, str]
    source_name: str


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
    return EntityBinding(cfg=cfg, kinds=src.kinds, source_name=source_name)


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
    columns, which the resolver ordered as the materialize path does.
    """
    names = entity_source_names(ename, ecfg)
    registry = {n: _header_only(profiles[n]) for n in names if n in profiles}
    src = bind_entity_source(ename, ecfg, registry)
    if isinstance(ecfg.get("source"), list):
        kinds = union_kinds([profiles[n] for n in names], src.file_header)
        kinds[SOURCE_COLUMN] = "string"
        src = replace(src, kinds=kinds)
    return _bind_from_source(ename, ecfg, src, "+".join(names))
