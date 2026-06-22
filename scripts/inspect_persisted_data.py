#!/usr/bin/env python3
"""Inspect or clean rows/documents persisted by Polyglot Import CSV in local Docker databases."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from polyglotimportcsv.console import (
    banner,
    dump_rows,
    empty_label,
    error,
    format_json_row,
    init_session_log,
    note,
    section,
    setup_logging,
    step,
    success,
    warn,
)

DEFAULT_CONFIG = Path("data/ecommerce/import_config.json")
DEFAULT_SGBD_CONFIG = Path("data/ecommerce/sgbd_config.json")
BACKENDS = ("postgres", "mongodb", "cassandra", "redis", "neo4j")

_BACKEND_LABEL = {
    "postgres": "PostgreSQL",
    "mongodb": "MongoDB",
    "cassandra": "Cassandra",
    "redis": "Redis",
    "neo4j": "Neo4j",
}


def _load_config(path: Path, sgbd_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load and merge the import + SGBD configs into one backend structure."""
    from polyglotimportcsv.config_parser import load_config

    return load_config(path, sgbd_path)


def _parse_only(raw: str) -> List[str]:
    if not raw.strip():
        return list(BACKENDS)
    chosen = [b.strip().lower() for b in raw.split(",") if b.strip()]
    unknown = [b for b in chosen if b not in BACKENDS]
    if unknown:
        raise SystemExit(f"Unknown backend(s): {', '.join(unknown)}. Use: {', '.join(BACKENDS)}")
    return chosen


def inspect_postgres(cfg: Dict[str, Any]) -> None:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn_cfg = cfg.get("connection") or {}
    schema = cfg.get("schema") or "public"
    entities = cfg.get("entities") or {}
    host = conn_cfg.get("host", "127.0.0.1")
    port = conn_cfg.get("port", 5432)
    database = conn_cfg.get("database", "postgres")
    section(f"PostgreSQL · {host}:{port}/{database}")

    cx = psycopg2.connect(
        host=host,
        port=int(port),
        dbname=database,
        user=conn_cfg.get("user", "postgres"),
        password=conn_cfg.get("password", ""),
    )
    try:
        with cx.cursor(cursor_factory=RealDictCursor) as cur:
            for table in entities:
                cur.execute(f'SELECT * FROM "{schema}"."{table}" ORDER BY 1')
                rows = [dict(r) for r in cur.fetchall()]
                dump_rows(f"table {schema}.{table}", rows)
    finally:
        cx.close()


def inspect_mongodb(cfg: Dict[str, Any]) -> None:
    from pymongo import MongoClient

    conn = cfg.get("connection") or {}
    entities = cfg.get("entities") or {}
    uri = conn.get("uri", "mongodb://127.0.0.1:27017")
    database = conn.get("database", "test")
    section(f"MongoDB · {database}")

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
        db = client[database]
        for collection in entities:
            docs = list(db[collection].find().sort("_id", 1))
            for doc in docs:
                doc.pop("_id", None)
            dump_rows(f"collection {collection}", docs)
    finally:
        client.close()


def inspect_cassandra(cfg: Dict[str, Any]) -> None:
    conn = cfg.get("connection") or {}
    entities = cfg.get("entities") or {}
    hosts = conn.get("hosts") or ["127.0.0.1"]
    port = int(conn.get("port", 9042))
    keyspace = conn.get("keyspace", "ecommerce")
    section(f"Cassandra · {keyspace} @ {hosts}:{port}")

    try:
        from cassandra.cluster import Cluster
    except Exception as e:
        error(f"Cassandra driver unavailable: {e}")
        return

    cluster = Cluster(hosts, port=port, connect_timeout=10)
    try:
        session = cluster.connect(keyspace)
        for table in entities:
            rows = session.execute(f'SELECT * FROM "{table}"')
            data = [dict(row._asdict()) for row in rows]
            dump_rows(f"table {keyspace}.{table}", data)
    finally:
        cluster.shutdown()


def inspect_redis(cfg: Dict[str, Any]) -> None:
    import json

    import redis

    conn = cfg.get("connection") or {}
    entities = cfg.get("entities") or {}
    host = conn.get("host", "127.0.0.1")
    port = int(conn.get("port", 6379))
    db_num = int(conn.get("db", 0))
    section(f"Redis · db={db_num} @ {host}:{port}")

    r = redis.Redis(
        host=host,
        port=port,
        db=db_num,
        password=conn.get("password") or None,
        decode_responses=True,
    )
    r.ping()
    keys = sorted(r.keys("*"))
    note(f"{len(keys)} key(s) in database")
    for entity in entities:
        note(f"entity config: {entity}")
    if not keys:
        print(f"    {empty_label()}")
        return
    for key in keys:
        kind = r.type(key)
        if kind == "string":
            value = r.get(key)
            try:
                parsed = json.loads(value)
                value_repr = format_json_row(parsed)
            except (TypeError, json.JSONDecodeError):
                value_repr = value
            print(f"    key={key!r}  value={value_repr}")
        else:
            warn(f"key={key!r} type={kind} (not displayed)")


