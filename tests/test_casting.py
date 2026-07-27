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


def test_infer_kinds_prefers_integer_over_year_like_dates():
    # pandas parses a bare 4-digit integer as a year ("1000" -> 1000-01-01), so an
    # ID column running past 999 crosses the datetime threshold and would be cast
    # to timestamps. A fully numeric column is an integer, never a datetime.
    df = pd.DataFrame({"product_id": [str(i) for i in range(1, 10001)]})
    assert infer_column_kinds(df)["product_id"] == "integer"


def test_infer_kinds_still_detects_real_datetimes():
    df = pd.DataFrame({"ts": ["2023-11-13 03:41:06Z", "2023-11-04 13:45:07Z"]})
    assert infer_column_kinds(df)["ts"] == "datetime"


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
    # Element types must be native Python int/bool, not upcast to float by
    # pandas when a column mixes numbers with None (regression: a column
    # like ['1', '', '3'] must not silently become [1.0, None, 3.0]).
    for v in out["n"]:
        if v is not None:
            assert type(v) is int, f"expected int, got {type(v)} for {v!r}"
    for v in out["flag"]:
        if v is not None:
            assert type(v) is bool, f"expected bool, got {type(v)} for {v!r}"


def test_cast_frame_float_column_keeps_none_and_float_type():
    df = pd.DataFrame({"x": ["1.5", "", "3.0"]})
    kinds = {"x": "float"}
    out = cast_frame(df, kinds)
    assert list(out["x"]) == [1.5, None, 3.0]
    for v in out["x"]:
        if v is not None:
            assert type(v) is float, f"expected float, got {type(v)} for {v!r}"
        else:
            assert v is None


def test_cast_frame_datetime_column_yields_plain_datetime():
    df = pd.DataFrame({"d": ["2023-11-02 03:30:00Z", "", "2024-01-01T00:00:00Z"]})
    kinds = {"d": "datetime"}
    out = cast_frame(df, kinds)
    values = list(out["d"])
    assert values[1] is None
    for v in (values[0], values[2]):
        # The contract is plain datetime.datetime. pandas.Timestamp is a
        # subclass of datetime, so isinstance() alone would not catch a
        # regression back to Timestamp objects here.
        assert type(v) is datetime, f"expected datetime.datetime, got {type(v)}"
        assert type(v) is not pd.Timestamp
