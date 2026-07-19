"""Rich-based terminal + session-file reporting (spec §4.1-§4.2).

Two independent destinations: the terminal respects the level given to
``setup_reporting`` (CLI --log-level, default INFO); the session file under
``logs/`` always records DEBUG as plain text without color. Module log
records flow through both via logging handlers; rich renderables (banners,
tables, row dumps) flow through both via ``print_rich``.
"""

from __future__ import annotations

import logging
import os
import re
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import IO, Any, Callable, Dict, Iterator, Optional, Sequence

from rich.console import Console
from rich.json import JSON
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

logger = logging.getLogger(__name__)

#: Entities with at most this many rows have their records dumped (spec §4.3).
DATA_DUMP_THRESHOLD = 50

_FILE_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

_console = Console(soft_wrap=True)
_terminal_level: int = logging.INFO
_file_console: Optional[Console] = None
_file_handle: Optional[IO[str]] = None
_session_log_path: Optional[Path] = None


def session_log_path() -> Optional[Path]:
    return _session_log_path


def reset() -> None:
    """Detach reporting handlers and close the session file (setup + tests)."""
    global _file_console, _file_handle, _session_log_path, _terminal_level
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_polyglot_reporting", False):
            root.removeHandler(handler)
            handler.close()
    if _file_handle is not None:
        _file_handle.close()
    _file_console = None
    _file_handle = None
    _session_log_path = None
    _terminal_level = logging.INFO


def _session_file_target(log_dir: str | Path, no_log: bool) -> Optional[Path]:
    if no_log or os.environ.get("POLYGLOT_NO_LOG") == "1":
        return None
    env_path = os.environ.get("POLYGLOT_DEBUG_LOG")
    if env_path:
        path = Path(env_path)
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = Path(log_dir) / f"polyglotimportcsv_{stamp}.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def setup_reporting(
    terminal_level: int = logging.INFO,
    *,
    log_dir: str | Path = "logs",
    no_log: bool = False,
) -> Optional[Path]:
    """Configure both destinations; return the session file path (or None)."""
    global _file_console, _file_handle, _session_log_path, _terminal_level
    reset()
    _terminal_level = terminal_level

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    terminal_handler = RichHandler(
        console=_console,
        level=terminal_level,
        show_time=False,
        show_path=False,
        markup=False,
        rich_tracebacks=False,
    )
    terminal_handler._polyglot_reporting = True  # type: ignore[attr-defined]
    root.addHandler(terminal_handler)

    path = _session_file_target(log_dir, no_log)
    if path is not None:
        _file_handle = path.open("a", encoding="utf-8")
        _file_handle.write(
            f"\n--- session started {datetime.now().isoformat(timespec='seconds')} ---\n"
        )
        _file_handle.flush()
        file_handler = logging.StreamHandler(_file_handle)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))
        file_handler._polyglot_reporting = True  # type: ignore[attr-defined]
        root.addHandler(file_handler)
        _file_console = Console(
            file=_file_handle, no_color=True, width=100, highlight=False, soft_wrap=True
        )
        _session_log_path = path.resolve()

    for noisy in ("cassandra", "cassandra.cluster", "cassandra.io", "neo4j", "neo4j.notifications"):
        logging.getLogger(noisy).setLevel(logging.ERROR)
    for chatty in ("pymongo", "urllib3", "asyncio"):
        logging.getLogger(chatty).setLevel(logging.WARNING)

    return _session_log_path


def print_rich(renderable: Any, *, level: int = logging.INFO) -> None:
    """Render to the terminal (subject to --log-level) and to the session file."""
    if level >= _terminal_level:
        _console.print(renderable)
    if _file_console is not None:
        _file_console.print(renderable)
        if _file_handle is not None:
            _file_handle.flush()


_BACKEND_STYLE: Dict[str, str] = {
    "postgres": "cyan",
    "mongodb": "green",
    "cassandra": "yellow",
    "redis": "red",
    "neo4j": "magenta",
}

_BACKEND_LINE = re.compile(r"^\[(\w+)\]\s*(.*)$", re.IGNORECASE)


def banner(title: str, *, subtitle: str = "") -> None:
    print_rich(Text(""))
    print_rich(Rule(style="dim"))
    print_rich(Text(f"  {title}", style="bold cyan"))
    if subtitle:
        print_rich(Text(f"  {subtitle}", style="dim"))
    print_rich(Rule(style="dim"))


def section(title: str) -> None:
    print_rich(Text(""))
    print_rich(Text(f"▸ {title}", style="bold blue"))
    print_rich(Rule(style="dim"))


