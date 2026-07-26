import pandas as pd
from polyglotimportcsv import stream_source as ss
from polyglotimportcsv.sources import SOURCE_COLUMN


def _write_csv(path, header, rows):
    path.write_text(",".join(header) + "\n" +
                    "\n".join(",".join(str(c) for c in r) for r in rows) + "\n",
                    encoding="utf-8")


def test_multi_yields_chunks_with_source_column(tmp_path):
    _write_csv(tmp_path / "a.csv", ["id", "v"], [(i, f"x{i}") for i in range(2500)])
    cfg = {"alpha": "a.csv"}
    chunks = list(ss.iter_entity_chunks(cfg, tmp_path, chunksize=1000))
    assert [name for name, _ in chunks] == ["alpha", "alpha", "alpha"]  # ceil(2500/1000)
    total = sum(len(df) for _, df in chunks)
    assert total == 2500
    first = chunks[0][1]
    assert SOURCE_COLUMN in first.columns
    assert (first[SOURCE_COLUMN] == "alpha").all()
    assert list(first.columns)[:2] == ["id", "v"]


def test_sample_union_sources_reads_one_chunk_per_multi_source(tmp_path):
    # Two multi sources with disjoint extra columns; only their FIRST chunk is
    # sampled (bounded: O(sources), not O(rows)).
    _write_csv(tmp_path / "a.csv", ["id", "a_col"], [(i, f"a{i}") for i in range(5000)])
    _write_csv(tmp_path / "b.csv", ["id", "b_col"], [(i, f"b{i}") for i in range(5000)])
    cfg = {"a": "a.csv", "b": "b.csv"}
    samples = ss.sample_union_sources(cfg, tmp_path, ["a", "b"], chunksize=1000)

    assert set(samples) == {"a", "b"}
    # Each sample is a single chunk (<= chunksize rows), carrying _source.
    assert len(samples["a"]) == 1000
    assert len(samples["b"]) == 1000
    assert list(samples["a"].columns) == ["id", "a_col", SOURCE_COLUMN]
    assert (samples["a"][SOURCE_COLUMN] == "a").all()
    assert list(samples["b"].columns) == ["id", "b_col", SOURCE_COLUMN]


def test_sample_union_sources_routes_combined_origins(tmp_path):
    rows = [("stock", i, f"s{i}") for i in range(10)] + [("cart", i, f"c{i}") for i in range(5)]
    _write_csv(tmp_path / "j.csv", ["action", "id", "v"], rows)
    cfg = {"ecom": {"file": "j.csv"}}
    samples = ss.sample_union_sources(cfg, tmp_path, ["stock", "cart"], chunksize=1000)
    assert set(samples) == {"stock", "cart"}
    assert "action" not in samples["stock"].columns
    assert (samples["stock"][SOURCE_COLUMN] == "stock").all()
    assert (samples["cart"][SOURCE_COLUMN] == "cart").all()


def test_combined_routes_by_origin(tmp_path):
    rows = [("stock", i, f"s{i}") for i in range(10)] + [("cart", i, f"c{i}") for i in range(5)]
    _write_csv(tmp_path / "j.csv", ["action", "id", "v"], rows)
    cfg = {"ecom": {"file": "j.csv"}}
    chunks = list(ss.iter_entity_chunks(cfg, tmp_path, chunksize=1000))
    by_name = {}
    for name, df in chunks:
        by_name.setdefault(name, 0)
        by_name[name] += len(df)
    assert by_name == {"stock": 10, "cart": 5}
    # origin column dropped; data columns + _source present
    a_chunk = next(df for name, df in chunks if name == "stock")
    assert "action" not in a_chunk.columns
    assert list(a_chunk.columns)[:2] == ["id", "v"]
    assert (a_chunk[SOURCE_COLUMN] == "stock").all()
