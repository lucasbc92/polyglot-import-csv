"""dbms_check: addresses from the drivers' own parsing, probes and hints."""

from __future__ import annotations

import pytest
from neo4j import GraphDatabase
from pymongo import MongoClient
from pymongo.errors import ConfigurationError

from polyglotimportcsv import dbms_check
from polyglotimportcsv.dbms_check import InvalidConnectionError, endpoints, format_endpoint


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
