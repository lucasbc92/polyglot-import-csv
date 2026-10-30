"""Median aggregation + consolidated benchmark output (spec §3.2, §3.4)."""

import csv
import json

import pytest

from polyglotimportcsv import benchmark_results as br


def _run(size, mode, rep, seconds, peak=12.5):
    return {
        "size": size, "mode": mode,
        "chunk_mb": 8, "peak_memory_mb": peak, "repetition": rep,
        "records": [{
            "backend": "postgres", "entity": "products", "phase": "write",
            "rows": 100, "seconds": seconds, "rows_per_second": 100 / seconds,
        }],
    }


def test_median_across_repetitions():
    runs = [_run(1000, "multi", 0, 0.2), _run(1000, "multi", 1, 0.4), _run(1000, "multi", 2, 0.3)]
    results = br.median_results(runs)
    assert len(results) == 1
    r = results[0]
    assert r["size"] == 1000 and r["mode"] == "multi"
    assert r["backend"] == "postgres" and r["entity"] == "products" and r["phase"] == "write"
    assert r["rows"] == 100
    assert r["median_seconds"] == 0.3
    assert abs(r["rows_per_second"] - 100 / 0.3) < 1e-9
    assert r["chunk_mb"] == 8


def test_chunk_mb_and_peak_memory_flow_to_results_and_csv(tmp_path):
    # Same key across reps with differing peaks -> median peak; chunk size kept.
    runs = [_run(1000, "multi", 0, 0.2, peak=10.0),
            _run(1000, "multi", 1, 0.2, peak=20.0),
            _run(1000, "multi", 2, 0.2, peak=15.0)]
    results = br.median_results(runs)
    assert len(results) == 1
    assert results[0]["chunk_mb"] == 8
    assert results[0]["peak_memory_mb"] == 15.0

    meta = {"timestamp": "t"}
    _, csv_path = br.write_consolidated(results, meta, out_dir=tmp_path)
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["chunk_mb"] == "8"
    assert rows[0]["peak_memory_mb"] == "15.0"


def test_distinct_chunk_mb_kept_separate():
    a = _run(1000, "multi", 0, 0.2)
    b = _run(1000, "multi", 0, 0.2)
    b["chunk_mb"] = 64
    results = br.median_results([a, b])
    assert {r["chunk_mb"] for r in results} == {8, 64}


def test_distinct_size_mode_kept_separate():
    runs = [_run(1000, "multi", 0, 0.2), _run(1000, "combined", 0, 0.5)]
    results = br.median_results(runs)
    keys = {(r["size"], r["mode"]) for r in results}
    assert keys == {(1000, "multi"), (1000, "combined")}


def test_write_consolidated(tmp_path):
    results = br.median_results([_run(1000, "multi", 0, 0.25)])
    meta = {"timestamp": "2026-07-19T10:00:00", "python": "3.11.0"}
    json_path, csv_path = br.write_consolidated(results, meta, out_dir=tmp_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["metadata"]["python"] == "3.11.0"
    assert data["results"][0]["phase"] == "write"
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["size"] == "1000"
    assert rows[0]["mode"] == "multi"
    assert rows[0]["timestamp"] == "2026-07-19T10:00:00"


def test_csv_appends(tmp_path):
    results = br.median_results([_run(1000, "multi", 0, 0.25)])
    meta = {"timestamp": "t"}
    br.write_consolidated(results, meta, out_dir=tmp_path)
    _, csv_path = br.write_consolidated(results, meta, out_dir=tmp_path)
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3  # header + two runs


def test_group_order_preserved():
    # Deliberate non-alphabetical order: redis before postgres, orders before
    # products, write before read. median_results must preserve first-seen
    # group order (via the `order` list), not fall back to dict/set iteration.
    run = {
        "size": 1000, "mode": "multi",
        "chunk_mb": 8, "peak_memory_mb": 8.0, "repetition": 0,
        "records": [
            {"backend": "redis", "entity": "orders", "phase": "write",
             "rows": 50, "seconds": 0.1, "rows_per_second": 500.0},
            {"backend": "postgres", "entity": "products", "phase": "write",
             "rows": 100, "seconds": 0.2, "rows_per_second": 500.0},
            {"backend": "redis", "entity": "customers", "phase": "read",
             "rows": 20, "seconds": 0.05, "rows_per_second": 400.0},
        ],
    }
    results = br.median_results([run])
    order = [(r["backend"], r["entity"], r["phase"]) for r in results]
    assert order == [
        ("redis", "orders", "write"),
        ("postgres", "products", "write"),
        ("redis", "customers", "read"),
    ]


def test_result_fields_have_no_strategy_column():
    assert "strategy" not in br._RESULT_FIELDS


@pytest.mark.parametrize("header", [
    # before the strategy column was removed
    "timestamp,size,mode,strategy,execution,backend,entity,phase,rows,"
    "median_seconds,rows_per_second,peak_memory_mb",
    # before the execution column became chunk_mb
    "timestamp,size,mode,execution,backend,entity,phase,rows,"
    "median_seconds,rows_per_second,peak_memory_mb",
])
def test_appending_to_a_csv_with_the_old_header_is_refused_and_leaves_it_intact(
        tmp_path, header):
    old = tmp_path / "benchmark_results.csv"
    content = header + "\n2026-08-01,1000,multi,stream,(stream),*,write,10,1.0,10.0,5.0\n"
    old.write_text(content, encoding="utf-8")
    results = br.median_results([_run(1000, "multi", 0, 0.2)])

    with pytest.raises(ValueError, match="header mismatch"):
        br.write_consolidated(results, {"timestamp": "t"}, out_dir=tmp_path)
    assert old.read_text(encoding="utf-8") == content
