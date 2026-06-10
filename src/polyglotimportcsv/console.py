"""Colored, verbose terminal output for Polyglot Import CSV."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, TextIO

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

_ANSI_ESCAPE = re.compile(r"\x1B\[[0-9;]*[a-zA-Z]")

_PALETTE: Dict[str, str] = {
    "reset": RESET,
    "bold": BOLD,
    "dim": DIM,
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    "gray": "\033[90m",
}

_BACKEND_STYLE: Dict[str, str] = {
    "postgres": "cyan",
    "mongodb": "green",
    "cassandra": "yellow",
    "redis": "red",
    "neo4j": "magenta",
}

_BACKEND_LINE = re.compile(r"^\[(\w+)\]\s*(.*)$", re.IGNORECASE)

_SESSION_LOG_PATH: Optional[Path] = None


def strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


class _TeeStream:
    """Write to terminal (with color) and log file (plain text)."""

    def __init__(self, stream: TextIO, log_file: TextIO) -> None:
        self._stream = stream
        self._log_file = log_file

    def write(self, data: str) -> int:
        self._stream.write(data)
        if data:
            self._log_file.write(strip_ansi(data))
        return len(data)

    def flush(self) -> None:
        self._stream.flush()
        self._log_file.flush()

    def isatty(self) -> bool:
        try:
            return self._stream.isatty()
        except Exception:
            return False

    def fileno(self) -> int:
        return self._stream.fileno()


def session_log_path() -> Optional[Path]:
    return _SESSION_LOG_PATH


def init_session_log(
    log_dir: str | Path = "logs",
    *,
    prefix: str = "polyglotimportcsv",
    log_file: str | Path | None = None,
) -> Optional[Path]:
    """
    Tee stdout/stderr to a timestamped file under ``log_dir``.

    Skipped when ``POLYGLOT_LOG_TEE=1`` (shell script already tees output).
    """
    global _SESSION_LOG_PATH

    if os.environ.get("POLYGLOT_LOG_TEE") == "1":
        env_path = os.environ.get("POLYGLOT_LOG_FILE")
        if env_path:
            _SESSION_LOG_PATH = Path(env_path)
        return _SESSION_LOG_PATH

    if os.environ.get("POLYGLOT_NO_LOG") == "1":
        return None

    if _SESSION_LOG_PATH is not None:
        return _SESSION_LOG_PATH

    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)

    if log_file is not None:
        path = Path(log_file)
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = directory / f"{prefix}_{stamp}.log"

    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a", encoding="utf-8")
    handle.write(f"\n--- session started {datetime.now().isoformat(timespec='seconds')} ---\n")
    handle.flush()

    sys.stdout = _TeeStream(sys.stdout, handle)  # type: ignore[assignment]
    sys.stderr = _TeeStream(sys.stderr, handle)  # type: ignore[assignment]
    _SESSION_LOG_PATH = path.resolve()
    os.environ["POLYGLOT_LOG_FILE"] = str(_SESSION_LOG_PATH)
    return _SESSION_LOG_PATH


def use_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def stylize(text: str, *styles: str) -> str:
    if not use_color() or not styles:
        return text
    prefix = "".join(_PALETTE.get(s, "") for s in styles)
    return f"{prefix}{text}{RESET}"


def _rule(char: str = "─", width: int = 72) -> str:
    return stylize(char * width, "dim")


def banner(title: str, *, subtitle: str = "") -> None:
    print()
    print(_rule("═"))
    print(stylize(f"  {title}", "bold", "cyan"))
    if subtitle:
        print(stylize(f"  {subtitle}", "dim"))
    print(_rule("═"))


def section(title: str) -> None:
    print()
    print(stylize(f"▸ {title}", "bold", "blue"))
    print(_rule())


def step(label: str, detail: str = "") -> None:
    arrow = stylize("→", "cyan")
    text = stylize(label, "bold")
    if detail:
        print(f"  {arrow} {text} {stylize(detail, 'dim')}")
    else:
        print(f"  {arrow} {text}")


def kv(key: str, value: Any) -> None:
    print(f"    {stylize(key + ':', 'dim')} {stylize(str(value), 'white')}")


def success(message: str) -> None:
    print(stylize(f"  ✓ {message}", "green"))


def warn(message: str) -> None:
    print(stylize(f"  ! {message}", "yellow"))


def error(message: str) -> None:
    print(stylize(f"  ✗ {message}", "red"), file=sys.stderr)


def note(message: str) -> None:
    print(stylize(f"    {message}", "dim"))


def empty_label() -> str:
    return stylize("(empty)", "dim")


def format_json_row(obj: Any) -> str:
    raw = json.dumps(obj, default=str, ensure_ascii=False)
    if not use_color():
        return raw
    # Light syntax highlighting for log readability.
    raw = re.sub(r'"([^"]+)":', lambda m: stylize(f'"{m.group(1)}"', "cyan") + ":", raw)
    raw = re.sub(
        r': "([^"]*)"',
        lambda m: ": " + stylize(f'"{m.group(1)}"', "green"),
        raw,
    )
    raw = re.sub(
        r": (\d+(?:\.\d+)?)([,}\]])",
        lambda m: ": " + stylize(m.group(1), "yellow") + m.group(2),
        raw,
    )
    return raw


def dump_rows(label: str, rows: Sequence[Dict[str, Any]]) -> None:
    count = len(rows)
    count_str = stylize(str(count), "bold", "yellow")
    print(f"  {stylize(label, 'bold')}: {count_str} row(s)")
    if not rows:
        print(f"    {empty_label()}")
        return
    for i, row in enumerate(rows, start=1):
        idx = stylize(f"[{i}]", "dim")
        print(f"    {idx} {format_json_row(row)}")


def color_backend_line(line: str) -> str:
    m = _BACKEND_LINE.match(line.strip())
    if not m:
        if line.startswith("  "):
            return stylize(line, "dim")
        return line
    backend, rest = m.group(1).lower(), m.group(2)
    style = _BACKEND_STYLE.get(backend, "white")
    tag = stylize(f"[{backend}]", "bold", style)
    if "dry-run" in rest or rest.startswith("would "):
        return f"{tag} {stylize(rest, 'yellow')}"
    if "inserted" in rest or "merged" in rest or "SET " in rest:
        return f"{tag} {stylize(rest, 'green')}"
    return f"{tag} {rest}"


class _ColoredFormatter(logging.Formatter):
    _LEVEL_STYLES = {
        logging.DEBUG: ("dim",),
        logging.INFO: (),
        logging.WARNING: ("yellow",),
        logging.ERROR: ("red", "bold"),
        logging.CRITICAL: ("red", "bold"),
    }

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.name.startswith("polyglotimportcsv") and message.startswith("["):
            message = color_backend_line(message)
        styles = self._LEVEL_STYLES.get(record.levelno, ())
        if styles and use_color():
            level = stylize(record.levelname.ljust(8), *styles)
        else:
            level = record.levelname.ljust(8)
        if record.levelno >= logging.WARNING:
            return f"{level} {message}"
        return message


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_ColoredFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    for noisy in ("cassandra", "cassandra.cluster", "neo4j", "neo4j.notifications"):
        logging.getLogger(noisy).setLevel(logging.ERROR)
