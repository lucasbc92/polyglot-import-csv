"""Postgres/Mongo/Cassandra/Redis/Neo4j sinks tested against fake DB clients
(no live DB)."""

import json
import logging
from pathlib import Path

import pandas as pd
import pytest

from polyglotimportcsv.business_exception import ImportExecutionError
from polyglotimportcsv.sinks import postgres_sink as pg_mod
from polyglotimportcsv.sinks import mongo_sink as mongo_mod
from polyglotimportcsv.sinks.postgres_sink import PostgresSink
from polyglotimportcsv.sinks.mongo_sink import MongoSink
from polyglotimportcsv.sinks.cassandra_sink import CassandraSink
from polyglotimportcsv.sinks.redis_sink import RedisSink
from polyglotimportcsv.sinks.neo4j_sink import Neo4jSink
from polyglotimportcsv.sources import SOURCE_COLUMN
from polyglotimportcsv.stream_binding import bind_entity_from_sample

CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "ecommerce" / "import_config.json"
_CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

INVENTORY_CFG = _CONFIG["postgres"]["entities"]["inventory"]
PRODUCTS_CFG = _CONFIG["postgres"]["entities"]["products"]
CATEGORIES_CFG = _CONFIG["postgres"]["entities"]["categories"]
PRODUCT_CATALOG_CFG = _CONFIG["mongodb"]["entities"]["product_catalog"]
USER_SESSION_CFG = _CONFIG["redis"]["entities"]["user_session"]
NEO4J_CFG = _CONFIG["neo4j"]
NEO4J_USER_CFG = NEO4J_CFG["entities"]["User"]
# The real config's only cassandra entity unions 4 sources (list); streaming
# doesn't support union sources (see stream_runner), so this sink test uses a
# single-source copy of the same entity/column shape.
CASSANDRA_CFG = dict(_CONFIG["cassandra"]["entities"]["user_activity_log"])
CASSANDRA_CFG["source"] = "stock"


def _stock_sample() -> pd.DataFrame:
    """A small realistic sample of the 'stock' source, with a duplicate
    product_id (row 0 and row 1) so pk-dedupe is exercised in flatten."""
    return pd.DataFrame(
        {
            "product_id": ["1", "1", "2"],
            "product_name": ["Widget", "Widget", "Gadget"],
            "product_variant": ["red", "red", "blue"],
            "product_brand": ["Acme", "Acme", "Acme"],
            "product_description": ["d1", "d1", "d2"],
            "product_image": ["img1", "img1", "img2"],
            "category_id": ["10", "10", "20"],
            "category_name": ["Cat A", "Cat A", "Cat B"],
            "quantity_available": ["5", "5", "3"],
            "price": ["9.99", "9.99", "19.99"],
            "last_restock_date": ["2023-01-01", "2023-01-01", "2023-01-02"],
            SOURCE_COLUMN: ["stock", "stock", "stock"],
        }
    )


# ---------------------------------------------------------------------------
# PostgresSink: fake psycopg2 client
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self):
        self.executed = []  # plain-string statements (DDL)
        self.execute_values_calls = []  # (sql_obj, tuples, page_size)

    def execute(self, stmt):
        self.executed.append(stmt)


class _FakeConn:
    def __init__(self):
        self.autocommit = False
        self.closed = False
        self.cur = _FakeCursor()

    def cursor(self):
        return self.cur

    def close(self):
        self.closed = True


def _fake_execute_values(cur, sql, argslist, page_size=100, fetch=False):
    cur.execute_values_calls.append((sql, list(argslist), page_size))


@pytest.fixture(autouse=True)
def _patch_execute_values(monkeypatch):
    """execute_values needs a *real* psycopg2 cursor to stringify Identifiers
    (C-level check); PostgresSink passes the Composed straight through so a
    fake execute_values can record the call without touching real psycopg2
    internals. See postgres_sink.write_batch for the rationale."""
    monkeypatch.setattr(pg_mod, "execute_values", _fake_execute_values)


