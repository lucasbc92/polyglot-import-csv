import dataclasses

import pandas as pd
import pytest

from polyglotimportcsv import stream_runner as sr
from polyglotimportcsv.business_exception import MappingError
from polyglotimportcsv.import_plan import plan_import
from polyglotimportcsv.metrics import MetricsCollector
from polyglotimportcsv.sources import SOURCE_COLUMN


def _write_csv(path, header, rows):
    path.write_text(
        ",".join(header) + "\n"
        + "\n".join(",".join(str(c) for c in r) for r in rows) + "\n",
        encoding="utf-8",
    )


class _FakeSink:
    """Records every call the orchestrator makes, without touching a real DB."""

    def __init__(self, backend_cfg=None):
        self.backend_cfg = backend_cfg
        self.schema_calls = 0
        self.ensure_calls = []  # partition names, in call order (may repeat if buggy)
        self.batches = {}  # partition -> [len(batch), ...] in flush order
        self.frames = {}   # partition -> [DataFrame, ...] as received
        self.closed = False
        self.calls = []          # ordered log of ("node", partition) / ("rel", rname)
        self.rel_rows = {}       # rname -> total rows received
        self.rel_frames = {}     # rname -> [DataFrame, ...] as received

    def create_schema(self):
        self.schema_calls += 1

    def ensure_partition(self, partition_name, binding):
        self.ensure_calls.append(partition_name)

    def write_batch(self, partition_name, binding, batch):
        self.calls.append(("node", partition_name))
        self.batches.setdefault(partition_name, []).append(len(batch))
        self.frames.setdefault(partition_name, []).append(batch.copy())
        return len(batch)

    def write_relationships(self, rname, rspec, from_binding, to_binding, batch):
        self.calls.append(("rel", rname))
        self.rel_rows[rname] = self.rel_rows.get(rname, 0) + len(batch)
        self.rel_frames.setdefault(rname, []).append(batch.copy())
        return len(batch)

    def close(self):
        self.closed = True


def _build_config(tmp_path):
    """A 2500-row single-entity source (batch-boundary test) plus a filtered,
    'each'-split source (partition test), mirroring data/ecommerce/import_config.json's
    shape: top-level 'sources' + one DBMS block of {"entities": {ename: ecfg}}."""
    items_rows = [(i, f"v{i}") for i in range(2500)]
    _write_csv(tmp_path / "items.csv", ["id", "value"], items_rows)

    events_rows = (
        [(i, "north", "keep") for i in range(10)]
        + [(10 + i, "north", "drop") for i in range(5)]
        + [(15 + i, "south", "keep") for i in range(5)]
    )
    _write_csv(tmp_path / "events.csv", ["id", "region", "note"], events_rows)

    config = {
        "sources": {
            "items": "items.csv",
            "events": "events.csv",
        },
        "postgres": {
            "entities": {
                "items": {"source": "items"},
                "events": {
                    "source": "events",
                    "filters": [
                        {"column": "note", "operator": "==", "value": "keep"},
                        {"column": "region", "operator": "each"},
                    ],
                },
            }
        },
    }
    return config


def _batches_plan(tmp_path):
    """Chunks of 1000 rows and batches of 800, so batches span chunk boundaries."""
    plan = plan_import(_build_config(tmp_path), tmp_path, dbms_names=["postgres"], batch_size=800)
    return dataclasses.replace(plan, rows_per_chunk={"items": 1000, "events": 1000})


