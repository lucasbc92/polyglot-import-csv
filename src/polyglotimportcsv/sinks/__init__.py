"""DbmsSink adapters, one per DBMS.

Each module implements ``DbmsSink`` (see ``polyglotimportcsv.dbms_sink``) for
one DBMS, on top of the row-shaping and batched-write helpers under
``polyglotimportcsv.importers``.
"""

from __future__ import annotations

from typing import Any, Dict

from polyglotimportcsv.dbms_sink import SinkFactory
from polyglotimportcsv.sinks.cassandra_sink import CassandraSink
from polyglotimportcsv.sinks.mongo_sink import MongoSink
from polyglotimportcsv.sinks.neo4j_sink import Neo4jSink
from polyglotimportcsv.sinks.postgres_sink import PostgresSink
from polyglotimportcsv.sinks.redis_sink import RedisSink


def default_sink_factories() -> Dict[str, SinkFactory]:
    """Wired defaults (production CLI).

    Each factory receives the DBMS's ``dbms_cfg`` (``config[dbms]``) and
    builds the adapter with its real driver; tests inject fakes instead. Only
    the DBMS present in the config are ever constructed (``run_stream_import``
    calls a factory once per configured DBMS)."""
    return {
        "postgres": PostgresSink,
        "redis": RedisSink,
        "mongodb": MongoSink,
        "cassandra": CassandraSink,
        "neo4j": Neo4jSink,
    }


__all__ = [
    "PostgresSink",
    "MongoSink",
    "CassandraSink",
    "RedisSink",
    "Neo4jSink",
    "default_sink_factories",
]
