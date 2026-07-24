"""The optimized (vectorized) cast_frame must equal the naive (per-cell) one."""

import logging

import pandas as pd

from polyglotimportcsv.casting import cast_frame


def _frame():
    # One column per kind, plus an integer column with an unparseable value
    # that must survive as text (the fallback path), and empties everywhere.
    return pd.DataFrame(
        {
            "i": ["1", "", "3", "10000"],
            "f": ["1.5", "", "3.0", "2"],
            "b": ["true", "FALSE", "", "true"],
            # Deliberately mixes "space" and "T" separators: without
            # format="mixed" the vectorized path silently NaTs the second form.
            "d": ["2023-11-02 03:30:00Z", "", "2024-01-01T00:00:00Z", "notadate"],
            "s": ["a", "", "c", "d"],
            "bad": ["1", "", "notanumber", "4"],
        }
    )


_KINDS = {"i": "integer", "f": "float", "b": "boolean",
          "d": "datetime", "s": "string", "bad": "integer"}


def test_optimized_equals_naive_cell_by_cell():
    df = _frame()
    naive = cast_frame(df, _KINDS, strategy="naive")
    opt = cast_frame(df, _KINDS, strategy="optimized")
    assert list(naive.columns) == list(opt.columns)
    for col in naive.columns:
        n, o = list(naive[col]), list(opt[col])
        assert n == o, f"column {col!r}: naive={n} optimized={o}"
        for a, b in zip(n, o):
            assert type(a) is type(b), f"{col!r}: {type(a)} vs {type(b)}"


def test_optimized_preserves_unparseable_as_text_and_warns(caplog):
    df = _frame()
    with caplog.at_level(logging.WARNING):
        opt = cast_frame(df, _KINDS, strategy="optimized")
    # 'notanumber' stays as the original string, not None
    assert list(opt["bad"]) == [1, None, "notanumber", 4]
    assert any("could not be cast" in r.message for r in caplog.records)
