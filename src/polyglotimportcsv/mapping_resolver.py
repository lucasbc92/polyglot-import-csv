"""Bind entities to sources and expand effective column mappings (spec §2.3-§2.6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import pandas as pd

from polyglotimportcsv.business_exception import MappingError
from polyglotimportcsv.casting import KIND_TO_DB_TYPE
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


def union_data_cols(headers: List[List[str]]) -> List[str]:
    """First-seen union of column names across ``headers``, in list order.

    The single source of truth for the union superset ordering rule, shared by
    ``_union_source``, ``source_profile`` and ``validation`` so all compute an
    identical superset.
    """
    data_cols: List[str] = []
    for header in headers:
        for c in header:
            if c not in data_cols:
                data_cols.append(c)
    return data_cols


def _merge_union_kinds(
    parts: List[SourceData], data_cols: List[str], df: pd.DataFrame
) -> Dict[str, str]:
    """Kinds for a union without re-inferring what the parts already agree on.

    Inference is the dominant cost of a large import, and running it again on the
    concatenated frame repeats work already done once per source. Where the parts
    carrying a column agree, inferring on the concatenation cannot reach a different
    answer, so theirs stands; only genuinely disputed columns are re-inferred.

    A part that lacks the column contributes the ``""`` filled in by ``reindex``,
    and one whose values are all blank is ``empty`` — inference drops both, so
    neither can outvote a part that actually has values.
    """
    kinds: Dict[str, str] = {}
    disputed: List[str] = []
    for col in data_cols:
        seen = {p.kinds[col] for p in parts if col in p.kinds}
        seen.discard("empty")
        if not seen:
            kinds[col] = "empty"
        elif len(seen) == 1:
            kinds[col] = seen.pop()
        else:
            disputed.append(col)
    if disputed:
        kinds.update(infer_column_kinds(df[disputed]))
    return kinds


def _union_source(
    entity_name: str, names: List[str], sources: Dict[str, SourceData]
) -> SourceData:
    parts: List[SourceData] = []
    for n in names:
        if n not in sources:
            raise MappingError(f"Entity '{entity_name}': unknown source '{n}'.")
        parts.append(sources[n])
    data_cols = union_data_cols([p.file_header for p in parts])
    all_cols = data_cols + [SOURCE_COLUMN]
    frames = [p.df.reindex(columns=all_cols, fill_value="") for p in parts]
    df = pd.concat(frames, ignore_index=True)
    kinds = _merge_union_kinds(parts, data_cols, df)
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
