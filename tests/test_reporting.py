"""Reporting core: terminal level vs always-DEBUG session file (spec §4.2)."""

import io
import logging
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
from rich.console import Console

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


def test_default_sample_size_is_fifty():
    assert reporting.DEFAULT_SAMPLE_SIZE == 50


def test_dump_entity_frame_shows_a_sample_of_a_large_entity(capsys):
    reporting.setup_reporting(logging.INFO, no_log=True)
    big = pd.DataFrame({"id": range(120)})
    reporting.dump_entity_frame("postgres", "items", big, sample_size=5)
    out = capsys.readouterr().out
    assert "[5]" in out
    assert "[6]" not in out
    assert "5 of 120 row(s)" in out


def test_dump_entity_frame_default_sample_is_fifty_rows(capsys):
    reporting.setup_reporting(logging.INFO, no_log=True)
    above = pd.DataFrame({"id": range(51)})
    reporting.dump_entity_frame("postgres", "items", above)
    out = capsys.readouterr().out
    assert "[50]" in out
    assert "[51]" not in out
    assert "50 of 51 row(s)" in out


def test_dump_entity_frame_small_entity_is_shown_whole(capsys):
    reporting.setup_reporting(logging.INFO, no_log=True)
    small = pd.DataFrame({"id": range(3)})
    reporting.dump_entity_frame("postgres", "items", small, sample_size=5)
    out = capsys.readouterr().out
    assert "[3]" in out
    assert "3 row(s)" in out
    assert " of " not in out


def test_dump_rows_page_continues_the_numbering(capsys):
    reporting.setup_reporting(logging.INFO, no_log=True)
    reporting.dump_rows_page([{"id": 7}, {"id": 8}], start=11)
    out = capsys.readouterr().out
    assert "[11]" in out and "[12]" in out
    assert "[1]" not in out


def test_dump_entity_frame_force_flags(capsys):
    reporting.setup_reporting(logging.INFO, no_log=True)
    big = pd.DataFrame({"id": range(60)})
    reporting.dump_entity_frame("postgres", "items", big, force=True)
    assert '"id"' in capsys.readouterr().out

    small = pd.DataFrame({"id": [1, 2]})
    reporting.dump_entity_frame("postgres", "items", small, force=False)
    assert '"id"' not in capsys.readouterr().out


def test_entity_progress_noop_at_or_below_threshold(capsys):
    with reporting.entity_progress("x", reporting.PROGRESS_THRESHOLD) as advance:
        assert callable(advance)
        advance(10)
    assert capsys.readouterr().out == ""  # no bar rendered at/below threshold


def test_entity_progress_noop_when_not_a_terminal(capsys):
    with reporting.entity_progress("x", 10_000) as advance:
        assert callable(advance)
        advance(500)  # pytest stdout is not a tty -> no-op path
    assert capsys.readouterr().out == ""


def test_forced_colour_console_never_uses_the_legacy_windows_api():
    console = reporting._make_console({"FORCE_COLOR": "1"})
    assert console.legacy_windows is False


def test_without_forced_colour_the_console_is_left_to_rich():
    """No override when colour is not forced: rich keeps its own detection."""
    console = reporting._make_console({})
    assert console.soft_wrap is True


def test_forced_colour_reaches_a_pipe_as_ansi():
    """The GUI reads the CLI through a pipe; FORCE_COLOR must yield escapes.

    Run in a subprocess so the module-level console is built from this
    environment, exactly as the child process of the GUI builds it.
    """
    script = (
        "from rich.text import Text\n"
        "from polyglotimportcsv import reporting\n"
        "reporting.print_rich(Text('ok', style='green'))\n"
    )
    env = dict(os.environ, FORCE_COLOR="1", POLYGLOT_NO_LOG="1")
    env.pop("NO_COLOR", None)  # Rich honors NO_COLOR over FORCE_COLOR; test must not depend on caller's shell
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, env=env, check=True
    )
    assert b"\x1b[" in result.stdout, result.stdout


def test_metrics_table_never_uses_heavy_box_glyphs():
    """Round 2, finding #2: the GUI console's font lacks the heavy glyphs.

    rich only substitutes ``HEAVY_HEAD`` (the table's default box) for a
    light one when the console is ``legacy_windows`` (see
    ``rich.box.Box.substitute`` / ``LEGACY_WINDOWS_SUBSTITUTIONS``). Task 3
    made the GUI's console ``legacy_windows=False`` so ANSI would reach the
    pipe at all, which left the heavy glyphs (``┏━┳┃┡╇┗┻``) in place; the
    console panel's monospace font has no glyphs for them, Qt falls back to
    a different font with different advance widths, and the table's columns
    visibly misalign. ``metrics_table`` now asks for ``box.SQUARE``
    explicitly, so this holds on every console regardless of
    ``legacy_windows``.
    """
    table = reporting.metrics_table(
        [{"backend": "postgres", "entity": "items", "phase": "write", "rows": 100, "seconds": 2.0,
          "rows_per_second": 50.0}]
    )
    console = Console(file=io.StringIO(), force_terminal=True, legacy_windows=False, width=100)
    console.print(table)
    text = console.file.getvalue()
    for glyph in "┏━┳┃┡╇┗┻":
        assert glyph not in text, "heavy box glyph {0!r} leaked into the table".format(glyph)
    assert "┌" in text
    assert "│" in text
