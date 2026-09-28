"""Runner uses an injectable importer registry (mock-friendly)."""

from pathlib import Path

import pytest

from polyglotimportcsv.business_exception import BusinessException, ConfigError, DbmsUnavailableError
from polyglotimportcsv.runner import run_check, run_import

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "data" / "ecommerce" / "import_config.json"


def test_run_import_with_stub_registry():
    calls: list[str] = []

    def stub_postgres(cfg, entities, *, dry_run, create_schema, strategy="optimized"):
        calls.append("postgres")
        assert isinstance(entities, dict) and entities, "expected bound entities"
        return ["[postgres] stub"]

    registry = {"postgres": stub_postgres}
    lines = run_import(
        CFG, dry_run=True, create_schema=False, only=["postgres"], importers=registry
    )
    assert calls == ["postgres"]
    assert "[postgres] stub" in lines


def test_run_import_rejects_invalid_config_even_with_stub():
    def never_called(*a, **k):
        raise AssertionError("importer should not run if validation fails")

    bad_cfg = ROOT / "data" / "db.json"
    if not bad_cfg.is_file():
        pytest.skip("data/db.json missing")
    with pytest.raises(BusinessException):
        run_import(bad_cfg, dry_run=True, importers={"postgres": never_called})


def test_run_import_streams_when_execution_stream(monkeypatch):
    """A real (non-dry) import with execution='stream' dispatches to the
    streaming orchestrator, not the materialize importer registry."""
    captured = {}

    def fake_stream(config, base_dir, *, sink_factories, only,
                    create_schema, source_overrides, **kw):
        captured["only"] = list(only) if only else None
        captured["create_schema"] = create_schema
        return {"user_session": 8, "shopping_cart": 5}

    monkeypatch.setattr("polyglotimportcsv.runner.run_stream_import", fake_stream)

    def must_not_run(*a, **k):
        raise AssertionError("materialize importer must not run when streaming")

    lines = run_import(
        CFG, execution="stream", create_schema=False,
        only=["postgres"], importers={"postgres": must_not_run},
    )
    assert captured["only"] == ["postgres"]
    assert captured["create_schema"] is False
    assert any("user_session" in L and "8" in L for L in lines)


def test_run_import_stream_records_summary_metric(monkeypatch):
    """The stream path records a summary metric into the collector so a
    streaming import is observable and benchmarkable (peak-memory comparison
    needs at least one carrier record)."""
    from polyglotimportcsv import metrics

    def fake_stream(config, base_dir, *, sink_factories, only,
                    create_schema, source_overrides, **kw):
        return {"user_session": 8, "shopping_cart": 5}

    monkeypatch.setattr("polyglotimportcsv.runner.run_stream_import", fake_stream)

    c = metrics.MetricsCollector()
    run_import(CFG, execution="stream", only=["postgres"], collector=c)
    recs = c.to_records()
    assert recs, "stream import should record at least one metric"
    assert sum(r["rows"] for r in recs) == 13


def test_run_import_materialize_does_not_stream(monkeypatch):
    """execution='materialize' keeps the existing importer-registry path and
    never touches the streaming orchestrator."""
    def boom(*a, **k):
        raise AssertionError("stream must not run for execution=materialize")

    monkeypatch.setattr("polyglotimportcsv.runner.run_stream_import", boom)

    calls: list[str] = []

    def stub(cfg, entities, *, dry_run, create_schema, strategy="optimized"):
        calls.append("postgres")
        return ["[postgres] stub"]

    run_import(CFG, execution="materialize", create_schema=False,
               only=["postgres"], importers={"postgres": stub})
    assert calls == ["postgres"]


def test_run_import_dry_run_stays_materialize_even_if_stream(monkeypatch):
    """dry-run is a planning activity with no live connection, so it always
    uses the materialize path regardless of the default execution."""
    def boom(*a, **k):
        raise AssertionError("dry-run must not stream")

    monkeypatch.setattr("polyglotimportcsv.runner.run_stream_import", boom)

    calls: list[str] = []

    def stub(cfg, entities, *, dry_run, create_schema, strategy="optimized"):
        calls.append("postgres")
        return ["[postgres] stub"]

    run_import(CFG, execution="stream", dry_run=True,
               only=["postgres"], importers={"postgres": stub})
    assert calls == ["postgres"]


