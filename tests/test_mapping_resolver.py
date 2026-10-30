"""Entity->source binding and effective column mapping expansion."""

import pandas as pd
import pytest

from polyglotimportcsv.business_exception import MappingError
from polyglotimportcsv.mapping_resolver import bind_entity_source, expand_entity_columns
from polyglotimportcsv.sources import SOURCE_COLUMN, SourceData


def _source(name, data, kinds=None):
    df = pd.DataFrame(data)
    header = [c for c in df.columns if c != SOURCE_COLUMN]
    if SOURCE_COLUMN not in df.columns:
        df[SOURCE_COLUMN] = name
    from polyglotimportcsv.csv_reader import infer_column_kinds

    k = kinds or infer_column_kinds(df[header])
    k[SOURCE_COLUMN] = "string"
    return SourceData(name=name, df=df, kinds=k, file_header=header)


@pytest.fixture()
def sources():
    return {
        "stock": _source("stock", {"product_id": ["1", "2"], "price": ["10.5", "20"]}),
        "purchase": _source("purchase", {"order": ["o1"], "product_id": ["1"]}),
    }


def test_binding_by_entity_key_name(sources):
    assert bind_entity_source("stock", {}, sources).name == "stock"


def test_binding_by_explicit_source(sources):
    assert bind_entity_source("inventory", {"source": "stock"}, sources).name == "stock"


def test_binding_unresolvable_raises(sources):
    with pytest.raises(MappingError, match="no source"):
        bind_entity_source("inventory", {}, sources)


def test_binding_unknown_source_raises(sources):
    with pytest.raises(MappingError, match="unknown source"):
        bind_entity_source("x", {"source": "nope"}, sources)


def test_list_source_unions_columns_and_tags_source(sources):
    sd = bind_entity_source("log", {"source": ["stock", "purchase"]}, sources)
    assert sd.file_header == ["product_id", "price", "order"]
    assert len(sd.df) == 3
    assert list(sd.df[SOURCE_COLUMN]) == ["stock", "stock", "purchase"]
    # Missing columns are filled with empty strings.
    assert list(sd.df["order"]) == ["", "", "o1"]


def test_auto_map_infers_types_and_excludes_source_column(sources):
    cols = expand_entity_columns("stock", {}, sources["stock"])
    assert cols == {
        "product_id": {"db_type": "BIGINT"},
        "price": {"db_type": "NUMERIC"},
    }


def test_hybrid_manual_overrides_win(sources):
    ecfg = {"auto_map": True, "columns": {"product_id": {"is_key": True}}}
    cols = expand_entity_columns("stock", ecfg, sources["stock"])
    assert cols["product_id"] == {"is_key": True}
    assert cols["price"] == {"db_type": "NUMERIC"}


def test_csv_columns_restricts_auto_map(sources):
    ecfg = {"csv_columns": ["1"]}
    cols = expand_entity_columns("stock", ecfg, sources["stock"])
    assert list(cols) == ["product_id"]


def test_csv_columns_with_manual_only_raises(sources):
    ecfg = {"columns": {"product_id": {}}, "csv_columns": ["1"]}
    with pytest.raises(MappingError, match="csv_columns"):
        expand_entity_columns("stock", ecfg, sources["stock"])


def test_binding_empty_source_list_raises(sources):
    with pytest.raises(MappingError, match="empty"):
        bind_entity_source("x", {"source": []}, sources)


def test_binding_invalid_source_type_raises(sources):
    with pytest.raises(MappingError, match="invalid"):
        bind_entity_source("x", {"source": 123}, sources)


def test_manual_only_columns_returns_copy_not_original(sources):
    ecfg = {"columns": {"product_id": {"is_key": True}}}
    cols = expand_entity_columns("stock", ecfg, sources["stock"])
    cols["product_id"] = "mutated"
    assert ecfg["columns"]["product_id"] == {"is_key": True}
