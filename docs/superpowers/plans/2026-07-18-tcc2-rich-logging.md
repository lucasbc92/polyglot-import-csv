# TCC2 Rich Logging & Metrics Implementation Plan (Plano 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hand-rolled ANSI console layer with a `rich`-based logging/reporting stack: leveled terminal output (`--log-level`), an always-DEBUG plain-text session file, a 50-row data-dump threshold with `--show-data`/`--no-data`, live progress bars, an always-on `MetricsCollector`, and `--benchmark` output files (spec §4 + CLI additions from §3.1 of `docs/superpowers/specs/2026-07-08-tcc2-import-modes-design.md`).

**Architecture:** A new `reporting.py` module owns two output channels: (1) Python `logging` with a `RichHandler` on the terminal (filtered by `--log-level`) plus a plain-text `StreamHandler` on the session file (always DEBUG), and (2) a `print_rich()` helper that renders rich renderables (banners, JSON row dumps, tables, progress) to the terminal console and, in parallel, to a no-color file console sharing the same file handle. A new `metrics.py` holds `MetricsCollector` plus a module-level "current collector" so importers keep their frozen signature `(backend_cfg, entities, *, dry_run, create_schema) -> List[str]` and record phases via `metrics.timed_phase(...)` no-op-safe helpers. `console.py` is deleted; `cli.py`, `runner.py`, and `scripts/inspect_persisted_data.py` migrate to `reporting.py`.

**Tech Stack:** Python >= 3.9, `rich` (new dependency), `click`, `pandas`, `pytest`.

## Global Constraints

- Data-dump threshold is exactly **50 rows** per entity (spec §4.3): at or below → records dumped as highlighted JSON at INFO; above → counts only. `--show-data` / `--no-data` force either way. `--benchmark` never dumps data.
- Terminal default level is **INFO**; `--log-level` accepts DEBUG/INFO/WARNING/ERROR (spec §4.2). The session file under `logs/` always records **DEBUG**, plain text, no color, and replaces the Python-side stdout tee (`_TeeStream` dies with `console.py`).
- `--benchmark` writes `benchmarks/benchmark_<timestamp>.json` plus a consolidatable CSV (`benchmarks/benchmark_history.csv`) with environment metadata: Python version, platform, config path, per-source row counts (spec §4.4).
- Progress bars appear only for entities **above** the dump threshold and only when stdout is a terminal (spec §4.4).
- DEBUG logs statements/templates and batch counts — **never per-row data values** (the session file must stay bounded at benchmark volumes).
- Importer contract is frozen: `(backend_cfg, entities: Dict[str, BoundEntity], *, dry_run, create_schema) -> List[str]`. Metrics/progress reach importers via module-level helpers, not signature changes.
- Exception taxonomy unchanged (`ConfigError`, `SourceError`, `MappingError`, `ImportExecutionError` under `BusinessException`); tests assert types, not message text.
- Test command: `./.venv/Scripts/python.exe -m pytest tests -q`. Baseline before this plan: **89 passed, 1 skipped** (the skip is pre-existing `data/db.json missing`). Suite must stay green after every task.
- Python floor is 3.9: `X | Y` unions only inside annotations (files use `from __future__ import annotations`); no `match` statements.
- NEVER push. Commit per task on branch `tcc2-config-v2`.

---

### Task 1: `rich` dependency + reporting core (two destinations)

**Files:**
- Modify: `pyproject.toml` (add `rich` to dependencies)
- Create: `src/polyglotimportcsv/reporting.py`
- Create: `tests/conftest.py`
- Test: `tests/test_reporting.py`

**Interfaces:**
- Consumes: nothing new (stdlib `logging`, `rich`).
- Produces: `setup_reporting(terminal_level: int = logging.INFO, *, log_dir: str | Path = "logs", no_log: bool = False) -> Optional[Path]`; `session_log_path() -> Optional[Path]`; `reset() -> None`; `print_rich(renderable, *, level: int = logging.INFO) -> None`; module constant `DATA_DUMP_THRESHOLD = 50`. Env contract: `POLYGLOT_NO_LOG=1` disables the session file; `POLYGLOT_DEBUG_LOG=<path>` redirects it to a shared file (used by `run_example.sh` in Task 10).

- [ ] **Step 1: Install the dependency and declare it**

Run: `./.venv/Scripts/python.exe -m pip install rich`

In `pyproject.toml`, change the dependencies list:

```toml
dependencies = [
    "click",
    "pandas",
    "jsonschema",
    "psycopg2-binary",
    "pymongo",
    "cassandra-driver",
    "pyasyncore; python_version >= '3.12'",
    "redis",
    "neo4j",
    "rich",
]
```

- [ ] **Step 2: Write the failing tests**

Create `tests/conftest.py`:

```python
"""Shared fixtures: keep tests from writing session logs into the repo's logs/ dir."""

import pytest

from polyglotimportcsv import reporting


@pytest.fixture(autouse=True)
def _quiet_reporting(monkeypatch):
    monkeypatch.setenv("POLYGLOT_NO_LOG", "1")
    yield
    reporting.reset()
```

Create `tests/test_reporting.py`:

```python
"""Reporting core: terminal level vs always-DEBUG session file (spec §4.2)."""

import logging
from pathlib import Path

from polyglotimportcsv import reporting


def test_setup_reporting_creates_debug_session_file(tmp_path, monkeypatch):
    monkeypatch.delenv("POLYGLOT_NO_LOG", raising=False)
    monkeypatch.delenv("POLYGLOT_DEBUG_LOG", raising=False)
    path = reporting.setup_reporting(logging.INFO, log_dir=tmp_path)
    assert path is not None
    assert path.name.startswith("polyglotimportcsv_") and path.suffix == ".log"
    logging.getLogger("polyglotimportcsv.test").debug("debug-only message")
    reporting.reset()
    content = path.read_text(encoding="utf-8")
    assert "debug-only message" in content
    assert "session started" in content


def test_terminal_respects_level_but_file_gets_debug(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("POLYGLOT_NO_LOG", raising=False)
    monkeypatch.delenv("POLYGLOT_DEBUG_LOG", raising=False)
    reporting.setup_reporting(logging.WARNING, log_dir=tmp_path)
    log = logging.getLogger("polyglotimportcsv.test")
    log.info("info-msg")
    log.warning("warn-msg")
    out = capsys.readouterr().out
    assert "warn-msg" in out
    assert "info-msg" not in out
    path = reporting.session_log_path()
    reporting.reset()
    content = Path(path).read_text(encoding="utf-8")
    assert "info-msg" in content and "warn-msg" in content


def test_no_log_env_disables_file(tmp_path, monkeypatch):
    monkeypatch.setenv("POLYGLOT_NO_LOG", "1")
    assert reporting.setup_reporting(logging.INFO, log_dir=tmp_path) is None
    assert reporting.session_log_path() is None


def test_debug_log_env_targets_shared_file(tmp_path, monkeypatch):
    monkeypatch.delenv("POLYGLOT_NO_LOG", raising=False)
    target = tmp_path / "shared_debug.log"
    monkeypatch.setenv("POLYGLOT_DEBUG_LOG", str(target))
    path = reporting.setup_reporting(logging.INFO, log_dir=tmp_path / "unused")
    assert path == target.resolve()
    logging.getLogger("polyglotimportcsv.test").debug("into-shared")
    reporting.reset()
    assert "into-shared" in target.read_text(encoding="utf-8")


def test_print_rich_honors_terminal_level_and_reaches_file(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("POLYGLOT_NO_LOG", raising=False)
    monkeypatch.delenv("POLYGLOT_DEBUG_LOG", raising=False)
    reporting.setup_reporting(logging.WARNING, log_dir=tmp_path)
    reporting.print_rich("suppressed-on-terminal", level=logging.INFO)
    out = capsys.readouterr().out
    assert "suppressed-on-terminal" not in out
    path = reporting.session_log_path()
    reporting.reset()
    assert "suppressed-on-terminal" in Path(path).read_text(encoding="utf-8")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_reporting.py -v`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'polyglotimportcsv.reporting'` (conftest import).

- [ ] **Step 4: Write the implementation**

Create `src/polyglotimportcsv/reporting.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_reporting.py -v`
Expected: 5 PASS.

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: 94 passed, 1 skipped (baseline 89 + 5 new; conftest must not break existing tests).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/polyglotimportcsv/reporting.py tests/conftest.py tests/test_reporting.py
git commit -m "feat: reporting core - rich terminal handler + always-DEBUG session file"
```

---

### Task 2: Presentation helpers (banners, JSON row dumps, backend lines)

**Files:**
- Modify: `src/polyglotimportcsv/reporting.py`
- Test: `tests/test_reporting.py`

