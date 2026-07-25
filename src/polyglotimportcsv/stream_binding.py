"""Bind a streamed entity from its first chunk (spec: streaming import, Task 2).

Reuses the existing binding/inference pieces from ``mapping_resolver`` and
``csv_reader`` so the streaming path binds each entity exactly the way
``resolve_backend_entities`` does for the materialize path, just without a
pre-loaded ``SourceData`` registry: the sample chunk itself stands in for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import pandas as pd

from polyglotimportcsv.csv_reader import infer_column_kinds
from polyglotimportcsv.mapping_resolver import bind_entity_source, expand_entity_columns
from polyglotimportcsv.sources import SOURCE_COLUMN, SourceData


@dataclass
class EntityBinding:
    """An entity bound once from its first chunk: expanded cfg + inferred kinds."""

    cfg: Dict[str, Any]
    kinds: Dict[str, str]
    source_name: str


def bind_entity_from_sample(
    ename: str,
    ecfg: Dict[str, Any],
    sample_df: pd.DataFrame,
    source_name: str,
) -> EntityBinding:
    """Bind ``ename`` from a sample chunk, reusing the materialize-path binding logic."""
    data_cols = [c for c in sample_df.columns if c != SOURCE_COLUMN]
    kinds = infer_column_kinds(sample_df[data_cols])
    kinds[SOURCE_COLUMN] = "string"
    sd = SourceData(name=source_name, df=sample_df, kinds=kinds, file_header=data_cols)

    src = bind_entity_source(ename, ecfg, {source_name: sd})
    cfg = dict(ecfg)
    cfg["columns"] = expand_entity_columns(ename, ecfg, src)
    cfg.pop("source", None)
    cfg.pop("csv_columns", None)
    cfg.pop("auto_map", None)

    return EntityBinding(cfg=cfg, kinds=src.kinds, source_name=source_name)
