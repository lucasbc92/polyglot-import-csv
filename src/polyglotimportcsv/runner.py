"""Orchestrate source loading, entity resolution, validation, and per-backend import."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd
from rich.text import Text

from polyglotimportcsv import metrics
from polyglotimportcsv.config_parser import load_config
from polyglotimportcsv.importers import default_importer_registry
from polyglotimportcsv.importers.base import ImporterRegistry
from polyglotimportcsv.mapping_resolver import resolve_backend_entities
from polyglotimportcsv.reporting import (
    backend_text,
    banner,
    dump_entity_frame,
    kv,
    metrics_table,
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
    collector: Optional[metrics.MetricsCollector] = None,
    benchmark: bool = False,
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

    collector = collector if collector is not None else metrics.MetricsCollector()
    metrics.set_current(collector)
    try:
        return _run(
            config_path,
            sgbd_config_path=sgbd_config_path,
            dry_run=dry_run,
            create_schema=create_schema,
            only=only,
            importers=importers,
            source_overrides=source_overrides,
            show_data=False if benchmark else show_data,
            collector=collector,
            benchmark=benchmark,
        )
    finally:
        metrics.set_current(None)


def _run(
    config_path: Path,
    *,
    sgbd_config_path: Optional[str | Path],
    dry_run: bool,
    create_schema: bool,
    only: Optional[Iterable[str]],
    importers: Optional[ImporterRegistry],
    source_overrides: Optional[Dict[str, str]],
    show_data: Optional[bool],
    collector: metrics.MetricsCollector,
    benchmark: bool,
) -> List[str]:
    mode = "dry-run" if dry_run else "import"
    step("Load config", str(config_path))
    config = load_config(config_path, sgbd_config_path)
    backends_in_cfg = [b for b in BACKENDS if b in config]
    note(f"{len(backends_in_cfg)} backend(s) configured: {', '.join(backends_in_cfg)}")

    step("Load sources")
    read_start = time.perf_counter()
    sources = load_sources(
        config.get("sources") or {}, config_path.parent, overrides=source_overrides
    )
    collector.record(
        "(sources)",
        "*",
        "read",
        rows=sum(len(sd.df) for sd in sources.values()),
        seconds=time.perf_counter() - read_start,
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
        with collector.timed(backend, "*", "map") as t:
            bound = resolve_backend_entities(bcfg, sources, cast_cache)
            t.rows = sum(len(be.df) for be in bound.values())
        validate_backend_entities(backend, bcfg, bound)
        for ename, be in bound.items():
            if len(be.df) == 0:
                logger.warning("entity %s/%s bound to 0 row(s)", backend, ename)
            dump_entity_frame(backend, ename, be.df, force=show_data)
        backend_lines = fn(bcfg, bound, dry_run=dry_run, create_schema=create_schema)
        log_lines.extend(backend_lines)
        for line in backend_lines:
            _print_backend_line(line)

    if collector.entries():
        print_rich(metrics_table(collector.to_records()))
    if benchmark:
        meta = metrics.environment_metadata(
            config_path, {n: len(sd.df) for n, sd in sources.items()}
        )
        json_path, csv_path = metrics.write_benchmark_files(collector, meta)
        kv("Benchmark JSON", json_path)
        kv("Benchmark CSV", csv_path)
    success(f"Finished {mode} — {len(log_lines)} log line(s) from importer(s)")
    return log_lines
