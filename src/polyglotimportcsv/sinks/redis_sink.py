"""RedisSink: DbmsSink adapter for Redis (spec: streaming import, Task 5).

Reuses the same key-value shaping (``_kv_pairs`` -> ``redis_payload_from_row``)
and batched-write helper (``_write_batched`` -> ``client.pipeline``) as the
materialize importer (``importers.redis_importer.run_redis_import``), so both
paths issue the same SET pipeline shape for the same entity config.
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from polyglotimportcsv.business_exception import ImportExecutionError
from polyglotimportcsv.importers.redis_importer import (
    _default_redis_client,
    _kv_pairs,
    _write_batched,
)
from polyglotimportcsv.stream_binding import EntityBinding


class RedisSink:
    """Streams cast batches into Redis keys, one pipeline per ``write_batch``."""

    def __init__(self, backend_cfg: Dict[str, Any], *, client_factory=_default_redis_client):
        conn = backend_cfg.get("connection") or {}
        self._client = client_factory(conn)
        try:
            self._client.ping()
        except Exception as e:
            raise ImportExecutionError(f"Redis connection failed: {e}") from e

    def create_schema(self) -> None:
        """No-op: Redis has no DDL."""

    def ensure_partition(self, partition_name: str, binding: EntityBinding) -> None:
        """No-op: Redis keys need no partition/table setup."""

    def write_batch(self, partition_name: str, binding: EntityBinding, batch: pd.DataFrame) -> int:
        pairs = _kv_pairs(batch, binding.cfg)
        if not pairs:
            return 0
        # A single pipeline covers the whole (already <= BATCH-sized) batch:
        # pass batch=len(pairs) so `_write_batched` issues exactly one
        # pipeline execute() instead of re-chunking at its own default of 1000.
        return _write_batched(self._client, pairs, lambda n: None, batch=len(pairs))

    def close(self) -> None:
        """No-op: no resource beyond the client connection is held open."""