**Interfaces:**
- Consumes: Task 1's `print_rich`, `_console`.
- Produces (all in `reporting.py`, signatures used by Tasks 3-4): `banner(title: str, *, subtitle: str = "") -> None`; `section(title: str) -> None`; `step(label: str, detail: str = "") -> None`; `kv(key: str, value: Any) -> None`; `note(message: str) -> None`; `success(message: str) -> None`; `warn(message: str) -> None` (routes to `logger.warning`); `error(message: str) -> None` (routes to `logger.error`); `empty_label() -> Text`; `format_json_row(obj: Any) -> Text`; `dump_rows(label: str, rows: Sequence[Dict[str, Any]]) -> None`; `backend_text(line: str) -> Text`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_reporting.py`:

```python
def test_dump_rows_prints_highlighted_json_records(capsys):
    reporting.setup_reporting(logging.INFO, no_log=True)
    reporting.dump_rows("table items", [{"id": 1, "name": "abc"}])
    out = capsys.readouterr().out
    assert "table items" in out and "1 row(s)" in out
    assert '"name"' in out and '"abc"' in out


def test_dump_rows_empty(capsys):
    reporting.setup_reporting(logging.INFO, no_log=True)
    reporting.dump_rows("table items", [])
    out = capsys.readouterr().out
    assert "0 row(s)" in out and "(empty)" in out


def test_backend_text_styles_known_backend():
    text = reporting.backend_text("[postgres] inserted 8 row(s) into public.products")
    assert text.plain.startswith("[postgres]")
    assert "inserted 8 row(s)" in text.plain


def test_warn_and_error_route_through_logging(capsys):
    reporting.setup_reporting(logging.INFO, no_log=True)
    reporting.warn("watch out")
    reporting.error("it broke")
    out = capsys.readouterr().out
    assert "watch out" in out and "it broke" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_reporting.py -v`
Expected: the 4 new tests FAIL with `AttributeError` (no `dump_rows` / `backend_text`).

- [ ] **Step 3: Write the implementation**

In `src/polyglotimportcsv/reporting.py`, extend the imports:

```python
import re
from typing import IO, Any, Dict, Optional, Sequence

from rich.console import Console
from rich.json import JSON
from rich.logging import RichHandler
from rich.rule import Rule
from rich.text import Text
```

Append after `print_rich`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_reporting.py -v`
Expected: all PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/reporting.py tests/test_reporting.py
git commit -m "feat: rich presentation helpers (banner/section/dump/backend lines)"
```

---

### Task 3: Migrate cli, runner, and inspect script; add `--log-level`; delete console.py

**Files:**
- Modify: `src/polyglotimportcsv/cli.py`
- Modify: `src/polyglotimportcsv/runner.py`
- Modify: `scripts/inspect_persisted_data.py`
- Delete: `src/polyglotimportcsv/console.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 1's `setup_reporting`; Task 2's helpers (`banner`, `section`, `step`, `kv`, `note`, `success`, `warn`, `error`, `dump_rows`, `format_json_row`, `empty_label`, `backend_text`, `print_rich`).
- Produces: `cli.main` gains `--log-level` (Choice DEBUG/INFO/WARNING/ERROR, default INFO, case-insensitive). `run_import` keeps its exact current signature and `List[str]` return. Nothing imports `polyglotimportcsv.console` afterwards.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
import logging


