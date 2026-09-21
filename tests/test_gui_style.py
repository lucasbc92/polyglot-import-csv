"""The checkbox/radio indicators must be drawn, and drawn differently when on.

Round 1 lost the indicators by targeting ``QCheckBox``/``QRadioButton`` with no
``::indicator`` sub-control rule, and the guard written then forbade those
selectors outright. That was the wrong conclusion: the global ``QWidget`` rule
already matches both controls, so Qt routed them through the stylesheet style
regardless and painted a *checked* radio as nothing at all. The fix is not to
avoid the selectors but to define the indicators explicitly, which is what this
module now guards.
"""

from __future__ import annotations

import re

from polyglotimportcsv.gui.style import STYLESHEET

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def stylesheet_rules() -> str:
    """The stylesheet with its ``/* ... */`` comments removed.

    C2: without this the guard could never fail. ``style.py`` carries a prose
    comment explaining this very trap, and that comment contains the literals
    ``QCheckBox``, ``QRadioButton`` and ``::indicator`` — so a plain substring
    check found all three in the comment and passed no matter what the actual
    rules did.
    """
    return _COMMENT_RE.sub("", STYLESHEET)


def _has_rule(pattern: str) -> bool:
    """True when ``pattern`` opens a rule line, ignoring comments."""
    return bool(re.search(r"^\s*[^/\n]*" + pattern, stylesheet_rules(), re.MULTILINE))


def test_both_controls_declare_an_indicator():
    """A stylesheet that touches them must say how the indicator looks."""
    for selector in ("QCheckBox", "QRadioButton"):
        assert _has_rule(selector + r"::indicator"), (
            "{0}::indicator has no rule; the global QWidget rule already routes "
            "the control through QStyleSheetStyle, so Qt drops the native "
            "indicator and the control renders with nothing in it.".format(selector)
        )


def test_the_checked_state_is_styled_apart_from_the_unchecked_one():
    """Without this, ticking a box changes nothing on screen."""
    for selector in ("QCheckBox", "QRadioButton"):
        assert _has_rule(selector + r"::indicator:checked"), (
            "{0}::indicator:checked has no rule, so the selected option looks "
            "exactly like the unselected ones.".format(selector)
        )


def test_the_guard_only_looks_at_rules_not_at_comments():
    """The guard itself must not be satisfied by prose in a comment."""
    commented_out = "/* QCheckBox::indicator:checked { } */\nQLabel { color: red; }"
    stripped = _COMMENT_RE.sub("", commented_out)
    assert "QCheckBox" in commented_out
    assert "QCheckBox" not in stripped
