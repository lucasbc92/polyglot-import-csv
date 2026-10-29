import re

import pandas as pd
import pytest
from polyglotimportcsv import stream_source as ss
from polyglotimportcsv.business_exception import SourceError
from polyglotimportcsv.sources import SOURCE_COLUMN


def _write_csv(path, header, rows):
    path.write_text(",".join(header) + "\n" +
                    "\n".join(",".join(str(c) for c in r) for r in rows) + "\n",
                    encoding="utf-8")


def test_multi_yields_chunks_with_source_column(tmp_path):
    _write_csv(tmp_path / "a.csv", ["id", "v"], [(i, f"x{i}") for i in range(2500)])
    cfg = {"alpha": "a.csv"}
    chunks = list(ss.iter_entity_chunks(cfg, tmp_path, rows_per_chunk={"alpha": 1000}))
    assert [name for name, _ in chunks] == ["alpha", "alpha", "alpha"]  # ceil(2500/1000)
    total = sum(len(df) for _, df in chunks)
    assert total == 2500
    first = chunks[0][1]
    assert SOURCE_COLUMN in first.columns
    assert (first[SOURCE_COLUMN] == "alpha").all()
    assert list(first.columns)[:2] == ["id", "v"]


def test_combined_routes_by_origin(tmp_path):
    rows = [("stock", i, f"s{i}") for i in range(10)] + [("cart", i, f"c{i}") for i in range(5)]
    _write_csv(tmp_path / "j.csv", ["action", "id", "v"], rows)
    cfg = {"ecom": {"file": "j.csv"}}
    chunks = list(ss.iter_entity_chunks(cfg, tmp_path, rows_per_chunk={"ecom": 1000}))
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


@pytest.mark.parametrize("decl", ["e.csv", {"file": "e.csv"}], ids=["plain", "combined"])
def test_a_zero_byte_file_is_a_source_error_in_every_read(tmp_path, decl):
    """pandas' EmptyDataError would reach the CLI as a traceback."""
    (tmp_path / "e.csv").write_bytes(b"")
    cfg = {"src": decl}
    message = re.escape(f"Source 'src': CSV file is empty (no header row): {tmp_path / 'e.csv'}")
    with pytest.raises(SourceError, match=message):
        ss.read_source_headers(cfg, tmp_path)
    with pytest.raises(SourceError, match=message):
        ss.chunk_rows("src", tmp_path / "e.csv", 8)
    with pytest.raises(SourceError, match=message):
        list(ss.iter_entity_chunks(cfg, tmp_path, rows_per_chunk={"src": 10}))
    with pytest.raises(SourceError, match=message):
        list(ss.iter_entity_chunks(cfg, tmp_path, rows_per_chunk={"src": 10},
                                   only_columns={"src": ["a"]}))


def _csv(tmp_path, name, cols, rows):
    path = tmp_path / name
    _write_csv(path, [f"c{j}" for j in range(cols)],
               [[f"value-{i}-{j}" for j in range(cols)] for i in range(rows)])
    return path


def test_chunk_rows_follows_the_memory_budget(tmp_path):
    narrow = _csv(tmp_path, "n.csv", cols=3, rows=5000)
    wide = _csv(tmp_path, "w.csv", cols=30, rows=5000)
    assert ss.chunk_rows("n", narrow, 1) > ss.chunk_rows("w", wide, 1) >= 1
    assert ss.chunk_rows("n", narrow, 2) >= 2 * ss.chunk_rows("n", narrow, 1) - 1


def test_chunk_rows_reads_a_bom_crlf_file(tmp_path):
    p = tmp_path / "b.csv"
    p.write_bytes("\ufeffa,b\r\n1,x\r\n2,y\r\n".encode("utf-8"))
    assert ss.chunk_rows("b", p, 8) >= 1
    assert ss.read_source_headers({"b": "b.csv"}, tmp_path, {}) == {"b": ["a", "b"]}


def test_chunk_rows_of_a_file_without_rows_is_one(tmp_path):
    (tmp_path / "h.csv").write_text("a,b\n", encoding="utf-8")
    assert ss.chunk_rows("h", tmp_path / "h.csv", 8) == 1


def test_chunk_rows_never_drops_below_one_row(tmp_path):
    assert ss.chunk_rows("w", _csv(tmp_path, "w.csv", cols=30, rows=50), 0.00001) == 1


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
    (_, chunk), = ss.iter_entity_chunks({"a": "a.csv"}, tmp_path, rows_per_chunk={"a": 10},
                                        only_columns={"a": ["w"]})
    assert list(chunk.columns) == ["w", SOURCE_COLUMN]


def test_only_columns_keeps_routing_a_combined_source_by_origin(tmp_path):
    rows = [("stock", i, f"s{i}", i) for i in range(4)] + [("cart", i, f"c{i}", i) for i in range(2)]
    _write_csv(tmp_path / "j.csv", ["action", "id", "v", "w"], rows)
    got = {name: df for name, df in ss.iter_entity_chunks(
        {"e": {"file": "j.csv"}}, tmp_path, rows_per_chunk={"e": 10}, only_columns={"e": ["v"]})}
    assert set(got) == {"stock", "cart"}
    assert list(got["stock"].columns) == ["v", SOURCE_COLUMN]
    assert len(got["stock"]) == 4 and len(got["cart"]) == 2


def test_every_chunk_is_indexed_by_the_row_position_in_the_file(tmp_path):
    # Data row k of the file (the header is not one) has index k - 1, in every chunk
    # and in every origin of a combined file: errors are reported by that position.
    _write_csv(tmp_path / "a.csv", ["id"], [(i,) for i in range(7)])
    _write_csv(tmp_path / "j.csv", ["action", "id"],
               [("b" if i % 3 == 0 else "a", i) for i in range(7)])
    plain = [list(df.index) for _, df in ss.iter_entity_chunks(
        {"a": "a.csv"}, tmp_path, rows_per_chunk={"a": 3})]
    assert plain == [[0, 1, 2], [3, 4, 5], [6]]
    by_origin = {}
    for name, df in ss.iter_entity_chunks(
            {"e": {"file": "j.csv"}}, tmp_path, rows_per_chunk={"e": 3}):
        by_origin.setdefault(name, []).extend(df.index)
    assert by_origin == {"a": [1, 2, 4, 5], "b": [0, 3, 6]}
