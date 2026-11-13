"""Tests for row shaping from entity config."""

import pandas as pd

from polyglotimportcsv.row_shaping import (
    flatten_entity_dataframe,
    mongo_document_from_row,
    mongo_documents,
    redis_payload_from_row,
    redis_payloads,
)


def test_mongo_document_nested_columns():
    row = pd.Series(
        {
            "product_id": "1",
            "category_id": "10",
            "category_name": "Books",
            "quantity_available": "5",
        }
    )
    ecfg = {
        "columns": {
            "product_id": {},
            "category": {"category_id": {}, "category_name": {}},
            "stock": {"quantity_available": {}},
        }
    }
    doc = mongo_document_from_row(row, ecfg)
    assert doc["product_id"] == "1"
    assert doc["category"] == {"category_id": "10", "category_name": "Books"}
    assert doc["stock"] == {"quantity_available": "5"}


def test_mongo_document_deep_nested_and_csv_column():
    row = pd.Series({"cat_id": "10", "name": "Books"})
    ecfg = {
        "columns": {
            "category": {
                "id": {"csv_column": "cat_id", "schema_column": "category_id"},
                "label": {"csv_column": "name", "schema_column": "category_name"},
            }
        }
    }
    doc = mongo_document_from_row(row, ecfg)
    assert doc["category"] == {"category_id": "10", "category_name": "Books"}


def test_flatten_entity_dataframe_rename():
    df = pd.DataFrame([{"timestamp": "2024-01-01", "user_id": "u1"}])
    ecfg = {
        "columns": {
            "timestamp": {"schema_column": "event_time"},
            "user_id": {},
        }
    }
    flat = flatten_entity_dataframe(df, ecfg)
    assert list(flat.columns) == ["event_time", "user_id"]


def test_flatten_entity_dataframe_duplicate_csv_column_mapping():
    df = pd.DataFrame([{"category_id": "1", "category_name": "Books"}])
    ecfg = {
        "columns": {
            "category_id_1": {
                "is_key": True,
                "csv_column": "category_id",
                "schema_column": "category_id_1",
            },
            "category_id_2": {
                "csv_column": "category_id",
                "schema_column": "category_id_2",
            },
            "category_name": {},
        }
    }
    flat = flatten_entity_dataframe(df, ecfg)
    assert list(flat.columns) == ["category_id_1", "category_id_2", "category_name"]
    assert flat.iloc[0]["category_id_1"] == "1"
    assert flat.iloc[0]["category_id_2"] == "1"
    assert flat.iloc[0]["category_name"] == "Books"


def test_the_first_row_of_a_duplicate_key_is_the_one_kept():
    """As between two batches, where the INSERT skips a key already in the table: which
    row is kept must not depend on where the batches are cut."""
    df = pd.DataFrame({"id": ["1", "2", "1", ""], "v": ["first", "b", "second", "no key"]})
    flat = flatten_entity_dataframe(df, {"columns": {"id": {"is_key": True}, "v": {}}})
    assert list(zip(flat["id"], flat["v"])) == [("1", "first"), ("2", "b")]


def test_documents_of_a_batch_equal_those_built_row_by_row():
    df = pd.DataFrame({"cat_id": ["10", "11"], "name": ["Books", "Games"], "extra": ["x", "y"]})
    ecfg = {"columns": {
        "name": {},
        "category": {"id": {"csv_column": 1, "schema_column": "category_id"}},
        "missing": {"csv_column": "not_in_the_file"},
    }}
    docs = mongo_documents(df, ecfg)
    assert docs == [mongo_document_from_row(row, ecfg) for _, row in df.iterrows()]
    assert docs[0] == {"name": "Books", "category": {"category_id": "10"}, "missing": None}


def test_redis_payloads_of_a_batch_skip_the_rows_without_a_key():
    df = pd.DataFrame({"id": ["a", None, "c"], "n": [1, 2, 3]})
    ecfg = {"columns": {"id": {"is_key": True}, "n": {"schema_column": "count"}}}
    assert redis_payloads(df, ecfg) == [("a", '{"count": 1}'), ("c", '{"count": 3}')]
    assert redis_payloads(df, ecfg)[0] == redis_payload_from_row(df.iloc[0], ecfg)
