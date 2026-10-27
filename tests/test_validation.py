"""validate_backend_entities: per-entity columns, filters, keys, relationships."""

import pandas as pd
import pytest

from polyglotimportcsv.business_exception import MappingError
from polyglotimportcsv.mapping_resolver import BoundEntity
from polyglotimportcsv.validation import validate_backend_entities, validate_headers


def _be(name, cfg, columns):
    df = pd.DataFrame({c: ["v"] for c in columns})
    kinds = {c: "string" for c in columns}
    return BoundEntity(name=name, cfg=cfg, df=df, kinds=kinds)


def test_unknown_column_raises():
    be = _be("t", {"columns": {"nope": {}}}, ["a", "_source"])
    with pytest.raises(MappingError, match="unknown column"):
        validate_backend_entities("redis", {}, {"t": be})


def test_source_pseudo_column_is_valid():
    be = _be(
        "t",
        {"columns": {"a": {"is_key": True}, "_source": {"schema_column": "event_type"}}},
        ["a", "_source"],
    )
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


# -- header-level validation shared by the CLI and the GUI ---------------------


def test_validate_headers_reports_unknown_mapped_column():
    cfg = {"sources": {"s": "s.csv"}, "postgres": {"entities": {"t": {"source": "s", "columns": {"nope": {}}}}}}
    with pytest.raises(MappingError, match="unknown column: nope"):
        validate_headers(cfg, {"s": ["a", "b"]}, (), ["postgres"])


def test_validate_headers_gives_unknown_names_the_combined_header():
    cfg = {"sources": {"e": {"file": "j.csv"}}, "redis": {"entities": {"purchase": {"columns": {"a": {"is_key": True}}}}}}
    validate_headers(cfg, {"e": ["a", "b"]}, ("e",), ["redis"])  # no error


@pytest.mark.parametrize("ename,entity", [
    ("t", {"source": "e"}),
    ("t", {"source": ["stock", "e"]}),
    ("e", {}),  # no source: bound by the entity's own name, here the combined file's
])
def test_validate_headers_rejects_the_declared_name_of_a_combined_file_as_a_source(ename, entity):
    entity = {**entity, "columns": {"a": {"is_key": True}}}
    cfg = {"sources": {"e": {"file": "j.csv"}}, "redis": {"entities": {ename: entity}}}
    with pytest.raises(MappingError) as exc:
        validate_headers(cfg, {"e": ["a", "b"]}, ("e",), ["redis"])
    assert f"Entity '{ename}' (redis): 'e' is the name of a combined CSV" in str(exc.value)
    assert "origin values of that file" in str(exc.value)


def test_validate_headers_accepts_a_declared_plain_source_beside_a_combined_one():
    cfg = {"sources": {"cart": "c.csv", "e": {"file": "j.csv"}}, "redis": {"entities": {
        "c": {"source": "cart", "columns": {"a": {"is_key": True}}},
        "s": {"source": ["stock", "cart"], "columns": {"a": {"is_key": True}}},
    }}}
    validate_headers(cfg, {"cart": ["a"], "e": ["a", "b"]}, ("e",), ["redis"])


def test_validate_headers_without_combined_sources_rejects_unknown_names():
    cfg = {"sources": {"e": "e.csv"}, "redis": {"entities": {"purchase": {"columns": {"a": {"is_key": True}}}}}}
    with pytest.raises(MappingError, match="purchase"):
        validate_headers(cfg, {"e": ["a", "b"]}, (), ["redis"])


def test_validate_headers_unions_every_combined_header_for_unknown_names():
    cfg = {
        "sources": {"A": {"file": "a.csv"}, "B": {"file": "b.csv"}},
        "redis": {"entities": {
            "ea": {"source": "sa", "columns": {"x1": {"is_key": True}}},
            "eb": {"source": "sb", "columns": {"y1": {"is_key": True}}},
        }},
    }
    validate_headers(cfg, {"A": ["x1"], "B": ["y1"]}, ("A", "B"), ["redis"])


def test_validate_headers_expands_auto_mapped_columns_from_the_header():
    cfg = {"sources": {"s": "s.csv"}, "redis": {"entities": {"t": {
        "source": "s", "columns": {"id": {"is_key": True}}, "auto_map": True,
    }}}}
    validate_headers(cfg, {"s": ["id", "name"]}, (), ["redis"])


def test_validate_headers_only_checks_the_requested_dbms():
    cfg = {"sources": {"s": "s.csv"},
           "postgres": {"entities": {"t": {"source": "s", "columns": {"nope": {}}}}},
           "mongodb": {"entities": {"t": {"source": "s", "columns": {"a": {}}}}}}
    validate_headers(cfg, {"s": ["a"]}, (), ["mongodb"])


