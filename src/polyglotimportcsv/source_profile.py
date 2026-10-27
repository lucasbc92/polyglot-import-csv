"""Whole-file type profile of every declared source, from one chunked read of each.

Binding and validation need to know what a column holds, and a first-chunk sample can
miss a value that only turns up far into the file. A profile folds the raw text of every
chunk into per-column ``ColumnStats`` instead, so its kinds are those of the entire file
in bounded memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial, reduce
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Mapping, Sequence

from polyglotimportcsv.csv_reader import ColumnStats
from polyglotimportcsv.sources import SOURCE_COLUMN, check_name_is_free
from polyglotimportcsv.stream_source import iter_entity_chunks, source_path


@dataclass
class SourceProfile:
    """What one source (a plain file, or one origin of a combined file) holds."""

    name: str       # the declared source name, or the origin value of a combined file
    declared: str   # the declared source whose file holds it
    path: Path
    header: List[str]  # data columns only: the origin column of a combined file is left out
    rows: int = 0
    stats: Dict[str, ColumnStats] = field(default_factory=dict)

    @property
    def kinds(self) -> Dict[str, str]:
        """Kind of every data column, in header order."""
        return {column: self.stats[column].kind() for column in self.header}


def profile_sources(
    sources_cfg: Dict[str, Any],
    base_dir: "str | Path",
    overrides: Dict[str, str],
    rows_per_chunk: Mapping[str, int],
) -> Dict[str, SourceProfile]:
    """Read every declared source once and profile it, by name or by origin value.

    A plain source gives one profile named after it, even without rows (its header
    still arrives, as one empty chunk). A combined source gives one per origin value
    seen, and none if the file has no rows. ``SourceError`` for a name used twice: an
    origin value equal to a declared source name, or the same origin in two files.

    A column the chunks left undecided (``ColumnStats.decided()``: they disagreed on
    whether it holds dates) is settled by one more read of that file, limited to those
    columns. Its stats are rebuilt there with exact counts, so the kind of every column
    is that of ``infer_column_kinds`` over the whole column, whatever the chunk size.
    """
    taken = set(sources_cfg)  # declared names and origin values must all be distinct
    profiles: Dict[str, SourceProfile] = {}
    for declared, decl in sources_cfg.items():
        path = source_path(declared, decl, base_dir, overrides)
        combined = not isinstance(decl, str)
        read = partial(
            iter_entity_chunks, {declared: decl}, base_dir, overrides,
            rows_per_chunk=rows_per_chunk,
        )
        file_profiles: Dict[str, SourceProfile] = {}
        for name, chunk in read():
            profile = file_profiles.get(name)
            if profile is None:
                if combined:
                    check_name_is_free(taken, name)
                    taken.add(name)
                header = [c for c in chunk.columns if c != SOURCE_COLUMN]
                profile = SourceProfile(
                    name=name, declared=declared, path=path, header=header,
                    stats={c: ColumnStats() for c in header},
                )
                file_profiles[name] = profile
            profile.rows += len(chunk)
            for column in profile.header:
                profile.stats[column].update(chunk[column])
        _settle_undecided(declared, file_profiles, read)
        profiles.update(file_profiles)
    return profiles


def _settle_undecided(
    declared: str, file_profiles: Dict[str, SourceProfile], read: Callable[..., Iterator]
) -> None:
    """Rebuild, with exact counts, the stats of the columns of one file left undecided.

    ``read`` yields the chunks of the file (``iter_entity_chunks`` over it). A column is
    open if it is so for any origin of the file; it is then rebuilt for all of them from
    a read of that column alone (plus the origin column, which routes the rows).
    Everything else in the profiles stays as it was.
    """
    if not file_profiles:
        return
    header = next(iter(file_profiles.values())).header  # every origin shares it
    open_columns = [
        c for c in header if not all(p.stats[c].decided() for p in file_profiles.values())
    ]
    if not open_columns:
        return
    for profile in file_profiles.values():
        for column in open_columns:
            profile.stats[column] = ColumnStats()
    for name, chunk in read(only_columns={declared: open_columns}):
        for column in open_columns:
            file_profiles[name].stats[column].update(chunk[column], exact=True)


def union_kinds(profiles: Sequence[SourceProfile], columns: Sequence[str]) -> Dict[str, str]:
    """Kind of each of ``columns`` over all the ``profiles`` that have it.

    The stats of the profiles holding a column are merged and read as one, so a column
    that is an integer in one source and a float in another is a float. A column none of
    them has is ``"empty"``.
    """
    return {
        column: reduce(
            ColumnStats.merged,
            (p.stats[column] for p in profiles if column in p.stats),
            ColumnStats(),
        ).kind()
        for column in columns
    }
