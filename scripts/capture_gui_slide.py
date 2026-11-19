"""Capture the GUI for the defense slides: a combined-mode import, all fields set.

The advisor asked the GUI slide to show every field of the form and the whole
command it builds, so the audience sees that the form and the command say the
same thing. The capture reuses the helpers of ``capture_gui_figures.py``: a
real ``MainWindow``, driven through its own panels, with nothing mocked. Nothing
runs; the window is captured idle, with the command already built.

Paths are relative to the repository root (the script changes into it), which
keeps the command short enough to read on a slide; the CLI accepts them as they
are when launched from the root.

Usage, from the repository root::

    .venv/Scripts/python.exe scripts/capture_gui_slide.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capture_gui_figures as cap  # noqa: E402

from polyglotimportcsv.gui import indicators  # noqa: E402
from polyglotimportcsv.gui.style import STYLESHEET  # noqa: E402

OUT = cap.REPO / "docs-tcc" / "apresentacao" / "gui-combinado.png"
CONFIG = Path("data/ecommerce/import_config_combined.json")
DBMS = Path("data/ecommerce/dbms_config.json")
JOINED = Path("data/ecommerce/ecommerce_join.csv")
SIZE = (800, 820)
SPLIT = [660, 140]


def main() -> int:
    os.chdir(cap.REPO)
    app = QApplication([sys.argv[0]])
    indicators.install(app)
    app.setStyleSheet(STYLESHEET)
    with tempfile.TemporaryDirectory() as tmp:
        cap.SIZE = SIZE
        cap.SPLIT = SPLIT
        window = cap.new_window(app, Path(tmp) / "capture.ini", CONFIG, DBMS)
        # Dry run checked, as the advisor asked: the command shown is a simulation.
        window.options_panel.dry_run_box.setChecked(True)
        window.sources_panel.add_row("ecommerce", str(JOINED))
        cap.pump(app, 0.3)
        window.grab().save(str(OUT))
        print(window.console_panel.command_text())
        print("saved", OUT, "-", window.status_label.text())
        window.hide()
    return 0


if __name__ == "__main__":
    sys.exit(main())
