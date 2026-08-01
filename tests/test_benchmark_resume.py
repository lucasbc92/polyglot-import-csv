"""Resuming an interrupted matrix from its checkpoint.

A full matrix runs for tens of minutes; a crash on run N used to mean re-measuring
the N-1 runs that already succeeded.
"""

import json
import sys
from pathlib import Path

import pytest

from polyglotimportcsv import benchmark_runner as brun

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_benchmarks as rb  # noqa: E402


def _labeled(size, mode, execution, repetition, *, strategy="optimized", seconds=1.0):
    return {
        "size": size, "mode": mode, "strategy": strategy,
        "execution": execution, "repetition": repetition,
        "peak_memory_mb": 1.0,
        "records": [{"backend": "postgres", "entity": "products",
                     "phase": "write", "rows": 10, "seconds": seconds}],
    }


def _matrix(tmp_path, seen, **kwargs):
    def fake_importer(config_path, *, sgbd_config_path, collector, show_data,
                      only, create_schema, source_overrides, strategy, execution):
        seen.append(execution)
        collector.record("postgres", "products", "write", rows=10, seconds=0.1)
        return []

    return brun.run_matrix(
        sizes=[1000], modes=["multi"], repetitions=2,
        executions=["materialize", "stream"],
        sgbd_config_path=None, config_dir="data/ecommerce", data_dir=tmp_path,
        seed=1, only=["postgres"], cleaners={},
        importer=fake_importer, load_cfg=lambda c, s: {"postgres": {}},
        generate=lambda out_dir, rows, seed, mode: None,
        **kwargs,
    )


def test_completed_runs_are_not_measured_again(tmp_path):
    already = [
        _labeled(1000, "multi", "materialize", 0),
        _labeled(1000, "multi", "stream", 0),
    ]
    seen = []

    _matrix(tmp_path, seen, completed=already)

    # Pass 0 was already done; only pass 1's two cells still run.
    assert seen == ["materialize", "stream"]


def test_completed_runs_are_carried_into_the_result(tmp_path):
    already = [_labeled(1000, "multi", "materialize", 0, seconds=42.0)]
    seen = []

    labeled = _matrix(tmp_path, seen, completed=already)

    assert len(labeled) == 4  # 2 executions x 2 repetitions, nothing lost
    carried = [r for r in labeled if r["records"][0]["seconds"] == 42.0]
    assert len(carried) == 1  # the resumed measurement, not re-run


def test_checkpoints_written_during_a_resume_include_the_earlier_runs(tmp_path):
    already = [_labeled(1000, "multi", "materialize", 0)]
    sizes_seen = []
    seen = []

    _matrix(tmp_path, seen, completed=already,
            on_run=lambda labeled: sizes_seen.append(len(labeled)))

    # A second crash must not discard what the first run had already banked.
    assert sizes_seen[0] == 2  # 1 carried + 1 just measured
    assert sizes_seen == [2, 3, 4]


def test_resume_reads_runs_whose_axes_match(tmp_path):
    meta = {"seed": 42, "sizes": [1000], "modes": ["multi"],
            "strategies": ["optimized"], "executions": ["stream"], "repetitions": 3}
    path = tmp_path / rb.CHECKPOINT_NAME
    runs = [_labeled(1000, "multi", "stream", 0)]
    path.write_text(json.dumps({"metadata": meta, "runs": runs}), encoding="utf-8")

    assert rb.resume_runs(path, dict(meta)) == runs


def test_resume_without_a_checkpoint_starts_fresh(tmp_path):
    assert rb.resume_runs(tmp_path / rb.CHECKPOINT_NAME, {"seed": 1}) == []


def test_resume_refuses_a_checkpoint_from_a_different_matrix(tmp_path):
    meta = {"seed": 42, "sizes": [1000], "modes": ["multi"],
            "strategies": ["optimized"], "executions": ["stream"], "repetitions": 3}
    path = tmp_path / rb.CHECKPOINT_NAME
    path.write_text(
        json.dumps({"metadata": meta, "runs": [_labeled(1000, "multi", "stream", 0)]}),
        encoding="utf-8",
    )

    # Silently mixing runs from two different matrices would corrupt the medians.
    with pytest.raises(ValueError, match="seed"):
        rb.resume_runs(path, dict(meta, seed=7))


def test_resume_names_every_axis_that_differs(tmp_path):
    meta = {"seed": 42, "sizes": [1000], "modes": ["multi"],
            "strategies": ["optimized"], "executions": ["stream"], "repetitions": 3}
    path = tmp_path / rb.CHECKPOINT_NAME
    path.write_text(json.dumps({"metadata": meta, "runs": []}), encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        rb.resume_runs(path, dict(meta, sizes=[1000, 10000], executions=["materialize"]))

    msg = str(excinfo.value)
    assert "sizes" in msg and "executions" in msg


def test_a_crashing_matrix_is_recorded_in_the_session_log(tmp_path, monkeypatch):
    # The crash that ends a tens-of-minutes matrix used to reach stderr only, so
    # the session log stopped mid-run with no trace of why.
    from polyglotimportcsv import reporting

    log_dir = tmp_path / "logs"
    # This test is about the session log file, so opt out of conftest's no-log
    # default -- writing under tmp_path, never the repo's logs/.
    monkeypatch.delenv("POLYGLOT_NO_LOG", raising=False)
    monkeypatch.setattr(
        rb, "setup_reporting",
        lambda level: reporting.setup_reporting(level, log_dir=log_dir),
    )

    def boom(**kwargs):
        raise RuntimeError("kaboom-in-the-matrix")

    monkeypatch.setattr(rb, "run_matrix", boom)

    try:
        code = rb.main(["--sizes", "1000", "--only", "postgres",
                        "--out", str(tmp_path / "out")])
    finally:
        reporting.reset()

    assert code == 1
    logged = "\n".join(p.read_text(encoding="utf-8") for p in log_dir.glob("*.log"))
    assert "kaboom-in-the-matrix" in logged
    assert "Traceback" in logged
