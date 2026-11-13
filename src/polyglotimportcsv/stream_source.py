"""Chunked reading of declared data sources (per-entity CSVs; combined CSVs routed by an
origin column).

Each file is read in chunks via pandas ``chunksize``, so the memory a read holds is
bounded by the read block, not by the file. The block is chosen per run, and the default
(``auto_size``) reads the largest source whole when that fits the memory budget; the
peak of an import then follows the block (``auto_size``: about ``PEAK_BASE_MB`` +
``PEAK_BASE_PER_DISK_MB`` × MiB of sources on disk + ``PEAK_MB_PER_CHUNK_MB`` × block).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from polyglotimportcsv.business_exception import SourceError
from polyglotimportcsv.sources import SOURCE_COLUMN, resolve_path

#: Size of a read block, in MB: the default and the bounds a user may choose within.
MIN_CHUNK_MB = 16
MAX_CHUNK_MB = MIN_CHUNK_MB*16
DEFAULT_CHUNK_MB = MIN_CHUNK_MB*8


#: Rows read from the start of a file to measure how wide its rows are.
PROBE_ROWS = 1000

#: Read options of csv_reader.read_csv, shared by every read in this module.
_READ_OPTIONS = {"dtype": str, "keep_default_na": False, "encoding": "utf-8-sig"}


def _unreadable(name: str, path: Path, exc: Exception) -> SourceError:
    """The ``SourceError`` of a file pandas cannot parse; its own error would reach the
    CLI as a traceback."""
    if isinstance(exc, pd.errors.EmptyDataError):
        return SourceError(f"Source '{name}': CSV file is empty (no header row): {path}")
    if isinstance(exc, UnicodeDecodeError):
        return SourceError(f"Source '{name}': CSV file is not valid UTF-8: {path} ({exc})")
    return SourceError(f"Source '{name}': malformed CSV: {path} ({exc})")


_READ_ERRORS = (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError)


def _read_csv(name: str, path: Path, **options: Any):
    """``pd.read_csv`` of source ``name`` with the read options of this module.

    A file pandas cannot read is a ``SourceError``: one with no header row at all (zero
    bytes, or only blank lines), which pandas reports when the read starts, also for a
    chunked read; a row with more fields than the header; bytes that are not UTF-8.
    """
    try:
        return pd.read_csv(path, **options, **_READ_OPTIONS)
    except _READ_ERRORS as e:
        raise _unreadable(name, path, e) from e


def _read_chunks(
    name: str, path: Path, chunksize: int, usecols: Optional[List[str]] = None
) -> Iterator[pd.DataFrame]:
    """The file in chunks of ``chunksize`` rows, read with this module's options.

    ``usecols`` limits the read to those columns, which skips building the others. A
    malformed row is only met when its chunk is read, so the same ``SourceError`` as
    ``_read_csv`` is raised from there.
    """
    try:
        yield from _read_csv(name, path, chunksize=chunksize, usecols=usecols)
    except _READ_ERRORS as e:
        raise _unreadable(name, path, e) from e


def _read_header(name: str, path: Path) -> List[str]:
    """The file's column names, origin column included, from a read of zero rows."""
    return [str(c) for c in _read_csv(name, path, nrows=0).columns]


def chunk_rows(name: str, path: Path, chunk_mb: float) -> int:
    """Rows per read block of source ``name`` so that one block takes about ``chunk_mb``
    of memory.

    The width of a row is measured on the first ``PROBE_ROWS`` rows, read as strings
    like every other read here, so the budget is approximate: a file whose rows grow
    wider further down will exceed it. A file without rows gives ``1``.
    """
    probe = _read_csv(name, path, nrows=PROBE_ROWS)
    if len(probe) == 0:
        return 1
    bytes_per_row = probe.memory_usage(deep=True, index=False).sum() / len(probe)
    return max(1, int(chunk_mb * 2**20 // bytes_per_row))


def source_memory_mb(name: str, path: Path) -> float:
    """MB of memory to hold source ``name`` whole, read as strings like every read here.

    Estimated without reading the file a second time: its size on disk times the
    ratio between the memory and the disk bytes of its first ``PROBE_ROWS`` rows
    (the same probe as ``chunk_rows``). Approximate in the same way: a file whose rows
    change width further down is misjudged. A file without rows gives ``0.0``.
    """
    probe = _read_csv(name, path, nrows=PROBE_ROWS)
    if len(probe) == 0:
        return 0.0
    with open(path, "rb") as fh:
        next(fh)  # header
        disk_bytes = sum(len(line) for _, line in zip(range(len(probe)), fh))
    memory_bytes = probe.memory_usage(deep=True, index=False).sum()
    return path.stat().st_size * memory_bytes / disk_bytes / 2**20


def source_file(
    name: str, decl: "str | Dict[str, Any]", base_dir: "str | Path", overrides: Dict[str, str]
) -> Path:
    """The CSV file a declared source reads (a ``--source`` override wins); it need not
    exist.

    ``decl`` is the source's declaration in the config: the file name of a plain
    source, or the ``{"file": ...}`` entry of a combined one.
    """
    file = decl if isinstance(decl, str) else decl["file"]
    return resolve_path(name, file, Path(base_dir), overrides)


def source_path(
    name: str, decl: "str | Dict[str, Any]", base_dir: "str | Path", overrides: Dict[str, str]
) -> Path:
    """``source_file``, for a file that must exist: ``SourceError`` when it does not."""
    path = source_file(name, decl, base_dir, overrides)
    if not path.is_file():
        raise SourceError(f"Source '{name}': CSV file not found: {path}")
    return path


def combined_data_columns(name: str, header: List[str], path: Path) -> List[str]:
    """The data columns of a combined source whose file has ``header``: every column but
    the origin column, which comes first. ``SourceError`` when no data column is left."""
    if len(header) < 2:
        raise SourceError(
            f"Source '{name}': combined CSV needs an origin column plus data columns: {path}"
        )
    return header[1:]


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
    ``SourceError`` for a missing or empty file and for a combined file with fewer
    than two columns.
    """
    base_dir = Path(base_dir)
    overrides = overrides or {}
    headers: Dict[str, List[str]] = {}
    for name, decl in (sources_cfg or {}).items():
        path = source_path(name, decl, base_dir, overrides)
        header = _read_header(name, path)
        headers[name] = header if isinstance(decl, str) else combined_data_columns(name, header, path)
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
            path = source_path(name, decl, base_dir, overrides)
            for chunk in _read_chunks(name, path, size, None if columns is None else list(columns)):
                yield name, chunk.assign(**{SOURCE_COLUMN: name})
            continue

        # Combined file: column 0 is the origin column (spec §2.2).
        path = source_path(name, decl, base_dir, overrides)
        usecols = None if columns is None else [_read_header(name, path)[0], *columns]
        for chunk in _read_chunks(name, path, size, usecols):
            data_columns = combined_data_columns(name, list(chunk.columns), path)
            origin_col = chunk.columns[0]
            origins = chunk[origin_col].astype(str)
            empty = (origins.str.strip() == "").to_numpy()
            if empty.any():
                first = int(chunk.index[empty][0]) + 2  # the header is line 1
                raise SourceError(
                    f"Source '{name}': combined CSV has row(s) with empty origin value "
                    f"(column '{origin_col}'); the first is at {path}:{first}."
                )
            data = chunk[data_columns]
            for value, group in data.groupby(origins, sort=True):
                yield str(value), group.assign(**{SOURCE_COLUMN: str(value)})