def test_ensure_partition_issues_create_table_ddl():
    conn = _FakeConn()
    sink = PostgresSink({"schema": "public"}, connection_factory=lambda c: conn)
    binding = bind_entity_from_sample("inventory", INVENTORY_CFG, _stock_sample(), "stock")

    sink.ensure_partition("inventory", binding)

    assert any("CREATE TABLE IF NOT EXISTS" in s for s in conn.cur.executed)
    assert any('"inventory"' in s for s in conn.cur.executed)
    assert sink._created["inventory"] is binding.cfg


def test_write_batch_inserts_deduped_rows_with_on_conflict():
    conn = _FakeConn()
    sink = PostgresSink({"schema": "public"}, connection_factory=lambda c: conn)
    binding = bind_entity_from_sample("inventory", INVENTORY_CFG, _stock_sample(), "stock")

    written = sink.write_batch("inventory", binding, _stock_sample())

    # product_id "1" is duplicated in the sample; flatten_entity_dataframe
    # dedupes on the pk (keep last), so only 2 rows should be inserted.
    assert written == 2
    assert len(conn.cur.execute_values_calls) == 1
    sql_obj, tuples, page_size = conn.cur.execute_values_calls[0]
    assert len(tuples) == 2
    assert "ON CONFLICT" in repr(sql_obj)
    assert page_size == 500


def test_write_batch_without_pk_has_no_on_conflict_clause():
    # 'categories' has no explicit pk column config here besides category_id
    # which IS a pk; use a synthetic pk-less cfg to exercise the plain-insert path.
    pkless_cfg = dict(INVENTORY_CFG)
    pkless_cfg["columns"] = dict(INVENTORY_CFG["columns"])
    pkless_cfg["columns"]["product_id"] = {"db_type": "BIGINT"}  # no is_key

    conn = _FakeConn()
    sink = PostgresSink({"schema": "public"}, connection_factory=lambda c: conn)
    binding = bind_entity_from_sample("inventory", pkless_cfg, _stock_sample(), "stock")

    written = sink.write_batch("inventory", binding, _stock_sample())

    assert written == 3  # no pk => no dedupe
    sql_obj, tuples, _ = conn.cur.execute_values_calls[0]
    assert "ON CONFLICT" not in repr(sql_obj)


def test_write_batch_empty_writes_nothing():
    conn = _FakeConn()
    sink = PostgresSink({"schema": "public"}, connection_factory=lambda c: conn)
    binding = bind_entity_from_sample("inventory", INVENTORY_CFG, _stock_sample(), "stock")

    written = sink.write_batch("inventory", binding, _stock_sample().iloc[0:0])

    assert written == 0
    assert conn.cur.execute_values_calls == []


def test_close_issues_fk_ddl_when_relationships_present_and_closes_connection():
    relationships = {"product_category": _CONFIG["postgres"]["relationships"]["product_category"]}
    conn = _FakeConn()
    sink = PostgresSink(
        {"schema": "public", "relationships": relationships},
        connection_factory=lambda c: conn,
    )
    sample = _stock_sample()
    products_binding = bind_entity_from_sample("products", PRODUCTS_CFG, sample, "stock")
    categories_binding = bind_entity_from_sample("categories", CATEGORIES_CFG, sample, "stock")
    sink.ensure_partition("products", products_binding)
    sink.ensure_partition("categories", categories_binding)
    conn.cur.executed.clear()  # isolate the FK-only assertions

    sink.close()

    assert any("ALTER TABLE" in s for s in conn.cur.executed)
    assert any("FOREIGN KEY" in s for s in conn.cur.executed)
    assert conn.closed is True


def test_close_skips_fk_ddl_when_no_relationships_declared():
    conn = _FakeConn()
    sink = PostgresSink({"schema": "public"}, connection_factory=lambda c: conn)
    binding = bind_entity_from_sample("inventory", INVENTORY_CFG, _stock_sample(), "stock")
    sink.ensure_partition("inventory", binding)
    conn.cur.executed.clear()

    sink.close()

    assert conn.cur.executed == []
    assert conn.closed is True


def test_create_schema_is_a_noop():
    conn = _FakeConn()
    sink = PostgresSink({"schema": "public"}, connection_factory=lambda c: conn)
    sink.create_schema()
    assert conn.cur.executed == []


