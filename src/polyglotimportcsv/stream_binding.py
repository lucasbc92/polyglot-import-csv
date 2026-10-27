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

from polyglotimportcsv.csv_reader import infer_column_kinds
from polyglotimportcsv.mapping_resolver import bind_entity_source, expand_entity_columns
from polyglotimportcsv.source_profile import SourceProfile, union_kinds
from polyglotimportcsv.sources import SOURCE_COLUMN, SourceData


@dataclass
class EntityBinding:
    """An entity bound once, before any row is written: expanded cfg + inferred kinds."""

    cfg: Dict[str, Any]
    kinds: Dict[str, str]
    source_name: str


def _sample_source_data(name: str, sample_df: pd.DataFrame) -> SourceData:
    """Wrap a sample chunk as a ``SourceData`` (kinds inferred, ``_source`` -> string)."""
    data_cols = [c for c in sample_df.columns if c != SOURCE_COLUMN]
    kinds = infer_column_kinds(sample_df[data_cols])
    kinds[SOURCE_COLUMN] = "string"
    return SourceData(name=name, df=sample_df, kinds=kinds, file_header=data_cols)


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


def _bind_from_registry(
    ename: str,
    ecfg: Dict[str, Any],
    registry: Dict[str, SourceData],
    source_name: str,
) -> EntityBinding:
    """Resolve+expand ``ename`` against a sample ``SourceData`` registry.

    Delegates to ``mapping_resolver.bind_entity_source`` + ``expand_entity_columns``
    so the streaming bind is byte-for-byte the materialize bind, just over
    samples. ``bind_entity_source`` handles the single-source and union (list)
    cases identically to the materialize path.
    """
    src = bind_entity_source(ename, ecfg, registry)
    return _bind_from_source(ename, ecfg, src, source_name)


def bind_entity_from_sample(
    ename: str,
    ecfg: Dict[str, Any],
    sample_df: pd.DataFrame,
    source_name: str,
) -> EntityBinding:
    """Bind ``ename`` from a single source's sample chunk (materialize-path logic)."""
    sd = _sample_source_data(source_name, sample_df)
    return _bind_from_registry(ename, ecfg, {source_name: sd}, source_name)


def bind_union_entity_from_samples(
    ename: str,
    ecfg: Dict[str, Any],
    samples: Dict[str, pd.DataFrame],
) -> EntityBinding:
    """Bind a union (``source: [...]``) entity from one first-chunk sample per source.

    Builds a sample ``SourceData`` registry and delegates to the same
    ``bind_entity_source`` union path the materialize resolver uses, so the
    superset column order and inferred kinds match ``_union_source`` exactly --
    just computed over samples instead of full frames. ``samples`` must be keyed
    in union-list order (so ``_union_source`` sees the sources in the declared
    order). Returns a binding whose ``kinds`` keys are the superset data columns
    (in that order) followed by ``SOURCE_COLUMN``.
    """
    registry = {name: _sample_source_data(name, df) for name, df in samples.items()}
    source_name = "+".join(samples.keys())
    return _bind_from_registry(ename, ecfg, registry, source_name)


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
