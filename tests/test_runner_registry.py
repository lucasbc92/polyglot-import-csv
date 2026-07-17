"""Runner uses an injectable importer registry (mock-friendly)."""

from pathlib import Path

import pytest

from polyglotimportcsv.business_exception import BusinessException
from polyglotimportcsv.runner import run_import

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "data" / "ecommerce" / "import_config.json"


@pytest.mark.xfail(reason="example migrates in Task 13", strict=False)
def test_run_import_with_stub_registry():
    calls: list[str] = []

    def stub_postgres(cfg, entities, *, dry_run, create_schema):
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
