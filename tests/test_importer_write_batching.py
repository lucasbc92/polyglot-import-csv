"""Batching of the writers behind the sinks, exercised with injected fake clients.

``_write_batched`` (Redis, Cassandra), ``_merge_nodes_batched`` and
``_merge_rels_batched`` (Neo4j) are called directly. Each fake records how the
driver was called so we can assert batched vs row-at-a-time behavior without a
live database.
"""

import pandas as pd
import pytest

from polyglotimportcsv.business_exception import ImportExecutionError


# ---------- Redis ----------

class _FakePipeline:
    def __init__(self, parent):
        self.parent = parent
        self.queued = 0

    def set(self, k, v):
        self.queued += 1
        return self

    def execute(self):
        self.parent.pipeline_execs += 1
        self.parent.piped_sets += self.queued
        self.queued = 0
        return []


class _FakeRedis:
    def __init__(self):
        self.set_calls = 0
        self.pipeline_execs = 0
        self.piped_sets = 0

    def ping(self):
        return True

    def set(self, k, v):
        self.set_calls += 1

    def pipeline(self, transaction=False):
        return _FakePipeline(self)


def _redis_pairs(n):
    from polyglotimportcsv.importers.redis_importer import _kv_pairs
    df = pd.DataFrame(
        {"cart_id": [f"c{i}" for i in range(n)], "qty": [str(i) for i in range(n)]}
    )
    return _kv_pairs(df, {"columns": {"cart_id": {"is_key": True}, "qty": {}}})


def test_redis_write_batched_uses_pipeline_no_per_row_set():
    from polyglotimportcsv.importers.redis_importer import _write_batched
    fake = _FakeRedis()
    count = _write_batched(fake, _redis_pairs(2500), lambda n: None)
    assert count == 2500
    assert fake.set_calls == 0
    assert fake.pipeline_execs == 3          # ceil(2500/1000)
    assert fake.piped_sets == 2500


# ---------- Cassandra ----------

class _FakeSession:
    def __init__(self):
        self.executes = []          # each execute() call

    def execute(self, stmt, params=None):
        self.executes.append((stmt, params))
        return []


def _cass_params(n):
    return [[f"u{i}", "x"] for i in range(n)]


def test_cassandra_write_batched_uses_concurrent_not_per_row(monkeypatch):
    import polyglotimportcsv.importers.cassandra_importer as ci
    calls = {"concurrent": 0, "rows": 0}

    def fake_concurrent(session, prepared, params, concurrency=64, **kw):
        calls["concurrent"] += 1
        calls["rows"] += len(list(params))
        return []

    monkeypatch.setattr(ci, "execute_concurrent_with_args", fake_concurrent)
    session = _FakeSession()
    count = ci._write_batched(session, ("prep", "cql"), _cass_params(2500), lambda n: None)
    assert count == 2500
    assert calls["concurrent"] == 1
    assert calls["rows"] == 2500
    # No per-row execute for INSERTs (the session's execute() is only for DDL)
    assert session.executes == []


def test_cassandra_write_batched_raises_when_driver_unavailable(monkeypatch):
    """If cassandra.concurrent could not be imported (module attribute is None),
    the batched path must fail with a friendly ImportExecutionError instead of
    a raw AttributeError/TypeError."""
    import polyglotimportcsv.importers.cassandra_importer as ci

    monkeypatch.setattr(ci, "execute_concurrent_with_args", None)
    with pytest.raises(ImportExecutionError):
        ci._write_batched(_FakeSession(), ("prep", "cql"), _cass_params(5), lambda n: None)


# ---------- Neo4j ----------

class _FakeNeoSession:
    def __init__(self, recorder):
        self.recorder = recorder

    def execute_write(self, fn, *a, **k):
        return fn(_FakeTx(self.recorder), *a, **k)


class _FakeTx:
    def __init__(self, recorder):
        self.recorder = recorder

    def run(self, q, **params):
        self.recorder["tx_run"].append((q, params))
        return []


def test_neo4j_merge_nodes_batched_uses_unwind():
    import polyglotimportcsv.importers.neo4j_importer as ni
    rec = {"tx_run": []}
    props_list = [{"user_id": f"u{i}"} for i in range(2500)]
    merged = ni._merge_nodes_batched(
        _FakeNeoSession(rec), "User", "user_id", props_list, lambda n: None
    )
    assert merged == 2500
    # Nodes written in UNWIND batches inside execute_write, not one run() per row.
    node_batches = [p for q, p in rec["tx_run"] if "UNWIND" in q and "MERGE (n" in q]
    assert sum(len(p["batch"]) for p in node_batches) == 2500
    assert len(node_batches) == 3          # ceil(2500/1000)
    assert len(rec["tx_run"]) == 3


def test_dedupe_props_is_first_wins_and_counts_the_skipped():
    from polyglotimportcsv.importers.neo4j_importer import _dedupe_props, props_from_row
    df = pd.DataFrame({"user_id": ["u0", "u1", "u0", "u2", "u1"]})
    props_list, skipped = _dedupe_props(
        df, {"columns": {"user_id": {"is_key": True}}}, "user_id", props_from_row
    )
    assert [p["user_id"] for p in props_list] == ["u0", "u1", "u2"]   # first-wins
    assert skipped == 2


# ---------- Neo4j relationships ----------

def test_neo4j_merge_rels_batched_uses_unwind():
    """User -[:PURCHASED {order_number}]-> Product, with a non-key rel prop
    (rating) so rprops is non-empty and a merge-key prop (order_number) so the
    `mk` path is exercised. Mirrors the real config shape (see
    data/ecommerce/import_config.json, neo4j.relationships.PURCHASED)."""
    import polyglotimportcsv.importers.neo4j_importer as ni
    total = 1500
    product_ids = [f"p{i}" for i in range(total)]
    product_ids[0] = None  # null to-id -> row must be skipped
    df = pd.DataFrame({
        "user_id": [f"u{i}" for i in range(total)],
        "product_id": product_ids,
        "order_number": [f"o{i}" for i in range(total)],
        "rating": [i % 5 for i in range(total)],
    })
    rel_cols = {"order_number": {"is_key": True}, "rating": {}}
    rows = ni._rel_rows_for_batch(df, "user_id", "product_id", rel_cols, ["order_number"])
    rec = {"tx_run": []}
    count = ni._merge_rels_batched(
        _FakeNeoSession(rec), "User", "user_id", "Product", "product_id",
        "PURCHASED", ["order_number"], rows, lambda n: None,
    )
    rel_batches = [
        (q, p) for q, p in rec["tx_run"]
        if "UNWIND" in q and "MERGE (a)" in q and "]->(b)" in q
    ]
    assert count == 1499
    assert len(rel_batches) == 2                       # ceil(1499/1000), one row skipped
    total_rows = sum(len(p["batch"]) for _, p in rel_batches)
    assert total_rows == 1499
    q0, p0 = rel_batches[0]
    assert "row.mk.order_number" in q0                  # merge-key mapped into nested row.mk
    sample = p0["batch"][0]
    assert set(sample.keys()) == {"a_id", "b_id", "rprops", "mk"}
    assert set(sample["mk"].keys()) == {"order_number"}
    assert "order_number" not in sample["rprops"]        # merge key excluded from rprops
    assert "rating" in sample["rprops"]
