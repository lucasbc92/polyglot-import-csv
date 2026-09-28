"""dbms_check: addresses from the drivers' own parsing, probes and hints."""

from __future__ import annotations

import socket
import time

import pytest
from neo4j import GraphDatabase
from pymongo import MongoClient
from pymongo.errors import ConfigurationError

from polyglotimportcsv import dbms_check
from polyglotimportcsv.dbms_check import (
    DOWN,
    INVALID,
    UP,
    InvalidConnectionError,
    check_dbms,
    endpoints,
    format_endpoint,
    not_ready_message,
    probe,
)


@pytest.fixture(autouse=True)
def _dbms_always_up():
    """Overrides the conftest stub: this module tests the real probe."""
    yield


def _mongo(uri):
    return endpoints("mongodb", {"connection": {"uri": uri, "database": "d"}})


def _neo4j(uri):
    return endpoints("neo4j", {"connection": {"uri": uri, "user": "u", "password": "p"}})


# -- defaults: the same as each importer's ------------------------------------


def test_defaults_match_the_importers():
    assert endpoints("postgres", {"connection": {}}) == [("127.0.0.1", 5432)]
    assert endpoints("redis", {"connection": {}}) == [("127.0.0.1", 6379)]
    assert endpoints("cassandra", {"connection": {"keyspace": "k"}}) == [("127.0.0.1", 9042)]
    assert endpoints("mongodb", {"connection": {}}) == [("127.0.0.1", 27017)]
    assert endpoints("neo4j", {"connection": {}}) == [("127.0.0.1", 7687)]


def test_cassandra_probes_every_host_on_the_shared_port():
    entry = {"connection": {"hosts": ["a", "b"], "port": 9043, "keyspace": "k"}}
    assert endpoints("cassandra", entry) == [("a", 9043), ("b", 9043)]


# -- postgres: libpq's rules for "host" ---------------------------------------


def test_postgres_host_may_list_several_hosts():
    entry = {"connection": {"host": "a, b", "port": 5433}}
    assert endpoints("postgres", entry) == [("a", 5433), ("b", 5433)]


def test_postgres_host_starting_with_a_slash_is_a_socket_directory():
    entry = {"connection": {"host": "/var/run/postgresql"}}
    assert endpoints("postgres", entry) == ["/var/run/postgresql/.s.PGSQL.5432"]


def test_postgres_empty_host_is_libpqs_default(monkeypatch):
    monkeypatch.setattr(dbms_check, "_ON_WINDOWS", True)
    assert endpoints("postgres", {"connection": {"host": ""}}) == [("localhost", 5432)]
    monkeypatch.setattr(dbms_check, "_ON_WINDOWS", False)
    assert endpoints("postgres", {"connection": {"host": ""}}) == [
        "/var/run/postgresql/.s.PGSQL.5432",
        "/tmp/.s.PGSQL.5432",
    ]


# -- consistency with the drivers (spec §5.1, §6.4) ----------------------------

VALID_MONGODB = [
    ("mongodb://127.0.0.1:27017", [("127.0.0.1", 27017)]),
    ("mongodb://u:p@db.example:27018/shop?authSource=admin", [("db.example", 27018)]),
    ("mongodb://a:1,b:2/?replicaSet=rs", [("a", 1), ("b", 2)]),
    ("mongodb://[::1]:27017", [("::1", 27017)]),
    ("mongodb://%2Ftmp%2Fmongodb-27017.sock", ["/tmp/mongodb-27017.sock"]),
    ("mongodb://h/?tls=true&directConnection=true", [("h", 27017)]),
    ("mongodb+srv://cluster0.example.net/shop", [("shard-0.example.net", 27017)]),
]
INVALID_MONGODB = [
    "mongodb://",
    "http://h",
    "mongodb://h:notaport",
    "mongodb://h:99999",
    "mongodb+srv://h:27017/db",
    "mongodb+srv://a,b/db",
]
VALID_NEO4J = [
    ("bolt://127.0.0.1:7687", [("127.0.0.1", 7687)]),
    ("bolt+s://h", [("h", 7687)]),
    ("bolt+ssc://h:7688", [("h", 7688)]),
    ("neo4j://h?policy=eu", [("h", 7687)]),
    ("neo4j+s://h:7690", [("h", 7690)]),
    ("neo4j+ssc://[::1]", [("::1", 7687)]),
    ("bolt://", [("localhost", 7687)]),
    ("bolt://h:0", [("h", 7687)]),  # the driver's Address.parse turns port 0 into the default
    ("bolt://h:http", [("h", "http")]),  # a service name, resolved by getaddrinfo
]
INVALID_NEO4J = ["bolt+routing://h", "http://h", "bolt://u:p@h"]


