"""run_import in three reads: headers, DBMS check, inference, validation, then the write.

Sinks are fakes injected through ``sink_factories``; the DBMS check is up by default
(conftest) and patched where a test needs it down.
"""

import inspect
import json
import logging
import re
from pathlib import Path

import pandas as pd
import pytest

from polyglotimportcsv import runner
from polyglotimportcsv.business_exception import (
    ConfigError,
    DataValidationError,
    DbmsUnavailableError,
    MappingError,
)
from polyglotimportcsv.metrics import MetricsCollector
from polyglotimportcsv.runner import run_check, run_import
from polyglotimportcsv.stream_runner import StreamCounts

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "data" / "ecommerce" / "import_config.json"

_CONNECTIONS = {
    "postgres": {"connection": {"host": "127.0.0.1"}},
    "redis": {"connection": {"host": "127.0.0.1"}},
}


def _write_csv(path, header, rows):
    path.write_text(
        ",".join(header) + "\n" + "".join(",".join(str(c) for c in r) + "\n" for r in rows),
        encoding="utf-8",
    )


def _config_file(tmp_path, config):
    """Write ``config`` and a dbms_config.json for its DBMS; return the config path."""
    dbms = {name: conn for name, conn in _CONNECTIONS.items() if name in config}
    (tmp_path / "dbms_config.json").write_text(
        json.dumps({"version": 1, **dbms}), encoding="utf-8"
    )
    path = tmp_path / "import_config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def _events(tmp_path, n=10, bad_date_at=None):
    """``n`` events in ev.csv, read by a PostgreSQL entity and a Redis one.

    ``bad_date_at`` puts an impossible date on that row: the column is still a
    datetime (one bad value in ten is under the 15% the inference tolerates), so
    the value does not convert and the validation read reports it.
    """
    when = [f"2023-01-{1 + i % 28:02d}" for i in range(n)]
    if bad_date_at is not None:
        when[bad_date_at] = "2023-02-30"
    _write_csv(tmp_path / "ev.csv", ["id", "when"], list(zip(range(n), when)))
    return _config_file(tmp_path, {
        "sources": {"ev": "ev.csv"},
        "postgres": {"entities": {"events": {
            "source": "ev", "columns": {"id": {"is_key": True}, "when": {}},
        }}},
        "redis": {"entities": {"sessions": {
            "source": "ev", "columns": {"id": {"is_key": True}},
        }}},
    })


class _FakeSink:
    def __init__(self, dbms, written):
        self.dbms = dbms
        self.written = written

    def create_schema(self):
        pass

    def ensure_partition(self, partition_name, binding):
        pass

    def write_batch(self, partition_name, binding, batch):
        self.written.append((self.dbms, partition_name, len(batch)))
        return len(batch)

    def close(self):
        pass


def _factories(written=None, built=None):
    """A fake sink factory per DBMS; ``built`` collects every DBMS a sink is built for."""
    written = [] if written is None else written

    def factory(dbms):
        def build(backend_cfg):
            if built is not None:
                built.append(dbms)
            return _FakeSink(dbms, written)
        return build

    return {dbms: factory(dbms) for dbms in ("postgres", "mongodb", "cassandra", "redis", "neo4j")}


def _must_not_run(*args, **kwargs):
    raise AssertionError("must not run")


def _probe_answers(value, seen=None):
    def fake(endpoint, timeout=2.0):
        if seen is not None:
            seen.append(endpoint)
        return value
    return fake


def test_run_import_takes_chunk_and_batch_sizes_not_importers_or_execution():
    params = inspect.signature(run_import).parameters
    assert "importers" not in params and "execution" not in params
    assert params["chunk_size_mb"].default == 8
    assert params["batch_size"].default == 1024


def test_a_validation_error_stops_before_any_sink_is_built(tmp_path, capsys):
    cfg = _events(tmp_path, bad_date_at=3)
    built = []
    message = "Data validation failed: 1 problem(s) in 1 group(s); nothing was written."
    with pytest.raises(DataValidationError, match=re.escape(message)):
        run_import(cfg, sink_factories=_factories(built=built))
    assert built == []
    out = capsys.readouterr().out
    assert "Data validation problems" in out
    assert "not_convertible" in out and "2023-02-30" in out


def test_steps_run_in_order(tmp_path, monkeypatch, capsys):
    cfg = _events(tmp_path)
    calls = []

    def spy(label, real):
        def wrapper(*args, **kwargs):
            calls.append((label, kwargs.get("on_batch", "-")))
            return real(*args, **kwargs)
        return wrapper

    for name, label in [
        ("read_source_headers", "headers"), ("validate_headers", "mappings"),
        ("_require_dbms", "dbms"), ("plan_import", "infer"),
        ("validate_data", "validate"), ("run_stream_import", "write"),
    ]:
        monkeypatch.setattr(runner, name, spy(label, getattr(runner, name)))

    run_import(cfg, sink_factories=_factories())

    assert [label for label, _ in calls] == [
        "headers", "mappings", "dbms", "infer", "validate", "write",
    ]
    on_batch = dict(calls)
    assert on_batch["validate"] is None  # the data display hangs off the write only
    assert on_batch["write"] is not None
    out = capsys.readouterr().out
    labels = ["Load config", "Check sources", "Validate mappings", "Check DBMS",
              "Infer types", "Validate data", "Write"]
    positions = [out.index(f"→ {label}") for label in labels]
    assert positions == sorted(positions)
    assert "mode: import" in out and "execution" not in out