def test_stream_import_batches_flushes_and_partitions(tmp_path):
    fake = _FakeSink()

    counts = sr.run_stream_import(
        _batches_plan(tmp_path), sink_factories={"postgres": lambda cfg: fake}
    )

    # (a) rows written per partition equal the CSV row counts after filters
    assert counts.written == {"postgres": {"items": 2500, "events_north": 10, "events_south": 5}}
    assert counts.entity_rows == {"postgres": {"items": 2500, "events": 15}}

    # (b) every recorded batch length is <= batch
    for lens in fake.batches.values():
        assert all(n <= 800 for n in lens)

    # (c) chunks of 1000, 1000, 500 flush as full batches plus the remainder
    assert fake.batches["items"] == [800, 800, 800, 100]

    # filtered + each-split partitions flush once each (below batch threshold)
    assert fake.batches["events_north"] == [10]
    assert fake.batches["events_south"] == [5]

    # (d) create_schema() called exactly once (no args)
    assert fake.schema_calls == 1

    # (e) ensure_partition called exactly once per distinct partition
    assert sorted(fake.ensure_calls) == sorted(["items", "events_north", "events_south"])
    assert len(fake.ensure_calls) == len(set(fake.ensure_calls))

    # (f) close() called
    assert fake.closed is True


def test_stream_import_unions_heterogeneous_multi_sources(tmp_path):
    # Two sources with disjoint extra columns: the streamed union must widen
    # every chunk to the superset (missing cells filled ""), exactly as
    # mapping_resolver._union_source does for the materialize path.
    _write_csv(tmp_path / "a.csv", ["id", "a_col"], [(i, f"a{i}") for i in range(3)])
    _write_csv(tmp_path / "b.csv", ["id", "b_col"], [(i, f"b{i}") for i in range(2)])
    config = {
        "sources": {"a": "a.csv", "b": "b.csv"},
        "postgres": {"entities": {"activity": {"source": ["a", "b"]}}},
    }
    fake = _FakeSink()

    counts = sr.run_stream_import(
        plan_import(config, tmp_path, dbms_names=["postgres"]),
        sink_factories={"postgres": lambda cfg: fake},
    )

    assert counts.written == {"postgres": {"activity": 5}}
    combined = pd.concat(fake.frames["activity"], ignore_index=True)
    # Superset columns in union-list order, _source last.
    assert list(combined.columns) == ["id", "a_col", "b_col", SOURCE_COLUMN]
    a_rows = combined[combined[SOURCE_COLUMN] == "a"]
    b_rows = combined[combined[SOURCE_COLUMN] == "b"]
    assert len(a_rows) == 3 and len(b_rows) == 2
    # Missing columns filled "" for the source that lacks them.
    assert (a_rows["b_col"] == "").all()
    assert (b_rows["a_col"] == "").all()
    assert set(a_rows["a_col"]) == {"a0", "a1", "a2"}
    assert set(b_rows["b_col"]) == {"b0", "b1"}


def test_stream_import_rejects_empty_union_list(tmp_path):
    # The plan binds every entity before any sink exists, so an empty union list
    # fails there, in mapping_resolver.bind_entity_source.
    _write_csv(tmp_path / "a.csv", ["id"], [(i,) for i in range(3)])
    config = {
        "sources": {"a": "a.csv"},
        "postgres": {"entities": {"bad": {"source": []}}},
    }

    with pytest.raises(MappingError, match="'source' list is empty"):
        plan_import(config, tmp_path, dbms_names=["postgres"])


def _likes_config(tmp_path):
    """Two node entities from two sources + one relationship whose 'from' is User
    (source 'people', carrying both FKs person_id and thing_id)."""
    _write_csv(tmp_path / "people.csv", ["person_id", "thing_id", "weight"],
               [(f"u{i}", f"t{i}", i) for i in range(3)])
    _write_csv(tmp_path / "things.csv", ["thing_id", "label"],
               [(f"t{i}", f"L{i}") for i in range(3)])
    return {
        "sources": {"people": "people.csv", "things": "things.csv"},
        "neo4j": {
            "entities": {
                "User": {"source": "people", "columns": {"person_id": {"is_key": True}}},
                "Thing": {"source": "things", "columns": {"thing_id": {"is_key": True}}},
            },
            "relationships": {
                "LIKES": {"from": "User", "to": "Thing", "type": "LIKES",
                          "columns": {"weight": {}}},
            },
        },
    }


