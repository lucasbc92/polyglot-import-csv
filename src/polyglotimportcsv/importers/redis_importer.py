"""Redis helpers shared by ``RedisSink``: client, key-value shaping and pipelined SET."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import redis

from polyglotimportcsv.row_shaping import redis_payload_from_row
from polyglotimportcsv.row_view import iter_rows


def _default_redis_client(conn: Dict[str, Any]):
    return redis.Redis(
        host=conn.get("host", "127.0.0.1"),
        port=int(conn.get("port", 6379)),
        db=int(conn.get("db", 0)),
        password=conn.get("password") or None,
        decode_responses=True,
    )


def _kv_pairs(part_df, entity_cfg) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for row in iter_rows(part_df):
        try:
            pairs.append(redis_payload_from_row(row, entity_cfg))
        except ValueError:
            continue
    return pairs


def _write_batched(client, pairs: List[Tuple[str, str]], advance, batch: int = 1000) -> int:
    count = 0
    for i in range(0, len(pairs), batch):
        chunk = pairs[i : i + batch]
        pipe = client.pipeline(transaction=False)
        for k, v in chunk:
            pipe.set(k, v)
        pipe.execute()
        count += len(chunk)
        advance(len(chunk))
    return count
