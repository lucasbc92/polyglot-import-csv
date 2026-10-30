"""Spec §4.2: WARNING for text fallbacks of the cast."""

import logging

import pandas as pd

from polyglotimportcsv.casting import cast_frame


def test_cast_frame_warns_on_text_fallback(caplog):
    df = pd.DataFrame({"n": ["1", "x", "3"]})
    with caplog.at_level(logging.DEBUG, logger="polyglotimportcsv.casting"):
        out = cast_frame(df, {"n": "integer"})
    assert list(out["n"]) == [1, "x", 3]
    assert any(
        r.levelno == logging.WARNING and "could not be cast" in r.message
        for r in caplog.records
    )