def test_stream_import_writes_relationships_after_all_nodes(tmp_path):
    fake = _FakeSink()

    counts = sr.run_stream_import(
        plan_import(_likes_config(tmp_path), tmp_path, dbms_names=["neo4j"]),
        sink_factories={"neo4j": lambda cfg: fake},
    )

    # (a) edges recorded and counted under the rel_type key
    assert fake.rel_rows == {"LIKES": 3}
    written = counts.written["neo4j"]
    assert written[":LIKES"] == 3
    assert written["User"] == 3 and written["Thing"] == 3

    # (b) every node write happens before the first relationship write
    first_rel = next(i for i, c in enumerate(fake.calls) if c[0] == "rel")
    assert all(c[0] == "node" for c in fake.calls[:first_rel])

    # (c) the relationship pass drives from the User source, resolving both
    #     endpoints' FKs (and the edge prop) from that one frame — verified by
    #     inspecting the actual batch handed to write_relationships, not just
    #     its length.
    rel_df = pd.concat(fake.rel_frames["LIKES"], ignore_index=True)
    assert {"person_id", "thing_id", "weight"} <= set(rel_df.columns)
    assert set(rel_df["person_id"]) == {"u0", "u1", "u2"}
    assert set(rel_df["thing_id"]) == {"t0", "t1", "t2"}

    assert fake.closed is True


def test_on_batch_sees_every_row_written_with_its_dbms(tmp_path):
    fake = _FakeSink()
    seen = []

    counts = sr.run_stream_import(
        _batches_plan(tmp_path),
        sink_factories={"postgres": lambda cfg: fake},
        on_batch=lambda dbms, part, frame: seen.append((dbms, part, len(frame))),
    )

    totals = {}
    for dbms, part, n in seen:
        assert dbms == "postgres"
        totals[part] = totals.get(part, 0) + n
    assert totals == counts.written["postgres"]
    assert [n for _, part, n in seen if part == "items"] == [800, 800, 800, 100]


def _pg_and_neo4j_config(tmp_path):
    _write_csv(tmp_path / "purchase.csv", ["order_number", "user_id", "product_id", "qty"],
               [(f"o{i}", f"u{i % 40}", f"p{i % 25}", i % 7) for i in range(300)])
    _write_csv(tmp_path / "products.csv", ["product_id", "label"],
               [(f"p{i}", f"label-{i}") for i in range(25)])
    return {
        "sources": {"purchase": "purchase.csv", "products": "products.csv"},
        "postgres": {"entities": {
            "purchase": {"source": "purchase"},
            "products": {"source": "products"},
        }},
        "neo4j": {
            "entities": {
                "User": {"source": "purchase", "columns": {"user_id": {"is_key": True}}},
                "Product": {"source": "products", "columns": {"product_id": {"is_key": True}}},
            },
            "relationships": {
                "PURCHASED": {"from": "User", "to": "Product", "type": "PURCHASED",
                              "columns": {"qty": {}}},
            },
        },
    }


def test_single_pass_and_per_dbms_runs_count_the_same(tmp_path):
    plan = plan_import(_pg_and_neo4j_config(tmp_path), tmp_path,
                       dbms_names=["postgres", "neo4j"], chunk_mb=0.01, batch_size=7)
    assert plan.rows_per_chunk["purchase"] < 300  # several chunks per file

    a = sr.run_stream_import(plan, sink_factories={"postgres": lambda c: _FakeSink(),
                                                   "neo4j": lambda c: _FakeSink()})
    b = sr.run_single_pass(plan, {"postgres": _FakeSink(), "neo4j": _FakeSink()})

    assert a.written == b.written and a.entity_rows == b.entity_rows
    assert b.written["neo4j"][":PURCHASED"] > 0
    assert b.written["postgres"] == {"purchase": 300, "products": 25}


