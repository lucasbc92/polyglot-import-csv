"""CLI v2: config-driven sources, repeatable --source overrides."""

from pathlib import Path
import pytest
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


def _capture_run_import(monkeypatch):
    captured = {}

    def fake_run_import(config_path, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr("polyglotimportcsv.cli.run_import", fake_run_import)
    return captured


def test_cli_sample_defaults_to_fifty(tmp_path, monkeypatch):
    captured = _capture_run_import(monkeypatch)
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")
    result = CliRunner().invoke(main, ["--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert captured["sample_size"] == 50
    assert captured["show_data"] is None


def test_cli_sample_size_is_passed_through(tmp_path, monkeypatch):
    captured = _capture_run_import(monkeypatch)
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")
    result = CliRunner().invoke(main, ["--config", str(cfg), "--sample", "7"])
    assert result.exit_code == 0, result.output
    assert captured["sample_size"] == 7


def test_cli_sample_rejects_zero(tmp_path):
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")
    result = CliRunner().invoke(main, ["--config", str(cfg), "--sample", "0"])
    assert result.exit_code == 2


def test_cli_sample_cannot_be_combined_with_show_data_or_no_data(tmp_path, monkeypatch):
    _capture_run_import(monkeypatch)
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")
    for flag in ("--show-data", "--no-data"):
        result = CliRunner().invoke(main, ["--config", str(cfg), "--sample", "5", flag])
        assert result.exit_code == 2, flag
        assert "--sample" in result.output


def test_cli_survives_a_non_utf8_output_encoding():
    """Redirected output on a Windows machine uses the ANSI code page (cp1252).

    rich's banner is made of box-drawing characters that cp1252 cannot encode,
    so ``polyglotimportcsv ... > saida.txt`` crashed with UnicodeEncodeError
    before doing anything. Found by the release smoke test on a GitHub runner.
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONIOENCODING="cp1252", POLYGLOT_NO_LOG="1")
    env.pop("FORCE_COLOR", None)
    result = subprocess.run(
        [sys.executable, "-m", "polyglotimportcsv",
         "--config", str(root / "data" / "ecommerce" / "import_config.json"),
         "--dry-run", "--no-data"],
        capture_output=True, env=env, cwd=root,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")[-800:]
    assert "Finished dry-run" in result.stdout.decode("utf-8", "replace")


ECOMMERCE = Path(__file__).resolve().parents[1] / "data" / "ecommerce"


def _report(ok):
    from polyglotimportcsv.dbms_check import DOWN, UP, DbmsCheckReport, DbmsStatus

    status = DbmsStatus("redis", (("127.0.0.1", 6379),), UP if ok else DOWN)
    return DbmsCheckReport((status,), (), (), False)


def _no_import(*a, **k):
    raise AssertionError("--check-dbms must not import")


def test_cli_check_dbms_exits_zero_when_all_are_up(tmp_path, monkeypatch):
    captured = {}

    def fake_run_check(config_path, **kwargs):
        captured.update(kwargs)
        return _report(True)

    monkeypatch.setattr("polyglotimportcsv.cli.run_check", fake_run_check)
    monkeypatch.setattr("polyglotimportcsv.cli.run_import", _no_import)
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")
    result = CliRunner().invoke(main, ["--config", str(cfg), "--check-dbms", "--only", "redis"])
    assert result.exit_code == 0, result.output
    assert captured == {"dbms_config_path": None, "only": ["redis"]}


def test_cli_check_dbms_exits_one_when_a_dbms_is_down(tmp_path, monkeypatch):
    monkeypatch.setattr("polyglotimportcsv.cli.run_check", lambda config_path, **kw: _report(False))
    monkeypatch.setattr("polyglotimportcsv.cli.run_import", _no_import)
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")
    result = CliRunner().invoke(main, ["--config", str(cfg), "--check-dbms"])
    assert result.exit_code == 1
    assert "DBMS not ready: redis (down)" in result.output


@pytest.mark.parametrize("flag", ["--dry-run", "--benchmark"])
def test_cli_check_dbms_rejects_dry_run_and_benchmark(tmp_path, flag):
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")
    result = CliRunner().invoke(main, ["--config", str(cfg), "--check-dbms", flag])
    assert result.exit_code == 2
    assert "--check-dbms cannot be combined" in result.output


def test_cli_check_dbms_exits_one_when_only_matches_no_declared_dbms(monkeypatch):
    def must_not_probe(*a, **k):
        raise AssertionError("probe must not run when there is no target DBMS")

    monkeypatch.setattr("polyglotimportcsv.dbms_check.probe", must_not_probe)
    result = CliRunner().invoke(main, [
        "--config", str(ECOMMERCE / "import_config.json"),
        "--check-dbms", "--only", "postgre",
    ])
    assert result.exit_code == 1
    assert "No target DBMS to check" in result.output


def test_cli_check_dbms_end_to_end_shows_the_start_command(monkeypatch):
    monkeypatch.setattr("polyglotimportcsv.dbms_check.probe", lambda ep, timeout=2.0: False)
    result = CliRunner().invoke(main, [
        "--config", str(ECOMMERCE / "import_config.json"),
        "--dbms-config", str(ECOMMERCE / "dbms_config_linux.json"),
        "--check-dbms", "--only", "redis",
    ])
    assert result.exit_code == 1
    assert "sudo systemctl start redis-server" in result.output
