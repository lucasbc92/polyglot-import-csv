"""Orchestrate source loading, entity resolution, validation, and per-backend import."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd
from rich.text import Text

from polyglotimportcsv.config_parser import load_config
from polyglotimportcsv.importers import default_importer_registry
from polyglotimportcsv.importers.base import ImporterRegistry
from polyglotimportcsv.mapping_resolver import resolve_backend_entities
from polyglotimportcsv.reporting import (
    backend_text,
    banner,
    dump_entity_frame,
    note,
    print_rich,
    section,
    step,
    success,
)
from polyglotimportcsv.sources import load_sources
from polyglotimportcsv.validation import BACKENDS, validate_backend_entities

logger = logging.getLogger(__name__)


def _print_backend_line(line: str) -> None:
    out = Text("  ")
    out.append_text(backend_text(line))
    print_rich(out)


def run_import(
    config_path: str | Path,
    *,
    sgbd_config_path: Optional[str | Path] = None,
    dry_run: bool = False,
    create_schema: bool = True,
    only: Optional[Iterable[str]] = None,
    importers: Optional[ImporterRegistry] = None,
    source_overrides: Optional[Dict[str, str]] = None,
    show_data: Optional[bool] = None,
) -> List[str]:
    """
    Load config and sources, bind entities, validate, then run configured backends.

    Data comes from the config's ``sources`` block (one CSV per entity, or a
    combined CSV with the origin in column 0). ``source_overrides`` remaps a
    source name to another CSV path without editing the config (CLI --source).
    """
    config_path = Path(config_path)

    mode = "dry-run" if dry_run else "import"
    banner("Polyglot Import CSV", subtitle=f"mode: {mode}")

    step("Load config", str(config_path))
    config = load_config(config_path, sgbd_config_path)
    backends_in_cfg = [b for b in BACKENDS if b in config]
    note(f"{len(backends_in_cfg)} backend(s) configured: {', '.join(backends_in_cfg)}")

    step("Load sources")
    sources = load_sources(
        config.get("sources") or {}, config_path.parent, overrides=source_overrides
    )
    for name in sorted(sources):
        sd = sources[name]
        note(f"source {name}: {len(sd.df)} row(s), {len(sd.file_header)} data column(s)")

    registry = importers or default_importer_registry()

    only_set: Optional[Set[str]] = None
    if only is not None:
        only_set = {x.strip().lower() for x in only if x and str(x).strip()}
        note(f"filter: only {', '.join(sorted(only_set))}")

    if dry_run:
        note("no database connections will be opened")
    elif create_schema:
        note("DDL will be created where applicable (--create-schema)")
    else:
        note("existing schema only (--no-create-schema)")

    cast_cache: Dict[Tuple[str, object], pd.DataFrame] = {}
    log_lines: List[str] = []
    for backend in BACKENDS:
        if backend not in config:
            continue
        if only_set and backend not in only_set:
            continue
        fn = registry.get(backend)
        if fn is None:
            continue
        section(f"Backend · {backend}")
        bcfg = config[backend]
        bound = resolve_backend_entities(bcfg, sources, cast_cache)
        validate_backend_entities(backend, bcfg, bound)
        for ename, be in bound.items():
            dump_entity_frame(backend, ename, be.df, force=show_data)
        backend_lines = fn(bcfg, bound, dry_run=dry_run, create_schema=create_schema)
        log_lines.extend(backend_lines)
        for line in backend_lines:
            _print_backend_line(line)

    success(f"Finished {mode} — {len(log_lines)} log line(s) from importer(s)")
    return log_lines
