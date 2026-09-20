"""The integrated CLI panel: command, edit mode and log."""

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from polyglotimportcsv.gui.widgets.console_panel import ConsolePanel  # noqa: E402


def test_command_is_read_only_by_default(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.set_command("polyglotimportcsv --config a.json")
    assert panel.command_edit.isReadOnly()
    assert panel.is_editing() is False
    assert panel.command_text() == "polyglotimportcsv --config a.json"
    assert "somente leitura" in panel.badge_label.text()


def test_entering_edit_mode_unlocks_the_text(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    with qtbot.waitSignal(panel.edit_mode_changed, timeout=1000) as blocker:
        panel.set_editing(True)
    assert blocker.args == [True]
    assert panel.is_editing() is True
    assert not panel.command_edit.isReadOnly()
    assert panel.edit_button.text() == "Voltar ao formulário"


def test_leaving_edit_mode_restores_the_generated_command(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.set_command("polyglotimportcsv --config a.json")
    panel.set_editing(True)
    panel.command_edit.setPlainText("qualquer coisa")
    panel.set_editing(False)
    assert panel.command_text() == "polyglotimportcsv --config a.json"


def test_set_command_is_ignored_while_editing(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.set_editing(True)
    panel.command_edit.setPlainText("texto do usuario")
    panel.set_command("polyglotimportcsv --config b.json")
    assert panel.command_text() == "texto do usuario"


def test_run_button_emits_run_requested(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    with qtbot.waitSignal(panel.run_requested, timeout=1000):
        panel.run_button.click()


def test_running_state_swaps_the_button(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.set_running(True)
    assert "Interromper" in panel.run_button.text()
    assert not panel.edit_button.isEnabled()
    with qtbot.waitSignal(panel.stop_requested, timeout=1000):
        panel.run_button.click()
    panel.set_running(False)
    assert "Executar" in panel.run_button.text()
    assert panel.edit_button.isEnabled()


def test_output_is_rendered_as_html(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.append_output("\x1b[32mok\x1b[0m\n")
    assert "ok" in panel.log_view.toPlainText()


def test_carriage_return_does_not_add_a_line(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.append_output("10%\r90%")
    assert panel.log_view.toPlainText().strip() == "90%"


def test_clear_output_empties_the_log(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.append_output("linha\n")
    panel.clear_output()
    assert panel.log_view.toPlainText().strip() == ""


def test_console_columns_is_positive(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.resize(900, 400)
    assert panel.console_columns() >= 40


def test_run_can_be_disabled(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.set_run_enabled(False)
    assert not panel.run_button.isEnabled()


def test_flush_output_reveals_a_pending_incomplete_escape(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.append_output("linha\x1b[3")
    assert "[3" not in panel.log_view.toPlainText()
    panel.flush_output()
    assert "[3" in panel.log_view.toPlainText()
