"""Chunked reading of declared data sources (bounded-memory streaming counterpart to sources.py).

Mirrors sources.load_sources' semantics (multi per-entity CSVs; combined CSVs routed by an
origin column) but reads each file in fixed-size chunks via pandas ``chunksize`` instead of
materializing the whole file, so peak memory stays ~constant in file size.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional, Tuple

import pandas as pd

from polyglotimportcsv.business_exception import ImportExecutionError, SourceError
from polyglotimportcsv.sources import SOURCE_COLUMN, _resolve_path

#: Read + inference-sample granularity (rows per chunk).
READ_CHUNK = 8192


def _read_chunks(path: Path, chunksize: int):
    """Same read options as csv_reader.read_csv, with chunksize for streaming."""
    return pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
        chunksize=chunksize,
    )


def iter_entity_chunks(
    sources_cfg: Dict[str, Any],
    base_dir: "str | Path",
    overrides: Optional[Dict[str, str]] = None,
    chunksize: int = READ_CHUNK,
) -> Iterator[Tuple[str, pd.DataFrame]]:
    """Yield ``(entity_name, chunk_df)`` pairs for every declared source, chunk by chunk.

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
        if isinstance(decl, str):
            path = _resolve_path(name, decl, base_dir, overrides)
            for chunk in _read_chunks(path, chunksize):
                chunk = chunk.copy()
                chunk[SOURCE_COLUMN] = name
                yield name, chunk
            continue

        # Combined file: column 0 is the origin column (spec §2.2).
        path = _resolve_path(name, decl["file"], base_dir, overrides)
        for chunk in _read_chunks(path, chunksize):
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
    ``ImportExecutionError`` if a requested name resolves to no source (for
    combined origins, only origins present in the combined file's first chunk
    are resolvable -- consistent with the streaming "kinds from first chunk"
    contract).
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

        # Combined file: sample its first chunk and route by origin. Homogeneous
        # columns mean any present origin gives the full column set.
        path = _resolve_path(name, decl["file"], base_dir, overrides)
        chunk = next(iter(_read_chunks(path, chunksize)), None)
        if chunk is None or len(chunk.columns) < 2:
            continue
        origin_col = chunk.columns[0]
        origins = chunk[origin_col].astype(str)
        data = chunk.drop(columns=[origin_col])
        for value, group in data.groupby(origins, sort=True):
            if str(value) not in wanted_set:
                continue
            sub = group.copy()
            sub[SOURCE_COLUMN] = str(value)
            samples[str(value)] = sub

    missing = [n for n in wanted if n not in samples]
    if missing:
        raise ImportExecutionError(
            "streaming union: no source provides " + ", ".join(repr(m) for m in missing)
            + " (for combined CSVs, the origin must appear in the file's first chunk)."
        )
    # Return in union-list order so the superset column order is deterministic.
    return {n: samples[n] for n in wanted}
