"""Tests for filter_engine."""

import pandas as pd

from polyglotimportcsv.filter_engine import apply_filters, each_partition_pattern, expand_each


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



def test_expand_each_applies_the_target_suffix_template():
    df = pd.DataFrame({"region": ["South", "North", "South", ""], "v": [1, 2, 3, 4]})
    flt = [{"column": "region", "operator": "each", "target_suffix": "r_{value}"}]
    assert sorted(n for n, _ in expand_each(df, flt, "sales")) == ["sales_r_North", "sales_r_South"]


def test_expand_each_template_takes_the_sanitized_value():
    df = pd.DataFrame({"city": ["São Paulo"]})
    flt = [{"column": "city", "operator": "each", "target_suffix": "c_{value}_x"}]
    assert [n for n, _ in expand_each(df, flt, "t")] == ["t_c_S_o_Paulo_x"]


def test_each_partition_pattern_matches_only_the_names_expand_each_gives():
    pat = each_partition_pattern(
        "orders", [{"column": "state", "operator": "each", "target_suffix": "state_{value}"}]
    )
    assert pat.fullmatch("orders_state_SP") and pat.fullmatch("orders_state_S_o_Paulo")
    for other in ("orders", "orders_state_", "orders_SP", "product_catalog", "xorders_state_SP"):
        assert not pat.fullmatch(other)
    default = each_partition_pattern("orders", [{"column": "state", "operator": "each"}])
    assert default.fullmatch("orders_SP") and not default.fullmatch("orders")
    assert each_partition_pattern("orders", [{"column": "state", "operator": "==", "value": "SP"}]) is None
    assert each_partition_pattern("orders", None) is None
