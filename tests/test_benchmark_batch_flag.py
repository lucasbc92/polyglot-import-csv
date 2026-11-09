"""``--batch-sizes`` of scripts/run_benchmarks.py: an axis of the matrix, like ``--chunk-sizes``.

The write batch is one of the two sizes the automatic choice will set, so a campaign
must be able to sweep it; each labeled run also records the free memory it started with.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_benchmarks as rb  # noqa: E402

from polyglotimportcsv import benchmark_runner as brun  # noqa: E402
from polyglotimportcsv.import_plan import DEFAULT_BATCH_LINES, MAX_BATCH_LINES, MIN_BATCH_LINES  # noqa: E402


def _run_main(monkeypatch, tmp_path, argv):
    captured = {}

    def fake_matrix(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(rb, "run_matrix", fake_matrix)
    code = rb.main([*argv, "--sizes", "1000", "--only", "postgres",
                    "--out", str(tmp_path / "out")])
    assert code == 0
    return captured


def _saved_metadata(tmp_path):
    (path,) = (tmp_path / "out").glob("benchmark_run_*.json")
    return json.loads(path.read_text(encoding="utf-8"))["metadata"]


def test_batch_sizes_default_to_the_default_batch(monkeypatch, tmp_path):
    captured = _run_main(monkeypatch, tmp_path, [])
    assert captured["batch_sizes"] == [DEFAULT_BATCH_LINES] == [2048]
    assert _saved_metadata(tmp_path)["batch_sizes"] == [2048]


def test_batch_sizes_flag_becomes_a_list_of_ints(monkeypatch, tmp_path):
    captured = _run_main(monkeypatch, tmp_path, ["--batch-sizes", "512,8192"])
    assert captured["batch_sizes"] == [512, 8192]
    assert _saved_metadata(tmp_path)["batch_sizes"] == [512, 8192]


def _matrix(tmp_path, seen, *, chunk_sizes=(128,), batch_sizes=(2048,)):
    def importer(config_path, *, chunk_size_mb, batch_size, **kwargs):
        seen.append((chunk_size_mb, batch_size))
        return []

    return brun.run_matrix(
        sizes=[10], modes=["multi"], repetitions=1,
        chunk_sizes=chunk_sizes, batch_sizes=batch_sizes,
        dbms_config_path=None, config_dir="data/ecommerce", data_dir=tmp_path,
        seed=1, only=["postgres"], cleaners={},
        importer=importer, load_cfg=lambda c, s: {"postgres": {}},
        generate=lambda out_dir, rows, seed, mode: None,
    )


def test_run_matrix_accepts_the_batch_limits_and_rejects_beyond(tmp_path):
    assert (MIN_BATCH_LINES, MAX_BATCH_LINES) == (512, 8192)
    seen = []
    _matrix(tmp_path, seen, batch_sizes=[512, 8192])
    assert seen == [(128, 512), (128, 8192)]
    for bad in (511, 8193):
        with pytest.raises(ValueError, match=r"batch size\(s\) out of range"):
            _matrix(tmp_path, seen, batch_sizes=[bad])
    assert seen == [(128, 512), (128, 8192)]  # nothing ran


def test_the_matrix_crosses_chunks_and_batches_and_labels_each_run(tmp_path, monkeypatch):
    monkeypatch.setattr(brun, "available_mb", lambda: 1234.5)
    seen = []
    labeled = _matrix(tmp_path, seen, chunk_sizes=(16, 64), batch_sizes=(512, 4096))
    assert seen == [(16, 512), (16, 4096), (64, 512), (64, 4096)]
    assert [(r["chunk_mb"], r["batch_lines"]) for r in labeled] == seen
    assert {r["free_memory_mb"] for r in labeled} == {1234.5}