# ---------------------------------------------------------------------------
# MongoSink: fake pymongo client
# ---------------------------------------------------------------------------


class _FakeCollection:
    def __init__(self):
        self.insert_many_calls = []

    def insert_many(self, docs):
        self.insert_many_calls.append(docs)


class _FakeDB:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


class _FakeClient:
    def __init__(self):
        self.closed = False
        self.dbs = {}

    def __getitem__(self, name):
        return self.dbs.setdefault(name, _FakeDB())

    def close(self):
        self.closed = True


def test_mongo_write_batch_inserts_one_batch_of_right_length():
    client = _FakeClient()
    sink = MongoSink({"connection": {"database": "shop"}}, client_factory=lambda c: client)
    binding = bind_entity_from_sample(
        "product_catalog", PRODUCT_CATALOG_CFG, _stock_sample(), "stock"
    )

    written = sink.write_batch("product_catalog", binding, _stock_sample())

    assert written == 3  # Mongo doesn't dedupe; all 3 rows become documents
    coll = client.dbs["shop"].collections["product_catalog"]
    assert len(coll.insert_many_calls) == 1
    docs = coll.insert_many_calls[0]
    assert len(docs) == 3
    assert docs[0]["category"] == {"category_id": "10", "category_name": "Cat A"}
    assert docs[0]["stock"]["quantity_available"] == "5"


def test_mongo_write_batch_empty_inserts_nothing():
    client = _FakeClient()
    sink = MongoSink({"connection": {"database": "shop"}}, client_factory=lambda c: client)
    binding = bind_entity_from_sample(
        "product_catalog", PRODUCT_CATALOG_CFG, _stock_sample(), "stock"
    )

    written = sink.write_batch("product_catalog", binding, _stock_sample().iloc[0:0])

    assert written == 0
    assert "product_catalog" not in client.dbs["shop"].collections


def test_mongo_create_schema_and_ensure_partition_are_noops():
    client = _FakeClient()
    sink = MongoSink({"connection": {"database": "shop"}}, client_factory=lambda c: client)
    binding = bind_entity_from_sample(
        "product_catalog", PRODUCT_CATALOG_CFG, _stock_sample(), "stock"
    )
    sink.create_schema()
    sink.ensure_partition("product_catalog", binding)
    assert client.dbs["shop"].collections == {}


def test_mongo_close_closes_client():
    client = _FakeClient()
    sink = MongoSink({"connection": {"database": "shop"}}, client_factory=lambda c: client)
    sink.close()
    assert client.closed is True


# ---------------------------------------------------------------------------
# RedisSink: fake redis client (pipeline style, mirrors test_importer_write_batching)
# ---------------------------------------------------------------------------


class _FakeRedisPipeline:
    def __init__(self, parent):
        self.parent = parent
        self.queued = []

    def set(self, k, v):
        self.queued.append((k, v))
        return self

    def execute(self):
        self.parent.pipeline_execs += 1
        self.parent.sets.extend(self.queued)
        self.queued = []
        return []


class _FakeRedisClient:
    def __init__(self):
        self.set_calls = 0
        self.pipeline_execs = 0
        self.sets = []

    def ping(self):
        return True

    def set(self, k, v):
        self.set_calls += 1

    def pipeline(self, transaction=False):
        return _FakeRedisPipeline(self)


def _user_session_sample():
    return pd.DataFrame(
        {
            "user_id": ["u1", "u2", "u3"],
            "user_name": ["Alice", "Bob", "Carol"],
            "user_email": ["a@x.com", "b@x.com", "c@x.com"],
            "timestamp": ["2023-01-01", "2023-01-02", "2023-01-03"],
            SOURCE_COLUMN: ["select_product", "select_product", "select_product"],
        }
    )


def test_redis_write_batch_pipelines_all_rows_in_one_call():
    client = _FakeRedisClient()
    sink = RedisSink({"connection": {}}, client_factory=lambda c: client)
    binding = bind_entity_from_sample(
        "user_session", USER_SESSION_CFG, _user_session_sample(), "select_product"
    )

    written = sink.write_batch("user_session", binding, _user_session_sample())

    assert written == 3
    assert client.set_calls == 0
    assert client.pipeline_execs == 1
    assert len(client.sets) == 3
    assert {k for k, _ in client.sets} == {"u1", "u2", "u3"}


