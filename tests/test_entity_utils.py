"""Unit tests for column mapping helpers."""

import pytest

from polyglotimportcsv.entity_utils import (
    collect_source_columns,
    entity_has_nested_branches,
    is_column_branch,
    is_column_spec,
    iter_leaf_columns,
    resolve_csv_column,
    target_field_name,
)


def test_is_column_spec_vs_branch():
    assert is_column_spec({})
    assert is_column_spec({"schema_column": "event_time"})
    assert not is_column_spec({"category_id": {}})
    assert is_column_branch({"category_id": {}, "category_name": {}})


def test_target_field_name_precedence():
    assert target_field_name("timestamp", {"schema_column": "event_time"}) == "event_time"
    assert target_field_name("timestamp", {"db_column": "legacy"}) == "legacy"
    assert target_field_name("timestamp", {}) == "timestamp"


def test_resolve_csv_column_index_and_name():
    cols = ["a", "b", "c"]
    assert resolve_csv_column("x", {"csv_column": 1}, cols) == "b"
    assert resolve_csv_column("x", {"csv_column": "c"}, cols) == "c"
    assert resolve_csv_column("a", {}, cols) == "a"


def test_resolve_csv_column_index_out_of_range():
    with pytest.raises(ValueError):
        resolve_csv_column("x", {"csv_column": 99}, ["a"])


def test_iter_leaf_columns_nested_in_columns():
    ecfg = {
        "columns": {
            "product_id": {},
            "category": {"category_id": {}, "category_name": {}},
        }
    }
    leaves = list(iter_leaf_columns(ecfg))
    assert len(leaves) == 3
    paths = [p for p, _, _ in leaves]
    assert (("category",), "category_id") in [(p, fk) for p, fk, _ in leaves]


def test_iter_leaf_columns_legacy_nested():
    ecfg = {
        "columns": {"product_id": {}},
        "nested": {"stock": {"columns": {"quantity_available": {}}}},
    }
    assert len(list(iter_leaf_columns(ecfg))) == 2


def test_entity_has_nested_branches():
    assert entity_has_nested_branches({"columns": {"a": {"b": {}}}})
    assert entity_has_nested_branches({"columns": {"a": {}}, "nested": {"x": {"columns": {}}}})
    assert not entity_has_nested_branches({"columns": {"a": {}, "b": {"schema_column": "c"}}})


def test_collect_source_columns_with_index():
    ecfg = {"columns": {"logical": {"csv_column": 0}}}
    assert collect_source_columns(ecfg, ["hdr_a", "hdr_b"]) == ["hdr_a"]
