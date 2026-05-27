"""Tests for row materialization from entity config."""

import pandas as pd

from polyglotimportcsv.materialize import flatten_entity_dataframe, mongo_document_from_row


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
