"""PostgresSink / MongoSink tested against fake DB clients (no live DB)."""

import json
from pathlib import Path

import pandas as pd
import pytest

from polyglotimportcsv.sinks import postgres_sink as pg_mod
from polyglotimportcsv.sinks import mongo_sink as mongo_mod
from polyglotimportcsv.sinks.postgres_sink import PostgresSink
from polyglotimportcsv.sinks.mongo_sink import MongoSink
from polyglotimportcsv.sources import SOURCE_COLUMN
from polyglotimportcsv.stream_binding import bind_entity_from_sample

CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "ecommerce" / "import_config.json"
_CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

INVENTORY_CFG = _CONFIG["postgres"]["entities"]["inventory"]
PRODUCTS_CFG = _CONFIG["postgres"]["entities"]["products"]
CATEGORIES_CFG = _CONFIG["postgres"]["entities"]["categories"]
PRODUCT_CATALOG_CFG = _CONFIG["mongodb"]["entities"]["product_catalog"]


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
