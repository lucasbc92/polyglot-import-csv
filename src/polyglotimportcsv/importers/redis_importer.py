"""Import key-value rows into Redis."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Tuple

import redis

from polyglotimportcsv import metrics
from polyglotimportcsv.business_exception import ImportExecutionError
from polyglotimportcsv.mapping_resolver import BoundEntity
from polyglotimportcsv.filter_engine import apply_filters, expand_each
from polyglotimportcsv.materialize import redis_payload_from_row
from polyglotimportcsv.reporting import entity_progress
from polyglotimportcsv.row_view import iter_rows

logger = logging.getLogger(__name__)


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


def _write_naive(client, pairs: List[Tuple[str, str]], advance) -> int:
    count = 0
    for k, v in pairs:
        client.set(k, v)
        count += 1
        advance(1)
    return count


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


def run_redis_import(
    backend_cfg: Dict[str, Any],
    entities: Dict[str, "BoundEntity"],
    *,
    dry_run: bool,
    create_schema: bool,
    strategy: str = "optimized",
    client_factory: Callable[[Dict[str, Any]], Any] = _default_redis_client,
) -> List[str]:
    lines: List[str] = []
    conn = backend_cfg.get("connection") or {}
    _ = create_schema  # Redis has no DDL

    if dry_run:
        lines.append("[redis] dry-run: would SET keys for entities.")
        for ename, be in entities.items():
            non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
            with metrics.timed_phase("redis", ename, "filter") as t:
                dff = apply_filters(be.df, non_each, be.kinds)
                t.rows = len(dff)
            for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
                lines.append(f"  entity {part_name}: {len(part_df)} row(s)")
        return lines

    client = client_factory(conn)
    try:
        client.ping()
    except Exception as e:
        raise ImportExecutionError(f"Redis connection failed: {e}") from e

    writer = _write_naive if strategy == "naive" else _write_batched
    for ename, be in entities.items():
        non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
        with metrics.timed_phase("redis", ename, "filter") as t:
            dff = apply_filters(be.df, non_each, be.kinds)
            t.rows = len(dff)
        for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
            if part_df.empty:
                logger.warning("[redis] entity %s has 0 row(s) after filters", part_name)
            with metrics.timed_phase("redis", part_name, "write") as tw:
                pairs = _kv_pairs(part_df, be.cfg)
                with entity_progress(f"redis · {part_name}", len(pairs)) as advance:
                    count = writer(client, pairs, advance)
                tw.rows = count
            logger.debug("[redis] SET %d key(s) for %s", count, part_name)
            lines.append(f"[redis] SET {count} key(s) for {part_name}")
    return lines
