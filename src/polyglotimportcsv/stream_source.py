"""Chunked reading of declared data sources (bounded-memory streaming counterpart to sources.py).

Mirrors sources.load_sources' semantics (multi per-entity CSVs; combined CSVs routed by an
origin column) but reads each file in fixed-size chunks via pandas ``chunksize`` instead of
materializing the whole file, so peak memory stays ~constant in file size.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from polyglotimportcsv.business_exception import ImportExecutionError, SourceError
from polyglotimportcsv.sources import SOURCE_COLUMN, _resolve_path

#: Read + inference-sample granularity (rows per chunk).
READ_CHUNK = 8192

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


def _chunks(path: Path, size: int, usecols: Optional[List[str]]):
    """``_read_chunks``, naming ``usecols`` only when there are some, so the whole-file
    reads keep calling it with just ``(path, chunksize)``."""
    return _read_chunks(path, size) if usecols is None else _read_chunks(path, size, usecols)


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
    chunksize: int = READ_CHUNK,
    rows_per_chunk: Optional[Mapping[str, int]] = None,
    only_columns: Optional[Mapping[str, Sequence[str]]] = None,
) -> Iterator[Tuple[str, pd.DataFrame]]:
    """Yield ``(entity_name, chunk_df)`` pairs for every declared source, chunk by chunk.

    ``rows_per_chunk``, when given, maps every declared source to its rows per chunk and
    takes the place of ``chunksize``. ``only_columns`` maps a declared source to the data
    columns to read of it (the origin column of a combined file is always read too, to
    route the rows); a source it does not name is read whole.

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
        size = chunksize if rows_per_chunk is None else rows_per_chunk[name]
        columns = (only_columns or {}).get(name)
        if isinstance(decl, str):
            path = _resolve_path(name, decl, base_dir, overrides)
            for chunk in _chunks(path, size, None if columns is None else list(columns)):
                chunk = chunk.copy()
                chunk[SOURCE_COLUMN] = name
                yield name, chunk
            continue

        # Combined file: column 0 is the origin column (spec §2.2).
        path = _resolve_path(name, decl["file"], base_dir, overrides)
        usecols = None if columns is None else [_read_header(path)[0], *columns]
        for chunk in _chunks(path, size, usecols):
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


def sample_union_sources(
    sources_cfg: Dict[str, Any],
    base_dir: "str | Path",
    names: Iterable[str],
    overrides: Optional[Dict[str, str]] = None,
    chunksize: int = READ_CHUNK,
) -> Dict[str, pd.DataFrame]:
    """Read one first-chunk sample for each requested source name / origin value.

    Union entities need all their sources' columns known *before* the first
    chunk is processed (to widen every chunk to the shared superset). In multi
    mode sources are separate files read one at a time, so we cannot wait to see
    a chunk from each -- that would buffer whole files (O(rows)). Instead we
    eagerly read just the **first chunk** of each named source once, which is
    O(sources) and constant in total row count.

    ``names`` are the entries of a union ``source: [...]`` list: multi source
    names (keys of ``sources_cfg``) and/or combined-CSV origin values. Returns
    ``{name: sample_df}`` (data columns + trailing ``SOURCE_COLUMN``). Raises
    ``ImportExecutionError`` if a requested name resolves to no source.

    A combined CSV holds every origin in one file, and such files are routinely
    grouped by origin (the benchmark generator writes all stock rows, then
    purchase, ...), so an origin's first rows can sit far past the first chunk.
    Its chunks are therefore scanned until every requested origin has been
    sampled -- each origin still keeping only the one chunk-slice it first
    appeared in, so peak memory stays O(sources x chunk), constant in total rows.
    Scanning stops at the chunk that completes the set; only a genuinely absent
    origin (an error) costs a full pass over the file.
    """
    base_dir = Path(base_dir)
    overrides = overrides or {}
    wanted = list(dict.fromkeys(names))  # de-dupe, preserve union-list order
    wanted_set = set(wanted)
    samples: Dict[str, pd.DataFrame] = {}

    for name, decl in (sources_cfg or {}).items():
        if isinstance(decl, str):
            if name not in wanted_set:
                continue
            path = _resolve_path(name, decl, base_dir, overrides)
            chunk = next(iter(_read_chunks(path, chunksize)), None)
            if chunk is None:
                chunk = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
            chunk = chunk.copy()
            chunk[SOURCE_COLUMN] = name
            samples[name] = chunk
            continue

        # Combined file: route chunks by origin, keeping the first slice seen for
        # each wanted origin, until they are all sampled (see the docstring).
        path = _resolve_path(name, decl["file"], base_dir, overrides)
        for chunk in _read_chunks(path, chunksize):
            if len(chunk.columns) < 2:
                break
            origin_col = chunk.columns[0]
            origins = chunk[origin_col].astype(str)
            data = chunk.drop(columns=[origin_col])
            for value, group in data.groupby(origins, sort=True):
                value = str(value)
                if value not in wanted_set or value in samples:
                    continue
                sub = group.copy()
                sub[SOURCE_COLUMN] = value
                samples[value] = sub
            if wanted_set <= samples.keys():
                break
        if wanted_set <= samples.keys():
            break

    missing = [n for n in wanted if n not in samples]
    if missing:
        raise ImportExecutionError(
            "streaming union: no source provides " + ", ".join(repr(m) for m in missing)
            + " (no declared source name, nor any origin value in a combined CSV, matches)."
        )
    # Return in union-list order so the superset column order is deterministic.
    return {n: samples[n] for n in wanted}
