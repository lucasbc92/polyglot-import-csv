"""Runner uses an injectable importer registry (mock-friendly)."""

from pathlib import Path

import pytest

from polyglotimportcsv.business_exception import BusinessException
from polyglotimportcsv.runner import run_import

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

    def fake_dump(backend, entity, df, *, force=None):
        calls.append((backend, entity, len(df), force))

    monkeypatch.setattr("polyglotimportcsv.runner.dump_entity_frame", fake_dump)

    def stub(cfg, entities, *, dry_run, create_schema, strategy="optimized"):
        return ["[postgres] stub"]

    run_import(CFG, dry_run=True, only=["postgres"], importers={"postgres": stub})
    assert calls, "expected one dump call per bound entity"
    assert all(backend == "postgres" and force is None for backend, _, _, force in calls)
