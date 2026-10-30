"""Whole-file type profile of every declared source, built in one chunked read.

The profile is what binding and validation trust instead of a first-chunk sample, so
these pin that a value far past the first chunk still counts, that an origin first
seen late gets its own profile, and that the verdict of a column the chunks disagreed
on is settled by an exact re-read (and only then).
"""

import pandas as pd
import pytest

from polyglotimportcsv.business_exception import SourceError
from polyglotimportcsv.csv_reader import ColumnStats, infer_column_kinds, read_csv
from polyglotimportcsv.source_profile import SourceProfile, profile_sources, union_kinds

#: 90% dates, but the first 300 values are junk: the first chunks are dirty, the rest clean.
DIRTY_BLOCK_THEN_DATES = ["n/a"] * 300 + (
    pd.date_range("2023-01-01", periods=2700, freq="min").strftime("%Y-%m-%dT%H:%M:%SZ").tolist()
)


#: 2000 distinct ISO datetimes, to be shared out between sources.
DATES = pd.date_range("2023-01-01", periods=2000, freq="min").strftime("%Y-%m-%dT%H:%M:%SZ").tolist()
CLEAN = DATES[:1000]                                                          # all dates
DIRTY = [f"junk-{i}" if i % 5 == 0 else DATES[1000 + i] for i in range(1000)]  # 80% dates
# Alone, CLEAN is a datetime and DIRTY is a string; together 90% parse, so a datetime. With
# small probe rounds each is decided on its own bounds while the merged bounds straddle the
# threshold, so only exact counts say what the concatenated column is.


def _write_csv(path, header, rows):
    path.write_text(",".join(header) + "\n" +
                    "".join(",".join(str(c) for c in r) + "\n" for r in rows),
                    encoding="utf-8")


def _stats(*values):
    st = ColumnStats()
    st.update(pd.Series(list(values), dtype=str))
    return st


def _profile(name, **columns):
    return SourceProfile(
        name=name, declared=name, path=None, header=list(columns), rows=1,
        stats={c: _stats(*v) for c, v in columns.items()},
    )


def test_whole_file_inference_sees_a_value_past_the_first_chunk(tmp_path):
    flags = ["true", "false"] * 1500 + ["maybe"]
    _write_csv(tmp_path / "s.csv", ["id", "flag"], [(i, f) for i, f in enumerate(flags)])
    prof = profile_sources({"s": "s.csv"}, tmp_path, {}, {"s": 500})["s"]
    assert prof.kinds["flag"] == "string" and prof.rows == 3001
    assert prof.kinds["id"] == "integer"


def test_the_profile_names_its_file_and_columns(tmp_path):
    _write_csv(tmp_path / "s.csv", ["id", "v"], [(1, "x"), (2, "y")])
    prof = profile_sources({"s": "s.csv"}, tmp_path, {}, {"s": 100})["s"]
    assert (prof.name, prof.declared, prof.path) == ("s", "s", tmp_path / "s.csv")
    assert prof.header == ["id", "v"] and prof.rows == 2
    assert prof.kinds == {"id": "integer", "v": "string"}


def test_a_source_override_replaces_the_declared_file(tmp_path):
    _write_csv(tmp_path / "other.csv", ["k"], [(1,), (2,), (3,)])
    prof = profile_sources({"s": "missing.csv"}, tmp_path, {"s": str(tmp_path / "other.csv")},
                           {"s": 100})["s"]
    assert prof.path == tmp_path / "other.csv" and prof.header == ["k"] and prof.rows == 3


def test_header_only_source_gets_a_zero_row_profile(tmp_path):
    (tmp_path / "s.csv").write_bytes(b"\xef\xbb\xbfa,b\r\n")
    prof = profile_sources({"s": "s.csv"}, tmp_path, {}, {"s": 100})["s"]
    assert prof.rows == 0 and prof.header == ["a", "b"] and prof.kinds["a"] == "empty"


def test_combined_origin_first_seen_after_many_chunks(tmp_path):
    rows = [("stock", i, f"s{i}") for i in range(2000)] + [("purchase", i, f"p{i}") for i in range(10)]
    _write_csv(tmp_path / "j.csv", ["action", "id", "v"], rows)
    profs = profile_sources({"e": {"file": "j.csv"}}, tmp_path, {}, {"e": 100})
    assert set(profs) == {"stock", "purchase"}
    assert profs["stock"].rows == 2000 and profs["purchase"].rows == 10
    assert profs["purchase"].declared == "e" and profs["purchase"].path == tmp_path / "j.csv"
    assert profs["purchase"].header == ["id", "v"]  # the origin column is not data
    assert profs["purchase"].kinds == {"id": "integer", "v": "string"}


def test_a_combined_file_without_rows_has_no_origin_profiles(tmp_path):
    (tmp_path / "j.csv").write_text("action,id\n", encoding="utf-8")
    assert profile_sources({"e": {"file": "j.csv"}}, tmp_path, {}, {"e": 100}) == {}


