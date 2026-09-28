"""Check that the target DBMS answer before anything is read or written.

No connection URI is parsed by hand here. MongoDB and Neo4j addresses come
from the drivers' own parsing: ``MongoClient(uri, connect=False)`` and
``GraphDatabase.driver(uri, auth=...)`` interpret a URI without connecting,
``pymongo.uri_parser.parse_uri`` performs the SRV lookup the client defers,
and ``neo4j.Address.parse`` applies the Neo4j driver's own defaults. A setting
the driver accepts is therefore never rejected here, and one it rejects never
passes (spec §5.1). PostgreSQL follows libpq's rules for ``host``; Redis and
Cassandra read ``host``/``hosts`` and ``port`` as their importers do.

Nothing here prints: the runner presents the report.
"""

from __future__ import annotations

import socket
import sys
from typing import Any, Dict, List, Tuple, Union
from urllib.parse import urlparse

from neo4j import Address, GraphDatabase
from pymongo import MongoClient, uri_parser

#: A TCP address ``(host, port)`` or the path of a Unix-domain socket. A port
#: may be a service name ("http"): the driver hands it to getaddrinfo as is,
#: and so does the probe.
Endpoint = Union[Tuple[str, Union[int, str]], str]

_ON_WINDOWS = sys.platform == "win32"
#: libpq's compiled-in socket directory is one of these on Linux/macOS builds.
_PG_DEFAULT_SOCKET_DIRS = ("/var/run/postgresql", "/tmp")


class InvalidConnectionError(ValueError):
    """The connection setting can never connect: the driver rejects it."""


def endpoints(dbms: str, entry: Dict[str, Any]) -> List[Endpoint]:
    """Addresses the importer of ``dbms`` would connect to, with its defaults."""
    conn = (entry or {}).get("connection") or {}
    if dbms == "postgres":
        return _postgres_endpoints(conn)
    if dbms == "redis":
        return [(conn.get("host", "127.0.0.1"), int(conn.get("port", 6379)))]
    if dbms == "cassandra":
        port = int(conn.get("port", 9042))
        return [(host, port) for host in (conn.get("hosts") or ["127.0.0.1"])]
    if dbms == "mongodb":
        return _mongodb_endpoints(conn.get("uri", "mongodb://127.0.0.1:27017"))
    if dbms == "neo4j":
        return _neo4j_endpoints(
            conn.get("uri", "bolt://127.0.0.1:7687"), conn.get("user"), conn.get("password")
        )
    raise ValueError("unknown DBMS: {0}".format(dbms))


def format_endpoint(endpoint: Endpoint) -> str:
    if isinstance(endpoint, str):
        return endpoint
    host, port = endpoint
    if ":" in host:  # an IPv6 literal
        return "[{0}]:{1}".format(host, port)
    return "{0}:{1}".format(host, port)


def _postgres_endpoints(conn: Dict[str, Any]) -> List[Endpoint]:
    """libpq: comma-separated hosts; '/dir' is a socket directory; '' the default."""
    port = int(conn.get("port", 5432))
    socket_name = ".s.PGSQL.{0}".format(port)
    result: List[Endpoint] = []
    for host in str(conn.get("host", "127.0.0.1")).split(","):
        host = host.strip()
        if not host:
            if _ON_WINDOWS:
                result.append(("localhost", port))
            else:
                result.extend(d + "/" + socket_name for d in _PG_DEFAULT_SOCKET_DIRS)
        elif host.startswith("/"):
            result.append(host.rstrip("/") + "/" + socket_name)
        else:
            result.append((host, port))
    return result


def _resolve_srv(uri: str) -> List[Tuple[str, int]]:
    """The SRV lookup ``MongoClient(connect=False)`` defers, with its tolerance
    for unknown URI options (``warn=True``: a warning, as in the client)."""
    return list(uri_parser.parse_uri(uri, warn=True)["nodelist"])


def _mongodb_endpoints(uri: str) -> List[Endpoint]:
    try:
        # Constructing the client parses and validates the URI; it connects
        # only when used.
        client = MongoClient(uri, connect=False)
    except Exception as exc:  # whatever the driver raises is its rejection
        raise InvalidConnectionError(str(exc)) from exc
    try:
        seeds = list(client.topology_description.server_descriptions())
    finally:
        client.close()
    if uri.startswith("mongodb+srv://"):
        try:
            seeds = _resolve_srv(uri)
        except Exception as exc:
            raise InvalidConnectionError(str(exc)) from exc
    # A Unix socket seed has no port: ("/tmp/mongodb-27017.sock", None).
    return [host if port is None else (host, port) for host, port in seeds]


def _neo4j_endpoints(uri: str, user: Any, password: Any) -> List[Endpoint]:
    try:
        # Construction checks the scheme and the URI without connecting.
        GraphDatabase.driver(uri, auth=(user, password)).close()
    except Exception as exc:
        raise InvalidConnectionError(str(exc)) from exc
    address = Address.parse(urlparse(uri).netloc, default_host="localhost", default_port=7687)
    return [(address.host, _usable_port(address.port))]


def _usable_port(port: Union[int, str]) -> Union[int, str]:
    """The Neo4j driver accepts any port text and fails only when it connects."""
    if isinstance(port, str) and not port.isdigit():
        try:
            socket.getservbyname(port, "tcp")
        except OSError as exc:
            raise InvalidConnectionError(
                "port {0!r} is neither a number nor a known service name".format(port)
            ) from exc
        return port
    number = int(port)
    if not 0 < number < 65536:
        raise InvalidConnectionError("port {0} is outside 1-65535".format(number))
    return number
