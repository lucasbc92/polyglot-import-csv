"""Run the CLI as a child process and stream its raw output.

This module knows Qt and nothing about ANSI: the console panel owns the
renderer, so the process layer stays a thin, testable wrapper over QProcess.
"""

from __future__ import annotations

import codecs
from pathlib import Path
from typing import Optional, Sequence

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from polyglotimportcsv.gui.launcher import child_environment

TERMINATE_GRACE_MS = 3000


class ImportProcess(QObject):
    """Owns one QProcess running the CLI, and reports what it says.

    Contract: exactly one of ``failed`` or ``finished`` fires per run.
    ``failed`` fires only when the child never started (``FailedToStart``);
    ``finished`` fires whenever the child did start, exit code included, even
    when it crashed or was killed (by :meth:`stop` or otherwise). Qt does not
    emit ``finished`` when a process fails to start, and does emit it on a
    crash, which is what makes this partition exhaustive.
    """

    started = Signal()
    output = Signal(str)
    failed = Signal(str)
    finished = Signal(int)

    def __init__(self, working_dir: Path, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._working_dir = Path(working_dir)
        self._started = False
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.setWorkingDirectory(str(self._working_dir))
        self._process.readyReadStandardOutput.connect(self._on_ready_read)
        self._process.started.connect(self._on_started)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)

    def is_running(self) -> bool:
        return self._process.state() != QProcess.NotRunning

    def start(self, argv: Sequence[str], columns: int = 120, color: bool = True) -> None:
        """Start ``argv`` (launcher prefix included) in the working directory."""
        if self.is_running():
            raise RuntimeError("an import is already running")
        self._started = False
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        environment = QProcessEnvironment.systemEnvironment()
        environment.remove("FORCE_COLOR")
        for key, value in child_environment(columns, color).items():
            environment.insert(key, value)
        self._process.setProcessEnvironment(environment)
        self._process.start(argv[0], list(argv[1:]))

    def stop(self) -> None:
        """Ask the child to quit, then kill it if it is still there."""
        if not self.is_running():
            return
        self._process.terminate()
        QTimer.singleShot(TERMINATE_GRACE_MS, self._kill_if_running)

    # -- internals --------------------------------------------------------

    def _kill_if_running(self) -> None:
        if self.is_running():
            self._process.kill()

    def _on_started(self) -> None:
        self._started = True
        self.started.emit()

    def _on_ready_read(self) -> None:
        data = bytes(self._process.readAllStandardOutput())
        if data:
            self.output.emit(self._decoder.decode(data))

    def _on_finished(self, code: int, _status: object) -> None:
        tail = self._decoder.decode(b"", True)
        if tail:
            self.output.emit(tail)
        self.finished.emit(int(code))

    def _on_error(self, error: object) -> None:
        # A crash reaches Qt as errorOccurred(Crashed) followed by
        # finished(exitCode, CrashExit); a kill from stop() is the same path.
        # Only a process that never started can leave finished() unfired, so
        # that is the only case in which we report `failed`.
        if self._started:
            return
        self.failed.emit(self._process.errorString())
