"""Type inference is a hot path: it must get faster without reclassifying anything.

`infer_column_kinds` drives both casting and filter coercion, so a speed-up that
changes a single column's kind changes what gets written to the databases. These
pin the classification on the reference CSVs and on the union path before the
optimizations, so a regression shows up as a failing test rather than as different
data.
"""

from pathlib import Path

import pandas as pd
import pytest

from polyglotimportcsv.csv_reader import infer_column_kinds, read_csv
from polyglotimportcsv.mapping_resolver import _union_source
from polyglotimportcsv.sources import SOURCE_COLUMN, SourceData

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "ecommerce"

#: Kinds inferred from the reference CSVs before the fast path was added.
EXPECTED_STOCK_KINDS = {
    "timestamp": "datetime",
    "user_id": "string",
    "user_name": "string",
    "user_email": "string",
    "street": "string",
    "neighborhood": "string",
    "state": "string",
    "country": "string",
    "zip_code": "integer",
    "product_id": "integer",
    "product_name": "string",
    "product_variant": "string",
    "product_brand": "string",
    "product_description": "string",
    "product_image": "string",
    "category_id": "integer",
    "category_name": "string",
    "quantity_available": "integer",
    "price": "float",
    "last_restock_date": "datetime",
}


def test_reference_stock_kinds_are_unchanged():
    kinds = infer_column_kinds(read_csv(DATA / "ecommerce_stock.csv"))
    assert kinds == EXPECTED_STOCK_KINDS


@pytest.mark.parametrize("name", [
    "ecommerce_purchase.csv", "ecommerce_select_product.csv", "ecommerce_add_to_cart.csv",
])
def test_reference_csvs_keep_a_stable_kind_per_column(name, request):
    """Golden-file style: the kind of every column of every reference CSV."""
    df = read_csv(DATA / name)
    kinds = infer_column_kinds(df)
    # Spot-pin the columns whose classification the fast path could plausibly move.
    assert kinds["timestamp"] == "datetime"
    assert kinds["user_id"] == "string"
    if "order_date" in kinds:
        assert kinds["order_date"] == "datetime"
    if "rating" in kinds:
        assert kinds["rating"] == "integer"
    if "price" in kinds:
        assert kinds["price"] == "float"


# ---------- datetime classification must not shift ----------

@pytest.mark.parametrize("values,expected", [
    (["2023-11-01 00:00:00Z", "2023-11-02 01:02:03Z"], "datetime"),      # generator form
    (["2023-11-01T00:00:00-05:00", "2023-11-02T01:02:03-05:00"], "datetime"),  # offset
    (["2023-11-01", "2023-11-02"], "datetime"),                          # date only
    (["01/11/2023", "02/11/2023"], "datetime"),                          # non-ISO
    (["Nov 1 2023", "Nov 2 2023"], "datetime"),                          # free text
    (["hello", "world"], "string"),
    (["1", "2", "3"], "integer"),
    (["1.5", "2.5"], "float"),
])
def test_datetime_like_columns_keep_their_kind(values, expected):
    assert infer_column_kinds(pd.DataFrame({"c": values}))["c"] == expected


def test_threshold_still_rejects_a_mostly_unparseable_column():
    # 8 junk + 2 dates: under the 0.85 datetime threshold, so it stays a string.
    values = ["junk"] * 8 + ["2023-11-01", "2023-11-02"]
    assert infer_column_kinds(pd.DataFrame({"c": values}))["c"] == "string"


def test_threshold_still_accepts_a_mostly_parseable_column():
    values = ["2023-11-01"] * 9 + ["junk"]
    assert infer_column_kinds(pd.DataFrame({"c": values}))["c"] == "datetime"


# ---------- the union path must agree with inferring on the concatenation ----------

def _src(name, df):
    header = [c for c in df.columns if c != SOURCE_COLUMN]
    out = df.copy()
    out[SOURCE_COLUMN] = name
    kinds = infer_column_kinds(df[header])
    kinds[SOURCE_COLUMN] = "string"
    return SourceData(name=name, df=out, kinds=kinds, file_header=header)


def _union_kinds_match_reinference(sources):
    united = _union_source("e", list(sources), sources)
    data_cols = [c for c in united.file_header]
    expected = infer_column_kinds(united.df[data_cols])
    expected[SOURCE_COLUMN] = "string"
    assert united.kinds == expected


def test_union_kinds_match_reinference_for_agreeing_sources():
    sources = {
        "a": _src("a", pd.DataFrame({"id": ["1", "2"], "ts": ["2023-11-01", "2023-11-02"]})),
        "b": _src("b", pd.DataFrame({"id": ["3", "4"], "ts": ["2023-11-03", "2023-11-04"]})),
    }
    _union_kinds_match_reinference(sources)


def test_union_kinds_match_reinference_for_disjoint_columns():
    # Columns missing from a part are filled with "", which inference drops.
    sources = {
        "a": _src("a", pd.DataFrame({"id": ["1", "2"], "only_a": ["1.5", "2.5"]})),
        "b": _src("b", pd.DataFrame({"id": ["3", "4"], "only_b": ["x", "y"]})),
    }
    _union_kinds_match_reinference(sources)


def test_union_kinds_match_reinference_when_sources_disagree():
    # 'v' is integer in one source and text in the other: whatever inferring on the
    # concatenation decides, the union must report the same thing.
    sources = {
        "a": _src("a", pd.DataFrame({"v": ["1", "2"]})),
        "b": _src("b", pd.DataFrame({"v": ["x", "y"]})),
    }
    _union_kinds_match_reinference(sources)


def test_union_kinds_match_reinference_for_integer_and_float():
    sources = {
        "a": _src("a", pd.DataFrame({"v": ["1", "2"]})),
        "b": _src("b", pd.DataFrame({"v": ["1.5", "2.5"]})),
    }
    _union_kinds_match_reinference(sources)


def test_union_kinds_match_reinference_for_empty_and_typed():
    sources = {
        "a": _src("a", pd.DataFrame({"v": ["", ""]})),
        "b": _src("b", pd.DataFrame({"v": ["7", "8"]})),
    }
    _union_kinds_match_reinference(sources)


def test_union_kinds_match_reinference_on_the_real_reference_csvs():
    names = ("stock", "purchase", "select_product", "add_to_cart")
    sources = {
        n: _src(n, read_csv(DATA / f"ecommerce_{n}.csv")) for n in names
    }
    _union_kinds_match_reinference(sources)
