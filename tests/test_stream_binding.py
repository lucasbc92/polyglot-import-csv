import pandas as pd
import pytest
from polyglotimportcsv import stream_binding as sb
from polyglotimportcsv.business_exception import MappingError
from polyglotimportcsv.csv_reader import ColumnStats
from polyglotimportcsv.source_profile import SourceProfile
from polyglotimportcsv.sources import SOURCE_COLUMN


def _profile(name, **columns):
    """A profile whose column stats were folded from these raw values, in one chunk."""
    stats = {}
    for column, values in columns.items():
        stats[column] = ColumnStats()
        stats[column].update(pd.Series(values, dtype=str))
    return SourceProfile(name=name, declared=name, path=None, header=list(columns),
                         rows=1, stats=stats)


def test_bind_entity_takes_the_kinds_from_the_whole_file_profile():
    profiles = {"e": _profile("e", id=["1", "2"], when=["2023-01-01", "2023-01-02"])}
    ecfg = {"source": "e", "columns": {"id": {"db_type": "TEXT"}}}  # declared TEXT wins
    b = sb.bind_entity("e", ecfg, profiles)
    assert b.kinds == {"id": "integer", "when": "datetime", SOURCE_COLUMN: "string"}
    assert b.cfg["columns"]["id"]["db_type"] == "TEXT"
    assert b.source_name == "e"
    assert not {"source", "csv_columns", "auto_map"} & set(b.cfg)


def test_bind_entity_auto_maps_the_inferred_db_types():
    profiles = {"e": _profile("e", id=["1"], price=["1.5"], on=["true"], note=["x"], gap=[""])}
    b = sb.bind_entity("e", {}, profiles)  # no source: bound by the entity name
    assert {c: spec["db_type"] for c, spec in b.cfg["columns"].items()} == {
        "id": "BIGINT", "price": "NUMERIC", "on": "BOOLEAN", "note": "TEXT", "gap": "TEXT",
    }


def test_bind_entity_of_a_source_without_rows_binds_with_empty_kinds():
    profiles = {"e": SourceProfile(name="e", declared="e", path=None, header=["a", "b"],
                                   rows=0, stats={"a": ColumnStats(), "b": ColumnStats()})}
    b = sb.bind_entity("e", {"source": "e"}, profiles)
    assert b.kinds == {"a": "empty", "b": "empty", SOURCE_COLUMN: "string"}
    assert set(b.cfg["columns"]) == {"a", "b"}


def test_bind_entity_union_builds_the_superset_with_whole_file_kinds():
    profiles = {
        "a": _profile("a", id=["1", "2"], a_col=["x", "y"]),
        "b": _profile("b", id=["3.5"], when=["2023-01-01"]),
    }
    b = sb.bind_entity("act", {"source": ["a", "b"]}, profiles)
    assert list(b.kinds) == ["id", "a_col", "when", SOURCE_COLUMN]
    assert b.kinds == {"id": "float", "a_col": "string", "when": "datetime", SOURCE_COLUMN: "string"}
    assert b.source_name == "a+b"
    assert set(b.cfg["columns"]) == {"id", "a_col", "when"}


def test_bind_entity_union_preserves_declared_db_type():
    profiles = {"a": _profile("a", id=["1"]), "b": _profile("b", id=["2"])}
    ecfg = {"source": ["a", "b"], "columns": {"id": {"db_type": "TEXT"}}}  # declared wins
    b = sb.bind_entity("act", ecfg, profiles)
    assert b.cfg["columns"]["id"]["db_type"] == "TEXT"


def test_bind_entity_union_follows_the_declared_order_of_the_list():
    profiles = {"a": _profile("a", x=["1"]), "b": _profile("b", y=["1"])}
    b = sb.bind_entity("act", {"source": ["b", "a"]}, profiles)
    assert list(b.kinds) == ["y", "x", SOURCE_COLUMN] and b.source_name == "b+a"


def test_bind_entity_applies_csv_columns_and_keeps_the_resolution_rule_in_one_place():
    profiles = {"e": _profile("e", id=["1"], secret=["x"])}
    b = sb.bind_entity("e", {"source": "e", "csv_columns": ["id"]}, profiles)
    assert set(b.cfg["columns"]) == {"id"}
    with pytest.raises(MappingError, match="unknown source 'ghost'"):
        sb.bind_entity("e", {"source": "ghost"}, profiles)
    with pytest.raises(MappingError, match="declares no 'source' and no source is named after it"):
        sb.bind_entity("other", {}, profiles)
    with pytest.raises(MappingError, match="'source' list is empty"):
        sb.bind_entity("e", {"source": []}, profiles)


def test_entity_source_names():
    assert sb.entity_source_names("e", {}) == ["e"]
    assert sb.entity_source_names("e", {"source": "s"}) == ["s"]
    assert sb.entity_source_names("e", {"source": ["a", "b"]}) == ["a", "b"]
