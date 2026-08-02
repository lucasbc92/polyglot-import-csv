"""The tracemalloc A/B: aggregation is pure, and the runner honors trace_memory."""

import sys
import tracemalloc
from pathlib import Path

import pytest

from polyglotimportcsv import benchmark_runner as brun

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import benchmark_tracemalloc_ab as ab  # noqa: E402


def _run(execution, seconds, *, phase="write"):
    return {
        "execution": execution,
        "records": [{"backend": "postgres", "entity": "products",
                     "phase": phase, "rows": 10, "seconds": seconds}],
    }


def test_reported_seconds_sums_the_reported_phases():
    run = {"records": [
        {"phase": "read", "seconds": 1.0},
        {"phase": "map", "seconds": 2.0},
        {"phase": "write", "seconds": 3.0},
    ]}
    assert ab.reported_seconds(run) == 6.0


def test_reported_seconds_ignores_excluded_phases():
    # `filter` is out of the report, so it must be out of the comparison too.
    run = {"records": [
        {"phase": "filter", "seconds": 5.0},
        {"phase": "write", "seconds": 3.0},
    ]}
    assert ab.reported_seconds(run) == 3.0


def test_summarize_reports_overhead_per_execution():
    traced = [_run("materialize", 1.2), _run("stream", 2.0)]
    untraced = [_run("materialize", 1.0), _run("stream", 1.0)]

    rows = {r["execution"]: r for r in ab.summarize(traced, untraced)}

    assert rows["materialize"]["overhead_pct"] == pytest.approx(20.0)
    assert rows["stream"]["overhead_pct"] == pytest.approx(100.0)
    assert rows["materialize"]["traced_seconds"] == 1.2
    assert rows["materialize"]["untraced_seconds"] == 1.0


def test_summarize_takes_the_median_across_passes():
    traced = [_run("stream", 5.0), _run("stream", 2.0), _run("stream", 2.0)]
    untraced = [_run("stream", 1.0), _run("stream", 1.0), _run("stream", 4.0)]

    [row] = ab.summarize(traced, untraced)

    assert row["traced_seconds"] == 2.0  # the 5.0 outlier is discarded
    assert row["untraced_seconds"] == 1.0


def test_summarize_handles_a_missing_arm():
    [row] = ab.summarize([_run("stream", 2.0)], [])
    assert row["untraced_seconds"] is None and row["overhead_pct"] is None


def test_summarize_handles_a_zero_untraced_median():
    [row] = ab.summarize([_run("stream", 2.0)], [_run("stream", 0.0)])
    assert row["overhead_pct"] is None  # no division by zero


def test_main_alternates_the_arms_across_passes(monkeypatch, capsys):
    """Both arms must share the warm-up.

    Running every traced pass and then every untraced one would leave the second
    arm systematically warmer, and the measured 'overhead' would include that.
    """
    calls = []

    def fake_run_matrix(*, trace_memory, executions, repetitions, **kwargs):
        calls.append(trace_memory)
        assert repetitions == 1  # one pass per call, so the arms can interleave
        return [_run(e, 1.0) for e in executions]

    monkeypatch.setattr(ab, "run_matrix", fake_run_matrix)
    rc = ab.main(["--size", "10", "--repetitions", "3", "--only", "postgres"])

    assert rc == 0
    # pass 1 traced-first, pass 2 untraced-first, pass 3 traced-first again
    assert calls == [True, False, False, True, True, False]
    out = capsys.readouterr().out
    assert "materialize" in out and "stream" in out


def test_run_matrix_without_trace_memory_does_not_trace(tmp_path):
    tracing = []

    def fake_importer(config_path, *, sgbd_config_path, collector, show_data,
                      only, create_schema, source_overrides, strategy, execution):
        tracing.append(tracemalloc.is_tracing())
        collector.record("postgres", "products", "write", rows=100, seconds=0.1)
        return []

    labeled = brun.run_matrix(
        sizes=[1000], modes=["multi"], repetitions=1,
        sgbd_config_path=None, config_dir="data/ecommerce", data_dir=tmp_path,
        seed=1, only=["postgres"], cleaners={},
        importer=fake_importer, load_cfg=lambda c, s: {"postgres": {}},
        generate=lambda out_dir, rows, seed, mode: None,
        trace_memory=False,
    )

    assert tracing == [False]  # the import ran without the allocation hook
    assert labeled[0]["peak_memory_mb"] is None


def test_run_matrix_traces_by_default(tmp_path):
    tracing = []

    def fake_importer(config_path, *, sgbd_config_path, collector, show_data,
                      only, create_schema, source_overrides, strategy, execution):
        tracing.append(tracemalloc.is_tracing())
        _ = [0] * 200_000  # allocate inside the traced region so peak > 0
        collector.record("postgres", "products", "write", rows=100, seconds=0.1)
        return []

    labeled = brun.run_matrix(
        sizes=[1000], modes=["multi"], repetitions=1,
        sgbd_config_path=None, config_dir="data/ecommerce", data_dir=tmp_path,
        seed=1, only=["postgres"], cleaners={},
        importer=fake_importer, load_cfg=lambda c, s: {"postgres": {}},
        generate=lambda out_dir, rows, seed, mode: None,
    )

    assert tracing == [True]
    assert labeled[0]["peak_memory_mb"] > 0
