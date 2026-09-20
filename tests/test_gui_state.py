"""Validation rules for the GUI form state."""

import pytest

from polyglotimportcsv.gui.state import (
    DBMS_NAMES,
    RunOptions,
    validate,
)


def test_defaults_mirror_the_cli_defaults():
    options = RunOptions()
    assert options.strategy == "optimized"
    assert options.execution == "stream"
    assert options.create_schema is True
    assert options.log_level == "INFO"
    assert options.show_data is None
    assert options.only == ()
    assert options.sources == ()


def test_missing_config_is_reported():
    errors = validate(RunOptions())
    assert "config_path" in errors
    assert errors["config_path"] == "Selecione a configuração de importação."


def test_existing_config_passes(tmp_path):
    cfg = tmp_path / "import_config.json"
    cfg.write_text("{}", encoding="utf-8")
    assert validate(RunOptions(config_path=cfg)) == {}


def test_nonexistent_config_is_reported(tmp_path):
    cfg = tmp_path / "ausente.json"
    errors = validate(RunOptions(config_path=cfg))
    assert errors["config_path"].startswith("Arquivo não encontrado")


def test_nonexistent_sgbd_config_is_reported(tmp_path):
    cfg = tmp_path / "import_config.json"
    cfg.write_text("{}", encoding="utf-8")
    errors = validate(RunOptions(config_path=cfg, sgbd_config_path=tmp_path / "x.json"))
    assert errors["sgbd_config_path"].startswith("Arquivo não encontrado")


def test_unknown_dbms_is_reported(tmp_path):
    cfg = tmp_path / "import_config.json"
    cfg.write_text("{}", encoding="utf-8")
    errors = validate(RunOptions(config_path=cfg, only=("postgres", "oracle")))
    assert errors["only"] == "SGBD desconhecido: oracle"


def test_known_dbms_names_are_the_cli_ones():
    assert DBMS_NAMES == ("postgres", "redis", "mongodb", "cassandra", "neo4j")


@pytest.mark.parametrize(
    "name, expected",
    [
        ("", "O nome da fonte não pode ficar vazio."),
        ("a=b", "O nome da fonte não pode conter '=': a=b"),
    ],
)
def test_bad_source_names_are_reported(tmp_path, name, expected):
    cfg = tmp_path / "import_config.json"
    cfg.write_text("{}", encoding="utf-8")
    csv = tmp_path / "stock.csv"
    csv.write_text("a\n", encoding="utf-8")
    errors = validate(RunOptions(config_path=cfg, sources=((name, csv),)))
    assert errors["sources"] == expected


def test_duplicate_source_name_is_reported(tmp_path):
    cfg = tmp_path / "import_config.json"
    cfg.write_text("{}", encoding="utf-8")
    csv = tmp_path / "stock.csv"
    csv.write_text("a\n", encoding="utf-8")
    errors = validate(RunOptions(config_path=cfg, sources=(("stock", csv), ("stock", csv))))
    assert errors["sources"] == "Nome de fonte repetido: stock"


def test_missing_source_file_is_reported(tmp_path):
    cfg = tmp_path / "import_config.json"
    cfg.write_text("{}", encoding="utf-8")
    errors = validate(RunOptions(config_path=cfg, sources=(("stock", tmp_path / "x.csv"),)))
    assert errors["sources"].startswith("Arquivo não encontrado")
