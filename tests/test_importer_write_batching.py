"""Write-path batching per backend, exercised with injected fake clients.

These are the first tests to run the importer write loop at all — the rest of
the suite is dry-run. Each fake records how the driver was called so we can
assert batched vs row-at-a-time behavior without a live database.
"""

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
