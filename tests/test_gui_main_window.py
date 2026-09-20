"""Wiring: form -> command -> process -> console."""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from polyglotimportcsv.gui.widgets.main_window import MainWindow  # noqa: E402


from PySide6.QtCore import QSettings  # noqa: E402


@pytest.fixture()
def config_files(tmp_path):
    cfg = tmp_path / "import_config.json"
    cfg.write_text("{}", encoding="utf-8")
    sgbd = tmp_path / "sgbd_config.json"
    sgbd.write_text('{"postgres": {}, "redis": {}}', encoding="utf-8")
    return cfg, sgbd


@pytest.fixture()
def window(qtbot, tmp_path):
    """A window with throwaway settings, so no test reads the real ones."""
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    widget = MainWindow(settings=settings)
    qtbot.addWidget(widget)
    return widget


def test_window_opens_with_an_empty_command(window):
    assert window.console_panel.command_text() == "polyglotimportcsv"


def test_choosing_a_config_updates_the_command(window, config_files):
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    assert "--config" in window.console_panel.command_text()
    assert str(cfg) in window.console_panel.command_text()


def test_toggling_an_option_updates_the_command(window, config_files):
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window.options_panel.dry_run_box.setChecked(True)
    assert "--dry-run" in window.console_panel.command_text()


def test_run_is_disabled_until_the_form_is_valid(window, config_files):
    cfg, _ = config_files
    assert not window.console_panel.run_button.isEnabled()
    window.config_panel.set_paths(cfg, None)
    assert window.console_panel.run_button.isEnabled()


def test_validation_errors_reach_the_panels(window, tmp_path):
    window.config_panel.set_paths(tmp_path / "ausente.json", None)
    assert "Arquivo não encontrado" in window.config_panel.error_label.text()


def test_edit_mode_disables_the_form(window, config_files):
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window.console_panel.set_editing(True)
    assert not window.config_panel.isEnabled()
    assert not window.options_panel.isEnabled()
    assert not window.sources_panel.isEnabled()
    window.console_panel.set_editing(False)
    assert window.config_panel.isEnabled()


def test_argv_for_run_uses_the_launcher_prefix(window, config_files):
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    argv = window.argv_for_run()
    assert argv[1:3] == ["-m", "polyglotimportcsv"]
    assert argv[3] == "--config"


def test_argv_for_run_in_edit_mode_uses_the_typed_text(window, config_files):
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window.console_panel.set_editing(True)
    window.console_panel.command_edit.setPlainText("polyglotimportcsv --dry-run")
    assert window.argv_for_run()[-1] == "--dry-run"


def test_declared_dbms_filter_the_checkboxes(window, config_files):
    cfg, sgbd = config_files
    window.config_panel.set_paths(cfg, sgbd)
    assert window.options_panel.dbms_boxes["postgres"].isEnabled()
    assert not window.options_panel.dbms_boxes["neo4j"].isEnabled()


def test_unreadable_sgbd_config_leaves_every_checkbox_enabled(window, tmp_path, config_files):
    cfg, _ = config_files
    broken = tmp_path / "quebrado.json"
    broken.write_text("{ nao e json", encoding="utf-8")
    window.config_panel.set_paths(cfg, broken)
    assert all(box.isEnabled() for box in window.options_panel.dbms_boxes.values())


def test_finishing_with_zero_sets_a_success_status(window, config_files):
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window._on_finished(0)
    assert "Concluído" in window.status_label.text()


def test_finishing_with_non_zero_sets_an_error_status(window, config_files):
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window._on_finished(2)
    assert "código de saída 2" in window.status_label.text()


def test_log_path_is_picked_up_from_the_output(window):
    # This is the real shape printed by reporting.kv("Log file", log_path):
    # a leading indent, a colon after the label, one space, then the path.
    window._on_output("    Log file: logs\\session-20260920-142233.log\n")
    assert "session-20260920-142233.log" in window.log_path_label.text()


def test_log_path_survives_a_split_across_two_chunks(window):
    """I1 robustness: readyRead can split the line at any byte boundary."""
    window._on_output("    Log file: logs\\sess")
    window._on_output("ion-20260920-142233.log\n")
    assert "session-20260920-142233.log" in window.log_path_label.text()