def step(label: str, detail: str = "") -> None:
    line = Text("  → ", style="cyan")
    line.append(label, style="bold")
    if detail:
        line.append(f" {detail}", style="dim")
    print_rich(line)


def kv(key: str, value: Any) -> None:
    line = Text(f"    {key}: ", style="dim")
    line.append(str(value))
    print_rich(line)


def note(message: str) -> None:
    print_rich(Text(f"    {message}", style="dim"))


def success(message: str) -> None:
    print_rich(Text(f"  ✓ {message}", style="green"))


def warn(message: str) -> None:
    logger.warning(message)


def error(message: str) -> None:
    logger.error(message)


def empty_label() -> Text:
    return Text("(empty)", style="dim")


def format_json_row(obj: Any) -> Text:
    """One record as compact, syntax-highlighted JSON text (spec §4.3)."""
    return JSON.from_data(obj, indent=None, default=str).text


def dump_rows(label: str, rows: Sequence[Dict[str, Any]]) -> None:
    header = Text(f"  {label}: ")
    header.append(str(len(rows)), style="bold yellow")
    header.append(" row(s)")
    print_rich(header)
    if not rows:
        line = Text("    ")
        line.append_text(empty_label())
        print_rich(line)
        return
    for i, row in enumerate(rows, start=1):
        line = Text(f"    [{i}] ", style="dim")
        line.append_text(format_json_row(row))
        print_rich(line)


def dump_entity_frame(
    backend: str, entity: str, df: Any, *, force: Optional[bool] = None
) -> None:
    """Dump entity records up to DATA_DUMP_THRESHOLD rows; counts only above (spec §4.3)."""
    n = len(df)
    show = force if force is not None else n <= DATA_DUMP_THRESHOLD
    if not show:
        note(f"{backend} · {entity}: {n} row(s) (data dump suppressed; --show-data forces it)")
        logger.debug("%s · %s: data dump suppressed for %d row(s)", backend, entity, n)
        return
    dump_rows(f"{backend} · {entity}", df.to_dict(orient="records"))


def metrics_table(records: Sequence[Dict[str, Any]]) -> Table:
    """Summary table for the end of a run (spec §4.4)."""
    table = Table(title="Import metrics", header_style="bold")
    table.add_column("backend")
    table.add_column("entity")
    table.add_column("phase")
    table.add_column("rows", justify="right")
    table.add_column("seconds", justify="right")
    table.add_column("rows/s", justify="right")
    for rec in records:
        rate = rec.get("rows_per_second")
        table.add_row(
            str(rec.get("backend", "")),
            str(rec.get("entity", "")),
            str(rec.get("phase", "")),
            str(rec.get("rows", 0)),
            f"{float(rec.get('seconds', 0.0) or 0.0):.3f}",
            "-" if rate is None else f"{float(rate):.0f}",
        )
    return table


def backend_text(line: str) -> Text:
    """Style an importer log line ('[postgres] inserted ...') for the terminal."""
    m = _BACKEND_LINE.match(line.strip())
    if not m:
        if line.startswith("  "):
            return Text(line, style="dim")
        return Text(line)
    backend, rest = m.group(1).lower(), m.group(2)
    style = _BACKEND_STYLE.get(backend, "white")
    out = Text(f"[{backend}]", style=f"bold {style}")
    if "dry-run" in rest or rest.startswith("would "):
        out.append(f" {rest}", style="yellow")
    elif "inserted" in rest or "merged" in rest or "SET " in rest:
        out.append(f" {rest}", style="green")
    else:
        out.append(f" {rest}")
    return out


class _RowRateColumn(ProgressColumn):
    def render(self, task) -> Text:
        speed = task.finished_speed or task.speed
        if speed is None:
            return Text("- rows/s", style="progress.data.speed")
        return Text(f"{speed:.0f} rows/s", style="progress.data.speed")


@contextmanager
def entity_progress(description: str, total: int) -> Iterator[Callable[[int], None]]:
    """Live progress for entities above the dump threshold (spec §4.4).

    No-op (yields a do-nothing advance) when the entity is small enough to
    be dumped instead, or when stdout is not a terminal.
    """
    if total <= DATA_DUMP_THRESHOLD or not _console.is_terminal:
        yield lambda n=1: None
        return
    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        _RowRateColumn(),
        TimeElapsedColumn(),
        console=_console,
        transient=True,
    )
    with progress:
        task_id = progress.add_task(description, total=total)
        yield lambda n=1: progress.advance(task_id, n)
