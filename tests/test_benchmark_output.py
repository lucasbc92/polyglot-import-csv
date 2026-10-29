"""--benchmark: benchmark_<timestamp>.json + consolidatable CSV (spec §4.4)."""

import json
from pathlib import Path

import pytest

from polyglotimportcsv import metrics
from polyglotimportcsv.benchmark_io import write_json_and_csv
from polyglotimportcsv.metrics import MetricsCollector
from polyglotimportcsv.runner import run_import

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "data" / "ecommerce" / "import_config.json"


def _collector():
    c = MetricsCollector()
    c.record("postgres", "items", "write", rows=10, seconds=0.5)
    return c


def test_write_benchmark_files(tmp_path):
    meta = metrics.environment_metadata(Path("cfg.json"), {"stock": 10})
    json_path, csv_path = metrics.write_benchmark_files(_collector(), meta, out_dir=tmp_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["metadata"]["python"]
    assert data["metadata"]["source_rows"] == {"stock": 10}
    assert data["metrics"][0]["phase"] == "write"
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "timestamp,backend,entity,phase,rows,seconds,rows_per_second"
    assert len(lines) == 2


def test_benchmark_csv_appends_history(tmp_path):
    meta = metrics.environment_metadata(Path("cfg.json"), {})
    metrics.write_benchmark_files(_collector(), meta, out_dir=tmp_path)
    _, csv_path = metrics.write_benchmark_files(_collector(), meta, out_dir=tmp_path)
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3  # one header + two runs


def test_run_import_benchmark_writes_files_and_suppresses_dump(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    run_import(CFG, dry_run=True, only=["postgres"], show_data=True, benchmark=True)

    out_dir = tmp_path / "benchmarks"
    [json_path] = out_dir.glob("benchmark_*.json")
    assert (out_dir / "benchmark_history.csv").is_file()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert [m["phase"] for m in data["metrics"]] == ["infer", "validate"]
    out = capsys.readouterr().out
    assert "Benchmark JSON" in out
    assert "postgres · " not in out  # --benchmark implies --no-data, even over --show-data


def test_append_to_mismatched_header_raises(tmp_path):
    csv_path = tmp_path / "r.csv"
    csv_path.write_text("timestamp,size,mode\n", encoding="utf-8")
    with pytest.raises(ValueError, match="header"):
        write_json_and_csv(
            tmp_path, {"timestamp": "t"},
            [{"size": 1, "mode": "multi", "extra": "x"}],
            json_prefix="j", csv_name="r.csv",
            csv_fields=("timestamp", "size", "mode", "extra"),
            payload_key="results",
        )


def test_mismatched_header_writes_nothing(tmp_path):
    # The header check used to run after the JSON was written, leaving a stray
    # run file next to a CSV that refused the rows.
    csv_path = tmp_path / "r.csv"
    content = "timestamp,size,mode\n1,1000,multi\n"
    csv_path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="CSV header mismatch"):
        write_json_and_csv(
            tmp_path, {"timestamp": "t"},
            [{"size": 1, "mode": "multi", "extra": "x"}],
            json_prefix="j", csv_name="r.csv",
            csv_fields=("timestamp", "size", "mode", "extra"),
            payload_key="results",
        )
    assert list(tmp_path.glob("j_*.json")) == []
    assert csv_path.read_text(encoding="utf-8") == content
