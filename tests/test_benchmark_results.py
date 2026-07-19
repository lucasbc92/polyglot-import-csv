"""Median aggregation + consolidated benchmark output (spec §3.2, §3.4)."""

import csv
import json

from polyglotimportcsv import benchmark_results as br


def _run(size, mode, rep, seconds):
    return {
        "size": size, "mode": mode, "repetition": rep,
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
