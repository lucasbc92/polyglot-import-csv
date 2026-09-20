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
    window._on_output("Log file logs\\session-20260920-142233.log\n")
    assert "session-20260920-142233.log" in window.log_path_label.text()


def test_finishing_flushes_a_pending_partial_escape(window, config_files):
    """Ruling 1: a lone trailing partial escape must not be stranded forever."""
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window.console_panel.append_output("linha\x1b[3")
    assert "[3" not in window.console_panel.log_view.toPlainText()
    window._on_finished(0)
    assert "[3" in window.console_panel.log_view.toPlainText()
