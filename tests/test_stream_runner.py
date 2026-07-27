import pandas as pd
import pytest

from polyglotimportcsv import stream_runner as sr
from polyglotimportcsv.business_exception import ImportExecutionError
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


def test_stream_import_batches_flushes_and_partitions(tmp_path):
    config = _build_config(tmp_path)
    fake = _FakeSink()

    written = sr.run_stream_import(
        config,
        tmp_path,
        sink_factories={"postgres": lambda cfg: fake},
        chunksize=800,  # spans batch boundaries across chunks: 800,800,800,100
        batch=1000,
    )

    # (a) rows written per partition equal the CSV row counts after filters
    assert written == {"items": 2500, "events_north": 10, "events_south": 5}

    # (b) every recorded batch length is <= batch
    for lens in fake.batches.values():
        assert all(n <= 1000 for n in lens)

    # (c) exactly 3 write_batch flushes for the 2500-row partition: 1000,1000,500
    assert fake.batches["items"] == [1000, 1000, 500]

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

    written = sr.run_stream_import(
        config, tmp_path, sink_factories={"postgres": lambda cfg: fake}, batch=1000
    )

    assert written == {"activity": 5}
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
    _write_csv(tmp_path / "a.csv", ["id"], [(i,) for i in range(3)])
    config = {
        "sources": {"a": "a.csv"},
        "postgres": {"entities": {"bad": {"source": []}}},
    }
    fake = _FakeSink()

    with pytest.raises(ImportExecutionError, match="empty"):
        sr.run_stream_import(config, tmp_path, sink_factories={"postgres": lambda cfg: fake})

    # fails fast: no sink was ever opened
    assert fake.schema_calls == 0
    assert fake.closed is False


def test_stream_import_writes_relationships_after_all_nodes(tmp_path):
    # Two node entities from two sources + one relationship whose 'from' is User
    # (source 'people', carrying both FKs person_id and thing_id).
    _write_csv(tmp_path / "people.csv", ["person_id", "thing_id", "weight"],
               [(f"u{i}", f"t{i}", i) for i in range(3)])
    _write_csv(tmp_path / "things.csv", ["thing_id", "label"],
               [(f"t{i}", f"L{i}") for i in range(3)])
    config = {
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
    fake = _FakeSink()

    written = sr.run_stream_import(
        config, tmp_path, sink_factories={"neo4j": lambda cfg: fake}, batch=1000
    )

    # (a) edges recorded and counted under the rel_type key
    assert fake.rel_rows == {"LIKES": 3}
    assert written[":LIKES"] == 3
    assert written["User"] == 3 and written["Thing"] == 3

    # (b) every node write happens before the first relationship write
    first_rel = next(i for i, c in enumerate(fake.calls) if c[0] == "rel")
    assert all(c[0] == "node" for c in fake.calls[:first_rel])

    # (c) the relationship pass drives from the User source, resolving both
    #     endpoints' FKs from that one frame
    assert fake.closed is True
