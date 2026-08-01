import pandas as pd
import pytest
from polyglotimportcsv import stream_source as ss
from polyglotimportcsv.business_exception import ImportExecutionError
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


def test_sample_union_sources_finds_origin_starting_after_the_first_chunk(tmp_path):
    # Combined CSVs are commonly grouped by origin (the benchmark generator emits
    # all stock rows, then purchase, then select_product, then add_to_cart). Once
    # the leading block is larger than one chunk, later origins are absent from the
    # first chunk, so sampling has to keep scanning to reach them.
    rows = ([("stock", i, f"s{i}") for i in range(2500)]
            + [("cart", i, f"c{i}") for i in range(5)])
    _write_csv(tmp_path / "j.csv", ["action", "id", "v"], rows)
    cfg = {"ecom": {"file": "j.csv"}}
    samples = ss.sample_union_sources(cfg, tmp_path, ["stock", "cart"], chunksize=1000)

    assert set(samples) == {"stock", "cart"}
    # Each origin still keeps at most one chunk-slice: bounded in total rows.
    assert len(samples["stock"]) == 1000
    assert len(samples["cart"]) == 5
    assert "action" not in samples["cart"].columns
    assert (samples["cart"][SOURCE_COLUMN] == "cart").all()


def test_sample_union_sources_stops_scanning_once_every_origin_is_sampled(tmp_path):
    # The scan is an eager read at bind time: it must stop at the chunk that
    # completes the sample set, not walk the rest of the file.
    rows = ([("stock", i, f"s{i}") for i in range(10)]
            + [("cart", i, f"c{i}") for i in range(10)]
            + [("tail", i, f"t{i}") for i in range(5000)])
    _write_csv(tmp_path / "j.csv", ["action", "id", "v"], rows)
    cfg = {"ecom": {"file": "j.csv"}}

    reads = []
    real_read_chunks = ss._read_chunks

    def counting_read_chunks(path, chunksize):
        for chunk in real_read_chunks(path, chunksize):
            reads.append(len(chunk))
            yield chunk

    ss._read_chunks = counting_read_chunks
    try:
        samples = ss.sample_union_sources(cfg, tmp_path, ["stock", "cart"], chunksize=1000)
    finally:
        ss._read_chunks = real_read_chunks

    assert set(samples) == {"stock", "cart"}
    assert len(reads) == 1  # both origins live in chunk 1; the 5000 tail rows are not read


def test_sample_union_sources_raises_when_an_origin_is_nowhere_in_the_file(tmp_path):
    rows = [("stock", i, f"s{i}") for i in range(2500)]
    _write_csv(tmp_path / "j.csv", ["action", "id", "v"], rows)
    cfg = {"ecom": {"file": "j.csv"}}
    with pytest.raises(ImportExecutionError) as exc:
        ss.sample_union_sources(cfg, tmp_path, ["stock", "ghost"], chunksize=1000)
    assert "'ghost'" in str(exc.value)


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