def inspect_neo4j(cfg: Dict[str, Any]) -> None:
    from neo4j import GraphDatabase

    conn = cfg.get("connection") or {}
    entities = cfg.get("entities") or {}
    relationships = cfg.get("relationships") or {}
    uri = conn.get("uri", "bolt://127.0.0.1:7687")
    database = conn.get("database") or None
    section(f"Neo4j · {uri}")

    driver = GraphDatabase.driver(uri, auth=(conn.get("user", "neo4j"), conn.get("password", "")))
    try:
        driver.verify_connectivity()
        with driver.session(database=database) as session:
            for label in entities:
                result = session.run(f"MATCH (n:`{label}`) RETURN properties(n) AS props")
                nodes = [rec["props"] for rec in result]
                dump_rows(f"nodes :{label}", nodes)

            for rname, rspec in relationships.items():
                rel_type = rspec.get("type") or rname
                result = session.run(
                    f"""
                    MATCH (a)-[r:`{rel_type}`]->(b)
                    RETURN labels(a) AS from_labels, properties(a) AS from_props,
                           type(r) AS rel_type, properties(r) AS rel_props,
                           labels(b) AS to_labels, properties(b) AS to_props
                    """
                )
                edges: List[Dict[str, Any]] = []
                for rec in result:
                    edges.append(
                        {
                            "from": {"labels": rec["from_labels"], "props": rec["from_props"]},
                            "rel": {"type": rec["rel_type"], "props": rec["rel_props"]},
                            "to": {"labels": rec["to_labels"], "props": rec["to_props"]},
                        }
                    )
                dump_rows(f"relationships :{rel_type}", edges)
    finally:
        driver.close()


