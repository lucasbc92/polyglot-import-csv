"""Colour the command in the console panel: program, options, values."""

from __future__ import annotations

from typing import Dict

from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat

from polyglotimportcsv.gui.command import classify

#: Light tones of the console palette (ansi.BRIGHT_COLORS), readable on the
#: panel's dark background.
COLOURS = {"program": "#6EA8FE", "option": "#E7C267", "value": "#57C77A"}


class CommandHighlighter(QSyntaxHighlighter):
    """Re-colours on every change, so it follows typing in edit mode as well."""

    def __init__(self, document) -> None:
        super().__init__(document)
        self._formats = {}  # type: Dict[str, QTextCharFormat]
        for kind, colour in COLOURS.items():
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(colour))
            if kind == "program":
                fmt.setFontWeight(600)
            self._formats[kind] = fmt

    def highlightBlock(self, text: str) -> None:  # noqa: N802 (Qt override)
        for start, length, kind in classify(text):
            self.setFormat(start, length, self._formats[kind])
