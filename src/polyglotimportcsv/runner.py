"""Orchestrate an import: header and DBMS checks, then the inference, validation and write reads."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, ContextManager, Dict, Iterable, Iterator, List, Optional, Set, Tuple

from rich import box
from rich.table import Table
from rich.text import Text

from polyglotimportcsv import casting, metrics
from polyglotimportcsv.business_exception import (
    ConfigError,
    DataValidationError,
    DbmsUnavailableError,
)
from polyglotimportcsv.config_parser import load_config, load_dbms_config, resolve_dbms_config_path
from polyglotimportcsv.data_preview import StreamDataPreview
from polyglotimportcsv.data_validation import print_validation_report, validate_data
from polyglotimportcsv.dbms_check import (
    DOWN,
    INVALID,
    UP,
    DbmsCheckReport,
    check_dbms,
    format_endpoint,
    not_ready_message,
)
from polyglotimportcsv.dbms_sink import SinkFactory
from polyglotimportcsv.import_plan import DEFAULT_BATCH_SIZE, ImportPlan, plan_import
from polyglotimportcsv.stream_binding import entity_source_names
from polyglotimportcsv.stream_runner import StreamCounts, run_stream_import
from polyglotimportcsv.reporting import (
    DEFAULT_SAMPLE_SIZE,
    backend_text,
    banner,
    kv,
    metrics_table,
    note,
    print_rich,
    step,
    success,
    warn,
)
from polyglotimportcsv.sinks import default_sink_factories
from polyglotimportcsv.stream_source import (
    DEFAULT_CHUNK_MB,
    check_source_overrides,
    read_source_headers,
)
from polyglotimportcsv.validation import BACKENDS, validate_headers

logger = logging.getLogger(__name__)


def _print_backend_line(line: str) -> None:
    out = Text("  ")
    out.append_text(backend_text(line))
    print_rich(out)


_STATE_STYLE = {UP: "green", DOWN: "red", INVALID: "red"}


def _dbms_targets(config: Dict, only: Optional[Iterable[str]]) -> List[str]:
    """The DBMS the import would write to: those configured, narrowed by --only."""
    only_set = {x.strip().lower() for x in only if x and str(x).strip()} if only else set()
    return [b for b in BACKENDS if b in config and (not only_set or b in only_set)]


def _no_target_dbms_message(config: Dict, only: Optional[Iterable[str]]) -> str:
    declared = [b for b in BACKENDS if b in config]
    msg = f"No target DBMS to check: the import configuration declares {', '.join(declared) or 'none'}"
    if only:
        selected = [str(x).strip() for x in only if x and str(x).strip()]
        msg += f"; --only selected {', '.join(selected)}"
    return msg + "."


def _print_command(line: str) -> None:
    # Never wrapped: a line break inside a command would be pasted along with it.
    print_rich(Text("      " + line, style="bold", no_wrap=True, overflow="ignore"))


def _print_dbms_check(report: DbmsCheckReport, dbms_config_path: Path) -> None:
    # box.SQUARE for the same reason as metrics_table: the GUI font lacks the
    # heavy box glyphs.
    table = Table(header_style="bold", box=box.SQUARE)
    table.add_column("DBMS")
    table.add_column("Endpoint")
    table.add_column("Status")
    for status in report.statuses:
        where = ", ".join(format_endpoint(e) for e in status.endpoints) or "—"
        table.add_row(status.dbms, where, Text(status.state, style=_STATE_STYLE[status.state]))
    print_rich(table)
    if report.fixes:
        note(f"Fix the connection settings in {dbms_config_path.name}:")
        for line in report.fixes:
            _print_command(line)
    if report.starts:
        note("To start the DBMS that are down, run in a terminal:")
        for line in report.starts:
            _print_command(line)
        if report.service_commands:
            note("Service commands (net start, systemctl) may need an administrator terminal or sudo.")


def _check_dbms_step(
    config_path: Path,
    dbms_config_path: Optional[str | Path],
    config: Dict,
    only: Optional[Iterable[str]],
) -> DbmsCheckReport:
    step("Check DBMS")
    path = resolve_dbms_config_path(config_path, dbms_config_path)
    report = check_dbms(_dbms_targets(config, only), load_dbms_config(path), path)
    _print_dbms_check(report, path)
    return report


def _require_dbms(
    config_path: Path,
    dbms_config_path: Optional[str | Path],
    config: Dict,
    only: Optional[Iterable[str]],
) -> None:
    """Stop before any data row is read when a target DBMS is not ready."""
    report = _check_dbms_step(config_path, dbms_config_path, config, only)
    if not report.ok:
        raise DbmsUnavailableError(not_ready_message(report))


def run_check(
    config_path: str | Path,
    *,
    dbms_config_path: Optional[str | Path] = None,
    only: Optional[Iterable[str]] = None,
) -> DbmsCheckReport:
    """Check the DBMS the import would use and return the report (CLI --check-dbms)."""
    config_path = Path(config_path)
    banner("Polyglot Import CSV", subtitle="mode: check")
    step("Load config", str(config_path))
    config = load_config(config_path, dbms_config_path)
    if not _dbms_targets(config, only):
        raise ConfigError(_no_target_dbms_message(config, only))
    report = _check_dbms_step(config_path, dbms_config_path, config, only)
    if report.ok:
        success("All target DBMS are up")
    return report


def _summary_lines(counts: StreamCounts) -> List[str]:
    """One ``[dbms] partition: N row(s)`` line per partition, relationships as ``:TYPE``."""
    return [
        f"[{dbms}] {partition}: {rows} row(s)"
        for dbms, written in counts.written.items()
        for partition, rows in sorted(written.items())
    ]


def _unused_origins(plan: ImportPlan) -> List[Tuple[str, int]]:
    """``(origin value, rows)`` of every origin of a combined file that no entity of the
    selected DBMS reads."""
    used = {
        name
        for dbms in plan.dbms_names
        for ename, ecfg in (plan.config[dbms].get("entities") or {}).items()
        for name in entity_source_names(ename, ecfg)
    }
    return [
        (name, profile.rows)
        for name, profile in plan.profiles.items()
        if not isinstance(plan.sources_cfg[profile.declared], str) and name not in used
    ]


class _CastWarnings:
    """Shows each cast warning (``casting.cast_frame``) once per column of a source.

    Every DBMS, entity and chunk casts the same rows again, so the validation read would
    log the same warning many times, with a different count in its text each time.
    ``once_per_column`` lets through the first warning of each ``(source, column)`` and
    drops the rest. The write casts the same rows as the validation read:
    ``without_repeats`` drops, there, the warnings of the pairs already shown, and only
    those. A warning with no source and column on its record always prints. Each filter
    stays on ``casting.logger`` only for its block.
    """

    def __init__(self) -> None:
        self._shown: Set[Tuple[Optional[str], str]] = set()

    @staticmethod
    def _key(record: logging.LogRecord) -> Optional[Tuple[Optional[str], str]]:
        column = getattr(record, "cast_column", None)
        if record.levelno < logging.WARNING or column is None:
            return None
        return getattr(record, "cast_source", None), column

    def _first(self, record: logging.LogRecord) -> bool:
        key = self._key(record)
        if key is None:
            return True
        if key in self._shown:
            return False
        self._shown.add(key)
        return True

    def _unseen(self, record: logging.LogRecord) -> bool:
        return self._key(record) not in self._shown

    @contextmanager
    def _filtered(self, check: Callable[[logging.LogRecord], bool]) -> Iterator[None]:
        casting.logger.addFilter(check)
        try:
            yield
        finally:
            casting.logger.removeFilter(check)

    def once_per_column(self) -> ContextManager[None]:
        """Log, inside the block, the first cast warning of each source column only."""
        return self._filtered(self._first)

    def without_repeats(self) -> ContextManager[None]:
        """Drop, inside the block, the cast warnings of the columns already shown."""
        return self._filtered(self._unseen)


def _print_summary(
    lines: List[str],
    collector: metrics.MetricsCollector,
    benchmark: bool,
    config_path: Path,
    plan: ImportPlan,
) -> None:
    for line in lines:
        _print_backend_line(line)
    print_rich(metrics_table(collector.to_records()))
    if benchmark:
        meta = metrics.environment_metadata(
            config_path, {name: profile.rows for name, profile in plan.profiles.items()}
        )
        json_path, csv_path = metrics.write_benchmark_files(collector, meta)
        kv("Benchmark JSON", json_path)
        kv("Benchmark CSV", csv_path)


def run_import(
    config_path: str | Path,
    *,
    dbms_config_path: Optional[str | Path] = None,
    dry_run: bool = False,
    create_schema: bool = True,
    only: Optional[Iterable[str]] = None,
    source_overrides: Optional[Dict[str, str]] = None,
    show_data: Optional[bool] = None,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    collector: Optional[metrics.MetricsCollector] = None,
    benchmark: bool = False,
    chunk_size_mb: float = DEFAULT_CHUNK_MB,
    batch_size: int = DEFAULT_BATCH_SIZE,
    sink_factories: Optional[Dict[str, SinkFactory]] = None,
) -> List[str]:
    """
    Check everything, then import, in three reads of the sources.

    Data comes from the config's ``sources`` block (one CSV per entity, or a
    combined CSV with the origin in column 0). ``source_overrides`` remaps a
    source name to another CSV path without editing the config (CLI --source).

    The headers are checked first, then the target DBMS (not in a dry-run). The
    inference read profiles every source the selected DBMS use, in read blocks of
    about ``chunk_size_mb``; the validation read checks every row the write would
    send, through the write's own engine. Any problem stops the run before anything
    is written. The write read streams one DBMS at a time through its sink, in
    batches of up to ``batch_size`` rows, and its counts are compared with those of
    the validation read. A dry-run stops after the validation read.

    ``show_data`` and ``sample_size`` choose the per-partition data display:
    ``True`` shows every row, ``False`` none, and ``None`` (the default) the
    first ``sample_size`` rows of each partition plus its total; ``benchmark``
    implies ``False``. Returns the summary lines, one per partition.
    """
    config_path = Path(config_path)
    banner("Polyglot Import CSV", subtitle=f"mode: {'dry-run' if dry_run else 'import'}")
    collector = collector if collector is not None else metrics.MetricsCollector()

    step("Load config", str(config_path))
    config = load_config(config_path, dbms_config_path)
    declared = [b for b in BACKENDS if b in config]
    note(f"{len(declared)} DBMS configured: {', '.join(declared)}")
    dbms_names = _dbms_targets(config, only)
    if not dbms_names:
        raise ConfigError(_no_target_dbms_message(config, only))

    step("Check sources")
    sources_cfg = config.get("sources") or {}
    check_source_overrides(sources_cfg, source_overrides)
    headers = read_source_headers(sources_cfg, config_path.parent, source_overrides)

    step("Validate mappings")
    combined = [name for name, decl in sources_cfg.items() if not isinstance(decl, str)]
    validate_headers(config, headers, combined, dbms_names)

    if not dry_run:
        _require_dbms(config_path, dbms_config_path, config, only)

    step("Infer types")
    start = time.perf_counter()
    plan = plan_import(
        config, config_path.parent, dbms_names=dbms_names, overrides=source_overrides,
        chunk_mb=chunk_size_mb, batch_size=batch_size,
    )
    rows = sum(profile.rows for profile in plan.profiles.values())
    collector.record("(sources)", "*", "infer", rows=rows, seconds=time.perf_counter() - start)

    step("Validate data")
    preview = StreamDataPreview(False if benchmark else show_data, sample_size)
    cast_warnings = _CastWarnings()
    start = time.perf_counter()
    with cast_warnings.once_per_column():
        report, expected = validate_data(plan, on_batch=preview.observe if dry_run else None)
    collector.record("(all)", "*", "validate", rows=rows, seconds=time.perf_counter() - start)
    if not report.ok():
        print_validation_report(report)
        raise DataValidationError(
            f"Data validation failed: {report.total()} problem(s) in "
            f"{len(report.groups())} group(s); nothing was written."
        )
    for dbms, entities in expected.entity_rows.items():
        for ename, n in entities.items():
            if n == 0:
                logger.warning("entity %s/%s bound to 0 row(s)", dbms, ename)
    for name, n in _unused_origins(plan):
        note(f"origin '{name}' ({n} row(s)) feeds no entity")

    if dry_run:
        preview.finish()
        lines = _summary_lines(expected)
        _print_summary(lines, collector, benchmark, config_path, plan)
        success("Finished dry-run — nothing was written")
        return lines

    step("Write")
    if create_schema:
        note("DDL will be created lazily per partition (--create-schema)")
    else:
        note("existing schema only (--no-create-schema)")
    with cast_warnings.without_repeats():
        counts = run_stream_import(
            plan,
            sink_factories=sink_factories or default_sink_factories(),
            create_schema=create_schema,
            on_batch=preview.observe,
            collector=collector,
        )
    preview.finish()
    # Validation and write run the same code over the same rows, so a difference is a
    # defect of the tool. What was written stays written: a warning, not a failure.
    for dbms in plan.dbms_names:
        validated, written = expected.written.get(dbms, {}), counts.written.get(dbms, {})
        for partition in sorted(validated.keys() | written.keys()):
            if validated.get(partition, 0) != written.get(partition, 0):
                warn(
                    f"{dbms} · {partition}: {written.get(partition, 0)} row(s) written, "
                    f"but the validation read counted {validated.get(partition, 0)}"
                )
    lines = _summary_lines(counts)
    _print_summary(lines, collector, benchmark, config_path, plan)
    success(f"Finished import — {len(lines)} partition(s) written")
    return lines
