"""DbmsSink adapters for the streaming import path (spec: streaming import, Task 4+).

Each module implements ``DbmsSink`` (see ``polyglotimportcsv.dbms_sink``) for
one DBMS, reusing the same row-shaping/batched-write helpers as the
materialize importer under ``polyglotimportcsv.importers``.
"""

from __future__ import annotations

from polyglotimportcsv.sinks.cassandra_sink import CassandraSink
from polyglotimportcsv.sinks.mongo_sink import MongoSink
from polyglotimportcsv.sinks.neo4j_sink import Neo4jSink
from polyglotimportcsv.sinks.postgres_sink import PostgresSink
from polyglotimportcsv.sinks.redis_sink import RedisSink

__all__ = ["PostgresSink", "MongoSink", "CassandraSink", "RedisSink", "Neo4jSink"]
