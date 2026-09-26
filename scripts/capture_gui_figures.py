"""Recapture the four GUI figures of the TCC report, from the real window.

The first round of figures was captured by hand, which is why they kept a
rendering defect (checkbox and radio indicators painted as nothing) long after
it had been noticed, and why the invalid configuration used by figure 15 was
never kept. This script makes the set reproducible: every figure is a genuine
capture of ``MainWindow``, driven through the same signals a person's clicks
would raise. Nothing is mocked.

Figures 12-14 are one ``--dry-run``, so no database has to be up; figure 15
never runs at all, because the pre-run validation blocks it.

Usage, from the repository root::

    .venv/Scripts/python.exe scripts/capture_gui_figures.py

Run it with the project's own interpreter: the "Executando:" line in figures 13
and 14 shows whichever Python spawned the importer, and the report's figures
show the project venv.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from polyglotimportcsv.gui import indicators
from polyglotimportcsv.gui.style import STYLESHEET
from polyglotimportcsv.gui.widgets.main_window import MainWindow

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data" / "ecommerce"
IMAGES = REPO / "docs-tcc" / "images"
CONFIG = DATA / "import_config.json"
INVALID = DATA / "import_config_invalido.json"
SGBD = DATA / "sgbd_config.json"
SIZE = (1240, 1020)
#: Form/console split of the published figures. A fresh QSettings has no saved
#: splitter position, and the default one leaves the console too short to show
#: any output at all.
SPLIT = [608, 360]


def pump(app: QApplication, seconds: float) -> None:
    """Run the event loop for ``seconds`` without blocking signal delivery."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def pump_until_text(
    app: QApplication, window: MainWindow, needle: str, limit: float = 30.0
) -> None:
    """Pump until ``needle`` reaches the console, the run ends, or time is up."""
    end = time.monotonic() + limit
    while time.monotonic() < end:
        app.processEvents()
        if needle in window.console_panel.log_view.toPlainText():
            return
        if not window.process.is_running():
            return
        time.sleep(0.01)


def pump_until_idle(app: QApplication, window: MainWindow, limit: float = 90.0) -> None:
    end = time.monotonic() + limit
    while window.process.is_running() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)
    pump(app, 0.4)  # let the final chunk render and the status settle


def new_window(app: QApplication, settings_path: Path, config: Path) -> MainWindow:
    """A window in the state shared by every figure, minus the run itself.

    The throwaway QSettings keeps the capture independent of whatever paths the
    developer's own GUI last remembered — and stops this script from
    overwriting them.
    """
    settings = QSettings(str(settings_path), QSettings.IniFormat)
    settings.clear()
    window = MainWindow(settings=settings)
    window.config_panel.set_paths(config, SGBD)
    window._on_config_changed()
    window.options_panel.dry_run_box.setChecked(True)
    window.resize(*SIZE)
    window.splitter.setSizes(SPLIT)
    window.show()
    app.processEvents()
    # Otherwise the --config field keeps the text caret, which no other figure
    # in the report shows.
    focused = app.focusWidget()
    if focused is not None:
        focused.clearFocus()
    app.processEvents()
    return window


def grab(window: MainWindow, name: str) -> None:
    window.grab().save(str(IMAGES / name))
    print("  {0} — {1}".format(name, window.status_label.text()))


def main() -> int:
    for path in (CONFIG, INVALID, SGBD):
        if not path.is_file():
            print("missing: {0}".format(path), file=sys.stderr)
            return 1

    app = QApplication([sys.argv[0]])
    indicators.install(app)
    app.setStyleSheet(STYLESHEET)
    with tempfile.TemporaryDirectory() as tmp:
        settings_path = Path(tmp) / "capture.ini"

        # Figures 12, 13 and 14 are one dry-run caught at three moments, so
        # the command shown is literally the same command throughout.
        window = new_window(app, settings_path, CONFIG)
        grab(window, "figure12-gui-ocioso.png")

        window.on_run()
        # Wait for the run to be visibly under way rather than for a fixed
        # delay, so the figure shows incremental output instead of a console
        # that merely happens to be empty on a slower machine.
        pump_until_text(app, window, "Load sources")
        pump(app, 0.08)  # one render cycle; more scrolls past the opening
        grab(window, "figure13-gui-executando.png")

        pump_until_idle(app, window)
        grab(window, "figure14-gui-sucesso.png")
        window.process.stop()
        window.hide()

        # Figure 15: a configuration whose "stock" source is a number, which
        # satisfies neither branch of the schema. The pre-run validation
        # rejects it before anything runs: the CLI's own message sits in the
        # configuration card and the Run button stays disabled, so there is
        # deliberately no on_run() here.
        failing = new_window(app, settings_path, INVALID)
        pump(app, 0.3)
        assert not failing.console_panel.run_button.isEnabled(), "run must be blocked"
        assert failing.config_panel.error_label.text(), "the schema error must be shown"
        grab(failing, "figure15-gui-erro.png")
        failing.hide()
    return 0


if __name__ == "__main__":
    sys.exit(main())
