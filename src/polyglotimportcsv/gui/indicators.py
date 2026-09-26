"""Draws the checkbox and radio indicators, because no stylesheet can.

Qt style sheets can give an indicator a size, a border and a fill, but they
cannot draw a tick inside it: the only way to get one through a stylesheet is
``image: url(...)``, which means shipping and packaging bitmaps. The result was
a checked box that read as a plain blue square and a checked radio drawn as a
thick ring rather than a dot — neither of which is what either control looks
like anywhere else on the desktop.

Painting them here removes the whole problem. A tick is a three-point polyline
and a radio's mark is a small filled circle, so the indicators end up looking
the way people expect while still using the application's own accent colour
instead of whatever the system theme happens to be. Nothing has to be shipped
alongside the code.

The stylesheet must therefore define **no** ``::indicator`` rule: one rule is
enough for Qt's stylesheet style to take the primitive over and paint it
itself, and this painter would never be called. ``tests/test_gui_style.py``
guards that, and ``tests/test_gui_indicators.py`` renders the controls and
checks the pixels rather than trusting either file to stay correct.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle, QWidget

from polyglotimportcsv.gui.style import (
    TOKEN_ACCENT,
    TOKEN_BORDER,
    TOKEN_DISABLED_FILL,
    TOKEN_DISABLED_LINE,
    TOKEN_FIELD,
)

#: Side of the indicator, in device-independent pixels. Qt hands over a rect
#: sized by the platform style, which on Windows 11 is larger than the rest of
#: this form needs; the mark is inscribed in a square of this size instead.
SIDE = 15.0


class IndicatorStyle(QProxyStyle):
    """The platform style, with the two indicator primitives repainted."""

    def drawPrimitive(
        self,
        element: QStyle.PrimitiveElement,
        option,
        painter: QPainter,
        widget: Optional[QWidget] = None,
    ) -> None:
        if element == QStyle.PE_IndicatorCheckBox:
            _draw_check(option, painter)
            return
        if element == QStyle.PE_IndicatorRadioButton:
            _draw_radio(option, painter)
            return
        super().drawPrimitive(element, option, painter, widget)


def install(app: QApplication) -> IndicatorStyle:
    """Install the painter on ``app``, keeping the platform style underneath.

    The style is built from the current style's *key* rather than from the
    object: ``QApplication.setStyle`` deletes the style it replaces, and
    ``QProxyStyle`` takes ownership of a style handed to it as an object, so
    passing the live instance sets up a double free. Asking for another
    instance by name sidesteps that entirely.
    """
    style = IndicatorStyle(app.style().objectName())
    app.setStyle(style)
    return style


def _square(option) -> QRectF:
    """A centred square inside the rect Qt allotted, on a half-pixel grid."""
    rect = QRectF(option.rect)
    side = min(SIDE, rect.width(), rect.height())
    return QRectF(
        round(rect.center().x() - side / 2.0) + 0.5,
        round(rect.center().y() - side / 2.0) + 0.5,
        side - 1.0,
        side - 1.0,
    )


def _colours(option):
    """Line and fill for the current state, as (outline, fill, mark)."""
    on = bool(option.state & QStyle.State_On)
    enabled = bool(option.state & QStyle.State_Enabled)
    hovered = bool(option.state & QStyle.State_MouseOver)
    if not enabled:
        return (
            QColor(TOKEN_DISABLED_LINE),
            QColor(TOKEN_DISABLED_FILL) if on else QColor(TOKEN_FIELD),
            QColor(TOKEN_DISABLED_LINE),
        )
    if on:
        return QColor(TOKEN_ACCENT), QColor(TOKEN_ACCENT), QColor(TOKEN_FIELD)
    outline = QColor(TOKEN_ACCENT) if hovered else QColor(TOKEN_BORDER)
    return outline, QColor(TOKEN_FIELD), QColor(TOKEN_ACCENT)


def _draw_check(option, painter: QPainter) -> None:
    box = _square(option)
    outline, fill, mark = _colours(option)
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(QPen(outline, 1.0))
    painter.setBrush(fill)
    painter.drawRoundedRect(box, 3.0, 3.0)
    if option.state & QStyle.State_On:
        painter.setPen(QPen(mark, 1.9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        width, height = box.width(), box.height()
        painter.drawPolyline(
            [
                box.topLeft() + QPointF(width * 0.23, height * 0.52),
                box.topLeft() + QPointF(width * 0.42, height * 0.71),
                box.topLeft() + QPointF(width * 0.78, height * 0.29),
            ]
        )
    elif option.state & QStyle.State_NoChange:
        painter.setPen(QPen(mark, 1.9, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(
            box.topLeft() + QPointF(box.width() * 0.25, box.height() * 0.5),
            box.topLeft() + QPointF(box.width() * 0.75, box.height() * 0.5),
        )
    painter.restore()


def _draw_radio(option, painter: QPainter) -> None:
    box = _square(option)
    outline, _fill, _mark = _colours(option)
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    # The ring stays hollow and the mark goes *inside* it: a radio filled to
    # its own edge reads as a checkbox that lost its corners.
    painter.setPen(QPen(outline, 1.0))
    painter.setBrush(QColor(TOKEN_FIELD))
    painter.drawEllipse(box)
    if option.state & QStyle.State_On:
        dot = (
            QColor(TOKEN_DISABLED_LINE)
            if not option.state & QStyle.State_Enabled
            else QColor(TOKEN_ACCENT)
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(dot)
        radius = box.width() * 0.27
        painter.drawEllipse(box.center(), radius, radius)
    painter.restore()
