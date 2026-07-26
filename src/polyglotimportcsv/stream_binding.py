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


def _sample_source_data(name: str, sample_df: pd.DataFrame) -> SourceData:
    """Wrap a sample chunk as a ``SourceData`` (kinds inferred, ``_source`` -> string)."""
    data_cols = [c for c in sample_df.columns if c != SOURCE_COLUMN]
    kinds = infer_column_kinds(sample_df[data_cols])
    kinds[SOURCE_COLUMN] = "string"
    return SourceData(name=name, df=sample_df, kinds=kinds, file_header=data_cols)


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
    cfg = dict(ecfg)
    cfg["columns"] = expand_entity_columns(ename, ecfg, src)
    cfg.pop("source", None)
    cfg.pop("csv_columns", None)
    cfg.pop("auto_map", None)
    return EntityBinding(cfg=cfg, kinds=src.kinds, source_name=source_name)


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
