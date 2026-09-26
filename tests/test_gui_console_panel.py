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


def test_leaving_edit_mode_restores_the_generated_command_after_confirmation(qtbot):
    """I2 / §5: the discard is confirmed, not silent.

    The earlier version of this test asserted the silent discard, which read
    as if it were intentional. The confirmation is injected through
    ``confirm_discard`` so no test ever opens a modal dialog.
    """
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.set_command("polyglotimportcsv --config a.json")
    panel.set_editing(True)
    panel.command_edit.setPlainText("qualquer coisa")
    asked = []
    panel.confirm_discard = lambda: asked.append(True) or True
    panel.set_editing(False)
    assert asked == [True]
    assert panel.is_editing() is False
    assert panel.command_text() == "polyglotimportcsv --config a.json"


def test_cancelling_the_confirmation_keeps_the_edited_command(qtbot):
    """I2: answering no must leave both edit mode and the typed text alone."""
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.set_command("polyglotimportcsv --config a.json")
    panel.set_editing(True)
    panel.command_edit.setPlainText("qualquer coisa")
    panel.confirm_discard = lambda: False
    changes = []
    panel.edit_mode_changed.connect(changes.append)
    panel.set_editing(False)
    assert panel.is_editing() is True
    assert panel.command_text() == "qualquer coisa"
    assert changes == []
    assert panel.edit_button.text() == "Voltar ao formulário"


def test_leaving_edit_mode_unchanged_does_not_ask(qtbot):
    """I2: the question only appears when the text actually differs."""
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.set_command("polyglotimportcsv --config a.json")
    panel.set_editing(True)
    panel.confirm_discard = lambda: pytest.fail("não deveria perguntar")
    panel.set_editing(False)
    assert panel.is_editing() is False


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


