"""Shared fixtures: keep tests from writing session logs into the repo's logs/ dir."""

import pytest

from polyglotimportcsv import metrics, reporting


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
