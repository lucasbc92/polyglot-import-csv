"""Import documents into MongoDB."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from pymongo import MongoClient

from polyglotimportcsv import metrics
from polyglotimportcsv.business_exception import ImportExecutionError
from polyglotimportcsv.mapping_resolver import BoundEntity
from polyglotimportcsv.filter_engine import apply_filters, expand_each
from polyglotimportcsv.materialize import mongo_document_from_row
from polyglotimportcsv.reporting import entity_progress

logger = logging.getLogger(__name__)


def run_mongodb_import(
    backend_cfg: Dict[str, Any],
    entities: Dict[str, "BoundEntity"],
    *,
    dry_run: bool,
    create_schema: bool,
    strategy: str = "optimized",
) -> List[str]:
    lines: List[str] = []
    conn = backend_cfg.get("connection") or {}
    _ = create_schema
    _ = strategy

    if dry_run:
        lines.append("[mongodb] dry-run: would insert documents.")
        for ename, be in entities.items():
            non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
            with metrics.timed_phase("mongodb", ename, "filter") as t:
                dff = apply_filters(be.df, non_each, be.kinds)
                t.rows = len(dff)
            for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
                lines.append(f"  collection {part_name}: {len(part_df)} document(s)")
        return lines

    uri = conn.get("uri", "mongodb://127.0.0.1:27017")
    database = conn.get("database", "test")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
    except Exception as e:
        raise ImportExecutionError(f"MongoDB connection failed: {e}") from e

    db = client[database]
    for ename, be in entities.items():
        non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
        with metrics.timed_phase("mongodb", ename, "filter") as t:
            dff = apply_filters(be.df, non_each, be.kinds)
            t.rows = len(dff)
        for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
            docs = [mongo_document_from_row(row, be.cfg) for _, row in part_df.iterrows()]
            if not docs:
                logger.warning("[mongodb] collection %s has 0 document(s) after filters", part_name)
                lines.append(f"[mongodb] inserted 0 document(s) into {part_name}")
                continue
            logger.debug("[mongodb] insert_many into %s: %d document(s)", part_name, len(docs))
            with metrics.timed_phase("mongodb", part_name, "write") as tw:
                with entity_progress(f"mongodb · {part_name}", len(docs)) as advance:
                    db[part_name].insert_many(docs)
                    advance(len(docs))
                tw.rows = len(docs)
            lines.append(f"[mongodb] inserted {len(docs)} document(s) into {part_name}")
    client.close()
    return lines
