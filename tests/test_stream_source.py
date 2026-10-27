import pandas as pd
import pytest
from polyglotimportcsv import stream_source as ss
from polyglotimportcsv.business_exception import ImportExecutionError, SourceError
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


def test_unknown_override_name_raises(tmp_path):
    cfg = {"stock": "s.csv", "ecom": {"file": "j.csv"}}
    with pytest.raises(SourceError) as exc:
        ss.check_source_overrides(cfg, {"zzz": "x.csv", "aaa": "y.csv"})
    message = str(exc.value)
    assert "--source override name(s) not declared in config: aaa, zzz" in message
    assert "Declared source names: ecom, stock" in message


def test_declared_or_absent_overrides_pass():
    cfg = {"stock": "s.csv"}
    assert ss.check_source_overrides(cfg, {"stock": "x.csv"}) is None
    assert ss.check_source_overrides(cfg, {}) is None
    assert ss.check_source_overrides(cfg, None) is None


def test_read_source_headers_strips_the_origin_column(tmp_path):
    _write_csv(tmp_path / "j.csv", ["action", "id", "v"], [("stock", 1, "a")])
    _write_csv(tmp_path / "s.csv", ["id", "name"], [(1, "x")])
    cfg = {"ecom": {"file": "j.csv"}, "stock": "s.csv"}
    assert ss.read_source_headers(cfg, tmp_path, {}) == {
        "ecom": ["id", "v"],
        "stock": ["id", "name"],
    }


def test_read_source_headers_reads_a_header_only_file_and_ignores_the_bom(tmp_path):
    (tmp_path / "s.csv").write_bytes(b"\xef\xbb\xbfid,name\r\n")
    assert ss.read_source_headers({"s": "s.csv"}, tmp_path, {}) == {"s": ["id", "name"]}


def test_read_source_headers_honors_an_override(tmp_path):
    _write_csv(tmp_path / "other.csv", ["k"], [(1,)])
    got = ss.read_source_headers({"s": "missing.csv"}, tmp_path, {"s": str(tmp_path / "other.csv")})
    assert got == {"s": ["k"]}


def test_read_source_headers_reports_a_missing_file(tmp_path):
    with pytest.raises(SourceError, match="Source 's': CSV file not found"):
        ss.read_source_headers({"s": "nope.csv"}, tmp_path, {})


def test_read_source_headers_rejects_a_combined_file_without_data_columns(tmp_path):
    _write_csv(tmp_path / "j.csv", ["action"], [("stock",)])
    with pytest.raises(SourceError, match="combined CSV needs an origin column plus data columns"):
        ss.read_source_headers({"e": {"file": "j.csv"}}, tmp_path, {})


def _csv(tmp_path, name, cols, rows):
    path = tmp_path / name
    _write_csv(path, [f"c{j}" for j in range(cols)],
               [[f"value-{i}-{j}" for j in range(cols)] for i in range(rows)])
    return path


def test_chunk_rows_follows_the_memory_budget(tmp_path):
    narrow = _csv(tmp_path, "n.csv", cols=3, rows=5000)
    wide = _csv(tmp_path, "w.csv", cols=30, rows=5000)
    assert ss.chunk_rows(narrow, 1) > ss.chunk_rows(wide, 1) >= 1
    assert ss.chunk_rows(narrow, 2) >= 2 * ss.chunk_rows(narrow, 1) - 1


def test_chunk_rows_reads_a_bom_crlf_file(tmp_path):
    p = tmp_path / "b.csv"
    p.write_bytes("\ufeffa,b\r\n1,x\r\n2,y\r\n".encode("utf-8"))
    assert ss.chunk_rows(p, 8) >= 1
    assert ss.read_source_headers({"b": "b.csv"}, tmp_path, {}) == {"b": ["a", "b"]}


def test_chunk_rows_of_a_file_without_rows_is_one(tmp_path):
    (tmp_path / "h.csv").write_text("a,b\n", encoding="utf-8")
    assert ss.chunk_rows(tmp_path / "h.csv", 8) == 1


def test_chunk_rows_never_drops_below_one_row(tmp_path):
    assert ss.chunk_rows(_csv(tmp_path, "w.csv", cols=30, rows=50), 0.00001) == 1


def test_source_path_resolves_plain_combined_and_overridden_sources(tmp_path):
    (tmp_path / "a.csv").write_text("x\n1\n", encoding="utf-8")
    (tmp_path / "j.csv").write_text("o,x\ns,1\n", encoding="utf-8")
    (tmp_path / "other.csv").write_text("x\n1\n", encoding="utf-8")
    assert ss.source_path("a", "a.csv", tmp_path, {}) == tmp_path / "a.csv"
    assert ss.source_path("e", {"file": "j.csv"}, tmp_path, {}) == tmp_path / "j.csv"
    override = {"a": str(tmp_path / "other.csv")}
    assert ss.source_path("a", "a.csv", tmp_path, override) == tmp_path / "other.csv"
    with pytest.raises(SourceError, match="CSV file not found"):
        ss.source_path("a", "nope.csv", tmp_path, {})


def test_rows_per_chunk_sets_the_chunk_size_of_each_declared_source(tmp_path):
    _write_csv(tmp_path / "a.csv", ["id"], [(i,) for i in range(2500)])
    _write_csv(tmp_path / "b.csv", ["id"], [(i,) for i in range(2500)])
    sizes = {}
    for name, df in ss.iter_entity_chunks(
        {"a": "a.csv", "b": "b.csv"}, tmp_path, rows_per_chunk={"a": 1000, "b": 2000}
    ):
        sizes.setdefault(name, []).append(len(df))
    assert sizes == {"a": [1000, 1000, 500], "b": [2000, 500]}


def test_rows_per_chunk_also_sizes_the_chunks_of_a_combined_source(tmp_path):
    _write_csv(tmp_path / "j.csv", ["action", "id"], [("stock", i) for i in range(250)])
    sizes = [len(df) for _, df in ss.iter_entity_chunks(
        {"e": {"file": "j.csv"}}, tmp_path, rows_per_chunk={"e": 100})]
    assert sizes == [100, 100, 50]


def test_only_columns_reads_just_those_columns_of_a_plain_source(tmp_path):
    _write_csv(tmp_path / "a.csv", ["id", "v", "w"], [(i, i, i) for i in range(5)])
    (_, chunk), = ss.iter_entity_chunks({"a": "a.csv"}, tmp_path, only_columns={"a": ["w"]})
    assert list(chunk.columns) == ["w", SOURCE_COLUMN]


def test_only_columns_keeps_routing_a_combined_source_by_origin(tmp_path):
    rows = [("stock", i, f"s{i}", i) for i in range(4)] + [("cart", i, f"c{i}", i) for i in range(2)]
    _write_csv(tmp_path / "j.csv", ["action", "id", "v", "w"], rows)
    got = {name: df for name, df in ss.iter_entity_chunks(
        {"e": {"file": "j.csv"}}, tmp_path, only_columns={"e": ["v"]})}
    assert set(got) == {"stock", "cart"}
    assert list(got["stock"].columns) == ["v", SOURCE_COLUMN]
    assert len(got["stock"]) == 4 and len(got["cart"]) == 2
