"""Import documents into MongoDB."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import pandas as pd
from pymongo import MongoClient

from polyglotimportcsv.business_exception import BusinessException
from polyglotimportcsv.filter_engine import apply_filters, expand_each
from polyglotimportcsv.materialize import mongo_document_from_row

logger = logging.getLogger(__name__)


def run_mongodb_import(
    backend_cfg: Dict[str, Any],
    df: pd.DataFrame,
    column_kinds: Dict[str, str],
    *,
    dry_run: bool,
    create_schema: bool,
) -> List[str]:
    lines: List[str] = []
    conn = backend_cfg.get("connection") or {}
    entities = backend_cfg.get("entities") or {}
    _ = create_schema

    if dry_run:
        lines.append("[mongodb] dry-run: would insert documents.")
        for ename, ecfg in entities.items():
            non_each = [f for f in (ecfg.get("filters") or []) if f.get("operator") != "each"]
            dff = apply_filters(df, non_each, column_kinds)
            for part_name, part_df in expand_each(dff, ecfg.get("filters") or [], ename):
                lines.append(f"  collection {part_name}: {len(part_df)} document(s)")
        return lines

    uri = conn.get("uri", "mongodb://127.0.0.1:27017")
    database = conn.get("database", "test")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
    except Exception as e:
        raise BusinessException(f"MongoDB connection failed: {e}") from e

    db = client[database]
    for ename, ecfg in entities.items():
        non_each = [f for f in (ecfg.get("filters") or []) if f.get("operator") != "each"]
        dff = apply_filters(df, non_each, column_kinds)
        for part_name, part_df in expand_each(dff, ecfg.get("filters") or [], ename):
            docs = [mongo_document_from_row(row, ecfg) for _, row in part_df.iterrows()]
            if docs:
                db[part_name].insert_many(docs)
            lines.append(f"[mongodb] inserted {len(docs)} document(s) into {part_name}")
    client.close()
    return lines
