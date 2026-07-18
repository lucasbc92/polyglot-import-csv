"""Mongo/Redis importers consume per-entity bound frames (dry-run, no DB)."""

import pandas as pd

from polyglotimportcsv.importers.mongodb_importer import run_mongodb_import
from polyglotimportcsv.importers.redis_importer import run_redis_import
from polyglotimportcsv.mapping_resolver import BoundEntity


def _be(name, cfg, data):
    df = pd.DataFrame(data)
    kinds = {c: "string" for c in df.columns}
    return BoundEntity(name=name, cfg=cfg, df=df, kinds=kinds)


def test_mongodb_dry_run_counts():
    be = _be("catalog", {"columns": {"a": {}}}, {"a": ["1", "2"], "_source": ["s", "s"]})
    lines = run_mongodb_import({}, {"catalog": be}, dry_run=True, create_schema=False)
    assert any("collection catalog: 2 document(s)" in L for L in lines)


def test_redis_dry_run_counts():
    be = _be(
        "cart",
        {"columns": {"k": {"is_key": True}, "v": {}}},
        {"k": ["a", "b"], "v": ["1", "2"], "_source": ["s", "s"]},
    )
    lines = run_redis_import({}, {"cart": be}, dry_run=True, create_schema=False)
    assert any("entity cart: 2 row(s)" in L for L in lines)
