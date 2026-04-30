"""Tests for filter_engine."""

import pandas as pd

from polyglotimportcsv.filter_engine import apply_filters, expand_each


def test_apply_filters_eq_string():
    df = pd.DataFrame({"action": ["a", "b", "a"], "x": [1, 2, 3]})
    kinds = {"action": "string", "x": "integer"}
    out = apply_filters(df, [{"column": "action", "operator": "==", "value": "a"}], kinds)
    assert len(out) == 2
    assert list(out["action"]) == ["a", "a"]


def test_expand_each_no_each():
    df = pd.DataFrame({"state": ["SC", "RS"], "v": [1, 2]})
    parts = expand_each(df, [], "tbl")
    assert len(parts) == 1
    assert parts[0][0] == "tbl"


def test_expand_each_splits():
    df = pd.DataFrame({"state": ["SC", "RS", "SC"], "v": [1, 2, 3]})
    parts = expand_each(
        df,
        [{"column": "state", "operator": "each"}],
        "orders",
    )
    names = sorted(n for n, _ in parts)
    assert names == ["orders_RS", "orders_SC"]

