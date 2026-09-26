"""A small round "i" whose tooltip explains the option next to it."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from polyglotimportcsv.gui.style import TOKEN_ACCENT

SIDE = 16


class InfoBadge(QWidget):
    """Hover shows the tooltip, as for any widget; a click shows it too.

    The click matters because a tooltip is easy to miss, and the whole point
    of the badge is that the person asked. ``show_tip`` is an injection point
    so tests never pop a real tooltip.
    """

    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(SIDE, SIDE)
        self.setToolTip(text)
        self.setAccessibleName("Ajuda")
        self.setCursor(Qt.WhatsThisCursor)
        self.show_tip = self._show_tip

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        accent = QColor(TOKEN_ACCENT)
        painter.setPen(QPen(accent, 1.4))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(1.0, 1.0, SIDE - 2.0, SIDE - 2.0))
        font = QFont(self.font())
        font.setBold(True)
        font.setPixelSize(11)
        painter.setFont(font)
        painter.drawText(QRectF(0.0, 0.0, SIDE, SIDE), Qt.AlignCenter, "i")
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.LeftButton:
            self.show_tip()
        super().mousePressEvent(event)

    def _show_tip(self) -> None:
        QToolTip.showText(self.mapToGlobal(self.rect().center()), self.toolTip(), self)
