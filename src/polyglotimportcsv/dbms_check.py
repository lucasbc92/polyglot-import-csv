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

import os
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union
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

UP = "up"
DOWN = "down"
INVALID = "invalid"

#: Seconds each probe waits. On Windows a refused connection to 127.0.0.1
#: takes about 2 s (TCP retries the SYN), which is why probes run in parallel.
PROBE_TIMEOUT = 2.0


class InvalidConnectionError(ValueError):
    """The connection setting can never connect: the driver rejects it."""


@dataclass(frozen=True)
class DbmsStatus:
    dbms: str
    endpoints: Tuple[Endpoint, ...]
    state: str  # UP, DOWN or INVALID
    error: str = ""  # the driver's message when INVALID


@dataclass(frozen=True)
class DbmsCheckReport:
    statuses: Tuple[DbmsStatus, ...]
    #: One line per INVALID DBMS: what to fix, and in which file.
    fixes: Tuple[str, ...]
    #: How to start each DOWN DBMS; compose services grouped per file.
    starts: Tuple[str, ...]
    #: True when a start hint is a plain command (net start, systemctl...),
    #: which usually needs an administrator terminal or sudo.
    service_commands: bool

    @property
    def ok(self) -> bool:
        return all(status.state == UP for status in self.statuses)

    @property
    def not_ready(self) -> List[DbmsStatus]:
        return [status for status in self.statuses if status.state != UP]


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


def probe(endpoint: Endpoint, timeout: float = PROBE_TIMEOUT) -> bool:
    """True when something accepts a connection at ``endpoint``. Never logs in."""
    try:
        if isinstance(endpoint, str):
            if not hasattr(socket, "AF_UNIX"):
                # Python on Windows has no AF_UNIX; the socket file exists
                # while its server runs.
                return os.path.exists(endpoint)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                sock.connect(endpoint)
            return True
        with socket.create_connection(endpoint, timeout=timeout):
            return True
    except (OSError, OverflowError, ValueError):
        # OverflowError/ValueError: a host/port setting with a port outside
        # 0-65535, which the driver could not connect to either.
        return False


def start_hints(
    down: Sequence[str], dbms_cfg: Dict[str, Any], dbms_config_path: Path
) -> List[str]:
    """How to start each DBMS in ``down``, in order; one docker command per compose file."""
    entries: List[Union[str, Path]] = []
    services: Dict[Path, List[str]] = {}
    for dbms in down:
        start = (dbms_cfg.get(dbms) or {}).get("start")
        if not start:
            entries.append('{0}: start the DBMS service, or declare "start" for it in {1}'.format(
                dbms, dbms_config_path.name))
        elif "command" in start:
            entries.append(start["command"])
        else:
            compose_file = (dbms_config_path.parent / start["compose"]["file"]).resolve()
            if compose_file not in services:
                services[compose_file] = []
                entries.append(compose_file)
            services[compose_file].append(start["compose"]["service"])
    return [
        'docker compose -f "{0}" up -d --wait {1}'.format(entry, " ".join(services[entry]))
        if isinstance(entry, Path) else entry
        for entry in entries
    ]


def check_dbms(
    targets: Sequence[str],
    dbms_cfg: Dict[str, Any],
    dbms_config_path: Path,
    probe_fn: Optional[Callable[[Endpoint], bool]] = None,
) -> DbmsCheckReport:
    """Probe every endpoint of ``targets`` in parallel and say what to do next."""
    probe_fn = probe_fn or probe  # looked up per call, so tests can patch probe
    resolved: Dict[str, Tuple[Endpoint, ...]] = {}
    errors: Dict[str, str] = {}
    for dbms in targets:
        try:
            resolved[dbms] = tuple(endpoints(dbms, dbms_cfg.get(dbms) or {}))
        except InvalidConnectionError as exc:
            errors[dbms] = str(exc)

    pairs = [(dbms, endpoint) for dbms, found in resolved.items() for endpoint in found]
    with ThreadPoolExecutor(max_workers=max(1, len(pairs))) as pool:
        answers = list(pool.map(lambda pair: probe_fn(pair[1]), pairs))
    answering = {dbms for (dbms, _), answered in zip(pairs, answers) if answered}

    statuses = tuple(
        DbmsStatus(dbms, (), INVALID, errors[dbms]) if dbms in errors
        else DbmsStatus(dbms, resolved[dbms], UP if dbms in answering else DOWN)
        for dbms in targets
    )
    down = [status.dbms for status in statuses if status.state == DOWN]
    fixes = tuple(
        '{0}: invalid connection ({1}). Fix "connection" for it in {2}'.format(
            status.dbms, status.error, dbms_config_path.name)
        for status in statuses if status.state == INVALID
    )
    service_commands = any(
        "command" in ((dbms_cfg.get(dbms) or {}).get("start") or {}) for dbms in down
    )
    return DbmsCheckReport(
        statuses, fixes, tuple(start_hints(down, dbms_cfg, dbms_config_path)), service_commands
    )


def not_ready_message(report: DbmsCheckReport) -> str:
    names = ", ".join("{0} ({1})".format(s.dbms, s.state) for s in report.not_ready)
    return "DBMS not ready: {0}. Fix or start them as shown above, then run again.".format(names)