def test_header_error_stops_before_the_dbms_check(tmp_path, monkeypatch):
    _write_csv(tmp_path / "ev.csv", ["id"], [(1,)])
    cfg = _config_file(tmp_path, {
        "sources": {"ev": "ev.csv"},
        "postgres": {"entities": {"events": {
            "source": "ev", "columns": {"id": {"is_key": True}, "missing": {}},
        }}},
    })
    monkeypatch.setattr(runner, "_require_dbms", _must_not_run)
    monkeypatch.setattr(runner, "plan_import", _must_not_run)
    with pytest.raises(MappingError, match="unknown column: missing"):
        run_import(cfg, sink_factories=_factories())


def test_dry_run_reads_the_data_and_never_checks_the_dbms(tmp_path, monkeypatch):
    monkeypatch.setattr("polyglotimportcsv.dbms_check.probe", _must_not_run)
    monkeypatch.setattr(runner, "_require_dbms", _must_not_run)
    monkeypatch.setattr(runner, "run_stream_import", _must_not_run)

    run_import(CFG, dry_run=True, only=["postgres"])

    cfg = _events(tmp_path, bad_date_at=3)
    with pytest.raises(DataValidationError, match="nothing was written"):
        run_import(cfg, dry_run=True)


def test_dry_run_prints_counts_per_dbms(tmp_path, capsys):
    cfg = _events(tmp_path, n=10)

    lines = run_import(cfg, dry_run=True, sample_size=2)

    assert lines == ["[postgres] events: 10 row(s)", "[redis] sessions: 10 row(s)"]
    out = capsys.readouterr().out
    for line in lines:
        assert line in out
    assert "mode: dry-run" in out
    assert "Finished dry-run — nothing was written" in out
    # The sample is that of the validation read: nothing is written in a dry-run.
    assert "postgres · events: 2 of 10 row(s)" in out


def test_zero_row_entity_warns_and_imports(tmp_path, caplog):
    _write_csv(tmp_path / "ev.csv", ["id", "label"], [(1, "a"), (2, "b")])
    _write_csv(tmp_path / "none.csv", ["id", "label"], [])  # header only
    cfg = _config_file(tmp_path, {
        "sources": {"ev": "ev.csv", "none": "none.csv"},
        "postgres": {"entities": {
            "events": {"source": "ev", "columns": {"id": {"is_key": True}, "label": {}}},
            "nothing": {"source": "none", "columns": {"id": {"is_key": True}, "label": {}}},
        }},
    })
    written = []

    with caplog.at_level(logging.WARNING, logger="polyglotimportcsv.runner"):
        lines = run_import(cfg, sink_factories=_factories(written=written))

    assert "entity postgres/nothing bound to 0 row(s)" in caplog.text
    assert "events bound to 0" not in caplog.text
    assert lines == ["[postgres] events: 2 row(s)"]
    assert written == [("postgres", "events", 2)]


def test_unused_origin_is_noted(tmp_path, capsys):
    _write_csv(tmp_path / "all.csv", ["action", "id"], [
        ("a", 1), ("b", 2), ("c", 3), ("c", 4),
    ])
    cfg = _config_file(tmp_path, {
        "sources": {"all": {"file": "all.csv", "origin_column": True}},
        "postgres": {"entities": {
            "a": {"columns": {"id": {"is_key": True}}},
            "bs": {"source": "b", "columns": {"id": {"is_key": True}}},
        }},
    })

    run_import(cfg, dry_run=True)

    out = capsys.readouterr().out
    assert "origin 'c' (2 row(s)) feeds no entity" in out
    assert "origin 'a'" not in out and "origin 'b'" not in out


def test_count_mismatch_warns_without_failing(tmp_path, monkeypatch, caplog):
    cfg = _events(tmp_path, n=10)
    real = runner.validate_data

    def one_more(plan, **kwargs):
        report, counts = real(plan, **kwargs)
        counts.written["postgres"]["events"] += 1
        return report, counts

    monkeypatch.setattr(runner, "validate_data", one_more)
    with caplog.at_level(logging.WARNING):
        lines = run_import(cfg, sink_factories=_factories())

    assert lines == ["[postgres] events: 10 row(s)", "[redis] sessions: 10 row(s)"]
    warnings = [r.getMessage() for r in caplog.records if "validation read" in r.getMessage()]
    assert warnings == [
        "postgres · events: 10 row(s) written, but the validation read counted 11",
    ]