def test_single_pass_reads_each_source_once(tmp_path, reads):
    _write_csv(tmp_path / "a.csv", ["id", "v"], [(i, f"a{i}") for i in range(50)])
    _write_csv(tmp_path / "b.csv", ["id", "w"], [(i, f"b{i}") for i in range(50)])
    config = {
        "sources": {"a": "a.csv", "b": "b.csv"},
        "postgres": {"entities": {"a": {}, "b": {}}},
        "redis": {"entities": {
            "a": {"columns": {"id": {"is_key": True}}},
            "b": {"columns": {"id": {"is_key": True}}},
        }},
    }
    plan = plan_import(config, tmp_path, dbms_names=["postgres", "redis"])
    reads.clear()  # the plan's own (inference) reads are not the single pass

    sinks = {"postgres": _FakeSink(), "redis": _FakeSink()}
    counts = sr.run_single_pass(plan, sinks)

    assert sorted(name for name, _ in reads) == ["a.csv", "b.csv"]
    assert counts.written == {"postgres": {"a": 50, "b": 50}, "redis": {"a": 50, "b": 50}}
    assert all(s.closed and s.schema_calls == 0 for s in sinks.values())


def test_batches_never_exceed_the_rows_of_one_chunk(tmp_path):
    _write_csv(tmp_path / "stock.csv", ["id", "v"], [(i, f"s{i}") for i in range(1000)])
    cfg = {"sources": {"stock": "stock.csv"}, "postgres": {"entities": {"stock": {}}}}
    plan = dataclasses.replace(
        plan_import(cfg, tmp_path, dbms_names=["postgres"], batch_size=1000),
        rows_per_chunk={"stock": 300},
    )
    fake = _FakeSink()

    sr.run_stream_import(plan, sink_factories={"postgres": lambda c: fake})

    assert max(fake.batches["stock"]) <= 300
    assert sum(fake.batches["stock"]) == 1000


def test_inspect_rows_sees_file_row_positions(tmp_path):
    # Data rows 3 and 7 pass the filter; with chunks of 3 rows they sit in the first
    # and the third chunk, and the 'each' split puts them in different partitions.
    rows = [(i, "yes" if i in (2, 6) else "no", "north" if i < 5 else "south") for i in range(9)]
    _write_csv(tmp_path / "s.csv", ["n", "keep", "region"], rows)
    cfg = {"sources": {"s": "s.csv"}, "postgres": {"entities": {"s": {"filters": [
        {"column": "keep", "operator": "==", "value": "yes"},
        {"column": "region", "operator": "each"},
    ]}}}}
    plan = dataclasses.replace(plan_import(cfg, tmp_path, dbms_names=["postgres"]),
                               rows_per_chunk={"s": 3})
    seen, parts = [], []

    class Spy(_FakeSink):
        def inspect_rows(self, source, partition, binding, raw, cast):
            assert list(raw.index) == list(cast.index)
            assert all(isinstance(v, str) for v in raw["n"])      # raw: not converted
            assert all(not isinstance(v, str) for v in cast["n"])  # cast: converted
            seen.extend(cast.index)
            parts.extend([partition] * len(cast))

    run = sr.run_single_pass(plan, {"postgres": Spy()})

    assert seen == [2, 6]   # data rows 3 and 7 -> positions 2 and 6
    assert parts == ["s_north", "s_south"]
    assert run.written == {"postgres": {"s_north": 1, "s_south": 1}}


def test_inspect_rows_sees_the_row_position_in_a_combined_file(tmp_path):
    rows = [("a" if i % 3 else "b", i) for i in range(10)]  # origin b on rows 0, 3, 6, 9
    _write_csv(tmp_path / "j.csv", ["action", "n"], rows)
    cfg = {"sources": {"j": {"file": "j.csv"}}, "postgres": {"entities": {"e": {"source": "b"}}}}
    plan = dataclasses.replace(plan_import(cfg, tmp_path, dbms_names=["postgres"]),
                               rows_per_chunk={"j": 4})
    seen = []

    class Spy(_FakeSink):
        def inspect_rows(self, source, partition, binding, raw, cast):
            assert source == "b"
            seen.extend(cast.index)

    sr.run_single_pass(plan, {"postgres": Spy()})

    assert seen == [0, 3, 6, 9]


