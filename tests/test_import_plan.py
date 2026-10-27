"""The import plan: what the first read of the files decides before anything is written.

It reads only the sources the selected DBMS use, sizes the blocks of each from a memory
budget, profiles every source over the whole file, and binds each entity from those
profiles, so no later stage re-derives a type from a sample.
"""

import pytest

from polyglotimportcsv.business_exception import MappingError, SourceError
from polyglotimportcsv.import_plan import (
    DEFAULT_BATCH_SIZE,
    MAX_BATCH_SIZE,
    MIN_BATCH_SIZE,
    plan_import,
)
from polyglotimportcsv.sources import SOURCE_COLUMN


def _write_csv(path, header, rows):
    path.write_text(",".join(header) + "\n" +
                    "".join(",".join(str(c) for c in r) + "\n" for r in rows),
                    encoding="utf-8")


def _entities(**by_name):
    return {"entities": by_name}


def test_batch_size_constants():
    assert (MIN_BATCH_SIZE, DEFAULT_BATCH_SIZE, MAX_BATCH_SIZE) == (1024, 1024, 8192)


def test_only_reads_the_sources_the_selected_dbms_use(tmp_path):
    _write_csv(tmp_path / "cart.csv", ["id"], [(1,), (2,)])  # stock.csv does not even exist
    cfg = {
        "sources": {"cart": "cart.csv", "stock": "stock.csv"},
        "postgres": _entities(t={"source": "stock"}),
        "redis": _entities(c={"source": "cart"}),
    }
    plan = plan_import(cfg, tmp_path, dbms_names=["redis"])
    assert set(plan.sources_cfg) == {"cart"} and "stock" not in plan.profiles
    assert set(plan.rows_per_chunk) == {"cart"}
    assert set(plan.bindings) == {"redis"} and set(plan.bindings["redis"]) == {"c"}


def test_the_plan_keeps_what_it_was_asked(tmp_path):
    _write_csv(tmp_path / "s.csv", ["id"], [(1,)])
    cfg = {"sources": {"s": "s.csv"}, "postgres": _entities(s={})}
    plan = plan_import(cfg, tmp_path, dbms_names=["postgres"], batch_size=77)
    assert plan.config is cfg and plan.base_dir == tmp_path
    assert plan.dbms_names == ["postgres"] and plan.batch_size == 77 and plan.overrides == {}


def test_a_source_override_is_profiled_in_place_of_the_declared_file(tmp_path):
    _write_csv(tmp_path / "other.csv", ["k"], [(1,), (2,), (3,)])
    cfg = {"sources": {"s": "missing.csv"}, "postgres": _entities(t={"source": "s"})}
    plan = plan_import(cfg, tmp_path, dbms_names=["postgres"],
                       overrides={"s": str(tmp_path / "other.csv")})
    assert plan.profiles["s"].path == tmp_path / "other.csv" and plan.profiles["s"].rows == 3
    assert plan.overrides == {"s": str(tmp_path / "other.csv")}


def test_an_entity_with_no_source_reads_the_source_named_after_it(tmp_path):
    _write_csv(tmp_path / "t.csv", ["id"], [(1,)])
    _write_csv(tmp_path / "unused.csv", ["id"], [(1,)])
    cfg = {"sources": {"t": "t.csv", "unused": "unused.csv"}, "postgres": _entities(t={})}
    plan = plan_import(cfg, tmp_path, dbms_names=["postgres"])
    assert set(plan.sources_cfg) == {"t"}
    assert plan.bindings["postgres"]["t"].source_name == "t"


