"""The package version lives in two places; they must agree."""

from pathlib import Path

import pytest

import polyglotimportcsv

tomllib = pytest.importorskip("tomllib")

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_pyproject_and_package_versions_agree():
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    assert project["version"] == polyglotimportcsv.__version__


def test_the_delivered_version_is_1_0_0():
    assert polyglotimportcsv.__version__ == "1.0.0"
