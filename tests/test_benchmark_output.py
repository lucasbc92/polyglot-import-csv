"""--benchmark: benchmark_<timestamp>.json + consolidatable CSV (spec §4.4)."""

import json
from pathlib import Path

from polyglotimportcsv import metrics
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


def test_run_import_benchmark_writes_files_and_suppresses_dump(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    forces = []
    monkeypatch.setattr(
        "polyglotimportcsv.runner.dump_entity_frame",
        lambda b, e, df, *, force=None: forces.append(force),
    )

    def stub(cfg, entities, *, dry_run, create_schema):
        return ["[postgres] stub"]

    run_import(CFG, dry_run=True, only=["postgres"], importers={"postgres": stub}, benchmark=True)
    assert forces and all(f is False for f in forces)
    out = tmp_path / "benchmarks"
    assert list(out.glob("benchmark_*.json"))
    assert (out / "benchmark_history.csv").is_file()