def test_run_import_rejects_unknown_execution():
    with pytest.raises(ValueError, match="execution"):
        run_import(CFG, execution="streamm", only=["postgres"])


def test_run_import_dumps_bound_entities(monkeypatch):
    calls = []

    def fake_dump(backend, entity, df, *, force=None, sample_size=None):
        calls.append((backend, entity, len(df), force, sample_size))

    monkeypatch.setattr("polyglotimportcsv.runner.dump_entity_frame", fake_dump)

    def stub(cfg, entities, *, dry_run, create_schema, strategy="optimized"):
        return ["[postgres] stub"]

    run_import(CFG, dry_run=True, only=["postgres"], importers={"postgres": stub})
    assert calls, "expected one dump call per bound entity"
    assert all(backend == "postgres" and force is None for backend, _, _, force, _ in calls)
    assert all(call[4] == 50 for call in calls)


def test_run_import_stream_passes_a_preview_to_the_orchestrator(monkeypatch, capsys):
    """The stream path shows the sample too: run_import wires an on_batch."""
    import pandas as pd

    def fake_stream(config, base_dir, *, sink_factories, only,
                    create_schema, source_overrides, on_batch=None, **kw):
        assert on_batch is not None
        on_batch("redis", "user_session", pd.DataFrame({"id": range(3)}))
        return {"user_session": 3}

    monkeypatch.setattr("polyglotimportcsv.runner.run_stream_import", fake_stream)
    run_import(CFG, execution="stream", only=["redis"], sample_size=2)
    out = capsys.readouterr().out
    assert "redis · user_session" in out
    assert "2 of 3 row(s)" in out


def _probe_answers(value, seen=None):
    def fake(endpoint, timeout=2.0):
        if seen is not None:
            seen.append(endpoint)
        return value
    return fake


def test_a_real_import_stops_before_reading_sources_when_a_dbms_is_down(monkeypatch):
    monkeypatch.setattr("polyglotimportcsv.dbms_check.probe", _probe_answers(False))

    def must_not_run(*a, **k):
        raise AssertionError("nothing may be read or written when a DBMS is down")

    monkeypatch.setattr("polyglotimportcsv.runner.load_sources", must_not_run)
    monkeypatch.setattr("polyglotimportcsv.runner.run_stream_import", must_not_run)
    with pytest.raises(DbmsUnavailableError, match=r"postgres \(down\)"):
        run_import(CFG, execution="stream", only=["postgres"])
    with pytest.raises(DbmsUnavailableError, match=r"postgres \(down\)"):
        run_import(CFG, execution="materialize", only=["postgres"],
                   importers={"postgres": must_not_run})


def test_dry_run_never_checks_the_dbms(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("dry-run must not probe")

    monkeypatch.setattr("polyglotimportcsv.dbms_check.probe", boom)
    run_import(CFG, dry_run=True, only=["postgres"],
               importers={"postgres": lambda cfg, entities, **kw: []})


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
    def must_not_probe(*a, **k):
        raise AssertionError("probe must not run when there is no target DBMS")

    monkeypatch.setattr("polyglotimportcsv.dbms_check.probe", must_not_probe)
    with pytest.raises(ConfigError, match=r"No target DBMS to check"):
        run_check(CFG, only=["postgre"])


def test_start_commands_are_never_wrapped(monkeypatch, capsys):
    """A wrapped command would carry a line break into the terminal it is pasted in."""
    monkeypatch.setattr("polyglotimportcsv.dbms_check.probe", _probe_answers(False))
    run_check(CFG, only=["redis"])  # dbms_config.json: a long docker compose line
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if "docker compose -f" in l)
    assert line.rstrip().endswith("up -d --wait redis")