def test_cli_log_level_controls_terminal_verbosity(tmp_path, monkeypatch):
    def fake_run_import(config_path, **kwargs):
        logging.getLogger("polyglotimportcsv.fake").debug("dbg-marker")
        return []

    monkeypatch.setattr("polyglotimportcsv.cli.run_import", fake_run_import)
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(main, ["--config", str(cfg), "--log-level", "debug"])
    assert result.exit_code == 0, result.output
    assert "dbg-marker" in result.output

    result = runner.invoke(main, ["--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert "dbg-marker" not in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_cli.py -v`
Expected: new test FAILS (exit code 2, `no such option: --log-level`).

- [ ] **Step 3: Rewrite `src/polyglotimportcsv/cli.py`**

```python
"""Command-line interface for PolyglotImportCSV."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Dict, Tuple

import click

from polyglotimportcsv.business_exception import BusinessException
from polyglotimportcsv.reporting import error, kv, setup_reporting
from polyglotimportcsv.runner import run_import

logger = logging.getLogger(__name__)


def _parse_source_overrides(pairs: Tuple[str, ...]) -> Dict[str, str]:
    overrides: Dict[str, str] = {}
    for pair in pairs:
        name, sep, path = pair.partition("=")
        if not sep or not name.strip() or not path.strip():
            raise click.UsageError(
                f"--source expects NAME=PATH, got: {pair!r}"
            )
        overrides[name.strip()] = path.strip()
    return overrides


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="JSON import (mapping) configuration with the 'sources' block.",
)
@click.option(
    "--sgbd-config",
    "sgbd_config_path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="JSON SGBD connection configuration. Defaults to sgbd_config.json next to --config.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate and print planned row counts; do not connect to databases.",
)
@click.option(
    "--create-schema/--no-create-schema",
    default=True,
    show_default=True,
    help="Create keyspace/tables/collections where applicable.",
)
@click.option(
    "--only",
    default="",
    help="Comma-separated backends to run (postgres,redis,mongodb,cassandra,neo4j). Empty = all configured.",
)
@click.option(
    "--source",
    "source_pairs",
    multiple=True,
    metavar="NAME=PATH",
    help="Override the CSV path of a source declared in the config (repeatable).",
)
@click.option(
    "--log-level",
    "log_level",
    default="INFO",
    show_default=True,
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    help="Terminal log level; the session log file always records DEBUG.",
)
def main(
    config_path: Path,
    sgbd_config_path: Path,
    dry_run: bool,
    create_schema: bool,
    only: str,
    source_pairs: Tuple[str, ...],
    log_level: str,
) -> None:
    """Import CSV sources into multiple databases according to --config."""
    log_path = setup_reporting(getattr(logging, log_level.upper()))
    if log_path is not None:
        kv("Log file", log_path)
    only_list = [x.strip() for x in only.split(",") if x.strip()] if only else None
    overrides = _parse_source_overrides(source_pairs)
    try:
        run_import(
            config_path,
            sgbd_config_path=sgbd_config_path,
            dry_run=dry_run,
            create_schema=create_schema,
            only=only_list,
            source_overrides=overrides or None,
        )
    except BusinessException as e:
        error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Rewrite `src/polyglotimportcsv/runner.py`**

(Intermediate version — dump/metrics arrive in Tasks 4 and 6.)

```python
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
        backend_lines = fn(bcfg, bound, dry_run=dry_run, create_schema=create_schema)
        log_lines.extend(backend_lines)
        for line in backend_lines:
            _print_backend_line(line)

    success(f"Finished {mode} — {len(log_lines)} log line(s) from importer(s)")
    return log_lines
```

- [ ] **Step 5: Migrate `scripts/inspect_persisted_data.py`**

Replace the import block (lines 11-24):

```python
from polyglotimportcsv.reporting import (
    banner,
    dump_rows,
    empty_label,
    error,
    format_json_row,
    note,
    print_rich,
    section,
    setup_reporting,
    step,
    success,
    warn,
)
from rich.text import Text
```

In `inspect_redis`, replace the two `print(...)` call sites:

```python
    if not keys:
        line = Text("    ")
        line.append_text(empty_label())
        print_rich(line)
        return
    for key in keys:
        kind = r.type(key)
        if kind == "string":
            value = r.get(key)
            line = Text(f"    key={key!r}  value=")
            try:
                parsed = json.loads(value)
                line.append_text(format_json_row(parsed))
            except (TypeError, json.JSONDecodeError):
                line.append(str(value))
            print_rich(line)
        else:
            warn(f"key={key!r} type={kind} (not displayed)")
```

In `main()`, replace the setup block (previously `setup_logging()` at the top and the `init_session_log`/`note` pair after arg parsing):

```python
def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Clean or inspect Docker databases using import_config.json."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_p = sub.add_parser("inspect", help="Log persisted rows/documents/keys.")
    _add_common_args(inspect_p)

    clean_p = sub.add_parser("clean", help="Remove imported data for a fresh reload.")
    _add_common_args(clean_p)

    args = parser.parse_args(argv)
    log_path = setup_reporting()
    config_path = args.config.resolve()
    if not config_path.is_file():
        error(f"Config not found: {config_path}")
        return 1
    sgbd_path = args.sgbd_config.resolve() if args.sgbd_config else None

    if log_path is not None:
        note(f"log file: {log_path}")
```

(The rest of `main()` — `_load_config`, `_parse_only`, banner/step, `_run_backends`, exit codes — stays exactly as-is.)

- [ ] **Step 6: Delete `src/polyglotimportcsv/console.py` and verify no references**

```bash
git rm src/polyglotimportcsv/console.py
grep -rn "polyglotimportcsv.console" src scripts tests || echo "clean"
```

Expected: `clean` (docs/plans may still mention it; that is fine).

- [ ] **Step 7: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: 95 passed, 1 skipped.

Smoke: `./.venv/Scripts/python.exe -m polyglotimportcsv --config data/ecommerce/import_config.json --dry-run`
Expected: banner, per-source notes, per-backend dry-run lines, success line; exit 0.

- [ ] **Step 8: Commit**

```bash
git add -A src/polyglotimportcsv scripts/inspect_persisted_data.py tests/test_cli.py
git commit -m "refactor: migrate cli, runner, and inspect script to reporting; drop console.py"
```

---

### Task 4: Data-dump threshold + `--show-data`/`--no-data`

**Files:**
- Modify: `src/polyglotimportcsv/reporting.py`
- Modify: `src/polyglotimportcsv/runner.py`
- Modify: `src/polyglotimportcsv/cli.py`
- Test: `tests/test_reporting.py`, `tests/test_cli.py`, `tests/test_runner_registry.py`

**Interfaces:**
- Consumes: Task 2's `dump_rows`, `note`.
- Produces: `reporting.dump_entity_frame(backend: str, entity: str, df: pd.DataFrame, *, force: Optional[bool] = None) -> None`; `run_import(..., show_data: Optional[bool] = None)`; CLI `--show-data/--no-data` mapped to that tri-state (None = threshold decides).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_reporting.py`:

```python
import pandas as pd


def test_dump_entity_frame_threshold_boundary(capsys):
    reporting.setup_reporting(logging.INFO, no_log=True)
    at_limit = pd.DataFrame({"id": range(reporting.DATA_DUMP_THRESHOLD)})
    reporting.dump_entity_frame("postgres", "items", at_limit)
    out = capsys.readouterr().out
    assert '"id"' in out

    above = pd.DataFrame({"id": range(reporting.DATA_DUMP_THRESHOLD + 1)})
    reporting.dump_entity_frame("postgres", "items", above)
    out = capsys.readouterr().out
    assert '"id"' not in out
    assert "51 row(s)" in out


def test_dump_entity_frame_force_flags(capsys):
    reporting.setup_reporting(logging.INFO, no_log=True)
    big = pd.DataFrame({"id": range(60)})
    reporting.dump_entity_frame("postgres", "items", big, force=True)
    assert '"id"' in capsys.readouterr().out

    small = pd.DataFrame({"id": [1, 2]})
    reporting.dump_entity_frame("postgres", "items", small, force=False)
    assert '"id"' not in capsys.readouterr().out
```

Append to `tests/test_cli.py`:

```python
def test_cli_show_data_tristate(tmp_path, monkeypatch):
    captured = {}

    def fake_run_import(config_path, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr("polyglotimportcsv.cli.run_import", fake_run_import)
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")
    runner = CliRunner()

    assert runner.invoke(main, ["--config", str(cfg)]).exit_code == 0
    assert captured["show_data"] is None
    assert runner.invoke(main, ["--config", str(cfg), "--show-data"]).exit_code == 0
    assert captured["show_data"] is True
    assert runner.invoke(main, ["--config", str(cfg), "--no-data"]).exit_code == 0
    assert captured["show_data"] is False
```

Append to `tests/test_runner_registry.py`:

```python
def test_run_import_dumps_bound_entities(monkeypatch):
    calls = []

    def fake_dump(backend, entity, df, *, force=None):
        calls.append((backend, entity, len(df), force))

    monkeypatch.setattr("polyglotimportcsv.runner.dump_entity_frame", fake_dump)

    def stub(cfg, entities, *, dry_run, create_schema):
        return ["[postgres] stub"]

    run_import(CFG, dry_run=True, only=["postgres"], importers={"postgres": stub})
    assert calls, "expected one dump call per bound entity"
    assert all(backend == "postgres" and force is None for backend, _, _, force in calls)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_reporting.py tests/test_cli.py tests/test_runner_registry.py -v`
Expected: new tests FAIL (`AttributeError: dump_entity_frame`, `KeyError: 'show_data'`).

- [ ] **Step 3: Implement**

In `src/polyglotimportcsv/reporting.py`, append:

```python
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
```

In `src/polyglotimportcsv/runner.py`:

1. Add `dump_entity_frame` to the `reporting` import list.
2. Add the parameter to the signature, after `source_overrides`:

```python
    source_overrides: Optional[Dict[str, str]] = None,
    show_data: Optional[bool] = None,
) -> List[str]:
```

3. Inside the backend loop, between `validate_backend_entities(...)` and the `fn(...)` call, insert:

```python
        validate_backend_entities(backend, bcfg, bound)
        for ename, be in bound.items():
            dump_entity_frame(backend, ename, be.df, force=show_data)
        backend_lines = fn(bcfg, bound, dry_run=dry_run, create_schema=create_schema)
```

In `src/polyglotimportcsv/cli.py`:

1. Add the option after `--log-level`:

```python
@click.option(
    "--show-data/--no-data",
    "show_data",
    default=None,
    help="Force or suppress per-entity data dumps (default: dump entities up to 50 rows).",
)
```

2. Add `show_data: Optional[bool],` to `main`'s parameters (and `Optional` to the `typing` import), then pass it through:

```python
        run_import(
            config_path,
            sgbd_config_path=sgbd_config_path,
            dry_run=dry_run,
            create_schema=create_schema,
            only=only_list,
            source_overrides=overrides or None,
            show_data=show_data,
        )
```

- [ ] **Step 4: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: 99 passed, 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/reporting.py src/polyglotimportcsv/runner.py src/polyglotimportcsv/cli.py tests/test_reporting.py tests/test_cli.py tests/test_runner_registry.py
git commit -m "feat: entity data-dump threshold with --show-data/--no-data"
```

---

### Task 5: Pipeline DEBUG/WARNING instrumentation (sources, mapping, casting)

**Files:**
- Modify: `src/polyglotimportcsv/sources.py`
- Modify: `src/polyglotimportcsv/mapping_resolver.py`
- Modify: `src/polyglotimportcsv/casting.py`
- Test: `tests/test_pipeline_logging.py` (new)

**Interfaces:**
- Consumes: nothing new — plain `logging` module loggers (records reach both destinations via Task 1's handlers).
- Produces: log records only; no API changes. Loggers: `polyglotimportcsv.sources`, `polyglotimportcsv.mapping_resolver`, `polyglotimportcsv.casting`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pipeline_logging.py`:

```python
"""Spec §4.2: DEBUG inference/mapping decisions; WARNING empty sources and text fallbacks."""

import logging

import pandas as pd

from polyglotimportcsv.casting import cast_frame
from polyglotimportcsv.mapping_resolver import resolve_backend_entities
from polyglotimportcsv.sources import load_sources


def test_load_sources_logs_kinds_and_warns_on_empty(tmp_path, caplog):
    (tmp_path / "empty.csv").write_text("id,name\n", encoding="utf-8")
    with caplog.at_level(logging.DEBUG, logger="polyglotimportcsv.sources"):
        load_sources({"empty": "empty.csv"}, tmp_path)
    assert any(
        r.levelno == logging.WARNING and "0 row(s)" in r.message for r in caplog.records
    )
    assert any("inferred kinds" in r.message for r in caplog.records)


def test_resolver_logs_effective_mapping_per_column(tmp_path, caplog):
    (tmp_path / "stock.csv").write_text("sku,qty\nA,5\n", encoding="utf-8")
    sources = load_sources({"stock": "stock.csv"}, tmp_path)
    bcfg = {"entities": {"stock": {}}}
    with caplog.at_level(logging.DEBUG, logger="polyglotimportcsv.mapping_resolver"):
        resolve_backend_entities(bcfg, sources)
    debug = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("sku" in m and "db_type" in m for m in debug)
    assert any("qty" in m and "BIGINT" in m for m in debug)


def test_cast_frame_warns_on_text_fallback(caplog):
    df = pd.DataFrame({"n": ["1", "x", "3"]})
    with caplog.at_level(logging.DEBUG, logger="polyglotimportcsv.casting"):
        out = cast_frame(df, {"n": "integer"})
    assert list(out["n"]) == [1, "x", 3]
    assert any(
        r.levelno == logging.WARNING and "could not be cast" in r.message
        for r in caplog.records
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_pipeline_logging.py -v`
Expected: 3 FAIL (no such log records yet).

- [ ] **Step 3: Implement**

`src/polyglotimportcsv/sources.py` — add below the imports:

```python
import logging

logger = logging.getLogger(__name__)
```

and extend `_register` (after the `kinds[SOURCE_COLUMN] = "string"` line):

```python
    kinds[SOURCE_COLUMN] = "string"
    logger.debug("source %s: inferred kinds: %s", name, {c: kinds[c] for c in file_header})
    if len(df) == 0:
        logger.warning("source %s has 0 row(s)", name)
    registry[name] = SourceData(name=name, df=df, kinds=kinds, file_header=file_header)
```

`src/polyglotimportcsv/mapping_resolver.py` — add below the imports:

```python
import logging

logger = logging.getLogger(__name__)
```

and in `resolve_backend_entities`, after `cfg["columns"] = expand_entity_columns(...)`:

```python
        cfg["columns"] = expand_entity_columns(ename, ecfg, src)
        manual_cols = set(ecfg.get("columns") or {})
        for col, spec in cfg["columns"].items():
            origin = "manual" if col in manual_cols else "inferred"
            logger.debug(
                "entity %s (source %s): column %r -> db_type=%s [%s]",
                ename, src.name, col, spec.get("db_type"), origin,
            )
```

`src/polyglotimportcsv/casting.py` — add below the imports:

```python
import logging

logger = logging.getLogger(__name__)
```

and rewrite `cast_frame`'s loop body (keep the existing docstring and the dtype-object comment):

```python
    out = df.copy()
    for col in out.columns:
        kind = kinds.get(col, "string")
        if kind in ("integer", "float", "boolean", "datetime"):
            # Build the object column directly from a list of already-cast
            # native Python values, rather than via Series.map(). map()
            # lets pandas infer a dtype for the intermediate result (e.g.
            # float64 for a mix of int and None), which silently upcasts
            # ints to floats (1 -> 1.0) before astype(object) ever runs.
            values = [cast_value(v, kind) for v in out[col]]
            fallbacks = sum(
                1
                for orig, v in zip(out[col], values)
                if v is orig and orig is not None and orig != ""
            )
            if fallbacks:
                logger.warning(
                    "column %r: %d value(s) could not be cast to %s and stayed text",
                    col, fallbacks, kind,
                )
            logger.debug("column %r cast to %s (%d value(s))", col, kind, len(values))
            out[col] = pd.Series(values, index=out.index, dtype=object)
    return out
```

(`cast_value` returns the original object unchanged on int/float failure, so the identity check `v is orig` counts exactly the text fallbacks.)

- [ ] **Step 4: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: 102 passed, 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/sources.py src/polyglotimportcsv/mapping_resolver.py src/polyglotimportcsv/casting.py tests/test_pipeline_logging.py
git commit -m "feat: pipeline DEBUG/WARNING instrumentation (sources, mapping, casting)"
```

---

### Task 6: `MetricsCollector` + runner phases + summary table

**Files:**
- Create: `src/polyglotimportcsv/metrics.py`
- Modify: `src/polyglotimportcsv/reporting.py` (add `metrics_table`)
- Modify: `src/polyglotimportcsv/runner.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_metrics.py` (new)

**Interfaces:**
- Consumes: Task 2's `print_rich`.
- Produces (used by Tasks 7-9):
  - `metrics.PhaseMetric` (dataclass: `backend, entity, phase, rows, seconds`; property `rows_per_second: Optional[float]`; `to_record() -> Dict[str, object]`).
  - `metrics.MetricsCollector` with `record(backend, entity, phase, *, rows, seconds)`, `timed(backend, entity, phase)` context manager yielding an object with a mutable `rows` attribute, `entries() -> List[PhaseMetric]`, `to_records() -> List[Dict[str, object]]`.
  - Module-level: `metrics.set_current(collector | None)`, `metrics.current()`, `metrics.timed_phase(backend, entity, phase)` — no-op-safe context manager importers call without signature changes.
  - `reporting.metrics_table(records: Sequence[Dict[str, object]]) -> rich.table.Table`.
  - `run_import(..., collector: Optional[MetricsCollector] = None)` — injectable; runner records phase `"read"` (backend `"(sources)"`, entity `"*"`, all sources aggregated — reading is global, not per SGBD) and phase `"map"` per backend (entity `"*"`). Phases `"filter"`/`"write"` come from importers (Tasks 7-8).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_metrics.py`:

```python
"""MetricsCollector: per-phase records, module-level current, runner integration."""

from io import StringIO
from pathlib import Path

from rich.console import Console

from polyglotimportcsv import metrics
from polyglotimportcsv.metrics import MetricsCollector
from polyglotimportcsv.reporting import metrics_table
from polyglotimportcsv.runner import run_import

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "data" / "ecommerce" / "import_config.json"


def test_collector_records_and_computes_rate():
    c = MetricsCollector()
    c.record("postgres", "items", "write", rows=100, seconds=2.0)
    [m] = c.entries()
    assert m.rows_per_second == 50.0
    rec = m.to_record()
    assert rec["backend"] == "postgres" and rec["phase"] == "write"


def test_zero_seconds_has_no_rate():
    c = MetricsCollector()
    c.record("postgres", "items", "write", rows=10, seconds=0.0)
    assert c.entries()[0].rows_per_second is None


def test_timed_phase_is_noop_without_current():
    metrics.set_current(None)
    with metrics.timed_phase("postgres", "items", "filter") as t:
        t.rows = 3  # must not raise
    assert metrics.current() is None  # nothing was implicitly created


def test_timed_phase_records_into_current():
    c = MetricsCollector()
    metrics.set_current(c)
    try:
        with metrics.timed_phase("postgres", "items", "filter") as t:
            t.rows = 7
    finally:
        metrics.set_current(None)
    [m] = c.entries()
    assert (m.backend, m.entity, m.phase, m.rows) == ("postgres", "items", "filter", 7)
    assert m.seconds >= 0


def test_run_import_records_read_and_map_phases():
    def stub(cfg, entities, *, dry_run, create_schema):
        return ["[postgres] stub"]

    c = MetricsCollector()
    run_import(
        CFG, dry_run=True, only=["postgres"], importers={"postgres": stub}, collector=c
    )
    phases = {(m.backend, m.phase) for m in c.entries()}
    assert ("(sources)", "read") in phases
    assert ("postgres", "map") in phases
    assert metrics.current() is None  # runner must reset after the run


def test_metrics_table_renders_rows():
    c = MetricsCollector()
    c.record("postgres", "items", "write", rows=100, seconds=2.0)
    buf = Console(file=StringIO(), width=120)
    buf.print(metrics_table(c.to_records()))
    text = buf.file.getvalue()
    assert "rows/s" in text and "postgres" in text and "50" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_metrics.py -v`
Expected: ERROR — `ModuleNotFoundError: No module named 'polyglotimportcsv.metrics'`.

- [ ] **Step 3: Create `src/polyglotimportcsv/metrics.py`**

```python
"""Per-phase import metrics: collector + module-level current instance (spec §4.4).

The runner owns one ``MetricsCollector`` per run and publishes it via
``set_current``; importers record through ``timed_phase`` without any change
to their frozen signature. Phases: read, filter, map, write.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional

PHASES = ("read", "filter", "map", "write")


@dataclass
class PhaseMetric:
    backend: str
    entity: str
    phase: str
    rows: int
    seconds: float

    @property
    def rows_per_second(self) -> Optional[float]:
        if self.seconds <= 0:
            return None
        return self.rows / self.seconds

    def to_record(self) -> Dict[str, object]:
        return {
            "backend": self.backend,
            "entity": self.entity,
            "phase": self.phase,
            "rows": self.rows,
            "seconds": self.seconds,
            "rows_per_second": self.rows_per_second,
        }


class _Timed:
    """Mutable row counter handed out by ``timed``/``timed_phase``."""

    def __init__(self) -> None:
        self.rows = 0


class MetricsCollector:
    def __init__(self) -> None:
        self._entries: List[PhaseMetric] = []

    def record(
        self, backend: str, entity: str, phase: str, *, rows: int, seconds: float
    ) -> None:
        self._entries.append(PhaseMetric(backend, entity, phase, rows, seconds))

    @contextmanager
    def timed(self, backend: str, entity: str, phase: str) -> Iterator[_Timed]:
        t = _Timed()
        start = time.perf_counter()
        try:
            yield t
        finally:
            self.record(
                backend, entity, phase, rows=t.rows, seconds=time.perf_counter() - start
            )

    def entries(self) -> List[PhaseMetric]:
        return list(self._entries)

    def to_records(self) -> List[Dict[str, object]]:
        return [m.to_record() for m in self._entries]


_current: Optional[MetricsCollector] = None


def set_current(collector: Optional[MetricsCollector]) -> None:
    global _current
    _current = collector


def current() -> Optional[MetricsCollector]:
    return _current


@contextmanager
def timed_phase(backend: str, entity: str, phase: str) -> Iterator[_Timed]:
    """Record into the current collector; harmless no-op when none is active."""
    if _current is None:
        yield _Timed()
        return
    with _current.timed(backend, entity, phase) as t:
        yield t
```

- [ ] **Step 4: Add `metrics_table` to `src/polyglotimportcsv/reporting.py`**

Add `from rich.table import Table` to the imports, then append:

```python
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
```

- [ ] **Step 5: Integrate into `src/polyglotimportcsv/runner.py`**

1. Add imports: `import time` and `from polyglotimportcsv import metrics`; add `metrics_table` to the `reporting` import list.
2. Add the parameter after `show_data`:

```python
    show_data: Optional[bool] = None,
    collector: Optional[metrics.MetricsCollector] = None,
) -> List[str]:
```

3. Wrap the body: after the `banner(...)` call, insert:

```python
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
            show_data=show_data,
            collector=collector,
        )
    finally:
        metrics.set_current(None)
```

and move everything from `step("Load config", ...)` down into a private function with the same parameters:

```python
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
) -> List[str]:
    mode = "dry-run" if dry_run else "import"
    step("Load config", str(config_path))
    ...
```

(`banner` stays in `run_import`; remove the `mode`/`banner` lines from `_run`'s copy except recomputing `mode` as shown.)

4. Time the read phase — replace the `load_sources` call block:

```python
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
```

5. Time the map phase — replace the `resolve_backend_entities` call:

```python
        with collector.timed(backend, "*", "map") as t:
            bound = resolve_backend_entities(bcfg, sources, cast_cache)
            t.rows = sum(len(be.df) for be in bound.values())
```

6. Also warn on empty bound entities inside the dump loop:

```python
        for ename, be in bound.items():
            if len(be.df) == 0:
                logger.warning("entity %s/%s bound to 0 row(s)", backend, ename)
            dump_entity_frame(backend, ename, be.df, force=show_data)
```

7. Print the summary table before the `success(...)` line:

```python
    if collector.entries():
        print_rich(metrics_table(collector.to_records()))
    success(f"Finished {mode} — {len(log_lines)} log line(s) from importer(s)")
    return log_lines
```

- [ ] **Step 6: Reset metrics between tests**

In `tests/conftest.py`, extend the fixture:

```python
import pytest

from polyglotimportcsv import metrics, reporting


@pytest.fixture(autouse=True)
def _quiet_reporting(monkeypatch):
    monkeypatch.setenv("POLYGLOT_NO_LOG", "1")
    yield
    reporting.reset()
    metrics.set_current(None)
```

- [ ] **Step 7: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: 108 passed, 1 skipped.

- [ ] **Step 8: Commit**

```bash
git add src/polyglotimportcsv/metrics.py src/polyglotimportcsv/reporting.py src/polyglotimportcsv/runner.py tests/conftest.py tests/test_metrics.py
git commit -m "feat: MetricsCollector with per-phase timing and summary table"
```

---

### Task 7: Progress helper + instrument postgres and mongodb importers

**Files:**
- Modify: `src/polyglotimportcsv/reporting.py` (add `entity_progress`)
- Modify: `src/polyglotimportcsv/importers/postgres_importer.py`
- Modify: `src/polyglotimportcsv/importers/mongodb_importer.py`
- Test: `tests/test_reporting.py`, `tests/test_importer_metrics.py` (new)

**Interfaces:**
- Consumes: Task 6's `metrics.timed_phase`; `DATA_DUMP_THRESHOLD`.
- Produces: `reporting.entity_progress(description: str, total: int)` — context manager yielding `advance(n: int = 1) -> None`; live rows/s bar only when `total > DATA_DUMP_THRESHOLD` and stdout is a terminal, otherwise a no-op (spec §4.4). Importers record phases `"filter"` (per entity, also in dry-run) and `"write"` (per part/table, live path only) and log DDL/SQL templates at DEBUG.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_reporting.py`:

```python
def test_entity_progress_noop_at_or_below_threshold(capsys):
    with reporting.entity_progress("x", reporting.DATA_DUMP_THRESHOLD) as advance:
        assert callable(advance)
        advance(10)
    assert capsys.readouterr().out == ""  # no bar rendered at/below threshold


def test_entity_progress_noop_when_not_a_terminal(capsys):
    with reporting.entity_progress("x", 10_000) as advance:
        assert callable(advance)
        advance(500)  # pytest stdout is not a tty -> no-op path
    assert capsys.readouterr().out == ""
```

Create `tests/test_importer_metrics.py`:

```python
"""Importers record the 'filter' phase in dry-run (no DB connections needed)."""

from pathlib import Path

from polyglotimportcsv.metrics import MetricsCollector
from polyglotimportcsv.runner import run_import

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "data" / "ecommerce" / "import_config.json"


def _filter_phases(only):
    c = MetricsCollector()
    run_import(CFG, dry_run=True, only=[only], collector=c)
    return {(m.backend, m.phase) for m in c.entries()}


def test_postgres_dry_run_records_filter_phase():
    assert ("postgres", "filter") in _filter_phases("postgres")


def test_mongodb_dry_run_records_filter_phase():
    assert ("mongodb", "filter") in _filter_phases("mongodb")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_reporting.py tests/test_importer_metrics.py -v`
Expected: `entity_progress` tests FAIL with AttributeError; importer tests FAIL on the missing `("postgres", "filter")` entry.

- [ ] **Step 3: Add `entity_progress` to `src/polyglotimportcsv/reporting.py`**

Extend imports:

```python
from contextlib import contextmanager
from typing import IO, Any, Callable, Dict, Iterator, Optional, Sequence

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
```

Append:

```python
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
```

- [ ] **Step 4: Rewrite `src/polyglotimportcsv/importers/postgres_importer.py`**

Add imports:

```python
from polyglotimportcsv import metrics
from polyglotimportcsv.reporting import entity_progress
```

Replace `run_postgres_import`'s dry-run block:

```python
    if dry_run:
        lines.append("[postgres] dry-run: would connect and import entities.")
        for ename, be in entities.items():
            non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
            with metrics.timed_phase("postgres", ename, "filter") as t:
                dff = apply_filters(be.df, non_each, be.kinds)
                t.rows = len(dff)
            for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
                mat = flatten_entity_dataframe(part_df, be.cfg)
                lines.append(f"  entity {part_name}: {len(mat)} row(s) after dedupe")
        return lines
```

Replace the schema-creation block:

```python
        if create_schema:
            for stmt in create_stmts:
                logger.debug("[postgres] DDL: %s", stmt)
                cur.execute(stmt)
            for stmt in fk_stmts:
                for sub in stmt.split(";"):
                    sub = sub.strip()
                    if sub:
                        logger.debug("[postgres] DDL: %s;", sub)
                        cur.execute(sub + ";")
```

Replace the insert loop (from `for ename in ordered_names:` to the final `lines.append`):

```python
        for ename in ordered_names:
            be = entities[ename]
            non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
            with metrics.timed_phase("postgres", ename, "filter") as t:
                dff = apply_filters(be.df, non_each, be.kinds)
                t.rows = len(dff)
            for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
                mat = flatten_entity_dataframe(part_df, be.cfg)
                if mat.empty:
                    logger.warning(
                        "[postgres] entity %s has 0 row(s) after filters; nothing to insert",
                        part_name,
                    )
                    continue
                cols = list(mat.columns)
                fq = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(part_name))
                col_sql = sql.SQL(", ").join(map(sql.Identifier, cols))
                pks = [
                    target_field_name(fk, spec)
                    for fk, _, spec in flat_leaf_columns(be.cfg)
                    if spec.get("is_key")
                ]
                base = sql.SQL("INSERT INTO {} ({}) VALUES %s").format(fq, col_sql)
                if pks:
                    full = base + sql.SQL(" ON CONFLICT ({}) DO NOTHING").format(
                        sql.SQL(", ").join(map(sql.Identifier, pks))
                    )
                else:
                    full = base
                tuples = [tuple(row) for row in mat.itertuples(index=False, name=None)]
                logger.debug(
                    "[postgres] SQL: %s (%d row(s), page_size=500)",
                    full.as_string(cx), len(tuples),
                )
                with metrics.timed_phase("postgres", part_name, "write") as tw:
                    with entity_progress(f"postgres · {part_name}", len(tuples)) as advance:
                        for i in range(0, len(tuples), 500):
                            chunk = tuples[i : i + 500]
                            execute_values(cur, full.as_string(cx), chunk, page_size=500)
                            advance(len(chunk))
                    tw.rows = len(tuples)
                lines.append(f"[postgres] inserted {len(tuples)} row(s) into {schema}.{part_name}")
```

- [ ] **Step 5: Rewrite `src/polyglotimportcsv/importers/mongodb_importer.py`**

Add the same two imports, then replace the dry-run loop:

```python
    if dry_run:
        lines.append("[mongodb] dry-run: would insert documents.")
        for ename, be in entities.items():
            non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
            with metrics.timed_phase("mongodb", ename, "filter") as t:
                dff = apply_filters(be.df, non_each, be.kinds)
                t.rows = len(dff)
            for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
                lines.append(f"  collection {part_name}: {len(part_df)} document(s)")
        return lines
```

and the live loop:

```python
    db = client[database]
    for ename, be in entities.items():
        non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
        with metrics.timed_phase("mongodb", ename, "filter") as t:
            dff = apply_filters(be.df, non_each, be.kinds)
            t.rows = len(dff)
        for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
            docs = [mongo_document_from_row(row, be.cfg) for _, row in part_df.iterrows()]
            if not docs:
                logger.warning("[mongodb] collection %s has 0 document(s) after filters", part_name)
                lines.append(f"[mongodb] inserted 0 document(s) into {part_name}")
                continue
            logger.debug("[mongodb] insert_many into %s: %d document(s)", part_name, len(docs))
            with metrics.timed_phase("mongodb", part_name, "write") as tw:
                with entity_progress(f"mongodb · {part_name}", len(docs)) as advance:
                    db[part_name].insert_many(docs)
                    advance(len(docs))
                tw.rows = len(docs)
            lines.append(f"[mongodb] inserted {len(docs)} document(s) into {part_name}")
    client.close()
    return lines
```

- [ ] **Step 6: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: 112 passed, 1 skipped.

- [ ] **Step 7: Commit**

```bash
git add src/polyglotimportcsv/reporting.py src/polyglotimportcsv/importers/postgres_importer.py src/polyglotimportcsv/importers/mongodb_importer.py tests/test_reporting.py tests/test_importer_metrics.py
git commit -m "feat: instrument postgres and mongodb importers (debug SQL, metrics, progress)"
```

---

### Task 8: Instrument cassandra, redis, and neo4j importers

**Files:**
- Modify: `src/polyglotimportcsv/importers/cassandra_importer.py`
- Modify: `src/polyglotimportcsv/importers/redis_importer.py`
- Modify: `src/polyglotimportcsv/importers/neo4j_importer.py`
- Test: `tests/test_importer_metrics.py`

**Interfaces:**
- Consumes: Task 6's `metrics.timed_phase`; Task 7's `entity_progress`.
- Produces: log records + metrics entries only; the `List[str]` return lines of all three importers are byte-identical to today's.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_importer_metrics.py`:

```python
def test_cassandra_dry_run_records_filter_phase():
    assert ("cassandra", "filter") in _filter_phases("cassandra")


def test_redis_dry_run_records_filter_phase():
    assert ("redis", "filter") in _filter_phases("redis")


def test_neo4j_dry_run_records_filter_phase():
    assert ("neo4j", "filter") in _filter_phases("neo4j")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_importer_metrics.py -v`
Expected: 3 new FAIL.

- [ ] **Step 3: Instrument `cassandra_importer.py`**

Add imports:

```python
from polyglotimportcsv import metrics
from polyglotimportcsv.reporting import entity_progress
```

Dry-run loop — wrap the filter exactly as in Task 7:

```python
        for ename, be in entities.items():
            non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
            with metrics.timed_phase("cassandra", ename, "filter") as t:
                dff = apply_filters(be.df, non_each, be.kinds)
                t.rows = len(dff)
            for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
                lines.append(f"  table {part_name}: {len(part_df)} row(s)")
```

Live path — log the keyspace DDL before executing it:

```python
    keyspace_ddl = (
        f"CREATE KEYSPACE IF NOT EXISTS {keyspace} "
        "WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};"
    )
    logger.debug("[cassandra] DDL: %s", keyspace_ddl)
    session.execute(keyspace_ddl)
    session.set_keyspace(keyspace)
```

(Replace the current triple-quoted `session.execute(f"""CREATE KEYSPACE ...""")` block with the above — same statement, now also logged.)

In the entity loop, wrap the filter identically:

```python
        non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
        with metrics.timed_phase("cassandra", ename, "filter") as t:
            dff = apply_filters(be.df, non_each, be.kinds)
            t.rows = len(dff)
```

And replace the per-table body (`for table, part_df in expand_each(...)`):

```python
        for table, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
            if create_schema:
                col_defs = []
                for src in ordered_src:
                    col_defs.append(f'"{pmap[src]}" {cql_by_src[src]}')
                ddl = f'CREATE TABLE IF NOT EXISTS "{table}" (' + ", ".join(col_defs) + f", {pk_clause});"
                logger.debug("[cassandra] DDL: %s", ddl)
                session.execute(ddl)

            cols_cql = ", ".join(f'"{c}"' for c in ordered_db)
            placeholders = ", ".join(["?"] * len(ordered_db))
            cql = f'INSERT INTO "{table}" ({cols_cql}) VALUES ({placeholders})'
            logger.debug("[cassandra] CQL: %s (%d row(s))", cql, len(part_df))
            prep = session.prepare(cql)
            if part_df.empty:
                logger.warning("[cassandra] table %s has 0 row(s) after filters", table)
            count = 0
            with metrics.timed_phase("cassandra", table, "write") as tw:
                with entity_progress(f"cassandra · {table}", len(part_df)) as advance:
                    for _, row in part_df.iterrows():
                        values = []
                        for src in ordered_src:
                            val = row.get(src)
                            if pd.isna(val):
                                values.append(None)
                            elif cql_by_src[src] == "text":
                                values.append(str(val))
                            else:
                                values.append(val)
                        session.execute(prep, values)
                        count += 1
                        advance(1)
                tw.rows = count
            lines.append(f"[cassandra] inserted {count} row(s) into {keyspace}.{table}")
```

- [ ] **Step 4: Instrument `redis_importer.py`**

Add the same two imports. Dry-run loop:

```python
        for ename, be in entities.items():
            non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
            with metrics.timed_phase("redis", ename, "filter") as t:
                dff = apply_filters(be.df, non_each, be.kinds)
                t.rows = len(dff)
            for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
                lines.append(f"  entity {part_name}: {len(part_df)} row(s)")
```

Live loop:

```python
    for ename, be in entities.items():
        non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
        with metrics.timed_phase("redis", ename, "filter") as t:
            dff = apply_filters(be.df, non_each, be.kinds)
            t.rows = len(dff)
        for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
            if part_df.empty:
                logger.warning("[redis] entity %s has 0 row(s) after filters", part_name)
            count = 0
            first_key = None
            with metrics.timed_phase("redis", part_name, "write") as tw:
                with entity_progress(f"redis · {part_name}", len(part_df)) as advance:
                    for _, row in part_df.iterrows():
                        try:
                            k, v = redis_payload_from_row(row, be.cfg)
                        except ValueError:
                            continue
                        if first_key is None:
                            first_key = k
                        r.set(k, v)
                        count += 1
                        advance(1)
                tw.rows = count
            logger.debug("[redis] SET %d key(s) for %s (first key: %s)", count, part_name, first_key)
            lines.append(f"[redis] SET {count} key(s) for {part_name}")
    return lines
```

- [ ] **Step 5: Instrument `neo4j_importer.py`**

Add the same two imports. Dry-run entity loop:

```python
        for ename, be in entities.items():
            non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
            with metrics.timed_phase("neo4j", ename, "filter") as t:
                dff = apply_filters(be.df, non_each, be.kinds)
                t.rows = len(dff)
            for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
                lines.append(f"  label {part_name}: {len(part_df)} row(s)")
```

Live node loop — wrap the filter the same way, then replace the per-part body (the MERGE query is loop-invariant per part, so hoist and log it once; count duplicate keys skipped for the spec §4.2 warning):

```python
            non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
            with metrics.timed_phase("neo4j", ename, "filter") as t:
                dff = apply_filters(be.df, non_each, be.kinds)
                t.rows = len(dff)
            for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
                plabel = _sanitize_label(part_name)
                q = f"MERGE (n:{plabel} {{{key_name}: $k}}) SET n += $props"
                logger.debug("[neo4j] Cypher: %s (%d row(s))", q, len(part_df))
                if part_df.empty:
                    logger.warning("[neo4j] label %s has 0 row(s) after filters", part_name)
                seen = set()
                merged = 0
                skipped = 0
                with metrics.timed_phase("neo4j", part_name, "write") as tw:
                    with entity_progress(f"neo4j · {part_name}", len(part_df)) as advance:
                        for _, row in part_df.iterrows():
                            props = props_from_row(row, be.cfg)
                            kid = props.get(key_name)
                            if kid is None or kid in seen:
                                if kid is not None:
                                    skipped += 1
                                advance(1)
                                continue
                            seen.add(kid)
                            rest = {k: v for k, v in props.items() if k != key_name}
                            session.run(q, k=kid, props=rest)
                            merged += 1
                            advance(1)
                    tw.rows = merged
                if skipped:
                    logger.warning(
                        "[neo4j] %s: %d duplicate key value(s) skipped (first MERGE wins)",
                        part_name, skipped,
                    )
                lines.append(f"[neo4j] merged {merged} node(s) :{plabel}")
```

Relationship loop — the query is also loop-invariant (merge-key *names* are fixed per relationship); hoist and log it, and record a write metric:

```python
        for rname, rspec in (relationships or {}).items():
            from_label = _sanitize_label(rspec["from"])
            to_label = _sanitize_label(rspec["to"])
            rel_type = _sanitize_label(rspec.get("type") or rname)
            from_be = entities[rspec["from"]]
            to_be = entities[rspec["to"]]
            fk_from = [(fk, sp) for fk, _, sp in flat_leaf_columns(from_be.cfg) if sp.get("is_key")][0]
            fk_to = [(fk, sp) for fk, _, sp in flat_leaf_columns(to_be.cfg) if sp.get("is_key")][0]
            from_key = target_field_name(fk_from[0], fk_from[1])
            to_key = target_field_name(fk_to[0], fk_to[1])
            from_src = resolve_csv_column(fk_from[0], fk_from[1], list(from_be.df.columns))
            to_src = resolve_csv_column(fk_to[0], fk_to[1], list(from_be.df.columns))
            rel_cols = rspec.get("columns") or {}
            mk_names = [
                target_field_name(fk, spec)
                for fk, spec in rel_cols.items()
                if spec.get("is_key")
            ]
            mk_clause = ", ".join(f"{k}: $mk_{k}" for k in mk_names)
            mk_block = f" {{{mk_clause}}}" if mk_clause else ""
            q = (
                f"MATCH (a:{from_label} {{{from_key}: $a_id}}), "
                f"(b:{to_label} {{{to_key}: $b_id}}) "
                f"MERGE (a)-[r:{rel_type}{mk_block}]->(b) SET r += $rprops"
            )
            logger.debug("[neo4j] Cypher: %s", q)
            f1 = [x for x in (from_be.cfg.get("filters") or []) if x.get("operator") != "each"]
            dff = apply_filters(from_be.df, f1, from_be.kinds)
            count = 0
            with metrics.timed_phase("neo4j", f"rel:{rel_type}", "write") as tw:
                with entity_progress(f"neo4j · :{rel_type}", len(dff)) as advance:
                    for _, row in dff.iterrows():
                        a_id = cell_scalar(row[from_src] if from_src in row.index else None)
                        b_id = cell_scalar(row[to_src] if to_src in row.index else None)
                        if a_id is None or b_id is None:
                            advance(1)
                            continue
                        rel_props: Dict[str, Any] = {}
                        csv_columns = list(row.index)
                        for field_key, spec in rel_cols.items():
                            name = target_field_name(field_key, spec)
                            src = resolve_csv_column(field_key, spec, csv_columns)
                            rel_props[name] = cell_scalar(row[src] if src in row.index else None)
                        mk_params = {f"mk_{k}": rel_props[k] for k in mk_names}
                        rest_props = {k: v for k, v in rel_props.items() if k not in mk_names}
                        session.run(q, a_id=a_id, b_id=b_id, rprops=rest_props, **mk_params)
                        count += 1
                        advance(1)
                tw.rows = count
            lines.append(f"[neo4j] merged {count} relationship(s) :{rel_type}")
```

(The old per-row `merge_key_cols`/`merge_keys` computation is replaced by the fixed `mk_names`; behavior is identical because the merge-key *names* never varied per row.)

- [ ] **Step 6: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: 115 passed, 1 skipped.

- [ ] **Step 7: Commit**

```bash
git add src/polyglotimportcsv/importers/cassandra_importer.py src/polyglotimportcsv/importers/redis_importer.py src/polyglotimportcsv/importers/neo4j_importer.py tests/test_importer_metrics.py
git commit -m "feat: instrument cassandra, redis, and neo4j importers"
```

---

### Task 9: `--benchmark` output files

**Files:**
- Modify: `src/polyglotimportcsv/metrics.py` (benchmark writers)
- Modify: `src/polyglotimportcsv/runner.py`
- Modify: `src/polyglotimportcsv/cli.py`
- Test: `tests/test_benchmark_output.py` (new), `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 6's `MetricsCollector`; Task 4's `show_data` plumbing.
- Produces: `metrics.environment_metadata(config_path, source_rows: Dict[str, int]) -> Dict[str, object]`; `metrics.write_benchmark_files(collector, metadata, out_dir: str | Path = "benchmarks") -> Tuple[Path, Path]` (JSON path, CSV path); `run_import(..., benchmark: bool = False)` — forces `show_data=False` and writes the files at the end; CLI `--benchmark` flag.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_benchmark_output.py`:

```python
"""--benchmark: benchmark_<timestamp>.json + consolidatable CSV (spec §4.4)."""

import json
from pathlib import Path

from polyglotimportcsv import metrics
from polyglotimportcsv.metrics import MetricsCollector
from polyglotimportcsv.runner import run_import

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "data" / "ecommerce" / "import_config.json"


def _collector():
    c = MetricsCollector()
    c.record("postgres", "items", "write", rows=10, seconds=0.5)
    return c


def test_write_benchmark_files(tmp_path):
    meta = metrics.environment_metadata(Path("cfg.json"), {"stock": 10})
    json_path, csv_path = metrics.write_benchmark_files(_collector(), meta, out_dir=tmp_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["metadata"]["python"]
    assert data["metadata"]["source_rows"] == {"stock": 10}
    assert data["metrics"][0]["phase"] == "write"
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "timestamp,backend,entity,phase,rows,seconds,rows_per_second"
    assert len(lines) == 2


def test_benchmark_csv_appends_history(tmp_path):
    meta = metrics.environment_metadata(Path("cfg.json"), {})
    metrics.write_benchmark_files(_collector(), meta, out_dir=tmp_path)
    _, csv_path = metrics.write_benchmark_files(_collector(), meta, out_dir=tmp_path)
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3  # one header + two runs


def test_run_import_benchmark_writes_files_and_suppresses_dump(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    forces = []
    monkeypatch.setattr(
        "polyglotimportcsv.runner.dump_entity_frame",
        lambda b, e, df, *, force=None: forces.append(force),
    )

    def stub(cfg, entities, *, dry_run, create_schema):
        return ["[postgres] stub"]

    run_import(CFG, dry_run=True, only=["postgres"], importers={"postgres": stub}, benchmark=True)
    assert forces and all(f is False for f in forces)
    out = tmp_path / "benchmarks"
    assert list(out.glob("benchmark_*.json"))
    assert (out / "benchmark_history.csv").is_file()
```

Append to `tests/test_cli.py`:

```python
def test_cli_benchmark_flag_passes_through(tmp_path, monkeypatch):
    captured = {}

    def fake_run_import(config_path, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr("polyglotimportcsv.cli.run_import", fake_run_import)
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")
    result = CliRunner().invoke(main, ["--config", str(cfg), "--benchmark"])
    assert result.exit_code == 0, result.output
    assert captured["benchmark"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_benchmark_output.py tests/test_cli.py -v`
Expected: FAIL (`AttributeError: environment_metadata`, `KeyError: 'benchmark'`).

- [ ] **Step 3: Add writers to `src/polyglotimportcsv/metrics.py`**

Extend imports:

```python
import csv
import json
import platform
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple
```

Append at the end of the file:

```python
_CSV_FIELDS = ("timestamp", "backend", "entity", "phase", "rows", "seconds", "rows_per_second")


def environment_metadata(
    config_path: "str | Path", source_rows: Dict[str, int]
) -> Dict[str, object]:
    """Run metadata stored with each benchmark (spec §4.4)."""
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "config": str(config_path),
        "source_rows": source_rows,
    }


def write_benchmark_files(
    collector: MetricsCollector,
    metadata: Dict[str, object],
    out_dir: "str | Path" = "benchmarks",
) -> Tuple[Path, Path]:
    """Write benchmark_<timestamp>.json and append benchmark_history.csv."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out / f"benchmark_{stamp}.json"
    json_path.write_text(
        json.dumps(
            {"metadata": metadata, "metrics": collector.to_records()},
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    csv_path = out / "benchmark_history.csv"
    new_file = not csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDS)
        if new_file:
            writer.writeheader()
        ts = metadata.get("timestamp", "")
        for rec in collector.to_records():
            row = {k: rec[k] for k in _CSV_FIELDS if k != "timestamp"}
            row["timestamp"] = ts
            writer.writerow(row)
    return json_path, csv_path
```

- [ ] **Step 4: Wire into `src/polyglotimportcsv/runner.py`**

1. Add `kv` to the `reporting` import list.
2. Add the parameter after `collector` in `run_import` and pass it into `_run` (same name); inside `run_import`'s delegation, force the dump off:

```python
    show_data: Optional[bool] = None,
    collector: Optional[metrics.MetricsCollector] = None,
    benchmark: bool = False,
) -> List[str]:
```

and where `run_import` calls `_run`:

```python
            show_data=False if benchmark else show_data,
            collector=collector,
            benchmark=benchmark,
```

3. `_run` gains `benchmark: bool` and, right after printing the metrics table (before `success(...)`):

```python
    if collector.entries():
        print_rich(metrics_table(collector.to_records()))
    if benchmark:
        meta = metrics.environment_metadata(
            config_path, {n: len(sd.df) for n, sd in sources.items()}
        )
        json_path, csv_path = metrics.write_benchmark_files(collector, meta)
        kv("Benchmark JSON", json_path)
        kv("Benchmark CSV", csv_path)
```

- [ ] **Step 5: Add the CLI flag in `src/polyglotimportcsv/cli.py`**

After `--show-data/--no-data`:

```python
@click.option(
    "--benchmark",
    is_flag=True,
    help="Record per-phase metrics to benchmarks/ after the run (implies --no-data).",
)
```

Add `benchmark: bool,` to `main`'s parameters and `benchmark=benchmark,` to the `run_import(...)` call.

- [ ] **Step 6: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: 119 passed, 1 skipped.

- [ ] **Step 7: Commit**

```bash
git add src/polyglotimportcsv/metrics.py src/polyglotimportcsv/runner.py src/polyglotimportcsv/cli.py tests/test_benchmark_output.py tests/test_cli.py
git commit -m "feat: --benchmark writes benchmarks/ JSON + consolidated CSV"
```

---

### Task 10: Shell integration, docs, gitignore

**Files:**
- Modify: `scripts/console.sh`
- Modify: `run_example.sh`
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`

**Interfaces:**
- Consumes: Task 1's `POLYGLOT_DEBUG_LOG` env contract.
- Produces: `run_example.sh` sessions get **two** files — the existing rendered shell log and one shared Python DEBUG log (`<shell-log>_debug.log`) that every Python step (dry-run, import, clean, inspect) appends to.

- [ ] **Step 1: Export the shared debug-log path in `scripts/console.sh`**

In `init_session_log`, right after `export POLYGLOT_LOG_TEE=1`, add:

```bash
  export POLYGLOT_LOG_TEE=1
  # Python steps append full-DEBUG records here (terminal shows INFO via tee above).
  export POLYGLOT_DEBUG_LOG="${LOG_FILE%.log}_debug.log"
```

- [ ] **Step 2: Surface it in `run_example.sh`**

In the header key/value block (after the existing `POLYGLOT_LOG_FILE` kv):

```bash
if [[ -n "${POLYGLOT_LOG_FILE:-}" ]]; then
  log_kv "Log file" "${POLYGLOT_LOG_FILE}"
fi
if [[ -n "${POLYGLOT_DEBUG_LOG:-}" ]]; then
  log_kv "Debug log" "${POLYGLOT_DEBUG_LOG}"
fi
```

And at the end of the script (after the existing `log_kv "Log saved to" ...` block):

```bash
if [[ -n "${POLYGLOT_LOG_FILE:-}" ]]; then
  log_kv "Log saved to" "${POLYGLOT_LOG_FILE}"
fi
if [[ -n "${POLYGLOT_DEBUG_LOG:-}" && -f "${POLYGLOT_DEBUG_LOG}" ]]; then
  log_kv "Debug log saved to" "${POLYGLOT_DEBUG_LOG}"
fi
```

- [ ] **Step 3: Ignore benchmark outputs**

Append to `.gitignore` (after the `logs/*` block):

```
# Benchmark outputs (--benchmark); consolidated results are cited in the report
benchmarks/
```

- [ ] **Step 4: Document the new flags in `README.md`**

Edit the English flags list — replace the line:

```
- `--only postgres,redis` — run only listed backends.
```

with:

```
- `--only postgres,redis` — run only listed backends.
- `--log-level DEBUG|INFO|WARNING|ERROR` — terminal verbosity (default `INFO`); the session log file under `logs/` always records `DEBUG`.
- `--show-data` / `--no-data` — force or suppress the per-entity record dump (default: entities with up to 50 rows are dumped).
- `--benchmark` — write per-phase metrics to `benchmarks/benchmark_<timestamp>.json` and append `benchmarks/benchmark_history.csv` (implies `--no-data`).
```

Edit the Portuguese flags list — replace the line:

```
- `--only postgres,redis` — executa só os backends listados.
```

with:

```
- `--only postgres,redis` — executa só os backends listados.
- `--log-level DEBUG|INFO|WARNING|ERROR` — verbosidade do terminal (padrão `INFO`); o arquivo de log de sessão em `logs/` sempre grava `DEBUG`.
- `--show-data` / `--no-data` — força ou suprime a exibição dos registros por entidade (padrão: entidades com até 50 linhas são exibidas).
- `--benchmark` — grava métricas por fase em `benchmarks/benchmark_<timestamp>.json` e acrescenta `benchmarks/benchmark_history.csv` (implica `--no-data`).
```

- [ ] **Step 5: Update `docs/ARCHITECTURE.md`**

In the English layering table, replace the Drivers row:

```
| **Drivers / Frameworks** | DB clients, CLI | `cli.py`, `importers/*.py` |
```

with:

```
| **Drivers / Frameworks** | DB clients, CLI, terminal/log output | `cli.py`, `importers/*.py`, `reporting.py` |
```

and the Application row:

```
| **Application / use case** | Orchestration, validation before I/O | `runner.py`, `validation.py` |
```

with:

```
| **Application / use case** | Orchestration, validation before I/O, metrics | `runner.py`, `validation.py`, `metrics.py` |
```

Add a bullet after the "Source pipeline (config v2)" bullet:

```
- **Reporting (rich)**: `reporting.py` drives two destinations — a terminal `RichHandler` filtered by `--log-level` and an always-DEBUG plain-text session file under `logs/`. `metrics.py` collects per-phase (read/filter/map/write) row counts and durations; `--benchmark` persists them under `benchmarks/`.
```

In the Portuguese table, apply the same two row changes:

```
| **Drivers** | Clientes de SGBD, CLI, saída de terminal/log | `cli.py`, `importers/*.py`, `reporting.py` |
| **Caso de uso** | Orquestração, validação antes de I/O, métricas | `runner.py`, `validation.py`, `metrics.py` |
```

and append to the PT prose paragraph (after the sentence ending "não leem CSV diretamente."):

```
A camada de saída usa a biblioteca `rich`: o terminal respeita `--log-level` (padrão INFO) e o arquivo de sessão em `logs/` sempre grava DEBUG em texto puro; `metrics.py` mede linhas e duração por fase (leitura, filtro, mapeamento, escrita) e o flag `--benchmark` persiste os resultados em `benchmarks/`.
```

- [ ] **Step 6: Verify**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: 119 passed, 1 skipped.

Run: `bash -n run_example.sh && bash -n scripts/console.sh`
Expected: no output (syntax OK).

Smoke: `./.venv/Scripts/python.exe -m polyglotimportcsv --config data/ecommerce/import_config.json --dry-run --log-level DEBUG --no-data`
Expected: DEBUG lines (inferred kinds, effective mapping), no record dumps, metrics table at the end; exit 0.

- [ ] **Step 7: Commit**

```bash
git add scripts/console.sh run_example.sh .gitignore README.md docs/ARCHITECTURE.md
git commit -m "docs: rich logging flags in README/ARCHITECTURE; shared debug log for run_example"
```

---

## Self-Review

**Spec coverage (§4 + §3.1 CLI additions):**
- §4.1 `rich` layer replacing `console.py`, `RichHandler`, no scattered `print` → Tasks 1-3 (the only remaining `print` users were cli/runner/inspect, all migrated).
- §4.2 levels: DEBUG statements/mapping/inference (Tasks 5, 7, 8), INFO phases/summary/metrics table (Tasks 3, 6), WARNING text-fallback/empty source-entity/duplicate keys (Tasks 5, 6, 8 — neo4j duplicates; Cassandra/Redis upsert-overwrite detection would need read-before-write and is intentionally not claimed), ERROR via `BusinessException` handler (Task 3). Two destinations with terminal `--log-level` and always-DEBUG file → Tasks 1, 3.
- §4.3 threshold 50, `--show-data`/`--no-data`, benchmark never dumps → Tasks 4, 9.
- §4.4 progress bar above threshold with rows/s, TTY-only → Task 7; MetricsCollector always active per SGBD×entity×phase with final table → Task 6 (documented deviation: `read` is recorded globally as `("(sources)", "*")` because sources load once, not per SGBD; `map` is per backend with entity `"*"`); `--benchmark` JSON + consolidatable CSV with environment metadata → Task 9.
- §3.1 CLI: `--log-level`, `--show-data`/`--no-data`, `--benchmark` → Tasks 3, 4, 9. (`--source` shipped in Plan 1.)
- Out of scope here (Plan 3): §5 dataset generators and `scripts/run_benchmarks.py`; the `collector` injection parameter added in Task 6 is the hook Plan 3's benchmark runner will use.

**Placeholder scan:** every code step carries complete code; the only "rest stays as-is" notes point at file regions the same step shows or that no task touches.

**Type consistency:** `timed_phase`/`timed` yield `_Timed` with mutable `.rows` everywhere; `entity_progress` yields `advance(n=1)` in Tasks 7-8; `dump_entity_frame(backend, entity, df, *, force)` matches the runner call and both monkeypatched fakes; `run_import` keyword additions accumulate as `show_data` (T4) → `collector` (T6) → `benchmark` (T9) in that order, and the T9 tests only use keywords, so order changes are safe; expected suite counts per task assume the stated number of new tests (89→94→95→99→102→108→112→115→119 passed, always 1 skipped) — if a count drifts by the odd test, the gate is "suite green", not the exact number.
