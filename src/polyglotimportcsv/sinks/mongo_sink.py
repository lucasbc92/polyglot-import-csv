"""MongoSink: DbmsSink adapter for MongoDB.

Shapes each batch into documents with ``mongo_documents``.
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd
from pymongo import MongoClient

from polyglotimportcsv.business_exception import ImportExecutionError
from polyglotimportcsv.row_shaping import mongo_documents
from polyglotimportcsv.stream_binding import EntityBinding


def _connect(conn: Dict[str, Any]):
    uri = conn.get("uri", "mongodb://127.0.0.1:27017")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
    except Exception as e:
        raise ImportExecutionError(f"MongoDB connection failed: {e}") from e
    return client


class MongoSink:
    """Streams cast batches into MongoDB collections, one collection per partition."""

    def __init__(self, dbms_cfg: Dict[str, Any], *, client_factory=None):
        conn = dbms_cfg.get("connection") or {}
        database = conn.get("database", "test")
        factory = client_factory or _connect
        self._client = factory(conn)
        self.db = self._client[database]

    def create_schema(self) -> None:
        """No-op: MongoDB is schemaless, databases/collections need no DDL."""

    def ensure_partition(self, partition_name: str, binding: EntityBinding) -> None:
        """No-op: collections are created implicitly on first insert."""

    def write_batch(self, partition_name: str, binding: EntityBinding, batch: pd.DataFrame) -> int:
        docs = mongo_documents(batch, binding.cfg)
        if not docs:
            return 0
        self.db[partition_name].insert_many(docs)
        return len(docs)

    def close(self) -> None:
        self._client.close()

    def abort(self) -> None:
        self._client.close()