def test_metrics_have_infer_validate_and_one_write_per_dbms(tmp_path):
    cfg = _events(tmp_path, n=10)
    collector = MetricsCollector()

    run_import(cfg, sink_factories=_factories(), collector=collector)

    assert [(m.backend, m.entity, m.phase, m.rows) for m in collector.entries()] == [
        ("(sources)", "*", "infer", 10),
        ("(all)", "*", "validate", 10),
        ("postgres", "*", "write", 10),
        ("redis", "*", "write", 10),
    ]
    assert all(m.seconds >= 0 for m in collector.entries())


def test_chunk_and_batch_sizes_reach_the_plan(tmp_path, monkeypatch):
    cfg = _events(tmp_path)
    seen = {}
    real = runner.plan_import

    def spy(*args, **kwargs):
        seen.update(chunk_mb=kwargs["chunk_mb"], batch_size=kwargs["batch_size"])
        return real(*args, **kwargs)

    monkeypatch.setattr(runner, "plan_import", spy)
    run_import(cfg, dry_run=True, chunk_size_mb=16, batch_size=2048)
    assert seen == {"chunk_mb": 16, "batch_size": 2048}


def test_the_write_does_not_repeat_the_cast_warnings_of_the_validation_read(tmp_path, caplog):
    qty = [str(i) for i in range(10)]
    qty[4] = "3.0"  # integral, so the column is integer; int("3.0") fails and the text stays
    _write_csv(tmp_path / "ev.csv", ["id", "qty"], list(zip(range(10), qty)))
    cfg = _config_file(tmp_path, {
        "sources": {"ev": "ev.csv"},
        # qty is not mapped: its cast fallback is a warning, not a validation error
        "postgres": {"entities": {"events": {"source": "ev", "columns": {"id": {"is_key": True}}}}},
    })

    with caplog.at_level(logging.WARNING, logger="polyglotimportcsv.casting"):
        run_import(cfg, sink_factories=_factories())

    cast = [r.getMessage() for r in caplog.records if r.name == "polyglotimportcsv.casting"]
    assert cast == ["column 'qty': 1 value(s) could not be cast to integer and stayed text"]
    assert logging.getLogger("polyglotimportcsv.casting").filters == []


def test_a_real_import_stops_before_reading_data_when_a_dbms_is_down(monkeypatch):
    monkeypatch.setattr("polyglotimportcsv.dbms_check.probe", _probe_answers(False))
    monkeypatch.setattr(runner, "plan_import", _must_not_run)
    monkeypatch.setattr(runner, "validate_data", _must_not_run)
    monkeypatch.setattr(runner, "run_stream_import", _must_not_run)
    with pytest.raises(DbmsUnavailableError, match=r"postgres \(down\)"):
        run_import(CFG, only=["postgres"], sink_factories=_factories())


def test_the_write_passes_a_preview_to_the_orchestrator(monkeypatch, capsys):
    """The data display hangs off the write: run_import wires an on_batch."""
    def fake_stream(plan, *, sink_factories, create_schema, on_batch=None, collector=None):
        assert on_batch is not None
        on_batch("redis", "user_session", pd.DataFrame({"id": range(3)}))
        return StreamCounts(written={"redis": {"user_session": 3}},
                            entity_rows={"redis": {"user_session": 3}})

    monkeypatch.setattr(runner, "run_stream_import", fake_stream)
    run_import(CFG, only=["redis"], sample_size=2)
    out = capsys.readouterr().out
    assert "redis · user_session" in out
    assert "2 of 3 row(s)" in out


def test_run_check_targets_follow_only(monkeypatch):
    seen = []
    monkeypatch.setattr("polyglotimportcsv.dbms_check.probe", _probe_answers(True, seen))
    report = run_check(CFG, only=["redis"])
    assert [s.dbms for s in report.statuses] == ["redis"]
    assert seen == [("127.0.0.1", 6379)]
    assert report.ok


def test_run_check_prints_the_table_and_the_start_command(monkeypatch, capsys):
    monkeypatch.setattr("polyglotimportcsv.dbms_check.probe", _probe_answers(False))
    linux = CFG.with_name("dbms_config_linux.json")
    report = run_check(CFG, dbms_config_path=linux, only=["redis", "neo4j"])
    out = capsys.readouterr().out
    assert not report.ok
    assert "Check DBMS" in out
    assert "127.0.0.1:6379" in out
    assert "To start the DBMS that are down, run in a terminal:" in out
    assert "sudo systemctl start redis-server" in out
    assert "sudo systemctl start neo4j" in out
    assert "administrator terminal or sudo" in out


def test_run_check_raises_when_only_matches_no_declared_dbms(monkeypatch):
    monkeypatch.setattr("polyglotimportcsv.dbms_check.probe", _must_not_run)
    with pytest.raises(ConfigError, match=r"No target DBMS to check"):
        run_check(CFG, only=["postgre"])


def test_start_commands_are_never_wrapped(monkeypatch, capsys):
    """A wrapped command would carry a line break into the terminal it is pasted in."""
    monkeypatch.setattr("polyglotimportcsv.dbms_check.probe", _probe_answers(False))
    run_check(CFG, only=["redis"])  # dbms_config.json: a long docker compose line
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if "docker compose -f" in l)
    assert line.rstrip().endswith("up -d --wait redis")
