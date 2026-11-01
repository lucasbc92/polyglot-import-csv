"""Cleaner and inspector of the campaign: MongoDB collections split by `each`."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import inspect_persisted_data as ipd  # noqa: E402

from polyglotimportcsv.config_parser import load_config  # noqa: E402

ECOMMERCE = Path(__file__).resolve().parents[1] / "data" / "ecommerce"


class _Collection:
    def __init__(self, db, name):
        self.db, self.name = db, name

    def delete_many(self, query):
        self.db.emptied.append(self.name)
        return SimpleNamespace(deleted_count=self.db.docs.get(self.name, 0))


class _Db:
    def __init__(self, docs):
        self.docs, self.emptied = docs, []

    def list_collection_names(self):
        return list(self.docs)

    def __getitem__(self, name):
        return _Collection(self, name)


class _Client:
    def __init__(self, db):
        self.db = db

    def __getitem__(self, name):
        return self.db

    def close(self):
        pass


def _mongodb_block():
    return load_config(ECOMMERCE / "import_config.json")["mongodb"]


def test_mongo_collections_lists_each_entity_by_its_partitions():
    db = _Db({"orders_state_SP": 2, "orders_state_RJ": 1, "unrelated": 5})
    assert ipd.mongo_collections(db, _mongodb_block()["entities"]) == [
        "product_catalog", "orders_state_RJ", "orders_state_SP",
    ]


def test_clean_mongodb_empties_every_partition_and_nothing_else(monkeypatch):
    db = _Db({"orders_state_SP": 2, "orders_state_RJ": 1, "product_catalog": 8, "unrelated": 5})
    monkeypatch.setattr("pymongo.MongoClient", lambda *a, **k: _Client(db))
    ipd.clean_mongodb(_mongodb_block())
    assert sorted(db.emptied) == ["orders_state_RJ", "orders_state_SP", "product_catalog"]
