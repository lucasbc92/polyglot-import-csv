"""Named source loading: per-entity files, combined files, collisions."""

from pathlib import Path

import pytest

from polyglotimportcsv.business_exception import SourceError
from polyglotimportcsv.sources import SOURCE_COLUMN, load_sources


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_file_source_gets_constant_source_column(tmp_path):
    _write(tmp_path, "stock.csv", "product_id,price\n1,10.5\n2,20\n")
    reg = load_sources({"stock": "stock.csv"}, tmp_path)
    sd = reg["stock"]
    assert sd.file_header == ["product_id", "price"]
    assert list(sd.df[SOURCE_COLUMN]) == ["stock", "stock"]
    assert sd.kinds["product_id"] == "integer"
    assert sd.kinds[SOURCE_COLUMN] == "string"


def test_combined_source_slices_by_column_zero(tmp_path):
    _write(
        tmp_path,
        "join.csv",
        "action,user_id,product_id\nstock,u1,1\npurchase,u2,2\nstock,u3,3\n",
    )
    reg = load_sources(
        {"eventos": {"file": "join.csv", "origin_column": True}}, tmp_path
    )
    # Whole-file source keeps every row; origin values become _source.
    assert sorted(reg) == ["eventos", "purchase", "stock"]
    assert list(reg["eventos"].df[SOURCE_COLUMN]) == ["stock", "purchase", "stock"]
    # Slices: origin column consumed, _source constant, data columns shared.
    assert reg["stock"].file_header == ["user_id", "product_id"]
    assert len(reg["stock"].df) == 2
    assert len(reg["purchase"].df) == 1
    assert list(reg["purchase"].df["user_id"]) == ["u2"]


def test_collision_between_declared_name_and_origin_value(tmp_path):
    _write(tmp_path, "join.csv", "action,x\nstock,1\n")
    _write(tmp_path, "stock.csv", "x\n2\n")
    with pytest.raises(SourceError, match="collision"):
        load_sources(
            {
                "stock": "stock.csv",
                "eventos": {"file": "join.csv", "origin_column": True},
            },
            tmp_path,
        )


def test_missing_file_raises_source_error(tmp_path):
    with pytest.raises(SourceError, match="not found"):
        load_sources({"stock": "nope.csv"}, tmp_path)


def test_empty_origin_value_raises(tmp_path):
    _write(tmp_path, "join.csv", "action,x\n,1\n")
    with pytest.raises(SourceError, match="empty origin"):
        load_sources({"e": {"file": "join.csv", "origin_column": True}}, tmp_path)


def test_override_replaces_path(tmp_path):
    _write(tmp_path, "real.csv", "a\n1\n")
    reg = load_sources({"stock": "nope.csv"}, tmp_path, overrides={"stock": str(tmp_path / "real.csv")})
    assert len(reg["stock"].df) == 1


def test_unknown_override_name_raises(tmp_path):
    _write(tmp_path, "stock.csv", "a\n1\n")
    with pytest.raises(SourceError, match="stok"):
        load_sources(
            {"stock": "stock.csv"}, tmp_path, overrides={"stok": "big.csv"}
        )
