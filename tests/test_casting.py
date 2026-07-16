"""Native-value casting and boolean kind detection."""

from datetime import datetime

import pandas as pd

from polyglotimportcsv.casting import KIND_TO_DB_TYPE, cast_frame, cast_value
from polyglotimportcsv.csv_reader import infer_column_kinds


def test_kind_to_db_type_table():
    assert KIND_TO_DB_TYPE == {
        "integer": "BIGINT",
        "float": "NUMERIC",
        "datetime": "TIMESTAMPTZ",
        "boolean": "BOOLEAN",
        "string": "TEXT",
        "empty": "TEXT",
    }


def test_cast_value_scalars():
    assert cast_value("42", "integer") == 42
    assert cast_value("3.5", "float") == 3.5
    assert cast_value("true", "boolean") is True
    assert cast_value("False", "boolean") is False
    assert cast_value("", "integer") is None
    assert cast_value(None, "float") is None
    dt = cast_value("2023-11-02 03:30:00Z", "datetime")
    assert isinstance(dt, datetime) and dt.tzinfo is not None
    # Unparseable values fall back untouched rather than crashing.
    assert cast_value("abc", "integer") == "abc"


def test_infer_kinds_detects_boolean():
    df = pd.DataFrame({"flag": ["true", "FALSE", ""], "n": ["1", "2", "3"]})
    kinds = infer_column_kinds(df)
    assert kinds["flag"] == "boolean"
    assert kinds["n"] == "integer"


def test_cast_frame_converts_typed_columns_and_keeps_strings():
    df = pd.DataFrame(
        {"n": ["1", "", "3"], "name": ["a", "", "c"], "flag": ["true", "false", ""]}
    )
    kinds = {"n": "integer", "name": "string", "flag": "boolean"}
    out = cast_frame(df, kinds)
    assert list(out["n"]) == [1, None, 3]
    assert list(out["flag"]) == [True, False, None]
    # String columns are untouched (empty string stays empty, not None).
    assert list(out["name"]) == ["a", "", "c"]
    # Original frame is not mutated.
    assert list(df["n"]) == ["1", "", "3"]
