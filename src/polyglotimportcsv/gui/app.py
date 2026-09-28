"""Entry point of the graphical front-end.

A frozen build ships one executable for both roles: when the first argument is
``--cli`` we hand over to the command-line interface instead of opening a
window. That is what lets the GUI spawn itself as the importer.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

import click

from polyglotimportcsv.gui.launcher import CLI_FLAG

_ASSETS = Path(__file__).resolve().parent / "assets"
#: 512 px icon; PNG needs no Qt image-format plugin, so it is the fallback.
ICON_PNG = _ASSETS / "picsv.png"
#: One image per size the Windows shell draws (16-256 px): the window and
#: taskbar icon, and the executable's icon in polyglotimportcsv.spec.
ICON_ICO = _ASSETS / "picsv.ico"
#: Without its own AppUserModelID, a GUI started with "python -m ..." is grouped
#: under python.exe on the Windows taskbar and shows Python's icon there.
APP_USER_MODEL_ID = "UFSC.PolyglotImportCSV"


def _claim_taskbar_identity() -> None:
    """Group the window under its own taskbar entry on Windows (no-op elsewhere)."""
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except (AttributeError, OSError):
        pass  # an old shell without the call: the window icon still applies


def window_icon():
    """The application icon: the ICO's hand-sized images, the PNG for larger sizes.

    Qt otherwise scales one large image down for the 16 and 32 px icons of the
    title bar and taskbar. Imported lazily: the --cli hand-off must not load Qt.
    """
    from PySide6.QtGui import QIcon

    icon = QIcon(str(ICON_ICO))
    icon.addFile(str(ICON_PNG))
    return icon


def main(argv: Optional[List[str]] = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == CLI_FLAG:
        from polyglotimportcsv.cli import main as cli_main

        # standalone_mode=False makes click return instead of calling sys.exit,
        # but it also disables click's own error rendering, so a bad flag
        # would otherwise propagate as a raw ClickException traceback instead
        # of the usual "Error: ..." message with exit code 2. We restore that
        # rendering here ourselves.
        try:
            return cli_main(arguments[1:], standalone_mode=False) or 0
        except click.ClickException as error:
            error.show()
            return error.exit_code
        except click.Abort:
            return 1

    _claim_taskbar_identity()

    from PySide6.QtWidgets import QApplication

    from polyglotimportcsv.gui import indicators
    from polyglotimportcsv.gui.style import STYLESHEET
    from polyglotimportcsv.gui.widgets.main_window import MainWindow

    app = QApplication([sys.argv[0]] + arguments)
    app.setApplicationName("PolyglotImportCSV")
    app.setOrganizationName("UFSC")
    app.setWindowIcon(window_icon())
    # Before the stylesheet: setStyle() resets the style, and the stylesheet
    # has to be applied on top of the style that will actually paint.
    indicators.install(app)
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
