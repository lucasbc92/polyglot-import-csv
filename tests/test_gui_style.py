"""Guard against reintroducing the round-1 checkbox/radio regression.

Once a stylesheet rule targets QCheckBox or QRadioButton directly, Qt stops
drawing their native indicator; with no ::indicator sub-control rule the
box/circle vanishes entirely. The project deliberately avoids maintaining
custom-drawn indicators, so if either selector shows up again it must come
with an ::indicator rule alongside it.
"""

from __future__ import annotations

import re

from polyglotimportcsv.gui.style import STYLESHEET

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def stylesheet_rules() -> str:
    """The stylesheet with its /* ... */ comments removed.

    C2: without this the guard could never fail. ``style.py`` carries a prose
    comment explaining this very trap, and that comment contains the literals
    ``QCheckBox``, ``QRadioButton`` and ``::indicator`` — so a plain substring
    check found all three in the comment and passed no matter what the actual
    rules did.
    """
    return _COMMENT_RE.sub("", STYLESHEET)


def test_checkbox_and_radio_selectors_are_not_targeted_without_an_indicator_rule():
    rules = stylesheet_rules()
    for selector in ("QCheckBox", "QRadioButton"):
        # Match the selector only where it opens a rule line, so a mention
        # inside a comment or a string cannot satisfy the condition.
        if re.search(r"^\s*" + selector + r"\b", rules, re.MULTILINE):
            assert "::indicator" in rules, (
                "{0} is targeted by the stylesheet without an ::indicator "
                "rule, which makes Qt drop the native checkbox/radio "
                "indicator entirely.".format(selector)
            )


def test_the_guard_only_looks_at_rules_not_at_comments():
    """The guard itself must not be satisfied by style.py's prose comment."""
    rules = stylesheet_rules()
    assert "QCheckBox" in STYLESHEET  # it is there, in the comment
    assert not re.search(r"^\s*QCheckBox\b", rules, re.MULTILINE)
    assert not re.search(r"^\s*QRadioButton\b", rules, re.MULTILINE)
    assert "::indicator" not in rules