def test_redis_write_batch_empty_does_nothing():
    client = _FakeRedisClient()
    sink = RedisSink({"connection": {}}, client_factory=lambda c: client)
    binding = bind_entity_from_sample(
        "user_session", USER_SESSION_CFG, _user_session_sample(), "select_product"
    )

    written = sink.write_batch("user_session", binding, _user_session_sample().iloc[0:0])

    assert written == 0
    assert client.pipeline_execs == 0


def test_redis_create_schema_and_ensure_partition_are_noops():
    client = _FakeRedisClient()
    sink = RedisSink({"connection": {}}, client_factory=lambda c: client)
    binding = bind_entity_from_sample(
        "user_session", USER_SESSION_CFG, _user_session_sample(), "select_product"
    )

    sink.create_schema()
    sink.ensure_partition("user_session", binding)

    assert client.pipeline_execs == 0
    assert client.set_calls == 0


def test_redis_ping_failure_raises_import_execution_error():
    class _BadRedisClient:
        def ping(self):
            raise ConnectionError("boom")

    with pytest.raises(ImportExecutionError):
        RedisSink({"connection": {}}, client_factory=lambda c: _BadRedisClient())


def test_redis_close_is_a_noop():
    client = _FakeRedisClient()
    sink = RedisSink({"connection": {}}, client_factory=lambda c: client)
    sink.close()  # must not raise


# ---------------------------------------------------------------------------
# CassandraSink: fake (cluster, session); execute_concurrent_with_args patched
# on the importer module (where _write_batched looks it up).
# ---------------------------------------------------------------------------


class _FakeCassSession:
    def __init__(self):
        self.executes = []
        self.prepared = []
        self.keyspace = None

    def execute(self, stmt, params=None):
        self.executes.append(stmt)
        return []

    def prepare(self, cql):
        self.prepared.append(cql)
        return ("prep", cql)

    def set_keyspace(self, ks):
        self.keyspace = ks


class _FakeCassCluster:
    def __init__(self):
        self.shutdown_called = False

    def shutdown(self):
        self.shutdown_called = True


def _activity_sample():
    return pd.DataFrame(
        {
            "user_id": ["u1", "u2"],
            "timestamp": ["2023-01-01 10:00:00", "2023-01-02 11:00:00"],
            "product_id": ["1", "2"],
            "order_number": ["o1", "o2"],
            "selected_product_id": ["s1", "s2"],
            "shopping_cart_id": ["c1", "c2"],
            SOURCE_COLUMN: ["stock", "stock"],
        }
    )


def test_cassandra_ensure_partition_issues_table_ddl_and_caches_prepared():
    session = _FakeCassSession()
    cluster = _FakeCassCluster()
    sink = CassandraSink(
        {"connection": {"keyspace": "ecom"}}, session_factory=lambda c: (cluster, session)
    )
    binding = bind_entity_from_sample(
        "user_activity_log", CASSANDRA_CFG, _activity_sample(), "stock"
    )

    sink.ensure_partition("user_activity_log", binding)

    assert any("CREATE TABLE IF NOT EXISTS" in s for s in session.executes)
    assert any('"user_activity_log"' in s for s in session.executes)
    assert session.keyspace == "ecom"
    assert len(session.prepared) == 1
    assert "INSERT INTO" in session.prepared[0]

    sink.ensure_partition("user_activity_log", binding)  # second call is a no-op
    assert len(session.prepared) == 1


def test_cassandra_create_schema_issues_keyspace_ddl():
    session = _FakeCassSession()
    cluster = _FakeCassCluster()
    sink = CassandraSink(
        {"connection": {"keyspace": "ecom"}}, session_factory=lambda c: (cluster, session)
    )

    sink.create_schema()

    assert any("CREATE KEYSPACE IF NOT EXISTS ecom" in s for s in session.executes)
    assert session.keyspace == "ecom"


