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


def test_cli_show_data_tristate(tmp_path, monkeypatch):
    captured = {}

    def fake_run_import(config_path, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr("polyglotimportcsv.cli.run_import", fake_run_import)
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")
    runner = CliRunner()

    assert runner.invoke(main, ["--config", str(cfg)]).exit_code == 0
    assert captured["show_data"] is None
    assert runner.invoke(main, ["--config", str(cfg), "--show-data"]).exit_code == 0
    assert captured["show_data"] is True
    assert runner.invoke(main, ["--config", str(cfg), "--no-data"]).exit_code == 0
    assert captured["show_data"] is False


def test_cli_benchmark_flag_passes_through(tmp_path, monkeypatch):
    captured = {}

    def fake_run_import(config_path, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr("polyglotimportcsv.cli.run_import", fake_run_import)
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")
    result = CliRunner().invoke(main, ["--config", str(cfg), "--benchmark"])
    assert result.exit_code == 0, result.output
    assert captured["benchmark"] is True


def test_cli_execution_defaults_to_stream(monkeypatch):
    captured = {}

    def fake_run_import(config_path, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr("polyglotimportcsv.cli.run_import", fake_run_import)
    from click.testing import CliRunner as _CR
    res = _CR().invoke(main, [
        "--config", "data/ecommerce/import_config.json", "--dry-run",
    ])
    assert res.exit_code == 0, res.output
    assert captured["execution"] == "stream"


def test_cli_passes_execution_materialize(monkeypatch):
    captured = {}

    def fake_run_import(config_path, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr("polyglotimportcsv.cli.run_import", fake_run_import)
    from click.testing import CliRunner as _CR
    res = _CR().invoke(main, [
        "--config", "data/ecommerce/import_config.json", "--dry-run",
        "--execution", "materialize",
    ])
    assert res.exit_code == 0, res.output
    assert captured["execution"] == "materialize"


def test_cli_rejects_unknown_execution():
    from click.testing import CliRunner as _CR
    res = _CR().invoke(main, [
        "--config", "data/ecommerce/import_config.json",
        "--execution", "nonsense",
    ])
    assert res.exit_code == 2
    assert "execution" in res.output.lower()


def test_cli_passes_strategy(monkeypatch):
    from click.testing import CliRunner
    import polyglotimportcsv.cli as climod

    captured = {}

    def fake_run_import(config_path, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(climod, "run_import", fake_run_import)
    runner = CliRunner()
    # --dry-run so no DB; reuse a config that exists in the repo
    res = runner.invoke(climod.main, [
        "--config", "data/ecommerce/import_config.json",
        "--dry-run", "--strategy", "naive",
    ])
    assert res.exit_code == 0, res.output
    assert captured["strategy"] == "naive"
