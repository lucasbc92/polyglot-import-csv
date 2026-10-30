"""Named data sources: the shape of a bound source, name checks and file resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Container, Dict, List

import pandas as pd

from polyglotimportcsv.business_exception import SourceError

#: Pseudo-column carrying each row's origin (source name or origin value).
SOURCE_COLUMN = "_source"


@dataclass
class SourceData:
    name: str
    df: pd.DataFrame          # data columns + trailing SOURCE_COLUMN (raw strings)
    kinds: Dict[str, str]     # per data column, plus SOURCE_COLUMN -> "string"
    file_header: List[str]    # data columns only: the 1-based index space


def check_name_is_free(taken: Container[str], name: str) -> None:
    """Raise ``SourceError`` when ``name`` is already used by another source."""
    if name in taken:
        raise SourceError(
            f"Source name collision: '{name}' is defined more than once "
            "(declared source names and origin values must all be distinct)."
        )


def _resolve_path(
    name: str, declared: str, base_dir: Path, overrides: Dict[str, str]
) -> Path:
    override = overrides.get(name)
    if override is not None:
        # Overrides are supplied at run time (--source NAME=PATH), so relative
        # paths follow the current working directory, not the config's folder.
        path = Path(override)
    else:
        path = Path(declared)
        if not path.is_absolute():
            path = base_dir / path
    if not path.is_file():
        raise SourceError(f"Source '{name}': CSV file not found: {path}")
    return path
