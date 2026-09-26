"""Checks run before an import, with the CLI's own code, on headers only."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from polyglotimportcsv.gui import preflight
from polyglotimportcsv.gui.state import RunOptions

ROOT = Path(__file__).resolve().parents[1]
ECOMMERCE = ROOT / "data" / "ecommerce"


@pytest.fixture(autouse=True)
def _fresh_cache():
    preflight.clear_cache()
    yield
    preflight.clear_cache()


@pytest.fixture()
def ecommerce(tmp_path):
    """A writable copy of the reference scenario."""
    target = tmp_path / "ecommerce"
    shutil.copytree(ECOMMERCE, target)
    return target


def _check(folder, config="import_config.json", **kwargs):
    return preflight.check(
        RunOptions(
            config_path=folder / config,
            sgbd_config_path=folder / "sgbd_config.json",
            **kwargs,
        )
    )


def test_reference_multi_config_passes_and_is_classified(ecommerce):
    result = _check(ecommerce)
    assert result.errors == {}
    assert result.kind == preflight.MULTI
    assert result.declared["stock"] == "ecommerce_stock.csv"


def test_reference_combined_config_passes_and_is_classified(ecommerce):
    result = _check(ecommerce, "import_config_combined.json")
    assert result.errors == {}
    assert result.kind == preflight.COMBINED
    assert result.declared == {"ecommerce": "ecommerce_join.csv"}


def test_classify_sources():
    assert preflight.classify_sources({"a": "a.csv", "b": "b.csv"}) == preflight.MULTI
    assert preflight.classify_sources({"x": {"file": "x.csv"}}) == preflight.COMBINED
    mixed = {"a": "a.csv", "x": {"file": "x.csv"}}
    assert preflight.classify_sources(mixed) == preflight.MULTI


def test_no_config_means_no_kind_and_no_preflight_errors():
    result = preflight.check(RunOptions())
    assert result.kind is None
    assert result.errors == {}


def test_schema_violation_is_reported_with_the_cli_message(ecommerce):
    result = _check(ecommerce, "import_config_invalido.json")
    assert result.kind is None
    assert result.errors["config_path"].startswith("Invalid import configuration JSON")


def test_unreadable_json_is_reported(ecommerce):
    (ecommerce / "import_config.json").write_text("{ quebrado", encoding="utf-8")
    result = _check(ecommerce)
    assert "Invalid JSON" in result.errors["config_path"]


def test_cache_sees_a_rewritten_config(ecommerce):
    """A config saved half-way, then fixed: the fix must be picked up."""
    path = ecommerce / "import_config.json"
    good = path.read_text(encoding="utf-8")
    path.write_text("{ quebrado", encoding="utf-8")
    assert "config_path" in _check(ecommerce).errors
    path.write_text(good, encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000_000))
    assert _check(ecommerce).errors == {}


def test_a_dbms_missing_from_the_sgbd_config_is_reported(ecommerce):
    sgbd = ecommerce / "sgbd_config.json"
    data = json.loads(sgbd.read_text(encoding="utf-8"))
    del data["neo4j"]
    sgbd.write_text(json.dumps(data), encoding="utf-8")
    result = _check(ecommerce)
    assert "neo4j" in result.errors["sgbd_config_path"]
    assert result.kind == preflight.MULTI, "sources can still be chosen"


def test_default_sgbd_config_next_to_the_import_config_is_used(ecommerce):
    result = preflight.check(RunOptions(config_path=ecommerce / "import_config.json"))
    assert result.errors == {}


def test_missing_default_sgbd_config_is_reported(ecommerce):
    (ecommerce / "sgbd_config.json").unlink()
    result = preflight.check(RunOptions(config_path=ecommerce / "import_config.json"))
    assert "sgbd_config.json" in result.errors["sgbd_config_path"]


def test_an_override_naming_an_undeclared_source_is_reported(ecommerce):
    csv = ecommerce / "ecommerce_stock.csv"
    result = _check(ecommerce, sources=(("ecommerce_stock", csv),))
    assert result.errors["sources"] == (
        "Fonte não declarada na configuração de importação: ecommerce_stock"
    )


def test_a_combined_config_accepts_a_single_file(ecommerce):
    join = ecommerce / "ecommerce_join.csv"
    result = _check(
        ecommerce, "import_config_combined.json",
        sources=(("ecommerce", join), ("outra", join)),
    )
    assert result.errors["sources"] == "A configuração combinada aceita um único arquivo CSV."


def test_a_missing_declared_file_is_reported(ecommerce):
    (ecommerce / "ecommerce_purchase.csv").unlink()
    result = _check(ecommerce)
    assert "purchase" in result.errors["config_path"]
    assert "ecommerce_purchase.csv" in result.errors["config_path"]


def test_a_column_missing_from_the_header_gives_the_cli_message(ecommerce):
    path = ecommerce / "import_config.json"
    path.write_text(
        path.read_text(encoding="utf-8").replace('"product_name"', '"product_nam3"', 1),
        encoding="utf-8",
    )
    result = _check(ecommerce)
    assert result.errors["config_path"] == (
        "Entity 'products' in 'postgres' references unknown column: product_nam3"
    )


def test_a_header_error_in_an_override_is_shown_under_sources(ecommerce, tmp_path):
    bad = tmp_path / "estoque.csv"
    bad.write_text("x,y\n1,2\n", encoding="utf-8")
    result = _check(ecommerce, sources=(("stock", bad),))
    assert "references unknown column" in result.errors["sources"]


def test_only_selected_dbms_are_checked(ecommerce):
    path = ecommerce / "import_config.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["neo4j"]["entities"]["User"]["columns"] = {"nao_existe": {"is_key": True}}
    path.write_text(json.dumps(data), encoding="utf-8")
    assert "config_path" in _check(ecommerce).errors
    assert _check(ecommerce, only=("postgres",)).errors == {}


def test_combined_file_needs_an_origin_and_a_data_column(ecommerce, tmp_path):
    lonely = tmp_path / "uma_coluna.csv"
    lonely.write_text("origem\nstock\n", encoding="utf-8")
    result = _check(ecommerce, "import_config_combined.json", sources=(("ecommerce", lonely),))
    assert "origin column plus data columns" in result.errors["sources"]


def test_a_bom_in_the_header_is_ignored(ecommerce):
    """Excel writes a UTF-8 BOM; the CLI reads with utf-8-sig and so must we."""
    path = ecommerce / "ecommerce_stock.csv"
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    assert _check(ecommerce).errors == {}


def test_relative_override_follows_the_working_directory(ecommerce, monkeypatch):
    """The CLI resolves --source paths from the working directory, not the config."""
    monkeypatch.chdir(ecommerce)
    result = _check(ecommerce, sources=(("stock", Path("ecommerce_stock.csv")),))
    assert result.errors == {}


def test_headers_are_read_once_while_unchanged(ecommerce, monkeypatch):
    reads = []
    real = preflight._read_header

    def counting(path):
        reads.append(path)
        return real(path)

    monkeypatch.setattr(preflight, "_read_header", counting)
    _check(ecommerce)
    first = len(reads)
    _check(ecommerce)
    assert first > 0
    assert len(reads) == first, "an unchanged file must not be re-read"


def test_the_pure_core_never_imports_qt():
    """state, command and preflight must stay importable without PySide6."""
    script = (
        "import sys\n"
        "import polyglotimportcsv.gui.state, polyglotimportcsv.gui.command\n"
        "import polyglotimportcsv.gui.preflight\n"
        "assert 'PySide6' not in sys.modules, 'the pure core imported PySide6'\n"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
