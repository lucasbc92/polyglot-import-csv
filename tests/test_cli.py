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


def test_cli_chunk_and_batch_defaults(monkeypatch):
    captured = _capture_run_import(monkeypatch)
    res = CliRunner().invoke(main, ["--config", str(ECOMMERCE / "import_config.json"), "--dry-run"])
    assert res.exit_code == 0, res.output
    assert captured["chunk_size_mb"] == 8
    assert captured["batch_size"] == 1024
    assert "execution" not in captured


def test_cli_passes_chunk_and_batch_sizes(monkeypatch):
    captured = _capture_run_import(monkeypatch)
    res = CliRunner().invoke(main, [
        "--config", str(ECOMMERCE / "import_config.json"), "--dry-run",
        "--chunk-size", "64", "--batch-size", "4096",
    ])
    assert res.exit_code == 0, res.output
    assert captured["chunk_size_mb"] == 64
    assert captured["batch_size"] == 4096


@pytest.mark.parametrize("flag,value", [
    ("--chunk-size", "7"), ("--chunk-size", "257"),
    ("--batch-size", "1023"), ("--batch-size", "8193"),
])
def test_cli_rejects_out_of_range_sizes(flag, value, monkeypatch):
    monkeypatch.setattr("polyglotimportcsv.cli.run_import", _no_run)
    res = CliRunner().invoke(main, [
        "--config", str(ECOMMERCE / "import_config.json"), "--dry-run", flag, value,
    ])
    assert res.exit_code == 2
    assert flag in res.output


def test_cli_has_no_execution_option(monkeypatch):
    monkeypatch.setattr("polyglotimportcsv.cli.run_import", _no_run)
    res = CliRunner().invoke(main, [
        "--config", str(ECOMMERCE / "import_config.json"), "--execution", "stream",
    ])
    assert res.exit_code == 2
    assert "No such option" in res.output and "--execution" in res.output


def test_cli_option_help_and_metadata():
    options = {p.name: p for p in main.params}
    chunk, batch = options["chunk_size_mb"], options["batch_size"]
    assert chunk.opts == ["--chunk-size"] and batch.opts == ["--batch-size"]
    assert (chunk.metavar, chunk.show_default, chunk.default) == ("MB", True, 8)
    assert (batch.metavar, batch.show_default, batch.default) == ("N", True, 1024)
    assert chunk.help == (
        "Memory budget of each read chunk, in MB (8-256). "
        "Rows per chunk follow each file's row width."
    )
    assert batch.help == "Rows per write batch (1024-8192), capped at the rows of one read chunk."
    assert options["dry_run"].help == (
        "Run every check, on headers and on the data rows, and print the row counts; "
        "do not connect to databases."
    )


def test_cli_reports_a_zero_byte_csv_without_a_traceback(tmp_path):
    (tmp_path / "ev.csv").write_bytes(b"")
    cfg = tmp_path / "import_config.json"
    cfg.write_text(
        '{"sources": {"ev": "ev.csv"}, '
        '"redis": {"entities": {"ev": {"columns": {"id": {"is_key": true}}}}}}',
        encoding="utf-8",
    )
    (tmp_path / "dbms_config.json").write_text(
        '{"version": 1, "redis": {"connection": {"host": "127.0.0.1"}}}', encoding="utf-8"
    )
    result = CliRunner().invoke(main, ["--config", str(cfg), "--dry-run"])
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)  # a clean exit, not an uncaught error
    assert "Source 'ev': CSV file is empty (no header row)" in result.output
    assert "Traceback" not in result.output


def test_cli_rejects_the_removed_strategy_option(monkeypatch):
    from click.testing import CliRunner
    import polyglotimportcsv.cli as climod

    called = []
    monkeypatch.setattr(climod, "run_import", lambda *a, **k: called.append(1) or [])
    res = CliRunner().invoke(climod.main, [
        "--config", "data/ecommerce/import_config.json",
        "--dry-run", "--strategy", "optimized",
    ])
    assert res.exit_code == 2
    assert "No such option" in res.output and "--strategy" in res.output
    assert called == []  # nothing ran


def test_cli_does_not_pass_a_strategy_to_the_runner(monkeypatch):
    from click.testing import CliRunner
    import polyglotimportcsv.cli as climod

    captured = {}

    def fake_run_import(config_path, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(climod, "run_import", fake_run_import)
    res = CliRunner().invoke(climod.main, [
        "--config", "data/ecommerce/import_config.json", "--dry-run",
    ])
    assert res.exit_code == 0, res.output
    assert "strategy" not in captured


def test_run_import_has_no_strategy_parameter():
    import inspect
    from polyglotimportcsv.runner import run_import
    assert "strategy" not in inspect.signature(run_import).parameters


def _no_run(*args, **kwargs):
    raise AssertionError("run_import must not be called")


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


def test_cli_import_exits_one_when_only_matches_no_declared_dbms():
    result = CliRunner().invoke(main, [
        "--config", str(ECOMMERCE / "import_config.json"), "--dry-run", "--only", "postgre",
    ])
    assert result.exit_code == 1
    assert "No target DBMS to check" in result.output
    assert "--only selected postgre" in result.output


def test_cli_check_dbms_end_to_end_shows_the_start_command(monkeypatch):
    monkeypatch.setattr("polyglotimportcsv.dbms_check.probe", lambda ep, timeout=2.0: False)
    result = CliRunner().invoke(main, [
        "--config", str(ECOMMERCE / "import_config.json"),
        "--dbms-config", str(ECOMMERCE / "dbms_config_linux.json"),
        "--check-dbms", "--only", "redis",
    ])
    assert result.exit_code == 1
    assert "sudo systemctl start redis-server" in result.output
