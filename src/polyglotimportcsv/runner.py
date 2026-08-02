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
from polyglotimportcsv.dbms_sink import SinkFactory
from polyglotimportcsv.importers import default_importer_registry
from polyglotimportcsv.importers.base import ImporterRegistry
from polyglotimportcsv.mapping_resolver import resolve_backend_entities
from polyglotimportcsv.stream_runner import run_stream_import
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
from polyglotimportcsv.sinks import default_sink_factories
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
    strategy: str = "optimized",
    execution: str = "stream",
    sink_factories: Optional[Dict[str, SinkFactory]] = None,
) -> List[str]:
    """
    Load config and sources, bind entities, validate, then run configured backends.

    Data comes from the config's ``sources`` block (one CSV per entity, or a
    combined CSV with the origin in column 0). ``source_overrides`` remaps a
    source name to another CSV path without editing the config (CLI --source).

    ``execution`` selects the write path. ``stream`` (default) streams each
    source in bounded memory through a ``DbmsSink`` per DBMS; ``materialize``
    reproduces the full-materialization phase baseline unchanged. A dry-run or
    a ``--benchmark`` phase capture always uses the materialize path: dry-run
    plans without connecting, and the per-phase benchmark metrics only the
    materialize importers record.
    """
    if execution not in ("stream", "materialize"):
        raise ValueError(
            f"unknown execution: {execution!r}. Valid: stream, materialize"
        )

    config_path = Path(config_path)
    use_stream = execution == "stream" and not dry_run and not benchmark

    mode = "dry-run" if dry_run else "import"
    subtitle = f"mode: {mode}" if not use_stream else f"mode: {mode} · execution: stream"
    banner("Polyglot Import CSV", subtitle=subtitle)

    collector = collector if collector is not None else metrics.MetricsCollector()
    prev_collector = metrics.current()
    metrics.set_current(collector)
    try:
        if use_stream:
            return _run_stream(
                config_path,
                sgbd_config_path=sgbd_config_path,
                create_schema=create_schema,
                only=only,
                source_overrides=source_overrides,
                sink_factories=sink_factories or default_sink_factories(),
                collector=collector,
                strategy=strategy,
            )
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
            strategy=strategy,
        )
    finally:
        metrics.set_current(prev_collector)


def _run_stream(
    config_path: Path,
    *,
    sgbd_config_path: Optional[str | Path],
    create_schema: bool,
    only: Optional[Iterable[str]],
    source_overrides: Optional[Dict[str, str]],
    sink_factories: Dict[str, SinkFactory],
    collector: metrics.MetricsCollector,
    strategy: str,
) -> List[str]:
    """Bounded-memory streaming path: hand the loaded config to ``run_stream_import``."""
    step("Load config", str(config_path))
    config = load_config(config_path, sgbd_config_path)
    backends_in_cfg = [b for b in BACKENDS if b in config]
    note(f"{len(backends_in_cfg)} backend(s) configured: {', '.join(backends_in_cfg)}")

    if strategy == "naive":
        note("streaming always uses the optimized (vectorized/batched) path; "
             "--strategy naive is ignored under --execution stream")

    if create_schema:
        note("DDL will be created lazily per partition (--create-schema)")
    else:
        note("existing schema only (--no-create-schema)")

    write_start = time.perf_counter()
    written = run_stream_import(
        config,
        config_path.parent,
        sink_factories=sink_factories,
        only=only,
        create_schema=create_schema,
        source_overrides=source_overrides,
    )
    # One summary metric for the whole streaming import. Streaming is
    # DBMS-agnostic and does not break into read/map/filter/write phases the
    # way the materialize importers do, so record a single aggregate row; it
    # also gives the benchmark a carrier for the per-import peak_memory_mb.
    collector.record(
        "(stream)", "*", "write",
        rows=sum(written.values()),
        seconds=time.perf_counter() - write_start,
    )
    log_lines = [f"[stream] {part}: {rows} row(s)" for part, rows in sorted(written.items())]
    for line in log_lines:
        _print_backend_line(line)
    success(f"Finished import (stream) — {len(log_lines)} partition(s) written")
    return log_lines


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
    strategy: str,
) -> List[str]:
    mode = "dry-run" if dry_run else "import"
    step("Load config", str(config_path))
    config = load_config(config_path, sgbd_config_path)
    backends_in_cfg = [b for b in BACKENDS if b in config]
    note(f"{len(backends_in_cfg)} backend(s) configured: {', '.join(backends_in_cfg)}")

    step("Load sources")
    read_start = time.perf_counter()
    sources_cfg = config.get("sources") or {}
    sources = load_sources(sources_cfg, config_path.parent, overrides=source_overrides)
    collector.record(
        "(sources)",
        "*",
        "read",
        # A combined CSV registers one slice per origin value on top of the whole
        # file. Those slices are views over rows already counted under the declared
        # source, so only declared sources count: summing the whole registry would
        # report twice the rows actually read.
        rows=sum(len(sources[name].df) for name in sources_cfg if name in sources),
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
            bound = resolve_backend_entities(bcfg, sources, cast_cache, strategy=strategy)
            t.rows = sum(len(be.df) for be in bound.values())
        validate_backend_entities(backend, bcfg, bound)
        for ename, be in bound.items():
            if len(be.df) == 0:
                logger.warning("entity %s/%s bound to 0 row(s)", backend, ename)
            dump_entity_frame(backend, ename, be.df, force=show_data)
        backend_lines = fn(bcfg, bound, dry_run=dry_run,
                           create_schema=create_schema, strategy=strategy)
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
