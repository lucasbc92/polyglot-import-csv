"""Guard against reintroducing the round-1 checkbox/radio regression.

Once a stylesheet rule targets QCheckBox or QRadioButton directly, Qt stops
drawing their native indicator; with no ::indicator sub-control rule the
box/circle vanishes entirely. The project deliberately avoids maintaining
custom-drawn indicators, so if either selector shows up again it must come
with an ::indicator rule alongside it.
"""

from __future__ import annotations

from polyglotimportcsv.gui.style import STYLESHEET


def test_checkbox_and_radio_selectors_are_not_targeted_without_an_indicator_rule():
    for selector in ("QCheckBox", "QRadioButton"):
        if selector in STYLESHEET:
            assert "::indicator" in STYLESHEET, (
                "{0} is targeted by the stylesheet without an ::indicator "
                "rule, which makes Qt drop the native checkbox/radio "
                "indicator entirely.".format(selector)
            )