def test_a_combined_file_with_an_empty_origin_is_rejected(tmp_path):
    _write_csv(tmp_path / "j.csv", ["action", "id"], [("stock", 1), (" ", 2)])
    with pytest.raises(SourceError, match="empty origin value"):
        profile_sources({"e": {"file": "j.csv"}}, tmp_path, {}, {"e": 100})


def test_plain_and_combined_sources_are_profiled_together(tmp_path):
    _write_csv(tmp_path / "c.csv", ["id"], [(1,), (2,)])
    _write_csv(tmp_path / "j.csv", ["action", "id"], [("stock", 1), ("purchase", 2)])
    profs = profile_sources({"cart": "c.csv", "e": {"file": "j.csv"}}, tmp_path, {},
                            {"cart": 100, "e": 100})
    assert {n: p.declared for n, p in profs.items()} == {"cart": "cart", "stock": "e", "purchase": "e"}


def test_undecided_column_is_resolved_by_an_exact_reread(tmp_path, small_probe_rounds, reads):
    _write_csv(tmp_path / "s.csv", ["id", "d"], list(enumerate(DIRTY_BLOCK_THEN_DATES)))
    prof = profile_sources({"s": "s.csv"}, tmp_path, {}, {"s": 500})["s"]
    whole = read_csv(tmp_path / "s.csv")
    assert prof.stats["d"].decided()
    assert prof.kinds["d"] == infer_column_kinds(whole)["d"] == "datetime"
    assert prof.rows == 3000 and prof.kinds["id"] == "integer"
    # the second read took only the open column, in blocks of the same size
    assert reads == [("s.csv", None), ("s.csv", ["d"])]


def test_the_profile_does_not_depend_on_the_chunk_size(tmp_path, small_probe_rounds):
    _write_csv(tmp_path / "s.csv", ["id", "d"], list(enumerate(DIRTY_BLOCK_THEN_DATES)))
    one_chunk = profile_sources({"s": "s.csv"}, tmp_path, {}, {"s": 3000})["s"]
    chunked = profile_sources({"s": "s.csv"}, tmp_path, {}, {"s": 500})["s"]
    assert (chunked.rows, chunked.kinds) == (one_chunk.rows, one_chunk.kinds)
    assert chunked.stats["id"] == one_chunk.stats["id"]


def test_undecided_column_of_a_combined_file_is_resolved_for_every_origin(
    tmp_path, small_probe_rounds, reads
):
    rows = [("stock", i, d) for i, d in enumerate(DIRTY_BLOCK_THEN_DATES)] + [
        ("cart", i, "2023-05-05T00:00:00Z") for i in range(20)
    ]
    _write_csv(tmp_path / "j.csv", ["action", "id", "d"], rows)
    profs = profile_sources({"e": {"file": "j.csv"}}, tmp_path, {}, {"e": 500})
    whole = read_csv(tmp_path / "j.csv")
    for origin in ("stock", "cart"):
        expected = infer_column_kinds(whole[whole["action"] == origin])
        assert profs[origin].kinds == {"id": expected["id"], "d": expected["d"]}
        assert profs[origin].stats["d"].decided()
    assert profs["stock"].kinds["d"] == "datetime"
    # the origin column came along, to route the rows of the second read
    assert reads[0] == ("j.csv", None)
    assert len(reads) == 2 and reads[1][0] == "j.csv" and set(reads[1][1]) == {"action", "d"}


def test_no_reread_when_every_column_is_decided(tmp_path, reads):
    _write_csv(tmp_path / "a.csv", ["id", "name"], [(i, f"n{i}") for i in range(300)])
    _write_csv(tmp_path / "j.csv", ["action", "id"], [("stock", i) for i in range(300)])
    profile_sources({"a": "a.csv", "e": {"file": "j.csv"}}, tmp_path, {}, {"a": 100, "e": 100})
    assert reads == [("a.csv", None), ("j.csv", None)]


def test_origin_equal_to_a_declared_name_collides(tmp_path):
    _write_csv(tmp_path / "s.csv", ["id"], [(1,)])
    _write_csv(tmp_path / "j.csv", ["action", "id"], [("s", 1)])
    with pytest.raises(SourceError, match="Source name collision: 's'"):
        profile_sources({"s": "s.csv", "e": {"file": "j.csv"}}, tmp_path, {}, {"s": 10, "e": 10})


def test_origin_equal_to_its_own_combined_name_collides(tmp_path):
    _write_csv(tmp_path / "j.csv", ["action", "id"], [("e", 1)])
    with pytest.raises(SourceError, match="Source name collision: 'e'"):
        profile_sources({"e": {"file": "j.csv"}}, tmp_path, {}, {"e": 10})


def test_the_same_origin_in_two_combined_files_collides(tmp_path):
    _write_csv(tmp_path / "j1.csv", ["action", "id"], [("stock", 1)])
    _write_csv(tmp_path / "j2.csv", ["action", "id"], [("stock", 2)])
    with pytest.raises(SourceError, match="Source name collision: 'stock'"):
        profile_sources({"e1": {"file": "j1.csv"}, "e2": {"file": "j2.csv"}}, tmp_path, {},
                        {"e1": 10, "e2": 10})


