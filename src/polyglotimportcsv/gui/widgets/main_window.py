"""The single window: form on top, integrated CLI below."""

from __future__ import annotations

import json
import os
import re
import shlex
import time
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtWidgets import (
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
from polyglotimportcsv.gui.process import ImportProcess
from polyglotimportcsv.gui.state import DBMS_NAMES, RunOptions, validate
from polyglotimportcsv.gui.widgets.config_panel import ConfigPanel
from polyglotimportcsv.gui.widgets.console_panel import ConsolePanel
from polyglotimportcsv.gui.widgets.options_panel import OptionsPanel
from polyglotimportcsv.gui.widgets.sources_panel import SourcesPanel

LOG_PATH_RE = re.compile(r"Log file\s+(\S+)")
IDLE_STATUS = "Pronto — nenhuma importação em execução"


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
        self.setMinimumSize(960, 680)

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
        self.log_path_label = QLabel("", self)
        status = QStatusBar(self)
        status.addWidget(self.status_label, 1)
        status.addPermanentWidget(self.log_path_label)
        self.setStatusBar(status)

        self.process = ImportProcess(Path(os.getcwd()), self)
        self.process.output.connect(self._on_output)
        self.process.finished.connect(self._on_finished)
        self.process.failed.connect(self._on_failed)

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(500)
        self._elapsed_timer.timeout.connect(self._tick)
        self._started_at = 0.0

        self.config_panel.changed.connect(self._on_config_changed)
        self.options_panel.changed.connect(self.refresh_command)
        self.sources_panel.changed.connect(self.refresh_command)
        self.console_panel.run_requested.connect(self.on_run)
        self.console_panel.stop_requested.connect(self.on_stop)
        self.console_panel.edit_mode_changed.connect(self._on_edit_mode_changed)

        self._settings = settings if settings is not None else QSettings("UFSC", "PolyglotImportCSV")
        self._restore_settings()
        self.refresh_command()

    # -- state ------------------------------------------------------------

    def options(self) -> RunOptions:
        return RunOptions(
            config_path=self.config_panel.config_path(),
            sgbd_config_path=self.config_panel.sgbd_config_path(),
            only=self.options_panel.only(),
            strategy=self.options_panel.strategy(),
            execution=self.options_panel.execution(),
            dry_run=self.options_panel.dry_run(),
            create_schema=self.options_panel.create_schema(),
            benchmark=self.options_panel.benchmark(),
            log_level=self.options_panel.log_level(),
            show_data=self.options_panel.show_data(),
            sources=self.sources_panel.sources(),
        )

    def refresh_command(self) -> None:
        """Rebuild the command text and the validation state from scratch."""
        options = self.options()
        errors = validate(options)
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
            return prefix + [token.strip('"') for token in tokens[1:]]
        return prefix + command_module.build_argv(self.options())

    # -- running ----------------------------------------------------------

    def on_run(self) -> None:
        self.console_panel.clear_output()
        argv = self.argv_for_run()
        self.console_panel.append_output(
            "Executando: {0} …\n".format(" ".join(launcher.resolve()))
        )
        self._set_form_enabled(False)
        self.console_panel.set_running(True)
        self.log_path_label.setText("")
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
        match = LOG_PATH_RE.search(chunk)
        if match:
            self.log_path_label.setText(match.group(1))

    def _on_finished(self, code: int) -> None:
        self._elapsed_timer.stop()
        self._set_form_enabled(True)
        self.console_panel.set_running(False)
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
        self._set_form_enabled(True)
        self.console_panel.set_running(False)
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
