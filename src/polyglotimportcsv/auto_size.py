"""The automatic read-block size: what an import uses when ``--chunk-size`` is not given.

The exploratory campaign (``benchmarks/v4-explore``) showed that reading the largest
source whole is what makes a block fast, and that the peak grows with the block:
``peak ≈ base + PEAK_MB_PER_CHUNK_MB × block``, where the base grows with the size of
the sources on disk (fitted on ``benchmarks/v4-preview``). So the block is the one
that reads the largest source whole, unless the predicted peak would not fit in a
fixed share of the free memory; then it is the largest block that fits.

The coefficients come from one machine, the multi-source mode and single-repetition
peaks; ``FREE_MEMORY_FRACTION`` is a chosen margin, not a measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from polyglotimportcsv.import_plan import dbms_sources
from polyglotimportcsv.stream_source import (
    MAX_CHUNK_MB, MIN_CHUNK_MB, source_memory_mb, source_path,
)

#: Peak memory of an import, in MB: PEAK_BASE_MB + PEAK_BASE_PER_DISK_MB × MiB of
#: the sources on disk + PEAK_MB_PER_CHUNK_MB × block size in MB.
PEAK_BASE_MB = 22.2
PEAK_BASE_PER_DISK_MB = 2.31
PEAK_MB_PER_CHUNK_MB = 1.078

#: Share of the free memory the predicted peak may take.
FREE_MEMORY_FRACTION = 0.25


@dataclass(frozen=True)
class AutoChunk:
    """The chosen block size, in MB, and why it was chosen."""

    mb: int
    reason: str


def choose_chunk_mb(
    largest_source_mb: float, sources_disk_mb: float, free_mb: Optional[float]
) -> AutoChunk:
    """The block that reads the largest source whole, capped at ``MAX_CHUNK_MB`` and
    by the safety limit of the free memory, within ``[MIN_CHUNK_MB, MAX_CHUNK_MB]``.

    ``free_mb`` of ``None`` (unreadable) drops the safety limit.
    """
    candidates = [(largest_source_mb, "whole"), (float(MAX_CHUNK_MB), "max")]
    if free_mb is not None:
        base = PEAK_BASE_MB + PEAK_BASE_PER_DISK_MB * sources_disk_mb
        limit = (FREE_MEMORY_FRACTION * free_mb - base) / PEAK_MB_PER_CHUNK_MB
        candidates.append((limit, "limit"))
    # min() keeps the first of equal values, so a tie goes to reading the source whole.
    raw, binding = min(candidates, key=lambda c: c[0])
    if binding == "whole":
        core = f"auto: largest source read whole ({largest_source_mb:.1f} MB)"
    elif binding == "limit":
        core = "auto: limited by free memory"
    else:
        core = (
            f"auto: largest source ({largest_source_mb:.1f} MB) exceeds the "
            f"{MAX_CHUNK_MB} MB maximum"
        )
    if raw < MIN_CHUNK_MB:
        core += f" (raised to the {MIN_CHUNK_MB} MB minimum)"
    suffix = f"; {free_mb:.0f} MB free" if free_mb is not None else "; free memory unknown"
    mb = int(min(max(raw, MIN_CHUNK_MB), MAX_CHUNK_MB))
    return AutoChunk(mb, core + suffix)


def auto_chunk_mb(
    config: Dict[str, Any],
    base_dir: "str | Path",
    dbms_names: Sequence[str],
    overrides: Optional[Dict[str, str]],
    free_mb: Optional[float],
) -> AutoChunk:
    """``choose_chunk_mb`` for the sources the DBMS ``dbms_names`` read, at the paths
    the import will read (a ``--source`` override wins)."""
    paths = {
        name: source_path(name, decl, Path(base_dir), overrides or {})
        for name, decl in dbms_sources(config, dbms_names).items()
    }
    largest = max((source_memory_mb(n, p) for n, p in paths.items()), default=0.0)
    disk_mb = sum(p.stat().st_size for p in paths.values()) / 2**20
    return choose_chunk_mb(largest, disk_mb, free_mb)