def test_an_origin_name_pulls_in_every_combined_source_but_not_the_other_plain_ones(tmp_path):
    _write_csv(tmp_path / "cart.csv", ["id"], [(1,)])
    _write_csv(tmp_path / "j.csv", ["action", "id"], [("stock", 1), ("purchase", 2)])
    cfg = {
        "sources": {"cart": "cart.csv", "other": "absent.csv", "e": {"file": "j.csv"}},
        "postgres": _entities(s={"source": "stock"}, c={"source": "cart"}),
    }
    plan = plan_import(cfg, tmp_path, dbms_names=["postgres"])
    assert list(plan.sources_cfg) == ["cart", "e"]
    assert set(plan.profiles) == {"cart", "stock", "purchase"}
    assert plan.profiles["stock"].declared == "e"


def test_only_plain_names_leave_the_combined_sources_alone(tmp_path):
    _write_csv(tmp_path / "cart.csv", ["id"], [(1,)])  # j.csv does not exist
    cfg = {
        "sources": {"cart": "cart.csv", "e": {"file": "j.csv"}},
        "postgres": _entities(c={"source": "cart"}),
    }
    assert set(plan_import(cfg, tmp_path, dbms_names=["postgres"]).sources_cfg) == {"cart"}


def test_unknown_origin_lists_the_origins_found(tmp_path):
    _write_csv(tmp_path / "j.csv", ["action", "id"], [("stock", 1), ("purchase", 2)])
    cfg = {
        "sources": {"e": {"file": "j.csv"}},
        "redis": _entities(t={"source": "purchse"}),
    }
    with pytest.raises(MappingError, match=r"purchse.*purchase.*stock") as exc:
        plan_import(cfg, tmp_path, dbms_names=["redis"])
    assert "'t'" in str(exc.value) and "redis" in str(exc.value)


def test_a_union_with_an_unknown_name_is_reported_like_any_other(tmp_path):
    _write_csv(tmp_path / "a.csv", ["id"], [(1,)])
    cfg = {"sources": {"a": "a.csv"}, "postgres": _entities(u={"source": ["a", "ghost"]})}
    with pytest.raises(MappingError, match="ghost"):
        plan_import(cfg, tmp_path, dbms_names=["postgres"])


def test_a_missing_file_is_a_source_error(tmp_path):
    cfg = {"sources": {"s": "nope.csv"}, "postgres": _entities(t={"source": "s"})}
    with pytest.raises(SourceError, match="CSV file not found"):
        plan_import(cfg, tmp_path, dbms_names=["postgres"])


def test_entity_batch_is_capped_by_rows_per_chunk(tmp_path):
    _write_csv(tmp_path / "s.csv", ["a", "b", "c"], [(i, f"x{i}", f"y{i}") for i in range(2000)])
    cfg = {"sources": {"s": "s.csv"}, "postgres": _entities(t={"source": "s"})}
    plan = plan_import(cfg, tmp_path, dbms_names=["postgres"], chunk_mb=0.01, batch_size=10_000)
    assert plan.entity_batch("postgres", "t") == plan.rows_per_chunk["s"] < 10_000


def test_entity_batch_is_the_batch_size_when_a_chunk_holds_more(tmp_path):
    _write_csv(tmp_path / "s.csv", ["a"], [(i,) for i in range(50)])
    cfg = {"sources": {"s": "s.csv"}, "postgres": _entities(t={"source": "s"})}
    plan = plan_import(cfg, tmp_path, dbms_names=["postgres"], batch_size=1024)
    assert plan.rows_per_chunk["s"] > 1024 and plan.entity_batch("postgres", "t") == 1024


def test_a_union_batch_follows_its_narrowest_source(tmp_path):
    _write_csv(tmp_path / "narrow.csv", ["id"], [(i,) for i in range(500)])
    wide = [f"c{j}" for j in range(40)]
    _write_csv(tmp_path / "wide.csv", wide, [[f"value-{i}-{j}" for j in range(40)] for i in range(500)])
    cfg = {
        "sources": {"narrow": "narrow.csv", "wide": "wide.csv"},
        "postgres": _entities(u={"source": ["narrow", "wide"]}, n={"source": "narrow"}),
    }
    plan = plan_import(cfg, tmp_path, dbms_names=["postgres"], chunk_mb=0.05, batch_size=10_000)
    assert plan.rows_per_chunk["wide"] < plan.rows_per_chunk["narrow"] < 10_000
    assert plan.entity_batch("postgres", "u") == plan.rows_per_chunk["wide"]
    assert plan.entity_batch("postgres", "n") == plan.rows_per_chunk["narrow"]


