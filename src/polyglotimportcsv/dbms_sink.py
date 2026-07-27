"""Write port for the streaming import path (spec: streaming import, Task 3).

``DbmsSink`` is the boundary between the DBMS-agnostic orchestrator
(``stream_runner.run_stream_import``) and each DBMS's product-specific
adapter (``PostgresSink``, ``MongoSink``, ``CassandraSink``, ``RedisSink``,
``Neo4jSink``). The orchestrator never speaks SQL/Cypher and never
deduplicates rows: both are the sink's responsibility. Row-shaping for the
target DBMS happens inside ``write_batch``, reusing the same helpers the
materialize importers use.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Protocol

import pandas as pd

from polyglotimportcsv.stream_binding import EntityBinding


class DbmsSink(Protocol):
    """One DBMS's streaming write adapter."""

    def create_schema(self) -> None:
        """Data-independent DBMS-level setup (e.g. keyspace/database). May be a no-op.

        Called at most once per run, before any chunk is processed. Must NOT
        depend on any bound entity: in streaming mode, bindings only exist
        after the first chunk of each entity has been read.
        """
        ...

    def ensure_partition(self, partition_name: str, binding: EntityBinding) -> None:
        """Create the partition's table/collection/etc if it does not exist yet.

        Called lazily, once per distinct partition, right before that
        partition's first ``write_batch``.
        """
        ...

    def write_batch(self, partition_name: str, binding: EntityBinding, batch: pd.DataFrame) -> int:
        """Shape and write one already-cast batch of rows; return the row count written."""
        ...

    def close(self) -> None:
        """Release any held resources (connections, sessions, pipelines, ...)."""
        ...


#: Builds a DbmsSink from a DBMS's backend_cfg (e.g. config["postgres"]).
SinkFactory = Callable[[Dict[str, Any]], "DbmsSink"]
