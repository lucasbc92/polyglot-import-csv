"""Chunked reading of declared data sources (bounded-memory streaming counterpart to sources.py).

Mirrors sources.load_sources' semantics (multi per-entity CSVs; combined CSVs routed by an
origin column) but reads each file in fixed-size chunks via pandas ``chunksize`` instead of
materializing the whole file, so peak memory stays ~constant in file size.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from polyglotimportcsv.business_exception import SourceError
from polyglotimportcsv.sources import SOURCE_COLUMN, _resolve_path

#: Size of a read block, in MB: the default and the bounds a user may choose within.
DEFAULT_CHUNK_MB = 8
MIN_CHUNK_MB = 8
MAX_CHUNK_MB = 256

#: Rows read from the start of a file to measure how wide its rows are.
PROBE_ROWS = 1000

#: Read options of csv_reader.read_csv, shared by every read in this module.
_READ_OPTIONS = {"dtype": str, "keep_default_na": False, "encoding": "utf-8-sig"}


def _read_chunks(path: Path, chunksize: int, usecols: Optional[List[str]] = None):
    """Same read options as csv_reader.read_csv, with chunksize for streaming.

    ``usecols`` limits the read to those columns, which skips building the others.
    """
    return pd.read_csv(path, chunksize=chunksize, usecols=usecols, **_READ_OPTIONS)


def _read_header(path: Path) -> List[str]:
    """The file's column names, origin column included, from a read of zero rows."""
    return [str(c) for c in pd.read_csv(path, nrows=0, **_READ_OPTIONS).columns]


def chunk_rows(path: Path, chunk_mb: float) -> int:
    """Rows per read block so that one block takes about ``chunk_mb`` of memory.

    The width of a row is measured on the first ``PROBE_ROWS`` rows, read as strings
    like every other read here, so the budget is approximate: a file whose rows grow
    wider further down will exceed it. A file without rows gives ``1``.
    """
    probe = pd.read_csv(path, nrows=PROBE_ROWS, **_READ_OPTIONS)
    if len(probe) == 0:
        return 1
    bytes_per_row = probe.memory_usage(deep=True, index=False).sum() / len(probe)
    return max(1, int(chunk_mb * 2**20 // bytes_per_row))


def source_path(
    name: str, decl: "str | Dict[str, Any]", base_dir: "str | Path", overrides: Dict[str, str]
) -> Path:
    """The CSV file a declared source reads (a ``--source`` override wins).

    ``decl`` is the source's declaration in the config: the file name of a plain
    source, or the ``{"file": ...}`` entry of a combined one. Raises ``SourceError``
    when the file does not exist.
    """
    file = decl if isinstance(decl, str) else decl["file"]
    return _resolve_path(name, file, Path(base_dir), overrides)


def check_source_overrides(
    sources_cfg: Dict[str, Any], overrides: Optional[Dict[str, str]]
) -> None:
    """Raise ``SourceError`` for a ``--source`` name the config does not declare."""
    unknown = set(overrides or {}) - set(sources_cfg or {})
    if unknown:
        raise SourceError(
            f"--source override name(s) not declared in config: {', '.join(sorted(unknown))}. "
            f"Declared source names: {', '.join(sorted(sources_cfg or {})) or '(none)'}. "
            "Only names declared in the config's 'sources' block can be overridden "
            "(origin-derived slice names of a combined CSV are not overridable)."
        )


def read_source_headers(
    sources_cfg: Dict[str, Any],
    base_dir: "str | Path",
    overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, List[str]]:
    """Read only the header row of every declared source.

    Returns ``{source_name: data_columns}``. For a combined source the origin
    column (column 0) is left out, as in ``iter_entity_chunks``. Raises
    ``SourceError`` for a missing file and for a combined file with fewer than
    two columns.
    """
    base_dir = Path(base_dir)
    overrides = overrides or {}
    headers: Dict[str, List[str]] = {}
    for name, decl in (sources_cfg or {}).items():
        combined = not isinstance(decl, str)
        path = source_path(name, decl, base_dir, overrides)
        header = _read_header(path)
        if combined:
            if len(header) < 2:
                raise SourceError(
                    f"Source '{name}': combined CSV needs an origin column plus data columns: {path}"
                )
            header = header[1:]
        headers[name] = header
    return headers


def iter_entity_chunks(
    sources_cfg: Dict[str, Any],
    base_dir: "str | Path",
    overrides: Optional[Dict[str, str]] = None,
    *,
    rows_per_chunk: Mapping[str, int],
    only_columns: Optional[Mapping[str, Sequence[str]]] = None,
) -> Iterator[Tuple[str, pd.DataFrame]]:
    """Yield ``(entity_name, chunk_df)`` pairs for every declared source, chunk by chunk.

    ``rows_per_chunk`` maps every declared source to its rows per chunk. ``only_columns``
    maps a declared source to the data columns to read of it (the origin column of a
    combined file is always read too, to route the rows); a source it does not name is
    read whole. Every chunk keeps the pandas index of its rows: the position of each data
    row in its file (the header is not one), counted across chunks and origins.

    Multi sources (``{"name": "file.csv"}``): each chunk of the file is yielded once, with a
    trailing ``SOURCE_COLUMN`` set to the source name.

    Combined sources (``{"name": {"file": "file.csv"}}``): column 0 is the origin column. Each
    chunk's rows are routed by origin value into per-origin sub-frames (origin column dropped,
    trailing ``SOURCE_COLUMN`` set to the origin value); one yield per distinct origin present
    in that chunk.
    """
    base_dir = Path(base_dir)
    overrides = overrides or {}
    for name, decl in (sources_cfg or {}).items():
        size = rows_per_chunk[name]
        columns = (only_columns or {}).get(name)
        if isinstance(decl, str):
            path = _resolve_path(name, decl, base_dir, overrides)
            for chunk in _read_chunks(path, size, None if columns is None else list(columns)):
                chunk = chunk.copy()
                chunk[SOURCE_COLUMN] = name
                yield name, chunk
            continue

        # Combined file: column 0 is the origin column (spec §2.2).
        path = _resolve_path(name, decl["file"], base_dir, overrides)
        usecols = None if columns is None else [_read_header(path)[0], *columns]
        for chunk in _read_chunks(path, size, usecols):
            if len(chunk.columns) < 2:
                raise SourceError(
                    f"Source '{name}': combined CSV needs an origin column plus data columns: {path}"
                )
            origin_col = chunk.columns[0]
            origins = chunk[origin_col].astype(str)
            if (origins.str.strip() == "").any():
                raise SourceError(
                    f"Source '{name}': combined CSV has row(s) with empty origin value "
                    f"(column '{origin_col}')."
                )
            data = chunk.drop(columns=[origin_col])
            for value, group in data.groupby(origins, sort=True):
                sub = group.copy()
                sub[SOURCE_COLUMN] = str(value)
                yield str(value), sub
