"""Bind entities to sources and expand effective column mappings (spec §2.3-§2.6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

from polyglotimportcsv.business_exception import MappingError
from polyglotimportcsv.casting import KIND_TO_DB_TYPE, cast_frame
from polyglotimportcsv.column_selector import select_columns
from polyglotimportcsv.csv_reader import infer_column_kinds
from polyglotimportcsv.sources import SOURCE_COLUMN, SourceData


@dataclass
class BoundEntity:
    """An entity bound to its source: expanded config + typed data frame."""

    name: str
    cfg: Dict[str, Any]       # entity cfg with expanded 'columns'
    df: pd.DataFrame          # cast source frame (data columns + _source)
    kinds: Dict[str, str]


def _union_source(
    entity_name: str, names: List[str], sources: Dict[str, SourceData]
) -> SourceData:
    parts: List[SourceData] = []
    for n in names:
        if n not in sources:
            raise MappingError(f"Entity '{entity_name}': unknown source '{n}'.")
        parts.append(sources[n])
    data_cols: List[str] = []
    for p in parts:
        for c in p.file_header:
            if c not in data_cols:
                data_cols.append(c)
    all_cols = data_cols + [SOURCE_COLUMN]
    frames = [p.df.reindex(columns=all_cols, fill_value="") for p in parts]
    df = pd.concat(frames, ignore_index=True)
    kinds = infer_column_kinds(df[data_cols])
    kinds[SOURCE_COLUMN] = "string"
    return SourceData(name="+".join(names), df=df, kinds=kinds, file_header=data_cols)


def bind_entity_source(
    entity_name: str, entity_cfg: Dict[str, Any], sources: Dict[str, SourceData]
) -> SourceData:
    """Resolve the entity's source: explicit name, list union, or key-name match."""
    ref = entity_cfg.get("source")
    if ref is None:
        if entity_name in sources:
            return sources[entity_name]
        raise MappingError(
            f"Entity '{entity_name}' declares no 'source' and no source is named after it."
        )
    if isinstance(ref, str):
        if ref not in sources:
            raise MappingError(f"Entity '{entity_name}': unknown source '{ref}'.")
        return sources[ref]
    if isinstance(ref, list):
        if not ref:
            raise MappingError(
                f"Entity '{entity_name}': 'source' list is empty; "
                "provide at least one source name."
            )
        return _union_source(entity_name, list(ref), sources)
    raise MappingError(
        f"Entity '{entity_name}': invalid 'source' value {ref!r} "
        f"(type {type(ref).__name__}); expected a string or a list of strings."
    )


def _binding_cache_key(entity_cfg: Dict[str, Any], entity_name: str) -> tuple:
    """Collision-proof cast-cache key for an already-validated binding.

    Must be called only after ``bind_entity_source`` has validated the
    binding, so ``ref`` here is guaranteed to be ``None``, a ``str``, or a
    non-empty ``list``. A plain "+".join(names) string key would collide
    between distinct union bindings (e.g. ["a+b", "c"] vs ["a", "b+c"]) and
    with a real source literally named after the join; keying on a typed
    tuple instead makes those cases distinguishable.
    """
    ref = entity_cfg.get("source")
    if ref is None:
        return ("single", entity_name)
    if isinstance(ref, str):
        return ("single", ref)
    return ("union", tuple(ref))


def expand_entity_columns(
    entity_name: str, entity_cfg: Dict[str, Any], source: SourceData
) -> Dict[str, Any]:
    """Effective columns: manual-only, full auto-map, or hybrid (spec §2.4)."""
    manual = entity_cfg.get("columns") or {}
    auto = bool(entity_cfg.get("auto_map")) or not manual
    if not auto:
        if entity_cfg.get("csv_columns"):
            raise MappingError(
                f"Entity '{entity_name}': 'csv_columns' requires auto-mapping "
                "(omit 'columns' or set \"auto_map\": true)."
            )
        return dict(manual)
    selection = entity_cfg.get("csv_columns")
    if selection:
        base_cols = select_columns(
            selection, source.file_header, context=f"entity '{entity_name}'"
        )
    else:
        base_cols = list(source.file_header)
    expanded: Dict[str, Any] = {}
    for col in base_cols:
        kind = source.kinds.get(col, "string")
        expanded[col] = {"db_type": KIND_TO_DB_TYPE.get(kind, "TEXT")}
    expanded.update(manual)
    return expanded


def resolve_backend_entities(
    backend_cfg: Dict[str, Any],
    sources: Dict[str, SourceData],
    cast_cache: Optional[Dict[tuple, pd.DataFrame]] = None,
) -> Dict[str, BoundEntity]:
    """Bind every entity of one backend and cast its frame to native values."""
    cast_cache = cast_cache if cast_cache is not None else {}
    out: Dict[str, BoundEntity] = {}
    for ename, ecfg in (backend_cfg.get("entities") or {}).items():
        src = bind_entity_source(ename, ecfg, sources)
        cfg = dict(ecfg)
        cfg["columns"] = expand_entity_columns(ename, ecfg, src)
        cfg.pop("source", None)
        cfg.pop("csv_columns", None)
        cfg.pop("auto_map", None)
        cache_key = _binding_cache_key(ecfg, ename)
        if cache_key not in cast_cache:
            cast_cache[cache_key] = cast_frame(src.df, src.kinds)
        out[ename] = BoundEntity(
            name=ename, cfg=cfg, df=cast_cache[cache_key], kinds=src.kinds
        )
    return out
