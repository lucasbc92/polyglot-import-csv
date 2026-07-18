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
