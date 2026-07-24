"""Write-path batching per backend, exercised with injected fake clients.

These are the first tests to run the importer write loop at all — the rest of
the suite is dry-run. Each fake records how the driver was called so we can
assert batched vs row-at-a-time behavior without a live database.
"""

import logging

import pandas as pd

from polyglotimportcsv.mapping_resolver import BoundEntity


def _be(name, cfg, data):
    df = pd.DataFrame(data)
    kinds = {c: "string" for c in df.columns}
    return BoundEntity(name=name, cfg=cfg, df=df, kinds=kinds)


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


def _redis_entity(n):
    return _be(
        "cart",
        {"columns": {"cart_id": {"is_key": True}, "qty": {}}},
        {"cart_id": [f"c{i}" for i in range(n)], "qty": [str(i) for i in range(n)]},
    )


def test_redis_optimized_uses_pipeline_no_per_row_set():
    from polyglotimportcsv.importers.redis_importer import run_redis_import
    fake = _FakeRedis()
    run_redis_import(
        {"entities": {}}, {"cart": _redis_entity(2500)},
        dry_run=False, create_schema=False, strategy="optimized",
        client_factory=lambda conn: fake,
    )
    assert fake.set_calls == 0
    assert fake.pipeline_execs == 3          # ceil(2500/1000)
    assert fake.piped_sets == 2500


def test_redis_naive_sets_one_per_row():
    from polyglotimportcsv.importers.redis_importer import run_redis_import
    fake = _FakeRedis()
    run_redis_import(
        {"entities": {}}, {"cart": _redis_entity(2500)},
        dry_run=False, create_schema=False, strategy="naive",
        client_factory=lambda conn: fake,
    )
    assert fake.set_calls == 2500
    assert fake.pipeline_execs == 0


# ---------- Cassandra ----------

class _FakeSession:
    def __init__(self):
        self.executes = []          # each execute() call
        self.prepared = 0

    def execute(self, stmt, params=None):
        self.executes.append((stmt, params))
        return []

    def prepare(self, cql):
        self.prepared += 1
        return ("prep", cql)

    def set_keyspace(self, ks):
        pass


class _FakeCluster:
    def __init__(self, session):
        self._session = session

    def shutdown(self):
        pass


def _cass_entity(n):
    return _be(
        "user_activity_log",
        {"columns": {"user_id": {"is_key": True}, "action": {}},
         "cassandra_partition": ["user_id"]},
        {"user_id": [f"u{i}" for i in range(n)], "action": ["x"] * n},
    )


def test_cassandra_optimized_uses_concurrent_not_per_row(monkeypatch):
    import polyglotimportcsv.importers.cassandra_importer as ci
    calls = {"concurrent": 0, "rows": 0}

    def fake_concurrent(session, prepared, params, concurrency=64, **kw):
        calls["concurrent"] += 1
        calls["rows"] += len(list(params))
        return []

    monkeypatch.setattr(ci, "execute_concurrent_with_args", fake_concurrent)
    session = _FakeSession()
    ci.run_cassandra_import(
        {"connection": {}}, {"user_activity_log": _cass_entity(2500)},
        dry_run=False, create_schema=False, strategy="optimized",
        session_factory=lambda conn: (_FakeCluster(session), session),
    )
    assert calls["concurrent"] == 1
    assert calls["rows"] == 2500
    # No per-row execute for INSERTs (execute() only used for DDL, skipped here)
    assert all("INSERT" not in str(s) for s, _ in session.executes)


def test_cassandra_naive_executes_one_per_row():
    import polyglotimportcsv.importers.cassandra_importer as ci
    session = _FakeSession()
    ci.run_cassandra_import(
        {"connection": {}}, {"user_activity_log": _cass_entity(2500)},
        dry_run=False, create_schema=False, strategy="naive",
        session_factory=lambda conn: (_FakeCluster(session), session),
    )
    insert_execs = [e for e in session.executes if e[1] is not None]
    assert len(insert_execs) == 2500


def test_cassandra_optimized_raises_when_driver_unavailable(monkeypatch):
    """If cassandra.concurrent could not be imported (module attribute is None),
    the batched path must fail with a friendly ImportExecutionError instead of
    a raw AttributeError/TypeError."""
    import polyglotimportcsv.importers.cassandra_importer as ci
    from polyglotimportcsv.business_exception import ImportExecutionError

    monkeypatch.setattr(ci, "execute_concurrent_with_args", None)
    session = _FakeSession()
    try:
        ci.run_cassandra_import(
            {"connection": {}}, {"user_activity_log": _cass_entity(5)},
            dry_run=False, create_schema=False, strategy="optimized",
            session_factory=lambda conn: (_FakeCluster(session), session),
        )
        assert False, "expected ImportExecutionError"
    except ImportExecutionError:
        pass


# ---------- Neo4j ----------

class _FakeNeoSession:
    def __init__(self, recorder):
        self.recorder = recorder

    def run(self, q, **params):
        self.recorder["run"].append((q, params))
        return []

    def execute_write(self, fn, *a, **k):
        return fn(_FakeTx(self.recorder), *a, **k)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeTx:
    def __init__(self, recorder):
        self.recorder = recorder

    def run(self, q, **params):
        self.recorder["tx_run"].append((q, params))
        return []


class _FakeDriver:
    def __init__(self, recorder):
        self.recorder = recorder

    def verify_connectivity(self):
        pass

    def session(self, database=None):
        return _FakeNeoSession(self.recorder)

    def close(self):
        pass


def _neo_entities(n):
    user = _be("User", {"columns": {"user_id": {"is_key": True}}},
               {"user_id": [f"u{i}" for i in range(n)]})
    return {"User": user}


