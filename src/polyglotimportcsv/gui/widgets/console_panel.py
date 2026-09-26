"""The integrated CLI panel: assembled command, actions and live log."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Signal
from PySide6.QtGui import QFontDatabase, QGuiApplication, QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from polyglotimportcsv.gui.ansi import AnsiRenderer
from polyglotimportcsv.gui.command import PROGRAM
from polyglotimportcsv.gui.launcher import MIN_COLUMNS
from polyglotimportcsv.gui.widgets.command_highlighter import CommandHighlighter

READ_ONLY_BADGE = "somente leitura"
EDITING_BADGE = "modo de edição"
RUNNING_BADGE = "em execução"
DISCARD_TITLE = "Descartar o comando editado"
DISCARD_QUESTION = (
    "O comando foi alterado à mão. Voltar ao formulário descarta o texto "
    "digitado e remonta o comando a partir dos controles. Descartar mesmo assim?"
)
LAUNCHER_TOOLTIP = (
    "O comando exibido começa por «{program}», que é o que se digitaria em um "
    "terminal. O processo realmente iniciado usa o prefixo resolvido para esta "
    "instalação:\n\n{prefix}\n\nO restante dos argumentos é idêntico ao exibido."
)
# MIN_COLUMNS is re-exported from launcher rather than redefined: it is the
# same floor the child's COLUMNS environment variable is clamped to, and two
# copies could drift apart silently.
__all__ = ["ConsolePanel", "MIN_COLUMNS"]


class ConsolePanel(QFrame):
    """Shows the command that will run, and the output of the run.

    The panel knows nothing about ``RunOptions``: the window hands it
    finished text and receives back ``run_requested``/``stop_requested``
    signals. This keeps the edit-mode interaction (the trickiest part)
    testable in isolation, since the panel never has to parse or rebuild
    the command it displays.
    """

    run_requested = Signal()
    stop_requested = Signal()
    edit_mode_changed = Signal(bool)
    save_log_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("consolePanel")
        self._renderer = AnsiRenderer()
        self._generated = ""
        self._editing = False
        self._running = False
        self._run_enabled = True
        self._rendered_lines = 0
        self._log_available = False
        # I2: injection point for the "discard the edited command?" question.
        # Tests replace it so no modal dialog is ever opened headlessly.
        self.confirm_discard = self._ask_discard_confirmation

        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)

        self.command_edit = QPlainTextEdit(self)
        self.command_edit.setObjectName("commandEdit")
        self.command_edit.setFont(mono)
        self.command_edit.setReadOnly(True)
        self.command_edit.setMaximumHeight(96)

        self._highlighter = CommandHighlighter(self.command_edit.document())

        self.badge_label = QLabel(READ_ONLY_BADGE, self)
        self.badge_label.setObjectName("badgeLabel")
        self.edit_button = QPushButton("Editar comando", self)
        self.copy_button = QPushButton("Copiar", self)
        self.run_button = QPushButton("▶  Executar", self)
        self.run_button.setObjectName("runButton")
        self.save_log_button = QPushButton("Salvar log…", self)
        self.save_log_button.setToolTip(
            "Salvar uma cópia do arquivo de log desta execução (nível DEBUG, sem cores)"
        )
        self.save_log_button.setEnabled(False)
        self.save_log_button.clicked.connect(self.save_log_requested)

        # I6: while editing, the typed text governs whether a run is possible,
        # so the button has to follow the text rather than the (disabled) form.
        self.command_edit.textChanged.connect(self._update_run_enabled)

        self.edit_button.clicked.connect(self._toggle_editing)
        self.copy_button.clicked.connect(self._copy)
        self.run_button.clicked.connect(self._on_run_clicked)

        actions = QHBoxLayout()
        actions.addWidget(self.badge_label)
        actions.addStretch(1)
        actions.addWidget(self.save_log_button)
        actions.addWidget(self.edit_button)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.run_button)

        self.log_view = QTextEdit(self)
        self.log_view.setObjectName("logView")
        self.log_view.setFont(mono)
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QTextEdit.NoWrap)

        layout = QVBoxLayout(self)
        layout.addWidget(self.command_edit)
        layout.addLayout(actions)
        layout.addWidget(self.log_view, 1)

    # -- command ----------------------------------------------------------

    def set_command(self, text: str) -> None:
        """Set the generated command; ignored while the user is editing."""
        self._generated = text
        if not self._editing:
            self.command_edit.setPlainText(text)

    def command_text(self) -> str:
        return self.command_edit.toPlainText()

    def is_editing(self) -> bool:
        return self._editing

    def has_manual_edits(self) -> bool:
        """True when the displayed text no longer matches the generated one."""
        return self._editing and self.command_text() != self._generated

    def set_launcher_prefix(self, prefix: str) -> None:
        """Show the resolved launcher prefix (§6.1) as the panel's tooltip.

        §6.1 names two mitigations for the one divergence between the command
        shown and the process spawned: this tooltip and the "Executando:" log
        line. Only the log line existed before.
        """
        tooltip = LAUNCHER_TOOLTIP.format(program=PROGRAM, prefix=prefix)
        self.setToolTip(tooltip)
        self.command_edit.setToolTip(tooltip)
        self.badge_label.setToolTip(tooltip)

    def set_editing(self, editing: bool) -> None:
        if self._running:
            # The command must stay locked and the "em execução" badge must
            # stay in force while a child process is running, regardless of
            # what a caller asks for. Task 10's MainWindow already disables
            # edit_button while running, but the panel enforces the
            # invariant itself rather than trusting the caller's discipline.
            return
        if editing == self._editing:
            return
        # I2 / §5: "Voltar ao formulário" discards whatever was typed, so it
        # asks first whenever the text actually differs from the generated
        # command. Cancelling leaves edit mode — and the typed text — intact.
        if not editing and self.has_manual_edits() and not self.confirm_discard():
            return
        self._editing = editing
        self.command_edit.setReadOnly(not editing)
        self.edit_button.setText("Voltar ao formulário" if editing else "Editar comando")
        self.badge_label.setText(EDITING_BADGE if editing else READ_ONLY_BADGE)
        if not editing:
            self.command_edit.setPlainText(self._generated)
        self._update_run_enabled()
        self.edit_mode_changed.emit(editing)

    # -- run state --------------------------------------------------------

    def set_running(self, running: bool) -> None:
        self._running = running
        self.run_button.setText("■  Interromper" if running else "▶  Executar")
        self.run_button.setProperty("running", running)
        self._update_run_enabled()
        self.edit_button.setEnabled(not running)
        self.save_log_button.setEnabled(self._log_available and not running)
        self.command_edit.setReadOnly(running or not self._editing)
        if running:
            self.badge_label.setText(RUNNING_BADGE)
        else:
            self.badge_label.setText(EDITING_BADGE if self._editing else READ_ONLY_BADGE)
        self.run_button.style().unpolish(self.run_button)
        self.run_button.style().polish(self.run_button)

    def set_run_enabled(self, enabled: bool) -> None:
        """Enable or disable the run button, unless a run is in progress.

        While ``_running`` is true, this same button is the Interromper
        button, so disabling it here would strand the user with no way to
        stop the child process. The requested state is remembered so that
        ``set_running(False)`` can restore it instead of unconditionally
        re-enabling the button (e.g. when the form is still invalid).
        """
        self._run_enabled = enabled
        self._update_run_enabled()

    def set_log_available(self, available: bool) -> None:
        """Offer "Salvar log…" once a finished run has left a log behind."""
        self._log_available = available
        self.save_log_button.setEnabled(available and not self._running)

    # -- log --------------------------------------------------------------

    def append_output(self, chunk: str) -> None:
        """Feed one decoded chunk of CLI output into the log view."""
        self._renderer.feed(chunk)
        self._apply_update()

    def flush_output(self) -> None:
        """Flush any buffered incomplete escape sequence and repaint.

        Task 10's ``MainWindow`` calls this when the child process ends, so
        a trailing partial escape sequence withheld by the renderer is not
        lost and its literal text still reaches the log.
        """
        self._renderer.flush()
        self._apply_update()

    def clear_output(self) -> None:
        self._renderer = AnsiRenderer()
        self._rendered_lines = 0
        self.log_view.clear()

    def console_columns(self) -> int:
        metrics = self.log_view.fontMetrics()
        width = max(1, metrics.horizontalAdvance("0"))
        return max(MIN_COLUMNS, self.log_view.viewport().width() // width)

    # -- internals --------------------------------------------------------

    def _apply_update(self) -> None:
        first, lines = self._renderer.take_update()
        # ``take_update`` guarantees first + len(lines) == line_count, and
        # ``_trim`` resets the dirty marker to 0 on any shrink, so an empty
        # ``lines`` here can only mean nothing changed since the last call
        # — never that content should be deleted. The guard below is thus
        # load-bearing, not defensive paranoia.
        if not lines and first >= self._rendered_lines:
            return
        self._replace_from(first, lines)

    def _replace_from(self, first: int, lines: List[str]) -> None:
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.Start)
        for _ in range(first):
            if not cursor.movePosition(QTextCursor.NextBlock):
                cursor.movePosition(QTextCursor.End)
                break
        cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        for offset, line in enumerate(lines):
            if offset:
                cursor.insertBlock()
            cursor.insertHtml(line)
        self._rendered_lines = first + len(lines)
        scrollbar = self.log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _update_run_enabled(self) -> None:
        """Decide whether the main button can be pressed, in every state."""
        if self._running:
            # It is the Interromper button now: it must always be pressable.
            self.run_button.setEnabled(True)
        elif self._editing:
            # I6: edit mode declares the typed text the source of truth and
            # disables the form, so gating the button on the form's own
            # validation would leave a complete, valid typed command greyed
            # out with no explanation. Any non-empty text can be run.
            self.run_button.setEnabled(bool(self.command_text().strip()))
        else:
            self.run_button.setEnabled(self._run_enabled)

    def _ask_discard_confirmation(self) -> bool:
        """Ask before throwing away a hand-edited command (§5)."""
        answer = QMessageBox.question(self, DISCARD_TITLE, DISCARD_QUESTION)
        return answer == QMessageBox.Yes

    def _toggle_editing(self) -> None:
        self.set_editing(not self._editing)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.command_text())

    def _on_run_clicked(self) -> None:
        if self._running:
            self.stop_requested.emit()
        else:
            self.run_requested.emit()
