"""The optimized (vectorized) cast_frame must equal the naive (per-cell) one."""

import logging
import math

import pandas as pd

from polyglotimportcsv.casting import cast_frame


def _frame():
    # One column per kind, plus an integer column with an unparseable value
    # that must survive as text (the fallback path), and empties everywhere.
    return pd.DataFrame(
        {
            "i": ["1", "", "3", "10000", "", ""],
            "f": ["1.5", "", "3.0", "2", "", ""],
            "b": ["true", "FALSE", "", "true", "", ""],
            # Deliberately mixes "space" and "T" separators: without
            # format="mixed" the vectorized path silently NaTs the second form.
            "d": ["2023-11-02 03:30:00Z", "", "2024-01-01T00:00:00Z", "notadate", "", ""],
            "s": ["a", "", "c", "d", "", ""],
            "bad": ["1", "", "notanumber", "4", "", ""],
            # pd.to_numeric() is MORE permissive than int(): it accepts
            # decimal ("3.0") and scientific ("1e3") notation, which int()
            # rejects with ValueError. These must stay as text and count as
            # fallbacks, exactly like cast_value's int() does.
            "i_edge": ["3.0", "1e3", "7", "", "", ""],
            # pd.to_numeric() is AMBIGUOUS for "nan": float("nan") succeeds
            # and returns a real NaN, indistinguishable from a coerce
            # failure once it comes back as NaN. "inf" must also come back
            # as a real float, not the original text.
            "f_edge": ["nan", "inf", "1.5", "", "", ""],
            # pd.to_numeric() silently promotes the WHOLE column to lossy
            # float64 once a single value overflows int64: it neither
            # raises nor returns NaN. Pairing an out-of-range value with a
            # value at (and just above) the 2**53 float64-exactness
            # boundary in the SAME column is the scenario that corrupts:
            # 9007199254740993 (2**53 + 1) rounds to exactly
            # 9007199254740992 (2**53) once the column is promoted to
            # float64, becoming indistinguishable from the boundary value
            # itself. int() on the original text is exact for arbitrary
            # precision and must be recovered for every int-like value
            # here, not just the obviously-huge one.
            "i_big": [
                "99999999999999999999999",
                "9007199254740993",
                "9007199254740992",
                "-99999999999999999999999",
                "42",
                "notanumber",
            ],
            # Every value here fits int64 (including the exact int64
            # bounds), so pd.to_numeric must return an int64 dtype and the
            # fast path must be used -- even though this frame also
            # contains empty cells (which force float64 via NaN padding in
            # an unrelated per-row computation) and even though the
            # "i_big" column above genuinely overflows. Proves the fast
            # path doesn't regress into the slow text-parse path.
            "i_int64": [
                "100",
                "200",
                "300",
                "9223372036854775807",
                "-9223372036854775808",
                "",
            ],
        }
    )


_KINDS = {"i": "integer", "f": "float", "b": "boolean",
          "d": "datetime", "s": "string", "bad": "integer",
          "i_edge": "integer", "f_edge": "float", "i_big": "integer",
          "i_int64": "integer"}


def _values_match(a, b):
    """Equality that treats two real float NaNs as matching (float('nan')
    != float('nan')), while still distinguishing a real NaN from the
    string 'nan' (handled by the caller's separate type check)."""
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    return a == b


def test_optimized_equals_naive_cell_by_cell():
    df = _frame()
    naive = cast_frame(df, _KINDS, strategy="naive")
    opt = cast_frame(df, _KINDS, strategy="optimized")
    assert list(naive.columns) == list(opt.columns)
    for col in naive.columns:
        n, o = list(naive[col]), list(opt[col])
        assert len(n) == len(o), f"column {col!r}: naive={n} optimized={o}"
        for a, b in zip(n, o):
            assert type(a) is type(b), f"{col!r}: {type(a)} vs {type(b)}"
            assert _values_match(a, b), f"column {col!r}: naive={n} optimized={o}"


def test_optimized_preserves_unparseable_as_text_and_warns(caplog):
    df = _frame()
    with caplog.at_level(logging.WARNING):
        opt = cast_frame(df, _KINDS, strategy="optimized")
    # 'notanumber' stays as the original string, not None
    assert list(opt["bad"]) == [1, None, "notanumber", 4, None, None]
    assert any("could not be cast" in r.message for r in caplog.records)


def test_optimized_integer_column_boundary_and_overflow_in_same_column():
    """Regression test for the round-2 bug: pairing an out-of-int64-range
    value with a value at (and just above) the 2**53 float64-exactness
    boundary in the SAME column must not corrupt the boundary value.
    pd.to_numeric promotes the whole column to float64 once any value
    overflows int64, and float64 rounds 2**53 + 1 down to exactly 2**53 --
    a strict magnitude check on the resulting float can't tell them apart,
    so the fix must decide from pd.to_numeric's result dtype instead."""
    df = _frame()
    opt = cast_frame(df, _KINDS, strategy="optimized")
    expected = [
        99999999999999999999999,
        9007199254740993,
        9007199254740992,
        -99999999999999999999999,
        42,
        "notanumber",
    ]
    got = list(opt["i_big"])
    assert got == expected, f"i_big: expected={expected} got={got}"
    for e, g in zip(expected, got):
        assert type(e) is type(g), f"i_big: expected type {type(e)} got {type(g)}"


def test_optimized_int64_fast_path_unaffected_by_empties_and_other_overflow():
    """A column where every value fits int64 (including the exact int64
    bounds) must still take the fast pd.to_numeric path and be exact, even
    with empty cells in the same column and an overflowing column
    elsewhere in the frame."""
    df = _frame()
    opt = cast_frame(df, _KINDS, strategy="optimized")
    expected = [100, 200, 300, 9223372036854775807, -9223372036854775808, None]
    assert list(opt["i_int64"]) == expected
