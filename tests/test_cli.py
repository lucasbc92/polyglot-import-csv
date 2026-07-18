"""CLI v2: config-driven sources, repeatable --source overrides."""

from click.testing import CliRunner

from polyglotimportcsv.cli import main


def test_cli_requires_config_and_takes_no_csv_argument(tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, ["some.csv"])
    assert result.exit_code == 2  # unexpected extra argument


def test_cli_source_override_is_parsed(tmp_path, monkeypatch):
    captured = {}

    def fake_run_import(config_path, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr("polyglotimportcsv.cli.run_import", fake_run_import)
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--config", str(cfg), "--dry-run", "--source", "stock=a.csv", "--source", "purchase=b.csv"],
    )
    assert result.exit_code == 0, result.output
    assert captured["source_overrides"] == {"stock": "a.csv", "purchase": "b.csv"}


def test_cli_rejects_malformed_source(tmp_path):
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(cfg), "--source", "nopath"])
    assert result.exit_code == 2
    assert "NAME=PATH" in result.output


import logging


def test_cli_log_level_controls_terminal_verbosity(tmp_path, monkeypatch):
    def fake_run_import(config_path, **kwargs):
        logging.getLogger("polyglotimportcsv.fake").debug("dbg-marker")
        return []

    monkeypatch.setattr("polyglotimportcsv.cli.run_import", fake_run_import)
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(main, ["--config", str(cfg), "--log-level", "debug"])
    assert result.exit_code == 0, result.output
    assert "dbg-marker" in result.output

    result = runner.invoke(main, ["--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert "dbg-marker" not in result.output
