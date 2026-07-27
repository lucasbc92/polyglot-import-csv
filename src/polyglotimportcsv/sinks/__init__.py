"""DbmsSink adapters for the streaming import path (spec: streaming import, Task 4+).

Each module implements ``DbmsSink`` (see ``polyglotimportcsv.dbms_sink``) for
one DBMS, reusing the same row-shaping/batched-write helpers as the
materialize importer under ``polyglotimportcsv.importers``.
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
    """Wired defaults for the streaming import path (production CLI).

    Each factory receives the DBMS's ``backend_cfg`` (``config[dbms]``) and
    builds the adapter with its real driver; tests inject fakes instead. Only
    the DBMS present in the config are ever constructed (``run_stream_import``
    calls a factory once per configured DBMS)."""
    return {
        "postgres": lambda bcfg: PostgresSink(bcfg),
        "redis": lambda bcfg: RedisSink(bcfg),
        "mongodb": lambda bcfg: MongoSink(bcfg),
        "cassandra": lambda bcfg: CassandraSink(bcfg),
        "neo4j": lambda bcfg: Neo4jSink(bcfg),
    }


__all__ = [
    "PostgresSink",
    "MongoSink",
    "CassandraSink",
    "RedisSink",
    "Neo4jSink",
    "default_sink_factories",
]