def test_neo4j_optimized_batches_nodes_with_unwind():
    import polyglotimportcsv.importers.neo4j_importer as ni
    rec = {"run": [], "tx_run": []}
    ni.run_neo4j_import(
        {"connection": {}}, _neo_entities(2500),
        dry_run=False, create_schema=True, strategy="optimized",
        driver_factory=lambda conn: _FakeDriver(rec),
    )
    # Nodes written in UNWIND batches inside execute_write, not one run() per row.
    assert any("UNWIND" in q for q, _ in rec["tx_run"])
    node_batches = [p for q, p in rec["tx_run"] if "UNWIND" in q and "MERGE (n" in q]
    assert sum(len(p["batch"]) for p in node_batches) == 2500
    assert len(node_batches) == 3          # ceil(2500/1000)
    # A uniqueness constraint was created.
    assert any("CONSTRAINT" in q and "UNIQUE" in q for q, _ in rec["run"])


def test_neo4j_naive_runs_one_merge_per_row():
    import polyglotimportcsv.importers.neo4j_importer as ni
    rec = {"run": [], "tx_run": []}
    ni.run_neo4j_import(
        {"connection": {}}, _neo_entities(2500),
        dry_run=False, create_schema=False, strategy="naive",
        driver_factory=lambda conn: _FakeDriver(rec),
    )
    merges = [q for q, _ in rec["run"] if "MERGE (n" in q]
    assert len(merges) == 2500


def test_neo4j_optimized_dedupes_nodes_first_wins_and_warns(caplog):
    """Duplicate key values must be first-wins deduped (via _dedupe_props) and
    the skip must surface through the existing warning, unchanged by batching."""
    import polyglotimportcsv.importers.neo4j_importer as ni
    rec = {"run": [], "tx_run": []}
    user = _be(
        "User", {"columns": {"user_id": {"is_key": True}}},
        {"user_id": ["u0", "u1", "u0", "u2", "u1"]},
    )
    with caplog.at_level(logging.WARNING, logger="polyglotimportcsv.importers.neo4j_importer"):
        ni.run_neo4j_import(
            {"connection": {}}, {"User": user},
            dry_run=False, create_schema=False, strategy="optimized",
            driver_factory=lambda conn: _FakeDriver(rec),
        )
    node_batches = [p for q, p in rec["tx_run"] if "UNWIND" in q and "MERGE (n" in q]
    keys = sorted({row["k"] for p in node_batches for row in p["batch"]})
    assert keys == ["u0", "u1", "u2"]                      # first-wins, 3 distinct keys
    assert sum(len(p["batch"]) for p in node_batches) == 3
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any(
        "duplicate key value(s) skipped" in r.message and "2 " in r.message
        for r in warnings
    )


# ---------- Neo4j relationships ----------

def _neo_rel_fixture(n, bad_row=False):
    """User -[:PURCHASED {order_number}]-> Product, with a non-key rel prop
    (rating) so rprops is non-empty and a merge-key prop (order_number) so the
    `mk` path is exercised. Mirrors the real config shape (see
    data/ecommerce/import_config.json, neo4j.relationships.PURCHASED)."""
    product_ids = [f"p{i}" for i in range(n)]
    user_product_ids = list(product_ids)
    if bad_row:
        user_product_ids[0] = None  # null to-id -> row must be skipped
    user = _be(
        "User", {"columns": {"user_id": {"is_key": True}}},
        {
            "user_id": [f"u{i}" for i in range(n)],
            "product_id": user_product_ids,
            "order_number": [f"o{i}" for i in range(n)],
            "rating": [i % 5 for i in range(n)],
        },
    )
    product = _be(
        "Product", {"columns": {"product_id": {"is_key": True}}},
        {"product_id": product_ids},
    )
    bcfg = {
        "relationships": {
            "PURCHASED": {
                "from": "User",
                "to": "Product",
                "type": "PURCHASED",
                "columns": {
                    "order_number": {"is_key": True},
                    "rating": {},
                },
            }
        }
    }
    return {"User": user, "Product": product}, bcfg


def test_neo4j_optimized_batches_relationships_with_unwind():
    import polyglotimportcsv.importers.neo4j_importer as ni
    rec = {"run": [], "tx_run": []}
    entities, bcfg = _neo_rel_fixture(1500, bad_row=True)
    ni.run_neo4j_import(
        bcfg, entities,
        dry_run=False, create_schema=False, strategy="optimized",
        driver_factory=lambda conn: _FakeDriver(rec),
    )
    rel_batches = [
        (q, p) for q, p in rec["tx_run"]
        if "UNWIND" in q and "MERGE (a)" in q and "]->(b)" in q
    ]
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


def test_neo4j_naive_relationship_skips_null_ids_and_runs_one_merge_per_row():
    import polyglotimportcsv.importers.neo4j_importer as ni
    rec = {"run": [], "tx_run": []}
    entities, bcfg = _neo_rel_fixture(50, bad_row=True)
    ni.run_neo4j_import(
        bcfg, entities,
        dry_run=False, create_schema=False, strategy="naive",
        driver_factory=lambda conn: _FakeDriver(rec),
    )
    rel_runs = [(q, p) for q, p in rec["run"] if "MERGE (a)" in q]
    assert len(rel_runs) == 49                          # one row skipped (null product_id)
    q, params = rel_runs[0]
    assert "$a_id" in q and "$b_id" in q and "]->(b)" in q
    assert {"a_id", "b_id", "rprops"} <= set(params.keys())
    assert any(k.startswith("mk_") for k in params.keys())
    assert "order_number" not in params["rprops"]        # merge key excluded from rprops
