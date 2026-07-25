"""Benchmark matrix orchestration — dependency-injected so src never imports scripts.

The script layer wires the real ``CLEANERS`` (from scripts/inspect_persisted_data.py),
``run_import``, and ``load_config``; tests inject stubs and run without databases.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from polyglotimportcsv import benchmark_data
from polyglotimportcsv.metrics import MetricsCollector

_ALL_BACKENDS = ("postgres", "mongodb", "cassandra", "redis", "neo4j")
_VALID_STRATEGIES = ("naive", "optimized")

# mode -> (import config filename, combined source name or None)
_MODE_CONFIG = {
    "multi": ("import_config.json", None),
    "combined": ("import_config_combined.json", "ecommerce"),
}


def _ensure_dataset(data_dir: Path, size: int, seed: int, mode: str, generate) -> Path:
    """Generate the dataset for ``size`` under ``data_dir/<size>/`` if files are missing."""
    dpath = data_dir / str(size)
    if mode == "combined":
        needed = [benchmark_data.JOIN_FILE]
        gen_mode = "combined"
    else:
        needed = list(benchmark_data.SOURCE_FILES.values())
        gen_mode = "multi"
    if not all((dpath / fname).is_file() for fname in needed):
        generate(dpath, rows=size, seed=seed, mode=gen_mode)
    return dpath


def _overrides(mode: str, dpath: Path) -> Dict[str, str]:
    if mode == "combined":
        return {"ecommerce": str(dpath / benchmark_data.JOIN_FILE)}
    return {src: str(dpath / fname) for src, fname in benchmark_data.SOURCE_FILES.items()}


def run_matrix(
    *,
    sizes: Iterable[int],
    modes: Iterable[str],
    repetitions: int,
    strategies: Iterable[str] = ("optimized",),
    sgbd_config_path: "Optional[str | Path]",
    config_dir: "str | Path",
    data_dir: "str | Path",
    seed: int,
    only: Optional[Iterable[str]],
    cleaners: Dict[str, Callable[[dict], None]],
    importer: Callable[..., List[str]],
    load_cfg: Callable[..., Dict[str, object]],
    generate: Callable[..., object] = benchmark_data.generate_dataset,
    on_run: Optional[Callable[[List[Dict[str, object]]], None]] = None,
) -> List[Dict[str, object]]:
    """Run sizes x modes x strategies x repetitions, cleaning before each import.

    Returns labeled runs.

    ``on_run`` is called with every labeled run collected so far, right after each
    import finishes. A full matrix over large sizes takes a long time and results
    are only consolidated at the end, so this lets the caller checkpoint: a crash
    on run N keeps the N-1 measurements that already succeeded.
    """
    config_dir = Path(config_dir)
    data_dir = Path(data_dir)
    modes = list(modes)
    unknown = [m for m in modes if m not in _MODE_CONFIG]
    if unknown:
        raise ValueError(
            f"unknown mode(s): {', '.join(unknown)}. Valid: {', '.join(_MODE_CONFIG)}"
        )
    requested = list(only) if only else None
    strategies = list(strategies)
    unknown_strategies = [s for s in strategies if s not in _VALID_STRATEGIES]
    if unknown_strategies:
        raise ValueError(
            f"unknown strategy(ies): {', '.join(unknown_strategies)}. "
            f"Valid: {', '.join(_VALID_STRATEGIES)}"
        )
    labeled: List[Dict[str, object]] = []

    for size in sizes:
        for mode in modes:
            cfg_name, _ = _MODE_CONFIG[mode]
            config_path = config_dir / cfg_name
            dpath = _ensure_dataset(data_dir, size, seed, mode, generate)
            overrides = _overrides(mode, dpath)
            merged = load_cfg(config_path, sgbd_config_path)
            selected = requested or [b for b in _ALL_BACKENDS if b in merged]
            for strategy in strategies:
                for rep in range(repetitions):
                    for backend in selected:
                        block = merged.get(backend)
                        if block is not None and backend in cleaners:
                            cleaners[backend](block)
                    collector = MetricsCollector()
                    importer(
                        config_path,
                        sgbd_config_path=sgbd_config_path,
                        collector=collector,
                        show_data=False,
                        only=selected,
                        create_schema=True,
                        source_overrides=overrides,
                        strategy=strategy,
                    )
                    labeled.append({
                        "size": size, "mode": mode, "strategy": strategy,
                        "repetition": rep, "records": collector.to_records(),
                    })
                    if on_run is not None:
                        on_run(labeled)
    return labeled
