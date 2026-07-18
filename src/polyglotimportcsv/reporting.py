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
from datetime import datetime
from pathlib import Path
from typing import IO, Any, Optional

from rich.console import Console
from rich.logging import RichHandler

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
