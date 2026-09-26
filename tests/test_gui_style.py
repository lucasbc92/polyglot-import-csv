"""The stylesheet must leave the indicator marks to the painter.

Round 1 lost the indicators by targeting ``QCheckBox``/``QRadioButton`` with no
``::indicator`` rule, and the guard written then forbade those selectors
outright. That was the wrong conclusion: the global ``QWidget`` rule already
matches both controls, so Qt routed them through the stylesheet style
regardless and painted a *checked* radio as nothing at all.

Round 2 added ``::indicator`` rules, which made the state visible but could
only draw a box and a fill — a checked box became a solid square with no tick.
The marks are now painted by ``gui/indicators.py``, and a single ``::indicator``
rule anywhere in this stylesheet is enough for Qt to reclaim the primitive and
disable that painter silently. Hence the guard below.

What the indicators actually look like is checked in
``tests/test_gui_indicators.py``, against pixels; this module only keeps the
stylesheet out of their way.
"""

from __future__ import annotations

import re

from polyglotimportcsv.gui import style as style_module
from polyglotimportcsv.gui.style import STYLESHEET

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

#: Tokens the painter shares with the rules around the mark. TOKEN_DISABLED_FILL
#: is left out on purpose: it fills the *inside* of a disabled indicator, which
#: nothing else on the form draws, so it has no counterpart to drift from.
SHARED_TOKENS = (
    style_module.TOKEN_ACCENT,
    style_module.TOKEN_BORDER,
    style_module.TOKEN_FIELD,
    style_module.TOKEN_DISABLED_LINE,
)


def stylesheet_rules() -> str:
    """The stylesheet with its ``/* ... */`` comments removed.

    C2: without this the guard could never fail. ``style.py`` carries a prose
    comment explaining this very trap, and that comment contains the literal
    ``::indicator`` — so a plain substring check found it there and passed no
    matter what the actual rules did.
    """
    return _COMMENT_RE.sub("", STYLESHEET)


def test_no_indicator_rule_takes_the_primitive_back_from_the_painter():
    assert "::indicator" not in stylesheet_rules(), (
        "an ::indicator rule makes Qt paint the indicator itself, which "
        "silently disables gui/indicators.py and loses the tick and the dot"
    )


def test_the_guard_only_looks_at_rules_not_at_comments():
    """The guard itself must not be satisfied — or defeated — by prose."""
    commented_out = "/* QCheckBox::indicator { } */\nQLabel { color: red; }"
    assert "::indicator" in commented_out
    assert "::indicator" not in _COMMENT_RE.sub("", commented_out)


def test_selected_rows_stay_highlighted_without_focus():
    """A selection that fades when the table loses focus looked like no selection."""
    assert "QTableWidget::item:selected" in STYLESHEET
    assert "QTableWidget::item:selected:!active" in STYLESHEET


def test_disabled_console_buttons_are_visibly_muted():
    """A disabled "Salvar log…" must not look identical to an enabled one.

    ``QFrame#consolePanel QPushButton`` sets ``color: #D6DCE5`` (an ID
    selector), which beats the generic ``QPushButton:disabled`` rule's
    specificity, so a disabled button inside the console panel kept the
    enabled text colour with no visual cue at all. The fix is a rule scoped
    to the same selector, ``QFrame#consolePanel QPushButton:disabled``, with
    ``::indicator`` still forbidden (test above).
    """
    rules = stylesheet_rules()
    match = re.search(
        r"QFrame#consolePanel\s+QPushButton:disabled\s*\{([^}]*)\}", rules
    )
    assert match is not None, (
        "no QFrame#consolePanel QPushButton:disabled rule: a disabled button "
        "in the console (e.g. \"Salvar log…\") looks identical to an enabled one"
    )
    body = match.group(1)
    color_match = re.search(r"color:\s*(#[0-9A-Fa-f]{6})", body)
    assert color_match is not None, "the disabled rule must set a muted text colour"
    enabled_match = re.search(
        r"QFrame#consolePanel\s+QPushButton\s*\{[^}]*color:\s*(#[0-9A-Fa-f]{6})", rules
    )
    assert enabled_match is not None
    assert color_match.group(1).upper() != enabled_match.group(1).upper(), (
        "the disabled console button colour must differ from the enabled one"
    )


def test_every_painted_token_is_a_colour_of_the_stylesheet():
    """The painter and the rules around it must not drift apart.

    ``indicators.py`` paints with these tokens while everything surrounding the
    mark stays in the stylesheet, so a colour changed in one place and not the
    other would show up as an indicator that no longer matches its own form.
    """
    rules = stylesheet_rules()
    for token in SHARED_TOKENS:
        assert token in rules, (
            "{0} is painted by indicators.py but no longer appears in the "
            "stylesheet".format(token)
        )
