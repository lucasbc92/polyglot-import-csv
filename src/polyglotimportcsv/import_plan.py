"""The import plan: everything the first read of the files decides before any write.

``plan_import`` reads only the sources the selected DBMS use, sizes the read blocks of
each from a memory budget, profiles every source over its whole file (so a column's
type is that of all its values, not of a sample), and binds each entity from those
profiles. Validation and the write then both run on the plan, with the same bindings.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from polyglotimportcsv.business_exception import MappingError
from polyglotimportcsv.source_profile import SourceProfile, profile_sources
from polyglotimportcsv.stream_binding import EntityBinding, bind_entity, entity_source_names
from polyglotimportcsv.stream_source import DEFAULT_CHUNK_MB, chunk_rows, source_path

#: Rows per write batch: the default and the bounds a user may choose within.
DEFAULT_BATCH_SIZE = 1024
MIN_BATCH_SIZE = 1024
MAX_BATCH_SIZE = 8192


@dataclass
class ImportPlan:
    """What an import reads, how it is cut, and how each entity is bound."""

    config: Dict[str, Any]
    base_dir: Path
    overrides: Dict[str, str]
    dbms_names: List[str]
    batch_size: int
    sources_cfg: Dict[str, Any]           # only the declared sources the plan reads
    rows_per_chunk: Dict[str, int]        # declared source -> rows per read block
    profiles: Dict[str, SourceProfile]    # source name or origin value -> profile
    bindings: Dict[str, Dict[str, EntityBinding]]  # DBMS -> entity -> binding

    def entity_batch(self, dbms: str, ename: str) -> int:
        """Rows per write batch of an entity: ``batch_size``, but never more than the
        rows of one read block of any of its sources."""
        ecfg = self.config[dbms]["entities"][ename]
        return min(
            self.batch_size,
            min(
                self.rows_per_chunk[self.profiles[n].declared]
                for n in entity_source_names(ename, ecfg)
            ),
        )


def _needed_sources(config: Dict[str, Any], dbms_names: Sequence[str]) -> Dict[str, Any]:
    """The declared sources the entities of ``dbms_names`` read.

    A name that is a plain declared source selects that source. Any other name is an
    origin value of a combined file, which could be any of them, so it selects them all.
    """
    declared = config.get("sources") or {}
    names = {
        n
        for dbms in dbms_names
        for ename, ecfg in (config[dbms].get("entities") or {}).items()
        for n in entity_source_names(ename, ecfg)
    }
    plain = {n for n in names if isinstance(declared.get(n), str)}
    wants_combined = bool(names - plain)
    return {
        name: decl
        for name, decl in declared.items()
        if name in plain or (wants_combined and not isinstance(decl, str))
    }


def plan_import(
    config: Dict[str, Any],
    base_dir: "str | Path",
    *,
    dbms_names: Sequence[str],
    overrides: Optional[Dict[str, str]] = None,
    chunk_mb: float = DEFAULT_CHUNK_MB,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> ImportPlan:
    """Read the sources ``dbms_names`` use once and bind their entities.

    ``chunk_mb`` is the memory budget of one read block of each source; it fixes the
    rows per block. Raises ``SourceError`` for a missing file or a name used twice, and
    ``MappingError`` for an entity whose source is neither a declared source nor an
    origin value found in the files, or that does not bind.
    """
    base_dir = Path(base_dir)
    overrides = dict(overrides or {})
    sources_cfg = _needed_sources(config, dbms_names)
    rows_per_chunk = {
        name: chunk_rows(source_path(name, decl, base_dir, overrides), chunk_mb)
        for name, decl in sources_cfg.items()
    }
    profiles = profile_sources(sources_cfg, base_dir, overrides, rows_per_chunk)
    for dbms in dbms_names:
        for ename, ecfg in (config[dbms].get("entities") or {}).items():
            for name in entity_source_names(ename, ecfg):
                if name not in profiles:
                    raise MappingError(
                        f"Entity '{ename}' ({dbms}): no source or origin value named '{name}' "
                        f"(found: {', '.join(sorted(profiles)) or 'none'})."
                    )
    bindings = {
        dbms: {
            ename: bind_entity(ename, ecfg, profiles)
            for ename, ecfg in (config[dbms].get("entities") or {}).items()
        }
        for dbms in dbms_names
    }
    return ImportPlan(
        config=config, base_dir=base_dir, overrides=overrides, dbms_names=list(dbms_names),
        batch_size=batch_size, sources_cfg=sources_cfg, rows_per_chunk=rows_per_chunk,
        profiles=profiles, bindings=bindings,
    )
