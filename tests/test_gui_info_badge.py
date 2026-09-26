"""The round "i" that explains an option."""

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtCore import Qt  # noqa: E402

from polyglotimportcsv.gui.widgets.info_badge import InfoBadge  # noqa: E402


def test_the_text_is_the_tooltip(qtbot):
    badge = InfoBadge("Explica a opção.")
    qtbot.addWidget(badge)
    assert badge.toolTip() == "Explica a opção."
    assert badge.accessibleName() == "Ajuda"


def test_clicking_shows_the_tip(qtbot):
    badge = InfoBadge("Explica a opção.")
    qtbot.addWidget(badge)
    shown = []
    badge.show_tip = lambda: shown.append(True)
    qtbot.mouseClick(badge, Qt.LeftButton)
    assert shown == [True]


def test_it_paints_something(qtbot):
    badge = InfoBadge("x")
    qtbot.addWidget(badge)
    badge.show()
    image = badge.grab().toImage()
    colours = {image.pixel(x, y) for x in range(image.width()) for y in range(image.height())}
    assert len(colours) > 1, "a blank square is not a badge"
