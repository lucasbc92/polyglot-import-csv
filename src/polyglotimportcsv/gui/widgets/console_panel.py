"""The integrated CLI panel: assembled command, actions and live log."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Signal
from PySide6.QtGui import QFontDatabase, QGuiApplication, QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from polyglotimportcsv.gui.ansi import AnsiRenderer

READ_ONLY_BADGE = "somente leitura"
EDITING_BADGE = "modo de edição"
RUNNING_BADGE = "em execução"
MIN_COLUMNS = 40


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

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("consolePanel")
        self._renderer = AnsiRenderer()
        self._generated = ""
        self._editing = False
        self._running = False
        self._run_enabled = True
        self._rendered_lines = 0

        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)

        self.command_edit = QPlainTextEdit(self)
        self.command_edit.setObjectName("commandEdit")
        self.command_edit.setFont(mono)
        self.command_edit.setReadOnly(True)
        self.command_edit.setMaximumHeight(96)

        self.badge_label = QLabel(READ_ONLY_BADGE, self)
        self.badge_label.setObjectName("badgeLabel")
        self.edit_button = QPushButton("Editar comando", self)
        self.copy_button = QPushButton("Copiar", self)
        self.run_button = QPushButton("▶  Executar", self)
        self.run_button.setObjectName("runButton")

        self.edit_button.clicked.connect(self._toggle_editing)
        self.copy_button.clicked.connect(self._copy)
        self.run_button.clicked.connect(self._on_run_clicked)

        actions = QHBoxLayout()
        actions.addWidget(self.badge_label)
        actions.addStretch(1)
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
        self._editing = editing
        self.command_edit.setReadOnly(not editing)
        self.edit_button.setText("Voltar ao formulário" if editing else "Editar comando")
        self.badge_label.setText(EDITING_BADGE if editing else READ_ONLY_BADGE)
        if not editing:
            self.command_edit.setPlainText(self._generated)
        self.edit_mode_changed.emit(editing)

    # -- run state --------------------------------------------------------

    def set_running(self, running: bool) -> None:
        self._running = running
        self.run_button.setText("■  Interromper" if running else "▶  Executar")
        self.run_button.setProperty("running", running)
        self.run_button.setEnabled(self._run_enabled or running)
        self.edit_button.setEnabled(not running)
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
        self.run_button.setEnabled(enabled or self._running)

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

    def _toggle_editing(self) -> None:
        self.set_editing(not self._editing)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.command_text())

    def _on_run_clicked(self) -> None:
        if self._running:
            self.stop_requested.emit()
        else:
            self.run_requested.emit()
