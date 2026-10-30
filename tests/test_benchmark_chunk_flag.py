"""``--chunk-sizes`` of scripts/run_benchmarks.py reaches the matrix and its metadata.

The sizes are an axis of the matrix and part of its resume identity (``RESUME_KEYS``), so
the list the matrix measures and the one the results record must be the one asked for.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_benchmarks as rb  # noqa: E402

from polyglotimportcsv import benchmark_runner as brun  # noqa: E402
from polyglotimportcsv.stream_source import DEFAULT_CHUNK_MB, MAX_CHUNK_MB, MIN_CHUNK_MB  # noqa: E402


def _run_main(monkeypatch, tmp_path, argv):
    """Call rb.main with run_matrix stubbed; return the kwargs it was given."""
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


def test_chunk_sizes_default_to_the_default_block(monkeypatch, tmp_path):
    captured = _run_main(monkeypatch, tmp_path, [])
    assert captured["chunk_sizes"] == [DEFAULT_CHUNK_MB] == [8]
    assert _saved_metadata(tmp_path)["chunk_sizes"] == [8]


def test_chunk_sizes_flag_becomes_a_list_of_ints_for_the_matrix(monkeypatch, tmp_path):
    captured = _run_main(monkeypatch, tmp_path, ["--chunk-sizes", "8,64"])
    assert captured["chunk_sizes"] == [8, 64]


def test_chunk_sizes_are_recorded_in_the_saved_metadata(monkeypatch, tmp_path):
    _run_main(monkeypatch, tmp_path, ["--chunk-sizes", "8,64"])
    assert _saved_metadata(tmp_path)["chunk_sizes"] == [8, 64]


def _matrix(tmp_path, chunk_sizes, seen):
    def importer(config_path, *, chunk_size_mb, **kwargs):
        seen.append(chunk_size_mb)
        return []

    return brun.run_matrix(
        sizes=[10], modes=["multi"], repetitions=1, chunk_sizes=chunk_sizes,
        dbms_config_path=None, config_dir="data/ecommerce", data_dir=tmp_path,
        seed=1, only=["postgres"], cleaners={},
        importer=importer, load_cfg=lambda c, s: {"postgres": {}},
        generate=lambda out_dir, rows, seed, mode: None,
    )


def test_run_matrix_accepts_the_largest_block_and_rejects_the_next(tmp_path):
    assert (MIN_CHUNK_MB, MAX_CHUNK_MB) == (8, 256)
    seen = []
    _matrix(tmp_path, [MIN_CHUNK_MB, MAX_CHUNK_MB], seen)
    assert seen == [8, 256]
    with pytest.raises(ValueError, match=r"chunk size\(s\) out of range: 257"):
        _matrix(tmp_path, [MAX_CHUNK_MB + 1], seen)
    assert seen == [8, 256]  # nothing ran
