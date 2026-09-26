"""Resolving the child process that actually runs the CLI."""

import sys

from polyglotimportcsv.gui.launcher import CLI_FLAG, child_environment, resolve


def test_source_checkout_runs_the_module(monkeypatch):
    monkeypatch.setattr(sys, "executable", "/venv/bin/python")
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert resolve() == ["/venv/bin/python", "-m", "polyglotimportcsv"]


def test_frozen_build_reenters_itself(monkeypatch):
    monkeypatch.setattr(sys, "executable", "/dist/PolyglotImportCSV.exe")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert resolve() == ["/dist/PolyglotImportCSV.exe", CLI_FLAG]


def test_environment_forces_color_and_width():
    env = child_environment(columns=132, color=True)
    assert env["FORCE_COLOR"] == "1"
    assert env["COLUMNS"] == "132"
    assert env["PYTHONUNBUFFERED"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_environment_without_color_omits_force_color():
    env = child_environment(columns=100, color=False)
    assert "FORCE_COLOR" not in env


def test_environment_clamps_a_silly_width():
    assert child_environment(columns=3, color=True)["COLUMNS"] == "40"
