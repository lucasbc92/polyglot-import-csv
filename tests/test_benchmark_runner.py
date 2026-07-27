"""Matrix orchestration is DB-free via dependency injection."""

from pathlib import Path

import pytest

from polyglotimportcsv import benchmark_data as bdata
from polyglotimportcsv import benchmark_runner as brun
from polyglotimportcsv.benchmark_results import median_results


def _write_csv(path: Path, columns, data_rows: int) -> None:
    """Write a header plus ``data_rows`` filler rows — only the count matters here."""
    path.parent.mkdir(parents=True, exist_ok=True)
    filler = ",".join("x" for _ in columns)
    path.write_text(
        ",".join(columns) + "\n" + (filler + "\n") * data_rows, encoding="utf-8"
    )


def _write_join(path: Path, split) -> None:
    """Write a combined file whose ``action`` column follows ``split``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    filler = ",".join("x" for _ in bdata.JOIN_COLUMNS[1:])
    lines = [",".join(bdata.JOIN_COLUMNS)]
    for action, count in split.items():
        lines.extend(f"{action},{filler}" for _ in range(count))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _recording_generate(calls):
    def generate(out_dir, rows, seed, mode):
        calls.append((Path(out_dir), rows, seed, mode))
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        return {}

    return generate


def test_run_matrix_rejects_unknown_mode(tmp_path):
    with pytest.raises(ValueError, match="unknown mode"):
        brun.run_matrix(
            sizes=[10], modes=["both"], repetitions=1,
            sgbd_config_path=None, config_dir="data/ecommerce", data_dir=tmp_path,
            seed=1, only=["postgres"], cleaners={},
            importer=lambda *a, **k: [], load_cfg=lambda c, s: {"postgres": {}},
            generate=lambda out_dir, rows, seed, mode: None,
        )


def test_run_matrix_rejects_unknown_strategy(tmp_path):
    with pytest.raises(ValueError, match="unknown strategy"):
        brun.run_matrix(
            sizes=[10], modes=["multi"], repetitions=1,
            strategies=["optimised"],  # British-spelling typo: would silently run optimized
            sgbd_config_path=None, config_dir="data/ecommerce", data_dir=tmp_path,
            seed=1, only=["postgres"], cleaners={},
            importer=lambda *a, **k: [], load_cfg=lambda c, s: {"postgres": {}},
            generate=lambda out_dir, rows, seed, mode: None,
        )


def test_run_matrix_iterates_and_cleans_before_import(tmp_path):
    events = []

    def make_cleaner(name):
        def _clean(block):
            events.append(("clean", name))
        return _clean

    cleaners = {"postgres": make_cleaner("postgres")}

    def fake_importer(config_path, *, sgbd_config_path, collector, show_data,
                      only, create_schema, source_overrides, strategy, execution="stream"):
        events.append(("import", str(config_path), tuple(sorted(source_overrides))))
        collector.record("postgres", "products", "write", rows=100, seconds=0.1)
        return []

    def fake_load_cfg(config_path, sgbd_path):
        return {"postgres": {"schema": "public"}}

    def fake_generate(out_dir, rows, seed, mode):
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        return {}

    labeled = brun.run_matrix(
        sizes=[1000], modes=["multi", "combined"], repetitions=2,
        sgbd_config_path="sgbd.json", config_dir="data/ecommerce",
        data_dir=tmp_path, seed=42, only=["postgres"],
        cleaners=cleaners, importer=fake_importer, load_cfg=fake_load_cfg,
        generate=fake_generate,
    )

    # 1 size x 2 modes x 2 reps = 4 labeled runs, each with 1 record
    assert len(labeled) == 4
    assert {(r["size"], r["mode"], r["repetition"]) for r in labeled} == {
        (1000, "multi", 0), (1000, "multi", 1),
        (1000, "combined", 0), (1000, "combined", 1),
    }
    # every import is immediately preceded by a clean
    imp_idx = [i for i, e in enumerate(events) if e[0] == "import"]
    for i in imp_idx:
        assert events[i - 1] == ("clean", "postgres")
    # median aggregation consumes the labeled output
    results = median_results(labeled)
    assert results[0]["rows"] == 100


def test_on_run_fires_after_each_import_and_survives_a_crash(tmp_path):
    seen: list[int] = []

    def fake_importer(config_path, *, sgbd_config_path, collector, show_data,
                      only, create_schema, source_overrides, strategy, execution="stream"):
        collector.record("postgres", "products", "write", rows=100, seconds=0.1)
        if len(seen) == 2:
            raise RuntimeError("backend blew up")
        return []

    with pytest.raises(RuntimeError, match="blew up"):
        brun.run_matrix(
            sizes=[10], modes=["multi"], repetitions=4,
            sgbd_config_path=None, config_dir="data/ecommerce", data_dir=tmp_path,
            seed=1, only=["postgres"], cleaners={},
            importer=fake_importer, load_cfg=lambda c, s: {"postgres": {}},
            generate=lambda out_dir, rows, seed, mode: None,
            on_run=lambda labeled: seen.append(len(labeled)),
        )

    # Called once per completed import, with the runs accumulated so far, so the
    # two measurements taken before the crash are still recoverable.
    assert seen == [1, 2]


def test_run_matrix_builds_mode_overrides(tmp_path):
    seen = []

    def fake_importer(config_path, *, sgbd_config_path, collector, show_data,
                      only, create_schema, source_overrides, strategy, execution="stream"):
        seen.append((Path(config_path).name, set(source_overrides)))
        return []

    brun.run_matrix(
        sizes=[10], modes=["multi", "combined"], repetitions=1,
        sgbd_config_path=None, config_dir="data/ecommerce", data_dir=tmp_path,
        seed=1, only=["postgres"], cleaners={},
        importer=fake_importer, load_cfg=lambda c, s: {"postgres": {}},
        generate=lambda out_dir, rows, seed, mode: None,
    )
    by_name = dict(seen)
    assert by_name["import_config.json"] == {
        "stock", "purchase", "select_product", "add_to_cart"}
    assert by_name["import_config_combined.json"] == {"ecommerce"}


def test_run_matrix_iterates_strategies(tmp_path):
    seen = []

    def fake_importer(config_path, *, sgbd_config_path, collector, show_data,
                      only, create_schema, source_overrides, strategy, execution="stream"):
        seen.append(strategy)
        collector.record("postgres", "products", "write", rows=100, seconds=0.1)
        return []

    labeled = brun.run_matrix(
        sizes=[1000], modes=["multi"], repetitions=1,
        strategies=["naive", "optimized"],
        sgbd_config_path=None, config_dir="data/ecommerce", data_dir=tmp_path,
        seed=1, only=["postgres"], cleaners={},
        importer=fake_importer, load_cfg=lambda c, s: {"postgres": {}},
        generate=lambda out_dir, rows, seed, mode: None,
    )
    assert sorted(seen) == ["naive", "optimized"]
    assert {r["strategy"] for r in labeled} == {"naive", "optimized"}
    from polyglotimportcsv.benchmark_results import median_results
    res = median_results(labeled)
    assert {r["strategy"] for r in res} == {"naive", "optimized"}


def test_run_matrix_rejects_unknown_execution(tmp_path):
    with pytest.raises(ValueError, match="unknown execution"):
        brun.run_matrix(
            sizes=[10], modes=["multi"], repetitions=1,
            executions=["strem"],  # typo: would silently run something else
            sgbd_config_path=None, config_dir="data/ecommerce", data_dir=tmp_path,
            seed=1, only=["postgres"], cleaners={},
            importer=lambda *a, **k: [], load_cfg=lambda c, s: {"postgres": {}},
            generate=lambda out_dir, rows, seed, mode: None,
        )


def test_run_matrix_iterates_executions(tmp_path):
    seen = []

    def fake_importer(config_path, *, sgbd_config_path, collector, show_data,
                      only, create_schema, source_overrides, strategy, execution):
        seen.append(execution)
        collector.record("postgres", "products", "write", rows=100, seconds=0.1)
        return []

    labeled = brun.run_matrix(
        sizes=[1000], modes=["multi"], repetitions=1,
        executions=["materialize", "stream"],
        sgbd_config_path=None, config_dir="data/ecommerce", data_dir=tmp_path,
        seed=1, only=["postgres"], cleaners={},
        importer=fake_importer, load_cfg=lambda c, s: {"postgres": {}},
        generate=lambda out_dir, rows, seed, mode: None,
    )
    assert sorted(seen) == ["materialize", "stream"]
    assert {r["execution"] for r in labeled} == {"materialize", "stream"}
    res = median_results(labeled)
    assert {r["execution"] for r in res} == {"materialize", "stream"}


def test_run_matrix_records_peak_memory(tmp_path):
    def fake_importer(config_path, *, sgbd_config_path, collector, show_data,
                      only, create_schema, source_overrides, strategy, execution):
        # Allocate something inside the timed/traced region so peak > 0.
        _ = [0] * 200_000
        collector.record("postgres", "products", "write", rows=100, seconds=0.1)
        return []

    labeled = brun.run_matrix(
        sizes=[1000], modes=["multi"], repetitions=1,
        sgbd_config_path=None, config_dir="data/ecommerce", data_dir=tmp_path,
        seed=1, only=["postgres"], cleaners={},
        importer=fake_importer, load_cfg=lambda c, s: {"postgres": {}},
        generate=lambda out_dir, rows, seed, mode: None,
    )
    assert len(labeled) == 1
    peak = labeled[0]["peak_memory_mb"]
    assert isinstance(peak, float) and peak > 0
    # Peak flows through consolidation onto the result row.
    res = median_results(labeled)
    assert res[0]["peak_memory_mb"] == peak


def test_ensure_dataset_reuses_a_cache_matching_the_split(tmp_path):
    split = bdata._split_rows(1000, 42)
    for src, fname in bdata.SOURCE_FILES.items():
        _write_csv(tmp_path / "1000" / fname, bdata.SOURCE_COLUMNS[src], split[src])

    calls = []
    brun._ensure_dataset(tmp_path, 1000, 42, "multi", _recording_generate(calls))

    assert calls == []  # counts agree with the split -> no regeneration


def test_ensure_dataset_regenerates_a_stale_multi_cache(tmp_path):
    # Old semantics: --sizes 1000 meant 1000 products -> 8000 total rows.
    stale = {"stock": 1000, "purchase": 3000, "select_product": 2000, "add_to_cart": 2000}
    for src, fname in bdata.SOURCE_FILES.items():
        _write_csv(tmp_path / "1000" / fname, bdata.SOURCE_COLUMNS[src], stale[src])

    calls = []
    brun._ensure_dataset(tmp_path, 1000, 42, "multi", _recording_generate(calls))

    assert calls == [(tmp_path / "1000", 1000, 42, "multi")]


def test_ensure_dataset_regenerates_a_stale_combined_cache(tmp_path):
    # Old semantics: --sizes 1000 meant 1000 products -> an 8000-row join file.
    stale = {"stock": 1000, "purchase": 3000, "select_product": 2000, "add_to_cart": 2000}
    _write_join(tmp_path / "1000" / bdata.JOIN_FILE, stale)

    calls = []
    brun._ensure_dataset(tmp_path, 1000, 42, "combined", _recording_generate(calls))

    assert calls == [(tmp_path / "1000", 1000, 42, "combined")]


def test_ensure_dataset_reuses_a_combined_cache_matching_the_split(tmp_path):
    _write_join(tmp_path / "1000" / bdata.JOIN_FILE, bdata._split_rows(1000, 42))

    calls = []
    brun._ensure_dataset(tmp_path, 1000, 42, "combined", _recording_generate(calls))

    assert calls == []


def test_ensure_dataset_regenerates_a_combined_cache_with_the_wrong_action_mix(tmp_path):
    # The join total is `size` under every seed, so the total alone cannot tell a
    # seed-42 cache from a seed-7 one — the per-action mix has to be checked too.
    split42 = bdata._split_rows(1000, 42)
    _write_join(tmp_path / "1000" / bdata.JOIN_FILE, split42)

    assert bdata._split_rows(1000, 7) != split42  # guard: the seeds really differ
    calls = []
    brun._ensure_dataset(tmp_path, 1000, 7, "combined", _recording_generate(calls))

    assert calls == [(tmp_path / "1000", 1000, 7, "combined")]


@pytest.mark.parametrize("mode", ["multi", "combined"])
def test_ensure_dataset_accepts_what_the_real_generator_writes(tmp_path, mode):
    # If the freshness check disagreed with the generator, every run would
    # regenerate the dataset instead of reusing the cache.
    calls = []

    def generate(out_dir, rows, seed, mode):
        calls.append(mode)
        return bdata.generate_dataset(out_dir, rows, seed=seed, mode=mode)

    brun._ensure_dataset(tmp_path, 1000, 42, mode, generate)
    brun._ensure_dataset(tmp_path, 1000, 42, mode, generate)

    assert calls == [mode]  # generated once, reused the second time


def test_ensure_dataset_regenerates_when_the_seed_changes_the_split(tmp_path):
    # A cache written with seed 42 must not be reused for a different seed whose
    # split differs, or the run silently benchmarks the wrong per-source shape.
    split42 = bdata._split_rows(1000, 42)
    for src, fname in bdata.SOURCE_FILES.items():
        _write_csv(tmp_path / "1000" / fname, bdata.SOURCE_COLUMNS[src], split42[src])

    assert bdata._split_rows(1000, 7) != split42  # guard: the seeds really differ
    calls = []
    brun._ensure_dataset(tmp_path, 1000, 7, "multi", _recording_generate(calls))

    assert calls == [(tmp_path / "1000", 1000, 7, "multi")]
