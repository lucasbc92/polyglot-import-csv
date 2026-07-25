"""Chunked reading of declared data sources (bounded-memory streaming counterpart to sources.py).

Mirrors sources.load_sources' semantics (multi per-entity CSVs; combined CSVs routed by an
origin column) but reads each file in fixed-size chunks via pandas ``chunksize`` instead of
materializing the whole file, so peak memory stays ~constant in file size.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple

import pandas as pd

from polyglotimportcsv.business_exception import SourceError
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