def test_the_batch_of_a_combined_origin_follows_the_chunk_of_its_declared_file(tmp_path):
    _write_csv(tmp_path / "j.csv", ["action", "id"], [("stock", i) for i in range(300)])
    cfg = {"sources": {"e": {"file": "j.csv"}}, "postgres": _entities(s={"source": "stock"})}
    plan = plan_import(cfg, tmp_path, dbms_names=["postgres"], chunk_mb=0.002, batch_size=10_000)
    assert plan.entity_batch("postgres", "s") == plan.rows_per_chunk["e"] < 300


def test_union_binding_uses_whole_file_kinds(tmp_path):
    # `v` is an integer in A and in the first rows of B; a float only turns up late in B,
    # many blocks past the first one a sample would have seen.
    _write_csv(tmp_path / "a.csv", ["v"], [(i,) for i in range(100)])
    _write_csv(tmp_path / "b.csv", ["v"], [(i,) for i in range(600)] + [("1.5",)])
    cfg = {"sources": {"a": "a.csv", "b": "b.csv"}, "postgres": _entities(u={"source": ["a", "b"]})}
    plan = plan_import(cfg, tmp_path, dbms_names=["postgres"], chunk_mb=0.002)
    assert plan.rows_per_chunk["b"] < 600
    binding = plan.bindings["postgres"]["u"]
    assert binding.kinds == {"v": "float", SOURCE_COLUMN: "string"}
    assert binding.cfg["columns"]["v"]["db_type"] == "NUMERIC"
    assert binding.source_name == "a+b"


def test_a_late_value_changes_the_single_source_binding_too(tmp_path):
    _write_csv(tmp_path / "s.csv", ["flag"], [("true",), ("false",)] * 300 + [("maybe",)])
    cfg = {"sources": {"s": "s.csv"}, "postgres": _entities(t={"source": "s"})}
    plan = plan_import(cfg, tmp_path, dbms_names=["postgres"], chunk_mb=0.002)
    assert plan.bindings["postgres"]["t"].kinds["flag"] == "string"


def test_every_selected_dbms_gets_its_own_bindings_from_the_same_profiles(tmp_path):
    _write_csv(tmp_path / "s.csv", ["id", "v"], [(1, "x"), (2, "y")])
    cfg = {
        "sources": {"s": "s.csv"},
        "postgres": _entities(t={"source": "s", "columns": {"id": {"db_type": "TEXT"}}}),
        "mongodb": _entities(t={"source": "s"}),
        "redis": _entities(ignored={"source": "ghost"}),
    }
    plan = plan_import(cfg, tmp_path, dbms_names=["postgres", "mongodb"])
    assert set(plan.bindings) == {"postgres", "mongodb"}
    assert plan.bindings["postgres"]["t"].cfg["columns"] == {"id": {"db_type": "TEXT"}}
    assert plan.bindings["mongodb"]["t"].cfg["columns"]["id"]["db_type"] == "BIGINT"


def test_a_source_without_rows_still_binds(tmp_path):
    (tmp_path / "s.csv").write_text("a,b\n", encoding="utf-8")
    cfg = {"sources": {"s": "s.csv"}, "postgres": _entities(t={"source": "s"})}
    plan = plan_import(cfg, tmp_path, dbms_names=["postgres"])
    assert plan.profiles["s"].rows == 0
    assert set(plan.bindings["postgres"]["t"].cfg["columns"]) == {"a", "b"}
    assert plan.entity_batch("postgres", "t") == min(DEFAULT_BATCH_SIZE, plan.rows_per_chunk["s"])