def test_inspect_relationship_rows_runs_before_each_relationship_write(tmp_path):
    seen = []

    class Spy(_FakeSink):
        def inspect_relationship_rows(self, source, rname, rspec, from_binding, to_binding, cast):
            assert source == "people" and rspec["type"] == "LIKES"
            assert from_binding.source_name == "people" and to_binding.source_name == "things"
            self.calls.append(("inspect", rname))
            seen.append(len(cast))

    spy = Spy()
    sr.run_single_pass(plan_import(_likes_config(tmp_path), tmp_path, dbms_names=["neo4j"]),
                       {"neo4j": spy})

    assert [c for c in spy.calls if c[0] != "node"] == [("inspect", "LIKES"), ("rel", "LIKES")]
    assert seen == [3]


def test_relationship_sources_need_a_sink_that_writes_relationships(tmp_path):
    class NodesOnly(_FakeSink):
        write_relationships = None

    plan = plan_import(_likes_config(tmp_path), tmp_path, dbms_names=["neo4j"])

    assert sr.DbmsStream("neo4j", plan, _FakeSink()).relationship_sources() == {
        "people": "people.csv"
    }
    assert sr.DbmsStream("neo4j", plan, NodesOnly()).relationship_sources() == {}


def test_relationship_sources_are_empty_without_relationships(tmp_path):
    plan = plan_import(_build_config(tmp_path), tmp_path, dbms_names=["postgres"])
    assert sr.DbmsStream("postgres", plan, _FakeSink()).relationship_sources() == {}


def test_an_entity_whose_source_has_no_rows_counts_zero_and_writes_nothing(tmp_path):
    (tmp_path / "empty.csv").write_text("id,v\n", encoding="utf-8")
    _write_csv(tmp_path / "s.csv", ["id"], [(1,), (2,)])
    cfg = {"sources": {"empty": "empty.csv", "s": "s.csv"},
           "postgres": {"entities": {"empty": {}, "s": {}}}}
    fake = _FakeSink()

    counts = sr.run_single_pass(plan_import(cfg, tmp_path, dbms_names=["postgres"]),
                                {"postgres": fake})

    assert counts.entity_rows == {"postgres": {"empty": 0, "s": 2}}
    assert counts.written == {"postgres": {"s": 2}}
    assert "empty" not in fake.ensure_calls


def test_run_stream_import_records_one_write_metric_per_dbms(tmp_path):
    plan = plan_import(_pg_and_neo4j_config(tmp_path), tmp_path, dbms_names=["postgres", "neo4j"])
    collector = MetricsCollector()

    counts = sr.run_stream_import(
        plan,
        sink_factories={"postgres": lambda c: _FakeSink(), "neo4j": lambda c: _FakeSink()},
        collector=collector,
    )

    recs = collector.to_records()
    assert [(r["backend"], r["entity"], r["phase"], r["rows"]) for r in recs] == [
        ("postgres", "*", "write", sum(counts.written["postgres"].values())),
        ("neo4j", "*", "write", sum(counts.written["neo4j"].values())),
    ]
    assert all(r["seconds"] >= 0 for r in recs)


def test_an_entity_is_fed_only_by_the_sources_it_is_bound_to(tmp_path):
    # 'users' reads source 'orders'; the source named 'users' feeds 'people' only.
    _write_csv(tmp_path / "o.csv", ["order_id", "user_id"], [(f"o{i}", f"u{i}") for i in range(4)])
    _write_csv(tmp_path / "u.csv", ["user_id", "name"], [(f"u{i}", f"n{i}") for i in range(3)])
    cfg = {"sources": {"orders": "o.csv", "users": "u.csv"},
           "postgres": {"entities": {"users": {"source": "orders"}, "people": {"source": "users"}}}}
    fake = _FakeSink()

    counts = sr.run_single_pass(plan_import(cfg, tmp_path, dbms_names=["postgres"]),
                                {"postgres": fake})

    assert counts.written == {"postgres": {"users": 4, "people": 3}}
    users = pd.concat(fake.frames["users"], ignore_index=True)
    assert set(users[SOURCE_COLUMN]) == {"orders"} and users["order_id"].notna().all()


