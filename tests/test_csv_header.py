"""The first line of every CSV is its header: there is no header detection.

The report (§4.2.1.1) states this requirement; these tests pin the behavior it
describes.
"""

from pathlib import Path

import pytest

from polyglotimportcsv.business_exception import MappingError
from polyglotimportcsv.import_plan import plan_import
from polyglotimportcsv.mapping_resolver import resolve_backend_entities
from polyglotimportcsv.sources import load_sources
from polyglotimportcsv.stream_runner import run_single_pass
from polyglotimportcsv.validation import validate_backend_entities

# Same columns as ecommerce_stock.csv would have, but without the header line.
HEADERLESS = "1,Phone,10\n2,Laptop,5\n3,Tablet,7\n"


def _write(tmp_path: Path) -> None:
    (tmp_path / "stock.csv").write_text(HEADERLESS, encoding="utf-8")


class _NullSink:
    def ensure_partition(self, partition_name, binding):
        pass

    def write_batch(self, partition_name, binding, batch):
        return len(batch)

    def close(self):
        pass


def test_stream_takes_the_first_data_row_as_the_header(tmp_path):
    _write(tmp_path)
    cfg = {"sources": {"stock": "stock.csv"}, "postgres": {"entities": {"stock": {}}}}
    plan = plan_import(cfg, tmp_path, dbms_names=["postgres"])
    assert plan.profiles["stock"].header == ["1", "Phone", "10"]
    counts = run_single_pass(plan, {"postgres": _NullSink()})
    assert counts.entity_rows["postgres"]["stock"] == 2  # the first row is not imported


def test_a_column_mapped_by_name_is_not_found_without_a_header(tmp_path):
    _write(tmp_path)
    sources = load_sources({"stock": "stock.csv"}, tmp_path)
    bcfg = {"entities": {"stock": {"columns": {"product_id": {"is_key": True}}}}}
    with pytest.raises(MappingError, match="product_id"):
        bound = resolve_backend_entities(bcfg, sources, {})
        validate_backend_entities("postgres", bcfg, bound)


def test_automatic_mapping_imports_without_a_header_and_loses_the_first_row(tmp_path):
    # No error to catch the missing header: the first row's values become the
    # column names, and that row is not imported.
    _write(tmp_path)
    sources = load_sources({"stock": "stock.csv"}, tmp_path)
    bcfg = {"entities": {"stock": {}}}
    bound = resolve_backend_entities(bcfg, sources, {})
    validate_backend_entities("postgres", bcfg, bound)
    stock = bound["stock"]
    assert len(stock.df) == 2
    assert list(stock.cfg["columns"]) == ["1", "Phone", "10"]