def clean_postgres(cfg: Dict[str, Any]) -> None:
    import psycopg2
    from psycopg2 import sql

    conn_cfg = cfg.get("connection") or {}
    schema = cfg.get("schema") or "public"
    entities = list((cfg.get("entities") or {}).keys())
    section(f"PostgreSQL · clean · {conn_cfg.get('host')}:{conn_cfg.get('port')}")

    cx = psycopg2.connect(
        host=conn_cfg.get("host", "127.0.0.1"),
        port=int(conn_cfg.get("port", 5432)),
        dbname=conn_cfg.get("database", "postgres"),
        user=conn_cfg.get("user", "postgres"),
        password=conn_cfg.get("password", ""),
    )
    try:
        cx.autocommit = True
        with cx.cursor() as cur:
            for table in entities:
                cur.execute(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM information_schema.tables
                      WHERE table_schema = %s AND table_name = %s
                    )
                    """,
                    (schema, table),
                )
                if not cur.fetchone()[0]:
                    note(f"skip {schema}.{table} (not created yet)")
                    continue
                fq = sql.SQL("TRUNCATE TABLE {}.{} RESTART IDENTITY CASCADE").format(
                    sql.Identifier(schema), sql.Identifier(table)
                )
                cur.execute(fq)
                note(f"truncated {schema}.{table}")
    finally:
        cx.close()


def clean_mongodb(cfg: Dict[str, Any]) -> None:
    from pymongo import MongoClient

    conn = cfg.get("connection") or {}
    entities = cfg.get("entities") or {}
    uri = conn.get("uri", "mongodb://127.0.0.1:27017")
    database = conn.get("database", "test")
    section(f"MongoDB · clean · {database}")

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    try:
        db = client[database]
        for collection in entities:
            result = db[collection].delete_many({})
            note(f"deleted {result.deleted_count} document(s) from {collection}")
    finally:
        client.close()


def clean_cassandra(cfg: Dict[str, Any]) -> None:
    conn = cfg.get("connection") or {}
    entities = cfg.get("entities") or {}
    hosts = conn.get("hosts") or ["127.0.0.1"]
    port = int(conn.get("port", 9042))
    keyspace = conn.get("keyspace", "ecommerce")
    section(f"Cassandra · clean · {keyspace}")

    try:
        from cassandra.cluster import Cluster
    except Exception as e:
        error(f"Cassandra driver unavailable: {e}")
        return

    cluster = Cluster(hosts, port=port, connect_timeout=10)
    try:
        session = cluster.connect()
        rows = list(
            session.execute(
                "SELECT keyspace_name FROM system_schema.keyspaces WHERE keyspace_name = %s",
                (keyspace,),
            )
        )
        if not rows:
            note(f"skip keyspace {keyspace} (not created yet)")
            return

        session.set_keyspace(keyspace)
        for table in entities:
            trows = list(
                session.execute(
                    "SELECT table_name FROM system_schema.tables "
                    "WHERE keyspace_name = %s AND table_name = %s",
                    (keyspace, table),
                )
            )
            if not trows:
                note(f"skip {keyspace}.{table} (not created yet)")
                continue
            session.execute(f'TRUNCATE "{table}"')
            note(f"truncated {keyspace}.{table}")
    finally:
        cluster.shutdown()


def clean_redis(cfg: Dict[str, Any]) -> None:
    import redis

    conn = cfg.get("connection") or {}
    host = conn.get("host", "127.0.0.1")
    port = int(conn.get("port", 6379))
    db_num = int(conn.get("db", 0))
    section(f"Redis · clean · db={db_num}")

    r = redis.Redis(
        host=host,
        port=port,
        db=db_num,
        password=conn.get("password") or None,
        decode_responses=True,
    )
    r.flushdb()
    note(f"flushed db {db_num} on {host}:{port}")


def clean_neo4j(cfg: Dict[str, Any]) -> None:
    from neo4j import GraphDatabase

    conn = cfg.get("connection") or {}
    uri = conn.get("uri", "bolt://127.0.0.1:7687")
    database = conn.get("database") or None
    section("Neo4j · clean")

    driver = GraphDatabase.driver(uri, auth=(conn.get("user", "neo4j"), conn.get("password", "")))
    try:
        with driver.session(database=database) as session:
            result = session.run("MATCH (n) DETACH DELETE n")
            result.consume()
            note("deleted all nodes and relationships")
    finally:
        driver.close()


INSPECTORS: Dict[str, Callable[[Dict[str, Any]], None]] = {
    "postgres": inspect_postgres,
    "mongodb": inspect_mongodb,
    "cassandra": inspect_cassandra,
    "redis": inspect_redis,
    "neo4j": inspect_neo4j,
}

CLEANERS: Dict[str, Callable[[Dict[str, Any]], None]] = {
    "postgres": clean_postgres,
    "mongodb": clean_mongodb,
    "cassandra": clean_cassandra,
    "redis": clean_redis,
    "neo4j": clean_neo4j,
}


def _run_backends(
    cfg: Dict[str, Any],
    selected: List[str],
    handlers: Dict[str, Callable[[Dict[str, Any]], None]],
    action_label: str,
) -> int:
    failures = 0
    for backend in selected:
        block = cfg.get(backend)
        if not block:
            warn(f"skipping {backend} (not in config)")
            continue
        try:
            handlers[backend](block)
        except Exception as e:
            failures += 1
            section(f"{_BACKEND_LABEL.get(backend, backend)} · ERROR ({action_label})")
            error(f"{type(e).__name__}: {e}")
    return failures


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"Import (mapping) JSON config (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--sgbd-config",
        type=Path,
        default=None,
        help="SGBD connection JSON config (default: sgbd_config.json next to --config)",
    )
    parser.add_argument(
        "--only",
        default="",
        help=f"Comma-separated backends (default: all). Choices: {', '.join(BACKENDS)}",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    setup_logging()
    parser = argparse.ArgumentParser(
        description="Clean or inspect Docker databases using import_config.json."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_p = sub.add_parser("inspect", help="Log persisted rows/documents/keys.")
    _add_common_args(inspect_p)

    clean_p = sub.add_parser("clean", help="Remove imported data for a fresh reload.")
    _add_common_args(clean_p)

    args = parser.parse_args(argv)
    config_path = args.config.resolve()
    if not config_path.is_file():
        error(f"Config not found: {config_path}")
        return 1
    sgbd_path = args.sgbd_config.resolve() if args.sgbd_config else None

    log_path = init_session_log(prefix=f"inspect_{args.command}")
    if log_path is not None:
        note(f"log file: {log_path}")

    from polyglotimportcsv.business_exception import BusinessException

    try:
        cfg = _load_config(config_path, sgbd_path)
    except BusinessException as e:
        error(str(e))
        return 1
    selected = _parse_only(args.only)

    title = "Inspect persisted data" if args.command == "inspect" else "Clean databases"
    banner(f"Polyglot Import CSV · {title}", subtitle=str(config_path))
    step("Backends", ", ".join(selected))

    handlers = INSPECTORS if args.command == "inspect" else CLEANERS
    failures = _run_backends(cfg, selected, handlers, args.command)

    if failures:
        error(f"Finished with {failures} backend error(s). Is docker compose up?")
        return 1

    success(f"{args.command.capitalize()} completed for {len(selected)} backend(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