def test_cassandra_write_batch_uses_concurrency_64(monkeypatch):
    import polyglotimportcsv.importers.cassandra_importer as ci

    calls = {"concurrency": None, "rows": 0, "n": 0}

    def fake_concurrent(session, prepared, params, concurrency=64, **kw):
        calls["concurrency"] = concurrency
        calls["rows"] = len(list(params))
        calls["n"] += 1
        return []

    monkeypatch.setattr(ci, "execute_concurrent_with_args", fake_concurrent)
    session = _FakeCassSession()
    cluster = _FakeCassCluster()
    sink = CassandraSink(
        {"connection": {"keyspace": "ecom"}}, session_factory=lambda c: (cluster, session)
    )
    binding = bind_entity_from_sample(
        "user_activity_log", CASSANDRA_CFG, _activity_sample(), "stock"
    )
    sink.ensure_partition("user_activity_log", binding)

    written = sink.write_batch("user_activity_log", binding, _activity_sample())

    assert written == 2
    assert calls["n"] == 1
    assert calls["concurrency"] == 64
    assert calls["rows"] == 2


def test_cassandra_write_batch_empty_does_nothing(monkeypatch):
    import polyglotimportcsv.importers.cassandra_importer as ci

    called = {"n": 0}

    def fake_concurrent(*a, **k):
        called["n"] += 1
        return []

    monkeypatch.setattr(ci, "execute_concurrent_with_args", fake_concurrent)
    session = _FakeCassSession()
    cluster = _FakeCassCluster()
    sink = CassandraSink(
        {"connection": {"keyspace": "ecom"}}, session_factory=lambda c: (cluster, session)
    )
    binding = bind_entity_from_sample(
        "user_activity_log", CASSANDRA_CFG, _activity_sample(), "stock"
    )
    sink.ensure_partition("user_activity_log", binding)

    written = sink.write_batch("user_activity_log", binding, _activity_sample().iloc[0:0])

    assert written == 0
    assert called["n"] == 0


def test_cassandra_write_batch_raises_when_driver_unavailable(monkeypatch):
    import polyglotimportcsv.importers.cassandra_importer as ci

    monkeypatch.setattr(ci, "execute_concurrent_with_args", None)
    session = _FakeCassSession()
    cluster = _FakeCassCluster()
    sink = CassandraSink(
        {"connection": {"keyspace": "ecom"}}, session_factory=lambda c: (cluster, session)
    )
    binding = bind_entity_from_sample(
        "user_activity_log", CASSANDRA_CFG, _activity_sample(), "stock"
    )
    sink.ensure_partition("user_activity_log", binding)

    with pytest.raises(ImportExecutionError):
        sink.write_batch("user_activity_log", binding, _activity_sample())


def test_cassandra_close_shuts_down_cluster():
    session = _FakeCassSession()
    cluster = _FakeCassCluster()
    sink = CassandraSink(
        {"connection": {"keyspace": "ecom"}}, session_factory=lambda c: (cluster, session)
    )

    sink.close()

    assert cluster.shutdown_called is True


# ---------------------------------------------------------------------------
# Neo4jSink: fake driver/session/tx (mirrors _FakeDriver in
# test_importer_write_batching). Nodes only; relationships are out of scope.
# ---------------------------------------------------------------------------


class _FakeNeoTx:
    def __init__(self, recorder):
        self.recorder = recorder

    def run(self, q, **params):
        self.recorder["tx_run"].append((q, params))
        return []


class _FakeNeoSession:
    def __init__(self, recorder):
        self.recorder = recorder

    def run(self, q, **params):
        self.recorder["run"].append((q, params))
        return []

    def execute_write(self, fn, *a, **k):
        return fn(_FakeNeoTx(self.recorder), *a, **k)


class _FakeNeoDriver:
    def __init__(self, recorder):
        self.recorder = recorder
        self.closed = False

    def verify_connectivity(self):
        pass

    def session(self, database=None):
        return _FakeNeoSession(self.recorder)

    def close(self):
        self.closed = True


