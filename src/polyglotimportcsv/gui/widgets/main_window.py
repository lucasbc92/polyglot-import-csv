"""The single window: form on top, integrated CLI below."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QSettings, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from polyglotimportcsv.gui import command as command_module
from polyglotimportcsv.gui import launcher
from polyglotimportcsv.gui import preflight
from polyglotimportcsv.gui.process import ImportProcess
from polyglotimportcsv.gui.state import DBMS_NAMES, RunOptions, validate
from polyglotimportcsv.gui.widgets.config_panel import ConfigPanel
from polyglotimportcsv.gui.widgets.console_panel import ConsolePanel
from polyglotimportcsv.gui.widgets.options_panel import OptionsPanel
from polyglotimportcsv.gui.widgets.sources_panel import SourcesPanel

# I4: the path is captured to the end of its own line, not with \S+. The real
# CLI prints path.resolve(), an absolute path, and on Windows those routinely
# contain spaces ("C:\Users\Lucas Bueno\..."); \S+ stopped at the first space
# and showed the user a truncated path. The per-line $ anchor also means a
# match can only complete once the line's newline has arrived, which is what
# makes the mid-chunk truncation check below reliable.
LOG_PATH_RE = re.compile(r"Log file:[ \t]*(.+?)[ \t\r]*$", re.MULTILINE)
# Strips SGR/CSI escape codes before searching for the log path: FORCE_COLOR=1
# lets rich wrap the "Log file:" label in a dim escape (reporting.kv() styles
# only the label span), which would otherwise land right before the path and
# defeat a plain \s* boundary.
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
# Bounds the tail kept across chunks while still hunting for the log path
# line, in case readyReadStandardOutput ever splits it mid-token.
_LOG_SEARCH_LIMIT = 4096
IDLE_STATUS = "Pronto — nenhuma importação em execução"
INVALID_EDIT_STATUS = "Comando inválido: aspas não fechadas"


class _PathLabel(QLabel):
    """The status-bar log path: plain text, and a click opens its folder."""

    clicked = Signal()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.LeftButton and self.text():
            self.clicked.emit()
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    """Owns the panels, the process and the transitions between states."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        settings: Optional[QSettings] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("PolyglotImportCSV")
        self.resize(1240, 1020)
        # M2: 680 was a guess made before any layout existed; measured, the
        # splitter's real floor is 773 (form 608 + console 200 - handle),
        # so anything below ~814 clips the option rows and collapses the
        # sources table to its header. 820 leaves a small margin.
        self.setMinimumSize(960, 820)

        self.config_panel = ConfigPanel(self)
        self.options_panel = OptionsPanel(self)
        self.sources_panel = SourcesPanel(self)
        self.console_panel = ConsolePanel(self)

        form = QWidget(self)
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.addWidget(self.config_panel)
        form_layout.addWidget(self.options_panel)
        form_layout.addWidget(self.sources_panel)

        splitter = QSplitter(Qt.Vertical, self)
        splitter.addWidget(form)
        splitter.addWidget(self.console_panel)
        splitter.setStretchFactor(1, 1)
        self.console_panel.setMinimumHeight(160)
        self.splitter = splitter

        container = QWidget(self)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(12, 12, 12, 8)
        container_layout.addWidget(splitter)
        self.setCentralWidget(container)

        self.status_label = QLabel(IDLE_STATUS, self)
        self.log_path_label = _PathLabel("", self)
        self.log_path_label.setCursor(Qt.PointingHandCursor)
        self.log_path_label.setToolTip("Abrir a pasta do log")
        self.log_path_label.clicked.connect(self._open_log_folder)
        status = QStatusBar(self)
        status.addWidget(self.status_label, 1)
        status.addPermanentWidget(self.log_path_label)
        self.setStatusBar(status)

        # Guarded here because it is where the CLI resolves "logs/" too: the
        # child process is spawned with this directory as its own cwd.
        self._working_dir = Path(os.getcwd())
        self.process = ImportProcess(self._working_dir, self)
        self.process.output.connect(self._on_output)
        self.process.finished.connect(self._on_finished)
        self.process.failed.connect(self._on_failed)

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(500)
        self._elapsed_timer.timeout.connect(self._tick)
        self._started_at = 0.0
        self._log_search_buffer = ""
        self._log_path_found = False
        self._log_path = None  # type: Optional[Path]

        self.config_panel.changed.connect(self._on_config_changed)
        self.options_panel.changed.connect(self.refresh_command)
        self.sources_panel.changed.connect(self.refresh_command)
        self.console_panel.run_requested.connect(self.on_run)
        self.console_panel.stop_requested.connect(self.on_stop)
        self.console_panel.edit_mode_changed.connect(self._on_edit_mode_changed)
        self.console_panel.save_log_requested.connect(self._save_log)

        # I3 / §6.1: the resolved launcher prefix is the one divergence between
        # the command shown and the process spawned, and the spec mitigates it
        # with a tooltip as well as the "Executando:" log line.
        self.console_panel.set_launcher_prefix(" ".join(launcher.resolve()))

        # Injection points, so tests never open a real dialog or file manager.
        self.choose_log_destination = self._ask_log_destination  # type: Callable[[Path], str]
        self.show_error = self._show_error  # type: Callable[[str], None]
        self.open_folder = self._open_folder_in_file_manager  # type: Callable[[Path], None]

        self._settings = settings if settings is not None else QSettings("UFSC", "PolyglotImportCSV")
        self._restore_settings()
        self.refresh_command()

    # -- state ------------------------------------------------------------

    def options(self) -> RunOptions:
        return RunOptions(
            config_path=self.config_panel.config_path(),
            sgbd_config_path=self.config_panel.sgbd_config_path(),
            only=self.options_panel.only(),
            execution=self.options_panel.execution(),
            dry_run=self.options_panel.dry_run(),
            create_schema=self.options_panel.create_schema(),
            log_level=self.options_panel.log_level(),
            show_data=self.options_panel.show_data(),
            sample_size=self.options_panel.sample_size(),
            sources=self.sources_panel.sources(),
        )

    def refresh_command(self) -> None:
        """Rebuild the command text and the validation state from scratch."""
        options = self.options()
        checked = preflight.check(options)
        # Local errors win: they describe the form itself (a missing path, a
        # repeated name), and the preflight skips whatever they already cover.
        errors = dict(checked.errors)
        errors.update(validate(options))
        self.sources_panel.set_source_kind(checked.kind, checked.declared)
        self.config_panel.set_errors(errors)
        self.options_panel.set_errors(errors)
        self.sources_panel.set_errors(errors)
        self.console_panel.set_command(command_module.to_display(command_module.build_argv(options)))
        self.console_panel.set_run_enabled(not errors)

    def argv_for_run(self) -> List[str]:
        """Full argv to spawn: launcher prefix plus the arguments."""
        prefix = launcher.resolve()
        if self.console_panel.is_editing():
            tokens = shlex.split(self.console_panel.command_text(), posix=os.name != "nt")
            # I5: drop the first token only when it is the program name, which
            # the resolved prefix replaces. Dropping it unconditionally turned
            # a typed "--dry-run" into a run with no arguments at all.
            if tokens and command_module.is_program_token(tokens[0]):
                tokens = tokens[1:]
            return prefix + [token.strip('"') for token in tokens]
        return prefix + command_module.build_argv(self.options())

    # -- running ----------------------------------------------------------

    def on_run(self) -> None:
        # I3: resolve argv before touching anything else. shlex.split raises
        # ValueError on an edited command with an unbalanced quote (e.g. a
        # pasted Windows path), and the previous run's log must survive that
        # rejection instead of being wiped by an early clear_output().
        try:
            argv = self.argv_for_run()
        except ValueError:
            self.status_label.setText(INVALID_EDIT_STATUS)
            return
        self.console_panel.clear_output()
        self.console_panel.append_output(
            "Executando: {0} …\n".format(" ".join(launcher.resolve()))
        )
        self._set_form_enabled(False)
        self.console_panel.set_running(True)
        self.log_path_label.setText("")
        self._log_search_buffer = ""
        self._log_path_found = False
        self._log_path = None
        self.console_panel.set_log_available(False)
        self._started_at = time.monotonic()
        self._elapsed_timer.start()
        self.status_label.setText("Executando — 00:00 decorridos")
        self.process.start(argv, self.console_panel.console_columns(), True)

    def on_stop(self) -> None:
        confirmed = QMessageBox.question(
            self,
            "Interromper a importação",
            "A importação pode parar pela metade e deixar dados parcialmente "
            "gravados. Interromper mesmo assim?",
        )
        if confirmed == QMessageBox.Yes:
            self.process.stop()

    # -- signal handlers --------------------------------------------------

    def _on_output(self, chunk: str) -> None:
        self.console_panel.append_output(chunk)
        # I1: the CLI prints "    Log file: <path>", not "Log file <path>",
        # so the regex must expect the colon. It is also matched against
        # ANSI-stripped, cross-chunk text: readyReadStandardOutput can split
        # the line at any byte boundary, and FORCE_COLOR=1 can wrap the
        # label in an SGR escape that would otherwise sit between the label
        # and the path.
        if self._log_path_found:
            return
        self._log_search_buffer += chunk
        stripped = _ANSI_RE.sub("", self._log_search_buffer)
        match = LOG_PATH_RE.search(stripped)
        # A match that reaches the end of the buffered text may just be a
        # path truncated mid-chunk: with the per-line $ anchor, the end of
        # the buffer is itself a valid anchor point. Only accept the match
        # once something follows it — normally the line's own newline —
        # otherwise keep buffering.
        if match and match.end() < len(stripped):
            text = match.group(1)
            self.log_path_label.setText(text)
            path = Path(text)
            self._log_path = path if path.is_absolute() else self._working_dir / path
            self._log_path_found = True
            self._log_search_buffer = ""
        else:
            self._log_search_buffer = self._log_search_buffer[-_LOG_SEARCH_LIMIT:]

    def _on_finished(self, code: int) -> None:
        self._elapsed_timer.stop()
        # I2: a run that ends while the user is mid-edit must not silently
        # re-enable the form — set_command() is ignored while editing, so
        # the displayed command would stop tracking the form even though
        # argv_for_run() still executes whatever text is typed.
        self._set_form_enabled(not self.console_panel.is_editing())
        self.console_panel.set_running(False)
        self.console_panel.set_log_available(self._log_path is not None)
        # Ruling 1: a lone trailing partial escape sequence must not be
        # stranded inside the renderer forever, so flush before reporting
        # the final status.
        self.console_panel.flush_output()
        elapsed = time.monotonic() - self._started_at if self._started_at else 0.0
        if code == 0:
            self.status_label.setText("Concluído — {0:.2f} s".format(elapsed))
        else:
            self.status_label.setText("Falhou — código de saída {0}".format(code))

    def _on_failed(self, message: str) -> None:
        self._elapsed_timer.stop()
        # I2: same invariant as _on_finished.
        self._set_form_enabled(not self.console_panel.is_editing())
        self.console_panel.set_running(False)
        self.console_panel.set_log_available(self._log_path is not None)
        # Ruling 1: same as _on_finished — flush before the final append and
        # status, so nothing withheld by the renderer is lost.
        self.console_panel.flush_output()
        self.console_panel.append_output("\x1b[31m{0}\x1b[0m\n".format(message))
        self.status_label.setText("Falhou — {0}".format(message))

    def _on_edit_mode_changed(self, editing: bool) -> None:
        self._set_form_enabled(not editing)
        if not editing:
            self.refresh_command()

    def _on_config_changed(self) -> None:
        self.options_panel.set_available_dbms(self._declared_dbms())
        self.refresh_command()

    def _tick(self) -> None:
        elapsed = int(time.monotonic() - self._started_at)
        self.status_label.setText(
            "Executando — {0:02d}:{1:02d} decorridos".format(elapsed // 60, elapsed % 60)
        )

    # -- internals --------------------------------------------------------

    def _set_form_enabled(self, enabled: bool) -> None:
        for panel in (self.config_panel, self.options_panel, self.sources_panel):
            panel.setEnabled(enabled)

    def _declared_dbms(self) -> Optional[List[str]]:
        """Names declared in the chosen sgbd_config.json, or None if unreadable."""
        path = self.config_panel.sgbd_config_path()
        if path is None or not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        if not isinstance(data, dict):
            return None
        declared = [name for name in DBMS_NAMES if name in data]
        return declared or None

    def log_path(self) -> Optional[Path]:
        """The session log of the last run, once the CLI has announced it."""
        return self._log_path

    def _save_log(self) -> None:
        source = self._log_path
        if source is None:
            return
        target = self.choose_log_destination(source)
        if not target:
            return
        try:
            shutil.copyfile(str(source), target)
        except OSError as exc:
            self.show_error("Não foi possível salvar o log: {0}".format(exc))
            return
        self.status_label.setText("Log salvo em {0}".format(target))

    def _ask_log_destination(self, suggested: Path) -> str:
        chosen, _ = QFileDialog.getSaveFileName(
            self, "Salvar log", suggested.name, "Log (*.log);;Todos (*)"
        )
        return chosen

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Salvar log", message)

    def _open_log_folder(self) -> None:
        text = self.log_path_label.text()
        if text:
            path = Path(text)
            path = path if path.is_absolute() else self._working_dir / path
            self.open_folder(path.parent)

    @staticmethod
    def _open_folder_in_file_manager(folder: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _restore_settings(self) -> None:
        geometry = self._settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        splitter_state = self._settings.value("splitter")
        if splitter_state is not None:
            self.splitter.restoreState(splitter_state)
        last_config = self._settings.value("last_config")
        last_sgbd = self._settings.value("last_sgbd")
        if last_config or last_sgbd:
            self.config_panel.set_paths(
                Path(last_config) if last_config else None,
                Path(last_sgbd) if last_sgbd else None,
            )

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("splitter", self.splitter.saveState())
        config = self.config_panel.config_path()
        sgbd = self.config_panel.sgbd_config_path()
        self._settings.setValue("last_config", str(config) if config else "")
        self._settings.setValue("last_sgbd", str(sgbd) if sgbd else "")
        if self.process.is_running():
            self.process.stop()
        super().closeEvent(event)
