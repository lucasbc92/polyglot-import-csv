"""Matrix orchestration is DB-free via dependency injection."""

from pathlib import Path

from polyglotimportcsv import benchmark_runner as brun
from polyglotimportcsv.benchmark_results import median_results


def test_run_matrix_iterates_and_cleans_before_import(tmp_path):
    events = []

    def make_cleaner(name):
        def _clean(block):
            events.append(("clean", name))
        return _clean

    cleaners = {"postgres": make_cleaner("postgres")}

    def fake_importer(config_path, *, sgbd_config_path, collector, show_data,
                      only, create_schema, source_overrides):
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


def test_run_matrix_builds_mode_overrides(tmp_path):
    seen = []

    def fake_importer(config_path, *, sgbd_config_path, collector, show_data,
                      only, create_schema, source_overrides):
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