def _user_sample(ids):
    return pd.DataFrame(
        {
            "user_id": list(ids),
            "user_name": [f"name-{i}" for i in ids],
            "user_email": [f"{i}@x.com" for i in ids],
            SOURCE_COLUMN: ["purchase"] * len(ids),
        }
    )


NEO4J_PRODUCT_CFG = NEO4J_CFG["entities"]["Product"]
PURCHASED_RSPEC = NEO4J_CFG["relationships"]["PURCHASED"]


def _purchase_rel_chunk():
    # The 'from' (User) source is 'purchase', which carries user_id, product_id
    # (the two endpoint FKs) plus the edge props order_number/quantity/price/rating.
    return pd.DataFrame(
        {
            "user_id": ["u1", "u2"],
            "product_id": ["p1", "p2"],
            "order_number": ["o1", "o2"],
            "quantity": ["1", "2"],
            "price": ["10", "20"],
            "rating": ["5", "4"],
            SOURCE_COLUMN: ["purchase", "purchase"],
        }
    )


def test_neo4j_ensure_partition_creates_uniqueness_constraint():
    rec = {"run": [], "tx_run": []}
    driver = _FakeNeoDriver(rec)
    sink = Neo4jSink({"connection": {}}, driver_factory=lambda c: driver)
    binding = bind_entity_from_sample(
        "User", NEO4J_USER_CFG, _user_sample(["u1", "u2"]), "purchase"
    )

    sink.ensure_partition("User", binding)

    assert any("CONSTRAINT" in q and "UNIQUE" in q for q, _ in rec["run"])


def test_neo4j_write_batch_unwind_merges_nodes():
    rec = {"run": [], "tx_run": []}
    driver = _FakeNeoDriver(rec)
    sink = Neo4jSink({"connection": {}}, driver_factory=lambda c: driver)
    binding = bind_entity_from_sample(
        "User", NEO4J_USER_CFG, _user_sample(["u1", "u2", "u3"]), "purchase"
    )

    written = sink.write_batch("User", binding, _user_sample(["u1", "u2", "u3"]))

    assert written == 3
    node_batches = [p for q, p in rec["tx_run"] if "UNWIND" in q and "MERGE (n" in q]
    assert len(node_batches) == 1
    assert sum(len(p["batch"]) for p in node_batches) == 3
    keys = {row["k"] for p in node_batches for row in p["batch"]}
    assert keys == {"u1", "u2", "u3"}


def test_neo4j_write_batch_empty_does_nothing():
    rec = {"run": [], "tx_run": []}
    driver = _FakeNeoDriver(rec)
    sink = Neo4jSink({"connection": {}}, driver_factory=lambda c: driver)
    binding = bind_entity_from_sample(
        "User", NEO4J_USER_CFG, _user_sample(["u1"]), "purchase"
    )

    written = sink.write_batch("User", binding, _user_sample(["u1"]).iloc[0:0])

    assert written == 0
    assert rec["tx_run"] == []


def test_neo4j_dedupe_first_wins_holds_across_write_batch_calls():
    """The same key value fed in two separate write_batch calls must be
    merged only once, proving dedupe state persists across calls (not just
    within one flush) — required for streaming's per-chunk batching."""
    rec = {"run": [], "tx_run": []}
    driver = _FakeNeoDriver(rec)
    sink = Neo4jSink({"connection": {}}, driver_factory=lambda c: driver)
    binding = bind_entity_from_sample(
        "User", NEO4J_USER_CFG, _user_sample(["u0", "u1"]), "purchase"
    )

    written1 = sink.write_batch("User", binding, _user_sample(["u0", "u1"]))
    written2 = sink.write_batch("User", binding, _user_sample(["u0", "u2"]))

    assert written1 == 2
    assert written2 == 1  # "u0" already seen in batch 1; only "u2" is new
    node_batches = [p for q, p in rec["tx_run"] if "UNWIND" in q and "MERGE (n" in q]
    assert len(node_batches) == 2
    keys = sorted(row["k"] for p in node_batches for row in p["batch"])
    assert keys == ["u0", "u1", "u2"]


