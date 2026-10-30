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
from typing import Any, Callable, Dict, Iterable, Iterator, List, Mapping, Sequence

from polyglotimportcsv.csv_reader import ColumnStats
from polyglotimportcsv.mapping_resolver import union_data_cols
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
    unions: Iterable[Sequence[str]] = (),
) -> Dict[str, SourceProfile]:
    """Read every declared source once and profile it, by name or by origin value.

    A plain source gives one profile named after it, even without rows (its header
    still arrives, as one empty chunk). A combined source gives one per origin value
    seen, and none if the file has no rows. ``SourceError`` for a name used twice: an
    origin value equal to a declared source name, or the same origin in two files.

    Two kinds of column are then settled by one more read of the file holding them,
    limited to those columns, with their stats rebuilt from exact counts. A column the
    chunks left undecided (``ColumnStats.decided()``: they disagreed on whether it holds
    dates), so that its kind is that of ``infer_column_kinds`` over the whole column,
    whatever the chunk size. And a column of a union, which ``unions`` lists as names of
    profiles (an entity's ``source`` list): sources that are each decided can still be
    undecided together, and the union must have the kind of its concatenated column. A
    file is read again at most once, whatever number of columns and unions need it.
    """
    taken = set(sources_cfg)  # declared names and origin values must all be distinct
    by_file: Dict[str, Dict[str, SourceProfile]] = {}
    readers: Dict[str, Callable[..., Iterator]] = {}
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
        by_file[declared] = file_profiles
        readers[declared] = read
    profiles = {name: p for file_profiles in by_file.values() for name, p in file_profiles.items()}
    for declared, columns in _columns_to_settle(profiles, unions).items():
        _rebuild_exact(declared, columns, by_file[declared], readers[declared])
    return profiles


def _merged_stats(profiles: Sequence[SourceProfile], column: str) -> ColumnStats:
    """The stats of ``column`` over all the ``profiles`` that have it, merged as one."""
    return reduce(
        ColumnStats.merged,
        (p.stats[column] for p in profiles if column in p.stats),
        ColumnStats(),
    )


def _columns_to_settle(
    profiles: Dict[str, SourceProfile], unions: Iterable[Sequence[str]]
) -> Dict[str, List[str]]:
    """Declared source -> its data columns whose stats must be rebuilt with exact counts.

    A column is open in a file when any of its profiles has it undecided, or when it is
    in a union that has two or more sources with it and the merged stats are undecided
    (every file holding it is then read). Rebuilding to exact counts only narrows
    the bounds, so a column that was decided never becomes open by another one being
    settled. A name in ``unions`` with no profile is left for the caller to report.
    """
    open_columns: Dict[str, Dict[str, None]] = {}  # ordered sets
    for profile in profiles.values():
        for column in profile.header:
            if not profile.stats[column].decided():
                open_columns.setdefault(profile.declared, {})[column] = None
    for names in unions:
        parts = [profiles[n] for n in dict.fromkeys(names) if n in profiles]
        for column in union_data_cols([p.header for p in parts]):
            having = [p for p in parts if column in p.stats]
            if len(having) > 1 and not _merged_stats(having, column).decided():
                for profile in having:
                    open_columns.setdefault(profile.declared, {})[column] = None
    return {declared: list(columns) for declared, columns in open_columns.items()}


def _rebuild_exact(
    declared: str,
    columns: List[str],
    file_profiles: Dict[str, SourceProfile],
    read: Callable[..., Iterator],
) -> None:
    """Rebuild the stats of ``columns`` of one file's profiles from exact counts.

    ``read`` yields the chunks of the file (``iter_entity_chunks`` over it). The columns
    are read alone (plus the origin column of a combined file, which routes the rows) and
    rebuilt for every origin of the file. Everything else in the profiles stays as it was.
    """
    for profile in file_profiles.values():
        for column in columns:
            profile.stats[column] = ColumnStats()
    for name, chunk in read(only_columns={declared: columns}):
        for column in columns:
            file_profiles[name].stats[column].update(chunk[column], exact=True)


def union_kinds(profiles: Sequence[SourceProfile], columns: Sequence[str]) -> Dict[str, str]:
    """Kind of each of ``columns`` over all the ``profiles`` that have it.

    The stats of the profiles holding a column are merged and read as one, so a column
    that is an integer in one source and a float in another is a float. A column none of
    them has is ``"empty"``.
    """
    return {column: _merged_stats(profiles, column).kind() for column in columns}
