"""Write port of the import: one adapter per DBMS.

``DbmsSink`` is the boundary between the DBMS-agnostic orchestrator
(``stream_runner.run_stream_import``) and each DBMS's product-specific
adapter (``PostgresSink``, ``MongoSink``, ``CassandraSink``, ``RedisSink``,
``Neo4jSink``). The orchestrator never speaks SQL/Cypher and never
deduplicates rows: both are the sink's responsibility. Row-shaping for the
target DBMS happens inside ``write_batch``.
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
        depend on any bound entity: it is given none (per-entity setup belongs
        in ``ensure_partition``).
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
        """Finish the load (whatever only makes sense once every row is written, such
        as adding foreign keys) and release any held resources (connections, sessions,
        pipelines, ...). Called once, after the last write succeeded."""
        ...

    def abort(self) -> None:
        """Release any held resources after a failed load, finishing nothing.

        Called instead of ``close()`` when a write raised. What was written stays
        written; it must not raise for a load that stopped half way.
        """
        ...


class RowInspector:
    """Sees the rows of one DBMS before they are written; every hook is a no-op here.

    The validation read passes one per DBMS to ``stream_runner.run_single_pass``. The
    frames are indexed by the position of each data row in its file.
    """

    def inspect_rows(
        self, source: str, partition: str, binding: EntityBinding,
        raw: pd.DataFrame, cast: pd.DataFrame,
    ) -> None:
        """Once per (chunk, entity, partition): the filtered raw rows and the same rows cast."""

    def inspect_unpartitioned_rows(
        self, source: str, binding: EntityBinding, raw: pd.DataFrame, cast: pd.DataFrame,
    ) -> None:
        """Once per (chunk, entity) whose ``each`` split dropped rows: those rows (an
        empty ``each`` value names no partition)."""

    def inspect_relationship_rows(
        self, source: str, rname: str, rspec: Dict[str, Any],
        from_binding: EntityBinding, to_binding: EntityBinding, cast: pd.DataFrame,
    ) -> None:
        """Before each ``write_relationships``: the cast rows of the ``from`` entity."""


#: Builds a DbmsSink from a DBMS's dbms_cfg (e.g. config["postgres"]).
SinkFactory = Callable[[Dict[str, Any]], "DbmsSink"]