def _mongodb_driver_accepts(uri):
    try:
        MongoClient(uri, connect=False).close()
    except Exception:
        return False
    return True


def _neo4j_driver_accepts(uri):
    try:
        GraphDatabase.driver(uri, auth=("u", "p")).close()
    except Exception:
        return False
    return True


@pytest.fixture()
def fake_srv(monkeypatch):
    """No DNS in tests: the SRV record of any +srv URI names one shard."""
    monkeypatch.setattr(dbms_check, "_resolve_srv", lambda uri: [("shard-0.example.net", 27017)])


@pytest.mark.parametrize("uri, expected", VALID_MONGODB)
def test_a_mongodb_uri_the_driver_accepts_is_never_invalid(uri, expected, fake_srv):
    assert _mongodb_driver_accepts(uri)
    assert sorted(_mongo(uri), key=str) == sorted(expected, key=str)


@pytest.mark.parametrize("uri", INVALID_MONGODB)
def test_a_mongodb_uri_the_driver_rejects_is_invalid(uri, fake_srv):
    assert not _mongodb_driver_accepts(uri)
    with pytest.raises(InvalidConnectionError):
        _mongo(uri)


@pytest.mark.parametrize("uri, expected", VALID_NEO4J)
def test_a_neo4j_uri_the_driver_accepts_is_never_invalid(uri, expected):
    assert _neo4j_driver_accepts(uri)
    assert _neo4j(uri) == expected


@pytest.mark.parametrize("uri", INVALID_NEO4J)
def test_a_neo4j_uri_the_driver_rejects_is_invalid(uri):
    assert not _neo4j_driver_accepts(uri)
    with pytest.raises(InvalidConnectionError):
        _neo4j(uri)


@pytest.mark.parametrize("uri", ["bolt://h:notaservice", "neo4j://h:99999"])
def test_a_neo4j_port_no_connection_could_use_is_invalid(uri):
    # The driver accepts these at construction and fails only when it
    # connects; such a port can never work, so no working URI is rejected.
    assert _neo4j_driver_accepts(uri)
    with pytest.raises(InvalidConnectionError):
        _neo4j(uri)


def test_a_srv_uri_that_does_not_resolve_is_invalid(monkeypatch):
    def no_such_name(uri):
        raise ConfigurationError("The DNS query name does not exist: _mongodb._tcp.nowhere.invalid.")

    monkeypatch.setattr(dbms_check, "_resolve_srv", no_such_name)
    with pytest.raises(InvalidConnectionError, match="DNS query name does not exist"):
        _mongo("mongodb+srv://nowhere.invalid/db")


# -- presentation -------------------------------------------------------------


def test_format_endpoint():
    assert format_endpoint(("127.0.0.1", 5432)) == "127.0.0.1:5432"
    assert format_endpoint(("::1", 27017)) == "[::1]:27017"
    assert format_endpoint("/tmp/mongodb-27017.sock") == "/tmp/mongodb-27017.sock"


# -- probe --------------------------------------------------------------------


def test_probe_is_true_for_a_listening_socket():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    try:
        assert probe(server.getsockname(), timeout=1.0) is True
    finally:
        server.close()


def test_probe_is_false_for_a_closed_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    assert probe(("127.0.0.1", port), timeout=0.5) is False


def test_probe_is_false_for_an_out_of_range_port():
    assert probe(("127.0.0.1", 70000), timeout=0.5) is False


def test_probe_is_false_for_a_missing_unix_socket(tmp_path):
    assert probe(str(tmp_path / "none.sock"), timeout=0.5) is False


# -- check_dbms ---------------------------------------------------------------

ALL = ["postgres", "mongodb", "cassandra", "redis", "neo4j"]


