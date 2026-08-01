"""Timings and peak memory cannot honestly come from the same run.

tracemalloc traces every allocation, so it inflates allocation-heavy phases far
more than network-bound ones -- measured at 8.6x on the read phase and ~6.5x on
map, against roughly nothing on the database writes. A matrix run under tracing
therefore reports peak_memory_mb correctly and median_seconds distorted, with the
distortion varying per phase. `--no-trace-memory` exists so timings can be
measured in a separate, untraced pass.

Because the two passes are not interchangeable, the tracing mode is part of the
resume identity: a traced checkpoint must not be continued untraced.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_benchmarks as rb  # noqa: E402


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


def test_tracing_is_on_by_default(monkeypatch, tmp_path):
    captured = _run_main(monkeypatch, tmp_path, [])
    assert captured["trace_memory"] is True


def test_no_trace_memory_turns_tracing_off(monkeypatch, tmp_path):
    captured = _run_main(monkeypatch, tmp_path, ["--no-trace-memory"])
    assert captured["trace_memory"] is False


def test_tracing_mode_is_recorded_in_the_run_metadata(tmp_path, monkeypatch):
    """The consolidated output has to say which kind of pass produced it."""
    captured = {}

    def fake_matrix(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(rb, "run_matrix", fake_matrix)
    out = tmp_path / "out"
    rb.main(["--no-trace-memory", "--sizes", "1000", "--only", "postgres",
             "--out", str(out)])
    payload = json.loads(next(out.glob("benchmark_run_*.json")).read_text(encoding="utf-8"))
    assert payload["metadata"]["trace_memory"] is False


def test_resume_refuses_a_checkpoint_measured_with_the_other_tracing_mode(tmp_path):
    meta = {"seed": 42, "sizes": [1000], "modes": ["multi"],
            "strategies": ["optimized"], "executions": ["stream"],
            "repetitions": 3, "trace_memory": True}
    path = tmp_path / rb.CHECKPOINT_NAME
    path.write_text(json.dumps({"metadata": meta, "runs": []}), encoding="utf-8")

    # Continuing a traced matrix untraced would mix distorted and honest timings.
    with pytest.raises(ValueError, match="trace_memory"):
        rb.resume_runs(path, dict(meta, trace_memory=False))


def test_resume_accepts_a_checkpoint_from_the_same_tracing_mode(tmp_path):
    meta = {"seed": 42, "sizes": [1000], "modes": ["multi"],
            "strategies": ["optimized"], "executions": ["stream"],
            "repetitions": 3, "trace_memory": False}
    path = tmp_path / rb.CHECKPOINT_NAME
    path.write_text(json.dumps({"metadata": meta, "runs": []}), encoding="utf-8")
    assert rb.resume_runs(path, dict(meta)) == []


def test_untraced_runs_consolidate_with_an_empty_peak():
    """An untraced run carries peak_memory_mb=None; consolidation must not choke."""
    from polyglotimportcsv.benchmark_results import median_results

    runs = [{"size": 1000, "mode": "multi", "strategy": "optimized",
             "execution": "stream", "repetition": r, "peak_memory_mb": None,
             "records": [{"backend": "postgres", "entity": "p", "phase": "write",
                          "rows": 10, "seconds": 0.1 * (r + 1)}]}
            for r in range(3)]

    out = median_results(runs)
    assert len(out) == 1
    assert out[0]["peak_memory_mb"] is None      # reported as empty, not 0.0
    assert out[0]["median_seconds"] == pytest.approx(0.2)   # timings still land
