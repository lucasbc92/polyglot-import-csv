"""validate_backend_entities: per-entity columns, filters, keys, relationships."""

import pandas as pd
import pytest

from polyglotimportcsv.business_exception import MappingError
from polyglotimportcsv.mapping_resolver import BoundEntity
from polyglotimportcsv.validation import validate_backend_entities


def _be(name, cfg, columns):
    df = pd.DataFrame({c: ["v"] for c in columns})
    kinds = {c: "string" for c in columns}
    return BoundEntity(name=name, cfg=cfg, df=df, kinds=kinds)


def test_unknown_column_raises():
    be = _be("t", {"columns": {"nope": {}}}, ["a", "_source"])
    with pytest.raises(MappingError, match="unknown column"):
        validate_backend_entities("redis", {}, {"t": be})


def test_source_pseudo_column_is_valid():
    be = _be("t", {"columns": {"_source": {"schema_column": "event_type"}}}, ["a", "_source"])
    validate_backend_entities("redis", {}, {"t": be})


def test_nested_columns_rejected_for_flat_backend():
    be = _be("t", {"columns": {"outer": {"inner": {}}}}, ["inner", "_source"])
    with pytest.raises(MappingError, match="nested"):
        validate_backend_entities("postgres", {}, {"t": be})


def test_filter_on_unknown_column_raises():
    be = _be("t", {"columns": {"a": {}}, "filters": [{"column": "x", "operator": "==", "value": 1}]},
             ["a", "_source"])
    with pytest.raises(MappingError, match="Filter column"):
        validate_backend_entities("redis", {}, {"t": be})


def test_cassandra_partition_must_exist():
    be = _be("t", {"columns": {"a": {}}, "cassandra_partition": ["missing"]}, ["a", "_source"])
    with pytest.raises(MappingError, match="partition"):
        validate_backend_entities("cassandra", {}, {"t": be})


def test_postgres_relationship_targets_checked():
    frm = _be("orders", {"columns": {"product_id": {}}}, ["product_id", "_source"])
    to = _be("products", {"columns": {"product_id": {"is_key": True}}}, ["product_id", "_source"])
    bcfg = {"relationships": {"r": {"from": "orders", "to": "products", "foreign_key": "product_id"}}}
    validate_backend_entities("postgres", bcfg, {"orders": frm, "products": to})
    bad = {"relationships": {"r": {"from": "orders", "to": "products", "foreign_key": "zzz"}}}
    with pytest.raises(MappingError, match="foreign_key"):
        validate_backend_entities("postgres", bad, {"orders": frm, "products": to})