def _cfg():
    return {
        "version": 1,
        "postgres": {"connection": {"host": "127.0.0.1", "port": 5432},
                     "start": {"command": "net start postgresql-x64-16"}},
        "mongodb": {"connection": {"uri": "mongodb://127.0.0.1:27017", "database": "d"},
                    "start": {"compose": {"file": "../docker-compose.yml", "service": "mongodb"}}},
        "cassandra": {"connection": {"hosts": ["10.0.0.1", "10.0.0.2"], "keyspace": "k"},
                      "start": {"compose": {"file": "../docker-compose.yml", "service": "cassandra"}}},
        "redis": {"connection": {}},
        "neo4j": {"connection": {"uri": "http://h", "user": "u", "password": "p"},
                  "start": {"command": "net start neo4j"}},
    }


def test_check_reports_each_state_and_what_to_do(tmp_path):
    path = tmp_path / "cfg" / "dbms_config.json"
    answering = {("127.0.0.1", 5432), ("10.0.0.2", 9042)}
    report = check_dbms(ALL, _cfg(), path, probe_fn=lambda ep: ep in answering)

    assert {s.dbms: s.state for s in report.statuses} == {
        "postgres": UP, "mongodb": DOWN, "cassandra": UP, "redis": DOWN, "neo4j": INVALID,
    }
    assert [s.dbms for s in report.statuses] == ALL
    assert not report.ok
    compose = (tmp_path / "docker-compose.yml").resolve()
    assert report.starts == (
        'docker compose -f "{0}" up -d --wait mongodb'.format(compose),
        'redis: start the DBMS service, or declare "start" for it in dbms_config.json',
    )
    assert len(report.fixes) == 1
    assert report.fixes[0].startswith("neo4j: invalid connection (")
    assert report.fixes[0].endswith('Fix "connection" for it in dbms_config.json')
    # The only command-type start (neo4j) belongs to an INVALID DBMS, not a DOWN one.
    assert report.service_commands is False


def test_compose_services_of_one_file_share_one_command(tmp_path):
    path = tmp_path / "cfg" / "dbms_config.json"
    report = check_dbms(["postgres", "mongodb", "cassandra"], _cfg(), path, probe_fn=lambda ep: False)
    compose = (tmp_path / "docker-compose.yml").resolve()
    assert report.starts == (
        "net start postgresql-x64-16",
        'docker compose -f "{0}" up -d --wait mongodb cassandra'.format(compose),
    )
    assert report.service_commands is True


def test_hints_name_the_dbms_config_actually_used(tmp_path):
    path = tmp_path / "dbms_config_windows.json"
    report = check_dbms(["redis", "neo4j"], _cfg(), path, probe_fn=lambda ep: False)
    assert report.starts[0].endswith("in dbms_config_windows.json")
    assert report.fixes[0].endswith("in dbms_config_windows.json")


def test_all_up_is_ok_and_has_nothing_to_say(tmp_path):
    report = check_dbms(["postgres", "redis"], _cfg(), tmp_path / "d.json", probe_fn=lambda ep: True)
    assert report.ok
    assert report.not_ready == []
    assert report.starts == () and report.fixes == ()


def test_an_invalid_connection_is_never_probed(tmp_path):
    seen = []
    report = check_dbms(["neo4j"], _cfg(), tmp_path / "d.json",
                        probe_fn=lambda ep: seen.append(ep) or True)
    assert seen == []
    assert report.statuses[0].state == INVALID
    assert report.statuses[0].endpoints == ()
    assert not report.ok


def test_probes_run_in_parallel(tmp_path):
    def slow(endpoint):
        time.sleep(0.5)
        return True

    start = time.monotonic()
    # postgres 1 + cassandra 2 + redis 1 = four endpoints of 0.5 s each
    check_dbms(["postgres", "cassandra", "redis"], _cfg(), tmp_path / "d.json", probe_fn=slow)
    assert time.monotonic() - start < 1.5


def test_not_ready_message_lists_each_dbms_and_state(tmp_path):
    report = check_dbms(ALL, _cfg(), tmp_path / "d.json", probe_fn=lambda ep: False)
    message = not_ready_message(report)
    assert message.startswith("DBMS not ready: postgres (down), mongodb (down), cassandra (down),")
    assert "neo4j (invalid)" in message