def test_union_kinds_merge_whole_file_stats():
    a = _profile("a", n=["1", "2"], only_a=["x"])
    b = _profile("b", n=["1.5", "2"], only_b=["true", "false"])
    assert union_kinds([a, b], ["n", "only_a", "only_b"]) == {
        "n": "float", "only_a": "string", "only_b": "boolean",
    }
    assert union_kinds([a], ["n", "only_b"]) == {"n": "integer", "only_b": "empty"}


def test_union_kinds_ignore_a_profile_whose_column_is_blank():
    a = _profile("a", n=["", ""])
    b = _profile("b", n=["1", "2"])
    assert union_kinds([a, b], ["n"]) == {"n": "integer"}
    assert union_kinds([a], ["n"]) == {"n": "empty"}


def _whole_kind(*parts):
    return infer_column_kinds(pd.DataFrame({"d": pd.Series(sum(parts, []), dtype=str)}))["d"]


def test_a_union_column_undecided_across_sources_is_settled_by_an_exact_reread(
    tmp_path, small_probe_rounds, reads
):
    _write_csv(tmp_path / "a.csv", ["d"], [(v,) for v in CLEAN])
    _write_csv(tmp_path / "b.csv", ["d"], [(v,) for v in DIRTY])
    cfg, args = {"a": "a.csv", "b": "b.csv"}, (tmp_path, {}, {"a": 5000, "b": 5000})
    alone = profile_sources(cfg, *args)
    assert (alone["a"].kinds["d"], alone["b"].kinds["d"]) == ("datetime", "string")
    assert alone["a"].stats["d"].decided() and alone["b"].stats["d"].decided()
    # decided one by one, yet the merged bounds straddle the threshold: provisional "string"
    assert not alone["a"].stats["d"].merged(alone["b"].stats["d"]).decided()
    assert union_kinds(list(alone.values()), ["d"]) == {"d": "string"}

    reads.clear()
    both = profile_sources(cfg, *args, unions=[["a", "b"]])
    assert union_kinds(list(both.values()), ["d"]) == {"d": _whole_kind(CLEAN, DIRTY)} == {"d": "datetime"}
    assert both["a"].stats["d"].merged(both["b"].stats["d"]).decided()
    assert reads == [("a.csv", None), ("b.csv", None), ("a.csv", ["d"]), ("b.csv", ["d"])]
    # their own kinds are still those of their own columns
    assert (both["a"].kinds["d"], both["b"].kinds["d"]) == ("datetime", "string")


def test_a_union_inside_one_combined_file_rereads_it_once_with_its_origin_column(
    tmp_path, small_probe_rounds, reads
):
    rows = [("s", v) for v in CLEAN] + [("p", v) for v in DIRTY]
    _write_csv(tmp_path / "j.csv", ["action", "d"], rows)
    profs = profile_sources({"e": {"file": "j.csv"}}, tmp_path, {}, {"e": 5000}, unions=[["s", "p"]])
    assert union_kinds(list(profs.values()), ["d"]) == {"d": "datetime"}
    assert reads[0] == ("j.csv", None)
    assert len(reads) == 2 and reads[1][0] == "j.csv" and set(reads[1][1]) == {"action", "d"}


def test_each_file_is_reread_once_whatever_number_of_unions_and_columns_need_it(
    tmp_path, small_probe_rounds, reads
):
    _write_csv(tmp_path / "a.csv", ["d", "e"], [(v, v) for v in CLEAN])
    _write_csv(tmp_path / "b.csv", ["d", "e"], [(v, v) for v in DIRTY])
    _write_csv(tmp_path / "c.csv", ["d"], [(v,) for v in DIRTY])
    profs = profile_sources(
        {"a": "a.csv", "b": "b.csv", "c": "c.csv"}, tmp_path, {}, {"a": 5000, "b": 5000, "c": 5000},
        unions=[["a", "b"], ["b", "a"], ["a", "c"]],
    )
    assert [r for r in reads if r[1] is None] == [("a.csv", None), ("b.csv", None), ("c.csv", None)]
    rereads = [(name, sorted(columns)) for name, columns in reads if columns is not None]
    assert rereads == [("a.csv", ["d", "e"]), ("b.csv", ["d", "e"]), ("c.csv", ["d"])]
    assert union_kinds([profs["a"], profs["c"]], ["d"]) == {"d": "datetime"}


def test_a_union_whose_merged_columns_are_all_decided_rereads_nothing(
    tmp_path, small_probe_rounds, reads
):
    _write_csv(tmp_path / "a.csv", ["d", "n", "only_a"], [(v, i, "x") for i, v in enumerate(CLEAN)])
    _write_csv(tmp_path / "b.csv", ["d", "n"], [(v, f"{i}.5") for i, v in enumerate(CLEAN)])
    profs = profile_sources({"a": "a.csv", "b": "b.csv"}, tmp_path, {}, {"a": 5000, "b": 5000},
                            unions=[["a", "b"], ["a"], ["b", "ghost"]])
    assert reads == [("a.csv", None), ("b.csv", None)]
    assert union_kinds(list(profs.values()), ["d", "n", "only_a"]) == {
        "d": "datetime", "n": "float", "only_a": "string",
    }
