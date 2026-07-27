"""Benchmark matrix orchestration — dependency-injected so src never imports scripts.

The script layer wires the real ``CLEANERS`` (from scripts/inspect_persisted_data.py),
``run_import``, and ``load_config``; tests inject stubs and run without databases.
"""

from __future__ import annotations

import tracemalloc
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from polyglotimportcsv import benchmark_data
from polyglotimportcsv.metrics import MetricsCollector

_ALL_BACKENDS = ("postgres", "mongodb", "cassandra", "redis", "neo4j")
_VALID_STRATEGIES = ("naive", "optimized")
_VALID_EXECUTIONS = ("stream", "materialize")

_BYTES_PER_MB = 1024 * 1024

# mode -> (import config filename, combined source name or None)
_MODE_CONFIG = {
    "multi": ("import_config.json", None),
    "combined": ("import_config_combined.json", "ecommerce"),
}


def _data_rows(path: Path) -> int:
    """Count data rows (lines minus header). The generator never emits embedded
    newlines, so line counting matches the CSV row count."""
    with open(path, "rb") as fh:
        return max(0, sum(1 for _ in fh) - 1)


def _action_counts(path: Path) -> Dict[str, int]:
    """Count rows per ``action`` in the combined file. ``action`` is the first
    column, so the leading field is read without parsing the full row."""
    counts: Dict[str, int] = {}
    with open(path, "rb") as fh:
        next(fh, None)  # header
        for line in fh:
            action = line.split(b",", 1)[0].decode("utf-8", "replace")
            counts[action] = counts.get(action, 0) + 1
    return counts


def _cache_matches(dpath: Path, size: int, seed: int, mode: str) -> bool:
    """Does the dataset cached at ``dpath`` match what ``(size, seed, mode)`` asks for?

    The on-disk cache is keyed only by size, so a directory written under different
    generator semantics (when ``--sizes`` meant products) or a different seed would
    otherwise be reused silently and benchmark the wrong row counts.
    """
    split = benchmark_data._split_rows(size, seed)
    if mode == "combined":
        path = dpath / benchmark_data.JOIN_FILE
        return path.is_file() and _action_counts(path) == split
    return all(
        (dpath / fname).is_file() and _data_rows(dpath / fname) == split[src]
        for src, fname in benchmark_data.SOURCE_FILES.items()
    )


def _ensure_dataset(data_dir: Path, size: int, seed: int, mode: str, generate) -> Path:
    """Generate the dataset for ``size`` under ``data_dir/<size>/`` unless a cached
    one already matches ``(size, seed)``."""
    dpath = data_dir / str(size)
    gen_mode = "combined" if mode == "combined" else "multi"
    if not _cache_matches(dpath, size, seed, gen_mode):
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
    executions: Iterable[str] = ("stream",),
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
    """Run sizes x modes x strategies x executions x repetitions, cleaning before each import.

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
    executions = list(executions)
    unknown_executions = [e for e in executions if e not in _VALID_EXECUTIONS]
    if unknown_executions:
        raise ValueError(
            f"unknown execution(s): {', '.join(unknown_executions)}. "
            f"Valid: {', '.join(_VALID_EXECUTIONS)}"
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
                for execution in executions:
                    for rep in range(repetitions):
                        for backend in selected:
                            block = merged.get(backend)
                            if block is not None and backend in cleaners:
                                cleaners[backend](block)
                        collector = MetricsCollector()
                        # Measure whole-import peak memory. Streaming's headline
                        # metric is a bounded peak (~one read chunk) versus the
                        # materialize path's peak that grows with dataset size.
                        tracemalloc.start()
                        tracemalloc.reset_peak()
                        importer(
                            config_path,
                            sgbd_config_path=sgbd_config_path,
                            collector=collector,
                            show_data=False,
                            only=selected,
                            create_schema=True,
                            source_overrides=overrides,
                            strategy=strategy,
                            execution=execution,
                        )
                        peak_bytes = tracemalloc.get_traced_memory()[1]
                        tracemalloc.stop()
                        labeled.append({
                            "size": size, "mode": mode, "strategy": strategy,
                            "execution": execution, "repetition": rep,
                            "peak_memory_mb": peak_bytes / _BYTES_PER_MB,
                            "records": collector.to_records(),
                        })
                        if on_run is not None:
                            on_run(labeled)
    return labeled