def test_sequential_appends_keep_earlier_lines(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.append_output("linha A\n")
    panel.append_output("linha B\n")
    panel.append_output("linha C\n")
    text = panel.log_view.toPlainText()
    assert "linha A" in text
    assert "linha B" in text
    assert "linha C" in text


def test_block_count_matches_rendered_lines(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.append_output("linha A\n")
    panel.append_output("linha B\n")
    panel.append_output("linha C\n")
    assert panel.log_view.document().blockCount() == panel._rendered_lines


def test_a_line_finished_mid_chunk_gets_its_own_block(qtbot):
    """Regression: a coloured run merged the "Import metrics" table's border.

    Root cause (found 2026-09-26, controller round 1): ``_replace_from``
    walked ``first`` blocks from the document start to find where to resume
    rendering. Whenever ``first`` named a line never rendered before —
    ``first == document().blockCount()``, the ordinary case for reporting a
    brand-new line for the first time — the walk could not reach it (every
    existing block index is smaller), fell back to ``QTextCursor.End``, and
    then (since ``offset == 0`` skipped ``insertBlock()``) spliced the new
    line's HTML onto the end of the *previous* line's block instead of
    starting a fresh one.

    This reliably fires whenever one ``append_output`` chunk ends a line
    without a trailing newline and the next chunk both terminates it and
    starts writing the following line — exactly what happens when a real
    ``QProcess`` delivers rich's output as it streams the child's stdout:
    confirmed in the evidence capture by feeding the CLI's actual
    ``--dry-run`` bytes (``FORCE_COLOR=1``) through ``ConsolePanel`` in
    small, unaligned chunks, which merged the table's top border into its
    header-separator line, identically to
    ``evidence/task10-e-dry-run-coloured.png``.

    The two lines below are the real box-drawing bytes rich emits for the
    "Import metrics" table's top border and header separator (captured via
    ``python -m polyglotimportcsv --config data/ecommerce/import_config.json
    --dry-run`` with ``FORCE_COLOR=1``), split at the exact chunk boundary
    that reproduces the bug: the first call ends the border line without a
    trailing newline, and the second terminates it and writes the whole next
    line in one shot.
    """
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    top_border = (
        "┏" + "━" * 11 + "┳" + "━" * 8 + "┳" + "━" * 7
        + "┳" + "━" * 6 + "┳" + "━" * 9 + "┳" + "━" * 8
        + "┓"
    )
    header_separator = (
        "┡" + "━" * 11 + "╇" + "━" * 8 + "╇" + "━" * 7
        + "╇" + "━" * 6 + "╇" + "━" * 9 + "╇" + "━" * 8
        + "┩"
    )
    panel.append_output("Import metrics\n" + top_border)
    panel.append_output("\n" + header_separator + "\n")

    document = panel.log_view.document()
    assert document.blockCount() == panel._rendered_lines
    # Spaces render as U+00A0 (_render's &nbsp; substitution keeps runs from
    # collapsing); normalize back to compare against the plain source text.
    rendered = [
        document.findBlockByNumber(i).text().replace(" ", " ")
        for i in range(document.blockCount())
    ]
    assert rendered == ["Import metrics", top_border, header_separator, " "]


def test_set_running_false_respects_run_enabled_false(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.set_run_enabled(False)
    panel.set_running(True)
    panel.set_running(False)
    assert not panel.run_button.isEnabled()


def test_set_editing_is_ignored_while_running(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.set_running(True)
    panel.set_editing(True)
    assert panel.is_editing() is False
    assert panel.command_edit.isReadOnly()
    assert "em execução" in panel.badge_label.text()


# -- fix round 2: edit mode governs the run button, and the launcher prefix
# is visible as a tooltip -------------------------------------------------


def test_run_is_enabled_in_edit_mode_for_any_non_empty_text(qtbot):
    """I6: the typed text is the source of truth, so the form must not gate it."""
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.set_run_enabled(False)  # the form is invalid — nothing chosen yet
    assert not panel.run_button.isEnabled()
    panel.set_editing(True)
    panel.command_edit.setPlainText("polyglotimportcsv --config a.json --dry-run")
    assert panel.run_button.isEnabled()


def test_run_is_disabled_in_edit_mode_for_empty_text(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.set_editing(True)
    panel.command_edit.setPlainText("   ")
    assert not panel.run_button.isEnabled()


def test_leaving_edit_mode_restores_the_form_derived_enablement(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.set_run_enabled(False)
    panel.set_editing(True)
    panel.command_edit.setPlainText("polyglotimportcsv --dry-run")
    assert panel.run_button.isEnabled()
    panel.confirm_discard = lambda: True
    panel.set_editing(False)
    assert not panel.run_button.isEnabled()


def test_launcher_prefix_is_shown_as_a_tooltip(qtbot):
    """I3 / §6.1: the displayed-vs-executed divergence is named in the UI."""
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.set_launcher_prefix(r"C:\py.exe -m polyglotimportcsv")
    assert r"C:\py.exe -m polyglotimportcsv" in panel.command_edit.toolTip()
    assert "polyglotimportcsv" in panel.toolTip()


from PySide6.QtGui import QColor  # noqa: E402

from polyglotimportcsv.gui.widgets.command_highlighter import COLOURS  # noqa: E402


def _colour_at(panel, position):
    block = panel.command_edit.document().firstBlock()
    for fmt in block.layout().formats():
        if fmt.start <= position < fmt.start + fmt.length:
            return fmt.format.foreground().color().name().upper()
    return None


def test_the_command_is_coloured_by_token_kind(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.set_command("polyglotimportcsv --config c.json")
    assert _colour_at(panel, 0) == QColor(COLOURS["program"]).name().upper()
    assert _colour_at(panel, len("polyglotimportcsv ")) == QColor(COLOURS["option"]).name().upper()
    assert _colour_at(panel, len("polyglotimportcsv --config ")) == (
        QColor(COLOURS["value"]).name().upper()
    )


def test_typed_text_is_coloured_too(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.set_editing(True)
    panel.command_edit.setPlainText("--dry-run")
    assert _colour_at(panel, 0) == QColor(COLOURS["option"]).name().upper()


def test_save_log_starts_disabled(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    assert panel.save_log_button.text() == "Salvar log…"
    assert not panel.save_log_button.isEnabled()


def test_save_log_is_enabled_when_a_log_is_available_and_nothing_runs(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.set_log_available(True)
    assert panel.save_log_button.isEnabled()
    panel.set_running(True)
    assert not panel.save_log_button.isEnabled()
    panel.set_running(False)
    assert panel.save_log_button.isEnabled()


def test_clicking_save_log_emits_the_request(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.set_log_available(True)
    with qtbot.waitSignal(panel.save_log_requested, timeout=1000):
        panel.save_log_button.click()
