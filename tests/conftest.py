"""Shared fixtures: keep tests from writing session logs into the repo's logs/ dir."""

import pytest

from polyglotimportcsv import csv_reader, metrics, reporting
from polyglotimportcsv import stream_source as ss


@pytest.fixture(autouse=True)
def _quiet_reporting(monkeypatch):
    monkeypatch.setenv("POLYGLOT_NO_LOG", "1")
    yield
    reporting.reset()
    metrics.set_current(None)


@pytest.fixture(autouse=True)
def _dbms_always_up(monkeypatch):
    """Runner and CLI tests use fake importers and sinks: the DBMS check that
    precedes every real import must not open sockets. test_dbms_check.py
    overrides this fixture to exercise the real probe."""
    from polyglotimportcsv import dbms_check

    monkeypatch.setattr(dbms_check, "probe", lambda endpoint, timeout=2.0: True)


@pytest.fixture
def small_probe_rounds(monkeypatch):
    """Probe 50 distinct values per round, so the early stop bites on test-sized chunks."""
    monkeypatch.setattr(csv_reader, "_DATETIME_PROBE_CHUNK", 50)


@pytest.fixture
def reads(monkeypatch):
    """Every ``stream_source._read_chunks`` call as ``(file name, usecols)``."""
    calls = []
    real = ss._read_chunks

    def counting(name, path, chunksize, usecols=None):
        calls.append((path.name, usecols))
        return real(name, path, chunksize, usecols)

    monkeypatch.setattr(ss, "_read_chunks", counting)
    return calls