@pytest.mark.parametrize("dbms", ["redis", "neo4j"])
def test_kv_and_graph_entities_need_exactly_one_key(dbms):
    none = _be("t", {"columns": {"a": {}}}, ["a", "_source"])
    with pytest.raises(MappingError, match="Entity 't' in '%s' must have exactly one is_key column" % dbms):
        validate_backend_entities(dbms, {}, {"t": none})
    two = _be("t", {"columns": {"a": {"is_key": True}, "b": {"is_key": True}}}, ["a", "b", "_source"])
    with pytest.raises(MappingError, match="exactly one is_key"):
        validate_backend_entities(dbms, {}, {"t": two})
    one = _be("t", {"columns": {"a": {"is_key": True}, "b": {}}}, ["a", "b", "_source"])
    validate_backend_entities(dbms, {}, {"t": one})


@pytest.mark.parametrize("dbms", ["postgres", "mongodb", "cassandra"])
def test_other_dbms_do_not_need_a_key_column(dbms):
    cfg = {"columns": {"a": {}}}
    if dbms == "cassandra":
        cfg["cassandra_partition"] = ["a"]
    validate_backend_entities(dbms, {}, {"t": _be("t", cfg, ["a", "_source"])})


def test_cassandra_entity_needs_a_partition():
    missing = _be("t", {"columns": {"a": {}}}, ["a", "_source"])
    with pytest.raises(MappingError, match="cassandra_partition"):
        validate_backend_entities("cassandra", {}, {"t": missing})
    empty = _be("t", {"columns": {"a": {}}, "cassandra_partition": []}, ["a", "_source"])
    with pytest.raises(MappingError, match="cassandra_partition"):
        validate_backend_entities("cassandra", {}, {"t": empty})
    ok = _be("t", {"columns": {"a": {}}, "cassandra_partition": ["a"]}, ["a", "_source"])
    validate_backend_entities("cassandra", {}, {"t": ok})


def _each(column):
    return [{"column": column, "operator": "each"}]


@pytest.mark.parametrize("end", ["from", "to"])
def test_postgres_relationship_endpoint_cannot_use_each(end):
    frm_cfg = {"columns": {"product_id": {}}}
    to_cfg = {"columns": {"product_id": {"is_key": True}}}
    (frm_cfg if end == "from" else to_cfg)["filters"] = _each("product_id")
    frm = _be("orders", frm_cfg, ["product_id", "_source"])
    to = _be("products", to_cfg, ["product_id", "_source"])
    bcfg = {"relationships": {"r": {"from": "orders", "to": "products", "foreign_key": "product_id"}}}
    with pytest.raises(MappingError, match="'each' filter"):
        validate_backend_entities("postgres", bcfg, {"orders": frm, "products": to})


@pytest.mark.parametrize("end", ["from", "to"])
def test_neo4j_relationship_endpoint_cannot_use_each(end):
    frm_cfg = {"columns": {"user_id": {"is_key": True}, "product_id": {}}}
    to_cfg = {"columns": {"product_id": {"is_key": True}}}
    (frm_cfg if end == "from" else to_cfg)["filters"] = _each("product_id")
    frm = _be("User", frm_cfg, ["user_id", "product_id", "_source"])
    to = _be("Product", to_cfg, ["product_id", "_source"])
    bcfg = {"relationships": {"r": {"from": "User", "to": "Product"}}}
    with pytest.raises(MappingError, match="'each' filter"):
        validate_backend_entities("neo4j", bcfg, {"User": frm, "Product": to})


def test_neo4j_relationship_needs_both_key_columns_in_the_from_source():
    to = _be("Product", {"columns": {"product_id": {"is_key": True}}}, ["product_id", "_source"])
    bcfg = {"relationships": {"r": {"from": "User", "to": "Product"}}}
    ok = _be("User", {"columns": {"user_id": {"is_key": True}}}, ["user_id", "product_id", "_source"])
    validate_backend_entities("neo4j", bcfg, {"User": ok, "Product": to})
    no_to_key = _be("User", {"columns": {"user_id": {"is_key": True}}}, ["user_id", "_source"])
    with pytest.raises(MappingError, match="product_id"):
        validate_backend_entities("neo4j", bcfg, {"User": no_to_key, "Product": to})


def test_neo4j_relationship_resolves_a_csv_column_key_in_the_from_source():
    frm = _be("User", {"columns": {"id": {"is_key": True, "csv_column": "user_id"}}},
              ["user_id", "product_id", "_source"])
    to = _be("Product", {"columns": {"id": {"is_key": True, "csv_column": "product_id"}}},
             ["product_id", "_source"])
    bcfg = {"relationships": {"r": {"from": "User", "to": "Product"}}}
    validate_backend_entities("neo4j", bcfg, {"User": frm, "Product": to})
    frm_missing = _be("User", {"columns": {"id": {"is_key": True, "csv_column": "user_id"}}},
                      ["user_id", "_source"])
    with pytest.raises(MappingError, match="product_id"):
        validate_backend_entities("neo4j", bcfg, {"User": frm_missing, "Product": to})
