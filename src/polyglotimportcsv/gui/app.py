"""Entry point of the graphical front-end.

A frozen build ships one executable for both roles: when the first argument is
``--cli`` we hand over to the command-line interface instead of opening a
window. That is what lets the GUI spawn itself as the importer.
"""

from __future__ import annotations

import sys
from typing import List, Optional

import click

from polyglotimportcsv.gui.launcher import CLI_FLAG


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

    from PySide6.QtWidgets import QApplication

    from polyglotimportcsv.gui.style import STYLESHEET
    from polyglotimportcsv.gui.widgets.main_window import MainWindow

    app = QApplication([sys.argv[0]] + arguments)
    app.setApplicationName("PolyglotImportCSV")
    app.setOrganizationName("UFSC")
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
