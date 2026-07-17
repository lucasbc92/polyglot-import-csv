"""Import key-value rows into Redis."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import pandas as pd
import redis

from polyglotimportcsv.business_exception import ImportExecutionError
from polyglotimportcsv.mapping_resolver import BoundEntity
from polyglotimportcsv.filter_engine import apply_filters, expand_each
from polyglotimportcsv.materialize import redis_payload_from_row

logger = logging.getLogger(__name__)


def run_redis_import(
    backend_cfg: Dict[str, Any],
    entities: Dict[str, "BoundEntity"],
    *,
    dry_run: bool,
    create_schema: bool,
) -> List[str]:
    lines: List[str] = []
    conn = backend_cfg.get("connection") or {}
    _ = create_schema  # Redis has no DDL

    if dry_run:
        lines.append("[redis] dry-run: would SET keys for entities.")
        for ename, be in entities.items():
            non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
            dff = apply_filters(be.df, non_each, be.kinds)
            for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
                lines.append(f"  entity {part_name}: {len(part_df)} row(s)")
        return lines

    r = redis.Redis(
        host=conn.get("host", "127.0.0.1"),
        port=int(conn.get("port", 6379)),
        db=int(conn.get("db", 0)),
        password=conn.get("password") or None,
        decode_responses=True,
    )
    try:
        r.ping()
    except Exception as e:
        raise ImportExecutionError(f"Redis connection failed: {e}") from e

    for ename, be in entities.items():
        non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
        dff = apply_filters(be.df, non_each, be.kinds)
        for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
            count = 0
            for _, row in part_df.iterrows():
                try:
                    k, v = redis_payload_from_row(row, be.cfg)
                except ValueError:
                    continue
                r.set(k, v)
                count += 1
            lines.append(f"[redis] SET {count} key(s) for {part_name}")
    return lines
