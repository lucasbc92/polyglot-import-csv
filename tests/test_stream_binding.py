import pandas as pd
from polyglotimportcsv import stream_binding as sb
from polyglotimportcsv.sources import SOURCE_COLUMN


def test_binding_infers_kinds_and_respects_declared_db_type():
    sample = pd.DataFrame({"id": ["1", "2"], "when": ["2023-01-01", "2023-01-02"],
                           SOURCE_COLUMN: ["e", "e"]})
    ecfg = {"source": "e", "columns": {"id": {"db_type": "TEXT"}}}  # declared TEXT wins
    b = sb.bind_entity_from_sample("e", ecfg, sample, "e")
    assert b.kinds["when"] == "datetime"        # inferred
    assert b.cfg["columns"]["id"]["db_type"] == "TEXT"   # declared preserved
    assert b.kinds[SOURCE_COLUMN] == "string"


def test_union_binding_builds_superset_from_heterogeneous_samples():
    # Two sources with disjoint extra columns (multi-mode union).
    sample_a = pd.DataFrame({"id": ["1", "2"], "a_col": ["x", "y"],
                             SOURCE_COLUMN: ["a", "a"]})
    sample_b = pd.DataFrame({"id": ["3"], "when": ["2023-01-01"],
                             SOURCE_COLUMN: ["b"]})
    ecfg = {"source": ["a", "b"]}  # auto-map over the superset
    b = sb.bind_union_entity_from_samples("act", ecfg, {"a": sample_a, "b": sample_b})

    # Superset data columns follow union-list order (a's, then b's new ones),
    # with _source last -- identical to mapping_resolver._union_source.
    assert list(b.kinds.keys()) == ["id", "a_col", "when", SOURCE_COLUMN]
    assert b.kinds[SOURCE_COLUMN] == "string"
    assert b.kinds["when"] == "datetime"  # inferred across the ""-filled union
    assert b.source_name == "a+b"
    # Auto-map covers the superset data columns only (_source is a pseudo-column
    # carried in kinds, not an auto-mapped data column) -- as in materialize.
    assert set(b.cfg["columns"]) == {"id", "a_col", "when"}


def test_union_binding_preserves_declared_db_type():
    sample_a = pd.DataFrame({"id": ["1"], SOURCE_COLUMN: ["a"]})
    sample_b = pd.DataFrame({"id": ["2"], SOURCE_COLUMN: ["b"]})
    ecfg = {"source": ["a", "b"], "columns": {"id": {"db_type": "TEXT"}}}  # declared wins
    b = sb.bind_union_entity_from_samples("act", ecfg, {"a": sample_a, "b": sample_b})
    assert b.cfg["columns"]["id"]["db_type"] == "TEXT"