def test_each_dbms_reads_only_its_own_sources(tmp_path, reads):
    _write_csv(tmp_path / "a.csv", ["id"], [(i,) for i in range(5)])
    _write_csv(tmp_path / "b.csv", ["id"], [(i,) for i in range(5)])
    cfg = {"sources": {"a": "a.csv", "b": "b.csv"},
           "postgres": {"entities": {"a": {}}},
           "redis": {"entities": {"b": {"columns": {"id": {"is_key": True}}}}}}
    plan = plan_import(cfg, tmp_path, dbms_names=["postgres", "redis"])
    reads.clear()  # the plan's own (inference) reads are not the write

    counts = sr.run_stream_import(plan, sink_factories={"postgres": lambda c: _FakeSink(),
                                                        "redis": lambda c: _FakeSink()})

    assert [name for name, _ in reads] == ["a.csv", "b.csv"]  # postgres reads a, redis reads b
    assert counts.written == {"postgres": {"a": 5}, "redis": {"b": 5}}


def test_single_pass_writes_the_nodes_of_every_dbms_before_any_relationship(tmp_path):
    log = []

    class Logged(_FakeSink):
        def __init__(self, dbms):
            super().__init__()
            self.dbms = dbms

        def write_batch(self, partition_name, binding, batch):
            log.append((self.dbms, "node"))
            return super().write_batch(partition_name, binding, batch)

        def write_relationships(self, rname, rspec, from_binding, to_binding, batch):
            log.append((self.dbms, "rel"))
            return super().write_relationships(rname, rspec, from_binding, to_binding, batch)

    plan = plan_import(_pg_and_neo4j_config(tmp_path), tmp_path,
                       dbms_names=["postgres", "neo4j"], chunk_mb=0.01, batch_size=7)
    sr.run_single_pass(plan, {"postgres": Logged("postgres"), "neo4j": Logged("neo4j")})

    first_rel = log.index(("neo4j", "rel"))
    assert {kind for _, kind in log[:first_rel]} == {"node"}
    assert {kind for _, kind in log[first_rel:]} == {"rel"}
    assert {dbms for dbms, _ in log[:first_rel]} == {"postgres", "neo4j"}


def test_inspect_rows_sees_file_row_positions_of_a_union_across_chunks(tmp_path):
    # Each value names its source and its data row position: a3 is row 4 of a.csv.
    _write_csv(tmp_path / "a.csv", ["n", "keep"], [(f"a{i}", "y" if i % 2 else "n") for i in range(7)])
    _write_csv(tmp_path / "b.csv", ["n", "other"], [(f"b{i}", i) for i in range(5)])
    cfg = {"sources": {"a": "a.csv", "b": "b.csv"}, "postgres": {"entities": {"u": {
        "source": ["a", "b"], "filters": [{"column": "keep", "operator": "!=", "value": "n"}],
    }}}}
    plan = dataclasses.replace(plan_import(cfg, tmp_path, dbms_names=["postgres"]),
                               rows_per_chunk={"a": 3, "b": 2})
    seen = []

    class Spy(_FakeSink):
        def inspect_rows(self, source, partition, binding, raw, cast):
            assert list(raw.index) == list(cast.index)
            seen.extend((source, i, raw.loc[i, "n"]) for i in cast.index)

    sr.run_single_pass(plan, {"postgres": Spy()})

    assert seen == [("a", 1, "a1"), ("a", 3, "a3"), ("a", 5, "a5")] + [
        ("b", i, f"b{i}") for i in range(5)]
