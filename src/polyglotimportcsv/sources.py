"""Load named data sources: per-entity CSV files and combined CSVs with origin column."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from polyglotimportcsv.business_exception import SourceError
from polyglotimportcsv.csv_reader import infer_column_kinds, read_csv

logger = logging.getLogger(__name__)

#: Pseudo-column carrying each row's origin (source name or origin value).
SOURCE_COLUMN = "_source"


@dataclass
class SourceData:
    name: str
    df: pd.DataFrame          # data columns + trailing SOURCE_COLUMN (raw strings)
    kinds: Dict[str, str]     # per data column, plus SOURCE_COLUMN -> "string"
    file_header: List[str]    # data columns only: the 1-based index space


def _register(
    registry: Dict[str, SourceData],
    name: str,
    df: pd.DataFrame,
    file_header: List[str],
) -> None:
    if name in registry:
        raise SourceError(
            f"Source name collision: '{name}' is defined more than once "
            "(declared source names and origin values must all be distinct)."
        )
    kinds = infer_column_kinds(df[file_header])
    kinds[SOURCE_COLUMN] = "string"
    logger.debug("source %s: inferred kinds: %s", name, {c: kinds[c] for c in file_header})
    if len(df) == 0:
        logger.warning("source %s has 0 row(s)", name)
    registry[name] = SourceData(name=name, df=df, kinds=kinds, file_header=file_header)


def _resolve_path(
    name: str, declared: str, base_dir: Path, overrides: Dict[str, str]
) -> Path:
    path = Path(overrides.get(name, declared))
    if not path.is_absolute():
        path = base_dir / path
    if not path.is_file():
        raise SourceError(f"Source '{name}': CSV file not found: {path}")
    return path


def load_sources(
    sources_cfg: Dict[str, Any],
    base_dir: Path,
    overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, SourceData]:
    """Read every declared source once; combined files also register per-origin slices."""
    registry: Dict[str, SourceData] = {}
    overrides = overrides or {}
    base_dir = Path(base_dir)

    unknown = set(overrides) - set(sources_cfg or {})
    if unknown:
        raise SourceError(
            f"--source override name(s) not declared in config: {', '.join(sorted(unknown))}. "
            f"Declared source names: {', '.join(sorted(sources_cfg or {})) or '(none)'}. "
            "Only names declared in the config's 'sources' block can be overridden "
            "(origin-derived slice names of a combined CSV are not overridable)."
        )

    for name, decl in (sources_cfg or {}).items():
        if isinstance(decl, str):
            path = _resolve_path(name, decl, base_dir, overrides)
            df = read_csv(path)
            header = list(df.columns)
            df = df.copy()
            df[SOURCE_COLUMN] = name
            _register(registry, name, df, header)
            continue

        # Combined file: column 0 is the origin column (spec §2.2).
        path = _resolve_path(name, decl["file"], base_dir, overrides)
        raw = read_csv(path)
        if len(raw.columns) < 2:
            raise SourceError(
                f"Source '{name}': combined CSV needs an origin column plus data columns: {path}"
            )
        origin_col = raw.columns[0]
        origins = raw[origin_col].astype(str)
        if (origins.str.strip() == "").any():
            raise SourceError(
                f"Source '{name}': combined CSV has row(s) with empty origin value (column '{origin_col}')."
            )
        data = raw.drop(columns=[origin_col])
        header = list(data.columns)
        data = data.copy()
        data[SOURCE_COLUMN] = origins
        _register(registry, name, data, header)
        for value, group in data.groupby(origins, sort=True):
            _register(registry, str(value), group.reset_index(drop=True), header)

    return registry
