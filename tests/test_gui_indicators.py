"""What the checkbox and radio indicators actually paint.

These assertions are about pixels because the defects they guard were about
pixels: a stylesheet that silently stopped drawing the mark, then a checked box
that was a solid square with no tick and a checked radio filled to its own rim.
Reading the rules out of ``style.py`` could not have caught any of the three.

The primitives are painted straight onto an image rather than grabbed from a
laid-out widget, so nothing here depends on screen scaling, fonts or the
platform's own indicator metrics.
"""

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QStyle, QStyleOption  # noqa: E402

from polyglotimportcsv.gui.indicators import IndicatorStyle  # noqa: E402
from polyglotimportcsv.gui.style import TOKEN_ACCENT, TOKEN_FIELD  # noqa: E402

SIZE = 20
ACCENT = QColor(TOKEN_ACCENT)
FIELD = QColor(TOKEN_FIELD)


@pytest.fixture
def style(qapp):
    return IndicatorStyle(qapp.style().objectName())


def render(style, element, on):
    """Paint one indicator on a white square and return the image."""
    image = QImage(SIZE, SIZE, QImage.Format_ARGB32)
    image.fill(FIELD)
    option = QStyleOption()
    option.rect = QRect(0, 0, SIZE, SIZE)
    option.state = QStyle.State_Enabled
    option.state |= QStyle.State_On if on else QStyle.State_Off
    painter = QPainter(image)
    style.drawPrimitive(element, option, painter, None)
    painter.end()
    return image


def near(pixel, colour, tolerance=60):
    """True when ``pixel`` is close to ``colour``, allowing for antialiasing."""
    actual = QColor(pixel)
    return (
        abs(actual.red() - colour.red()) <= tolerance
        and abs(actual.green() - colour.green()) <= tolerance
        and abs(actual.blue() - colour.blue()) <= tolerance
    )


def accent_pixels(image):
    return [
        (x, y)
        for y in range(image.height())
        for x in range(image.width())
        if near(image.pixelColor(x, y), ACCENT)
    ]


def runs_of_accent(image, row):
    """Lengths of the contiguous accent stretches along one scan line."""
    lengths = []
    current = 0
    for x in range(image.width()):
        if near(image.pixelColor(x, row), ACCENT):
            current += 1
        elif current:
            lengths.append(current)
            current = 0
    if current:
        lengths.append(current)
    return lengths


# -- the mark is drawn at all ---------------------------------------------


@pytest.mark.parametrize(
    "element",
    [QStyle.PE_IndicatorCheckBox, QStyle.PE_IndicatorRadioButton],
)
def test_checked_and_unchecked_do_not_look_alike(style, element):
    """Q1: the original bug was a checked control that looked unchecked."""
    assert render(style, element, on=True) != render(style, element, on=False)


@pytest.mark.parametrize(
    "element",
    [QStyle.PE_IndicatorCheckBox, QStyle.PE_IndicatorRadioButton],
)
def test_an_unchecked_indicator_is_still_visible(style, element):
    """An empty box must be an empty box, not blank space."""
    image = render(style, element, on=False)
    assert any(
        not near(image.pixelColor(x, y), FIELD, tolerance=10)
        for y in range(SIZE)
        for x in range(SIZE)
    )


# -- Q2: a tick, not a filled square --------------------------------------


def test_a_checked_box_holds_a_tick_inside_its_fill(style):
    """The mark has to be a tick: a solid blue square has no light pixels."""
    image = render(style, QStyle.PE_IndicatorCheckBox, on=True)
    filled = accent_pixels(image)
    assert filled, "the checked box is not painted in the accent colour"
    left = min(x for x, _ in filled)
    right = max(x for x, _ in filled)
    top = min(y for _, y in filled)
    bottom = max(y for _, y in filled)
    light = [
        (x, y)
        for y in range(top + 2, bottom - 1)
        for x in range(left + 2, right - 1)
        if near(image.pixelColor(x, y), FIELD, tolerance=70)
    ]
    assert light, (
        "the checked box is a solid block of accent colour: there is no tick "
        "drawn inside it"
    )


# -- Q2: a dot inside the ring, not a ring filled from the rim ------------


def test_a_checked_radio_is_marked_on_the_inside(style):
    """Across the middle: ring, gap, dot, gap, ring — three accent runs.

    A radio filled to its own edge, which is what the stylesheet version drew,
    would give a single run instead.
    """
    image = render(style, QStyle.PE_IndicatorRadioButton, on=True)
    runs = runs_of_accent(image, SIZE // 2)
    assert len(runs) == 3, (
        "expected the ring and the dot to be separated by the field colour, "
        "got accent runs {0!r} across the middle".format(runs)
    )
    ring_left, dot, ring_right = runs
    assert dot > ring_left and dot > ring_right, (
        "the mark should be the widest part of the scan line; got {0!r}".format(runs)
    )


def test_an_unchecked_radio_has_only_its_ring(style):
    image = render(style, QStyle.PE_IndicatorRadioButton, on=False)
    assert accent_pixels(image) == [], "an unchecked radio must carry no mark"