def test_neo4j_no_nodes_only_warning_when_relationships_declared(caplog):
    rec = {"run": [], "tx_run": []}
    driver = _FakeNeoDriver(rec)

    with caplog.at_level(logging.WARNING, logger="polyglotimportcsv.sinks.neo4j_sink"):
        Neo4jSink(NEO4J_CFG, driver_factory=lambda c: driver)

    warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert not any("nodes only" in m for m in warnings)


def test_neo4j_no_warning_when_no_relationships_declared(caplog):
    rec = {"run": [], "tx_run": []}
    driver = _FakeNeoDriver(rec)

    with caplog.at_level(logging.WARNING, logger="polyglotimportcsv.sinks.neo4j_sink"):
        Neo4jSink({"connection": {}}, driver_factory=lambda c: driver)

    assert caplog.records == []


def test_neo4j_create_schema_is_a_noop():
    rec = {"run": [], "tx_run": []}
    driver = _FakeNeoDriver(rec)
    sink = Neo4jSink({"connection": {}}, driver_factory=lambda c: driver)

    sink.create_schema()

    assert rec["run"] == []
    assert rec["tx_run"] == []


def test_neo4j_close_closes_driver():
    rec = {"run": [], "tx_run": []}
    driver = _FakeNeoDriver(rec)
    sink = Neo4jSink({"connection": {}}, driver_factory=lambda c: driver)

    sink.close()

    assert driver.closed is True


def test_neo4j_write_relationships_unwind_merges_edges():
    rec = {"run": [], "tx_run": []}
    driver = _FakeNeoDriver(rec)
    sink = Neo4jSink({"connection": {}}, driver_factory=lambda c: driver)

    from_binding = bind_entity_from_sample("User", NEO4J_USER_CFG, _user_sample(["u1", "u2"]), "purchase")
    to_binding = bind_entity_from_sample(
        "Product", NEO4J_PRODUCT_CFG,
        pd.DataFrame({"product_id": ["p1", "p2"], "product_name": ["a", "b"],
                      "product_brand": ["x", "y"], SOURCE_COLUMN: ["stock", "stock"]}),
        "stock",
    )

    count = sink.write_relationships("PURCHASED", PURCHASED_RSPEC, from_binding, to_binding, _purchase_rel_chunk())

    assert count == 2
    rel_batches = [p for q, p in rec["tx_run"] if "UNWIND" in q and "MERGE (a)" in q]
    assert len(rel_batches) == 1
    payload = rel_batches[0]["batch"]
    assert {r["a_id"] for r in payload} == {"u1", "u2"}
    assert {r["b_id"] for r in payload} == {"p1", "p2"}
    # order_number is the edge's is_key -> travels in the mk block, not rprops
    assert all("order_number" in r["mk"] for r in payload)


def test_neo4j_write_relationships_skips_null_endpoints():
    rec = {"run": [], "tx_run": []}
    driver = _FakeNeoDriver(rec)
    sink = Neo4jSink({"connection": {}}, driver_factory=lambda c: driver)

    from_binding = bind_entity_from_sample("User", NEO4J_USER_CFG, _user_sample(["u1"]), "purchase")
    to_binding = bind_entity_from_sample(
        "Product", NEO4J_PRODUCT_CFG,
        pd.DataFrame({"product_id": ["p1"], "product_name": ["a"],
                      "product_brand": ["x"], SOURCE_COLUMN: ["stock"]}),
        "stock",
    )
    # A genuinely null endpoint key (None, as an all-NaN cast column would yield)
    # is dropped by _rel_rows_for_batch. An empty string, by contrast, survives
    # here and is skipped later by Cypher MATCH (not exercised by the fake
    # driver) -- both match the materialize path, which uses the same helper.
    chunk = pd.DataFrame(
        {"user_id": ["u1", None], "product_id": ["p1", "p2"], "order_number": ["o1", "o2"],
         "quantity": ["1", "2"], "price": ["10", "20"], "rating": ["5", "4"],
         SOURCE_COLUMN: ["purchase", "purchase"]}
    )

    count = sink.write_relationships("PURCHASED", PURCHASED_RSPEC, from_binding, to_binding, chunk)

    # The row with a null user_id (a_id None) is dropped; only 1 edge shaped.
    assert count == 1
