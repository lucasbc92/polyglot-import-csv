"""Equivalence oracle: iter_rows must be indistinguishable from iterrows.

Every importer and sink shapes rows through one of four helpers. Swapping the
frame-wide iteration underneath them is only safe if each helper produces
byte-identical output -- same values AND same Python types, since a np.int64
leaking where an int used to be would reach the DB drivers (and json.dumps).
This runs all four over the committed data/benchmark/ reference for every entity
of every backend, in both multi and combined mode.
"""

import json
from pathlib import Path

import pytest

from polyglotimportcsv.importers.cassandra_importer import _row_values
from polyglotimportcsv.importers.neo4j_importer import props_from_row
from polyglotimportcsv.mapping_resolver import resolve_backend_entities
from polyglotimportcsv.materialize import mongo_document_from_row, redis_payload_from_row
from polyglotimportcsv.row_view import iter_rows
from polyglotimportcsv.sources import load_sources

_REF = Path("data/benchmark")
_CFG_DIR = Path("data/ecommerce")


def _typed(obj):
    """Value plus exact type, recursively -- so 1 and np.int64(1) do not compare equal."""
    if isinstance(obj, dict):
        return {k: _typed(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return type(obj).__name__, [_typed(v) for v in obj]
    return type(obj).__name__, obj


def _bound(mode):
    cfg = json.loads((_CFG_DIR / (
        "import_config_combined.json" if mode == "combined" else "import_config.json"
    )).read_text(encoding="utf-8"))
    if mode == "combined":
        ov = {"ecommerce": str(_REF / "ecommerce_join.csv")}
    else:
        ov = {s: str(_REF / f"ecommerce_{s}.csv")
              for s in ("stock", "purchase", "select_product", "add_to_cart")}
    sources = load_sources(cfg.get("sources") or {}, ".", ov)
    out = {}
    for backend in ("postgres", "mongodb", "cassandra", "redis", "neo4j"):
        if backend in cfg:
            out[backend] = resolve_backend_entities(cfg[backend], sources)
    return out


def _both_ways(df, fn):
    old = [fn(row) for _, row in df.iterrows()]
    new = [fn(row) for row in iter_rows(df)]
    return old, new


@pytest.mark.parametrize("mode", ["multi", "combined"])
def test_neo4j_props_identical(mode):
    for be in _bound(mode)["neo4j"].values():
        old, new = _both_ways(be.df, lambda r: props_from_row(r, be.cfg))
        assert old and _typed(old) == _typed(new)


@pytest.mark.parametrize("mode", ["multi", "combined"])
def test_mongo_documents_identical(mode):
    for be in _bound(mode)["mongodb"].values():
        old, new = _both_ways(be.df, lambda r: mongo_document_from_row(r, be.cfg))
        assert old and _typed(old) == _typed(new)


@pytest.mark.parametrize("mode", ["multi", "combined"])
def test_redis_payloads_identical(mode):
    def payload(row, cfg):
        try:
            return redis_payload_from_row(row, cfg)
        except ValueError as e:  # skipped rows must be skipped the same way
            return f"ValueError:{e}"

    for be in _bound(mode)["redis"].values():
        old, new = _both_ways(be.df, lambda r: payload(r, be.cfg))
        assert old and _typed(old) == _typed(new)


@pytest.mark.parametrize("mode", ["multi", "combined"])
def test_cassandra_row_values_identical(mode):
    for be in _bound(mode)["cassandra"].values():
        ordered_src = list(be.df.columns)
        # Alternate text/non-text so both branches of _row_values are exercised.
        cql_by_src = {s: ("text" if i % 2 else "int")
                      for i, s in enumerate(ordered_src)}
        old, new = _both_ways(be.df, lambda r: _row_values(r, ordered_src, cql_by_src))
        assert old and _typed(old) == _typed(new)


def test_row_view_surface_matches_series():
    """row[col], row.get, `in row.index` and list(row.index) behave as before."""
    import pandas as pd

    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    for (_, series), view in zip(df.iterrows(), iter_rows(df)):
        assert list(view.index) == list(series.index)
        assert "a" in view.index and "missing" not in view.index
        assert view["b"] == series["b"]
        assert view.get("a") == series.get("a")
        assert view.get("missing") is None
