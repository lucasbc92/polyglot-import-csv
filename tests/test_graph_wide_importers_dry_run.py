"""Cassandra/Neo4j importers consume per-entity bound frames (dry-run, no DB)."""

import pandas as pd

from polyglotimportcsv.importers.cassandra_importer import run_cassandra_import
from polyglotimportcsv.importers.neo4j_importer import run_neo4j_import
from polyglotimportcsv.mapping_resolver import BoundEntity


def _be(name, cfg, data):
    df = pd.DataFrame(data)
    kinds = {c: "string" for c in df.columns}
    return BoundEntity(name=name, cfg=cfg, df=df, kinds=kinds)


def test_cassandra_dry_run_counts():
    be = _be(
        "log",
        {
            "columns": {"user_id": {}, "_source": {"schema_column": "event_type"}},
            "cassandra_partition": ["user_id"],
        },
        {"user_id": ["u1", "u2", "u3"], "_source": ["a", "b", "a"]},
    )
    lines = run_cassandra_import({}, {"log": be}, dry_run=True, create_schema=False)
    assert any("table log: 3 row(s)" in L for L in lines)


def test_neo4j_dry_run_counts_nodes_and_relationships():
    user = _be(
        "User",
        {"columns": {"user_id": {"is_key": True}}},
        {"user_id": ["u1", "u2"], "product_id": ["p1", "p2"], "_source": ["purchase"] * 2},
    )
    prod = _be(
        "Product",
        {"columns": {"product_id": {"is_key": True}}},
        {"product_id": ["p1"], "_source": ["stock"]},
    )
    bcfg = {
        "relationships": {
            "PURCHASED": {"from": "User", "to": "Product", "type": "PURCHASED", "columns": {}}
        }
    }
    lines = run_neo4j_import(bcfg, {"User": user, "Product": prod}, dry_run=True, create_schema=False)
    assert any("label User: 2 row(s)" in L for L in lines)
    assert any("relationship type PURCHASED" in L for L in lines)