def test_log_path_ignores_a_surrounding_colour_escape(window):
    """I1 robustness: FORCE_COLOR=1 can wrap the dim label in SGR codes."""
    window._on_output("\x1b[2m    Log file: \x1b[0mlogs\\session-20260920-142233.log\n")
    assert window.log_path_label.text() == "logs\\session-20260920-142233.log"


def test_finishing_flushes_a_pending_partial_escape(window, config_files):
    """Ruling 1: a lone trailing partial escape must not be stranded forever."""
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window.console_panel.append_output("linha\x1b[3")
    assert "[3" not in window.console_panel.log_view.toPlainText()
    window._on_finished(0)
    assert "[3" in window.console_panel.log_view.toPlainText()


def test_finishing_does_not_reenable_the_form_while_editing(window, config_files):
    """I2: edit mode must stay in force across a run that ends while active."""
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window.console_panel.set_editing(True)
    window._on_finished(0)
    assert not window.config_panel.isEnabled()
    assert not window.options_panel.isEnabled()
    assert not window.sources_panel.isEnabled()


def test_failing_does_not_reenable_the_form_while_editing(window, config_files):
    """I2: same invariant on the failure path."""
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window.console_panel.set_editing(True)
    window._on_failed("não foi possível iniciar o processo")
    assert not window.config_panel.isEnabled()


def test_on_run_rejects_unbalanced_quotes_in_edit_mode(window, config_files):
    """I3: a malformed edited command must not raise or start a process."""
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window.console_panel.set_editing(True)
    window.console_panel.command_edit.setPlainText('polyglotimportcsv --config "C:\\a b.json')
    window.on_run()
    assert "inválido" in window.status_label.text().lower()
    assert not window.process.is_running()


def test_on_run_preserves_previous_log_on_a_rejected_command(window, config_files):
    """I3: a rejected command must not wipe out the previous run's output."""
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window.console_panel.append_output("saída da execução anterior\n")
    window.console_panel.set_editing(True)
    window.console_panel.command_edit.setPlainText('polyglotimportcsv --config "C:\\a b.json')
    window.on_run()
    assert "saída da execução anterior" in window.console_panel.log_view.toPlainText()


# -- fix round 2 (C3): the happy path through on_run(), end to end ----------


def test_a_full_run_shows_the_child_output_in_the_console(qtbot, window, config_files, monkeypatch):
    """C3: on_run -> process.start -> _on_output -> _on_finished, for real.

    The whole chain had never been exercised: every earlier test called
    on_run() only on its rejection path or poked _on_finished() directly, so
    a run whose console stayed completely blank still reported "Concluído"
    and passed. This test asserts the child's own text is visible, which is
    what C1 (CRLF wiping every line) made false.
    """
    import sys

    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    fake_cli = Path(__file__).parent / "gui_fake_cli.py"
    monkeypatch.setattr(
        window, "argv_for_run", lambda: [sys.executable, str(fake_cli), "0"]
    )

    with qtbot.waitSignal(window.process.finished, timeout=15000) as blocker:
        window.on_run()
    assert blocker.args == [0]
    qtbot.waitUntil(lambda: "Concluído" in window.status_label.text(), timeout=5000)

    text = window.console_panel.log_view.toPlainText()
    assert "primeira linha" in text
    assert "segunda linha" in text
    # The bare "\r" redraw still collapses onto one line, as rich intends.
    assert "progresso 90%" in text
    assert "progresso 10%" not in text
    # And no line the child wrote was erased by its own CRLF terminator.
    body = [line for line in text.splitlines() if line.strip()]
    assert len(body) >= 4  # "Executando: …" plus the three child lines


def test_a_full_run_re_enables_the_form_and_clears_the_running_badge(
    qtbot, window, config_files, monkeypatch
):
    """C3: the run must land back in the idle state, not stay stuck."""
    import sys

    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    fake_cli = Path(__file__).parent / "gui_fake_cli.py"
    monkeypatch.setattr(
        window, "argv_for_run", lambda: [sys.executable, str(fake_cli), "3"]
    )

    with qtbot.waitSignal(window.process.finished, timeout=15000):
        window.on_run()
    qtbot.waitUntil(lambda: "código de saída 3" in window.status_label.text(), timeout=5000)
    assert window.config_panel.isEnabled()
    assert "Executar" in window.console_panel.run_button.text()
