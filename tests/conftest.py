"""Shared fixtures: keep tests from writing session logs into the repo's logs/ dir."""

import pytest

from polyglotimportcsv import metrics, reporting


@pytest.fixture(autouse=True)
def _quiet_reporting(monkeypatch):
    monkeypatch.setenv("POLYGLOT_NO_LOG", "1")
    yield
    reporting.reset()
    metrics.set_current(None)
