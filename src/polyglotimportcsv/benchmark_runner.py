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


def _run_key(run: Dict[str, object]) -> tuple:
    """Identity of a labeled run: which matrix cell, and which repetition of it."""
    return (run["size"], run["mode"], run["strategy"], run["execution"],
            run["repetition"])


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
    trace_memory: bool = True,
    completed: Optional[List[Dict[str, object]]] = None,
) -> List[Dict[str, object]]:
    """Run repetitions x sizes x modes x strategies x executions, cleaning before each import.

    One repetition is a full sweep of the (size, mode, strategy, execution) matrix,
    not a burst of back-to-back runs of the same cell: warm-up then affects every
    cell's first pass equally instead of concentrating on whichever cell happens to
    run first. Returns labeled runs.

    ``on_run`` is called with every labeled run collected so far, right after each
    import finishes. A full matrix over large sizes takes a long time and results
    are only consolidated at the end, so this lets the caller checkpoint: a crash
    on run N keeps the N-1 measurements that already succeeded.

    ``completed`` carries labeled runs from an interrupted matrix: those cells are
    not measured again, and the runs are returned (and checkpointed) alongside the
    new ones, so a resumed matrix consolidates into the same result as an
    uninterrupted one.

    ``trace_memory`` toggles the ``tracemalloc`` capture. It is what makes
    ``peak_memory_mb`` available, but it instruments every allocation and so
    inflates the recorded seconds by an amount that depends on how many
    allocations the path makes. Turn it off for timing-only runs, or to measure
    the instrumentation's own cost (scripts/benchmark_tracemalloc_ab.py); runs
    then carry ``peak_memory_mb=None``, which consolidation already tolerates.
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
    # Prepare every (size, mode) cell up front. Generating datasets and loading
    # configs is not part of any measurement, so it stays out of the repetition
    # passes; it also fails fast when a size cannot be prepared, instead of after
    # the earlier sizes have already been measured.
    cells: List[Dict[str, object]] = []
    for size in sizes:
        for mode in modes:
            cfg_name, _ = _MODE_CONFIG[mode]
            config_path = config_dir / cfg_name
            dpath = _ensure_dataset(data_dir, size, seed, mode, generate)
            merged = load_cfg(config_path, sgbd_config_path)
            cells.append({
                "size": size,
                "mode": mode,
                "config_path": config_path,
                "overrides": _overrides(mode, dpath),
                "merged": merged,
                "selected": requested or [b for b in _ALL_BACKENDS if b in merged],
            })

    labeled: List[Dict[str, object]] = list(completed or [])
    already_measured = {_run_key(run) for run in labeled}

    # Repetitions are the OUTERMOST loop: each pass sweeps the whole matrix once.
    # With the repetition innermost, all measurements of the first cell would land
    # in the process/JVM/page-cache warm-up window while every later cell ran warm
    # — a bias aligned with the axes being compared, since the first level of each
    # axis always goes first. Sweeping instead means every cell takes its coldest
    # sample in pass 0, so the median across passes discards it uniformly.
    for rep in range(repetitions):
        for cell in cells:
            merged = cell["merged"]
            selected = cell["selected"]
            for strategy in strategies:
                for execution in executions:
                    key = (cell["size"], cell["mode"], strategy, execution, rep)
                    if key in already_measured:
                        continue
                    for backend in selected:
                        block = merged.get(backend)
                        if block is not None and backend in cleaners:
                            cleaners[backend](block)
                    collector = MetricsCollector()
                    # Measure whole-import peak memory. Streaming's headline
                    # metric is a bounded peak (~one read chunk) versus the
                    # materialize path's peak that grows with dataset size.
                    if trace_memory:
                        tracemalloc.start()
                        tracemalloc.reset_peak()
                    importer(
                        cell["config_path"],
                        sgbd_config_path=sgbd_config_path,
                        collector=collector,
                        show_data=False,
                        only=selected,
                        create_schema=True,
                        source_overrides=cell["overrides"],
                        strategy=strategy,
                        execution=execution,
                    )
                    peak_mb: Optional[float] = None
                    if trace_memory:
                        peak_mb = tracemalloc.get_traced_memory()[1] / _BYTES_PER_MB
                        tracemalloc.stop()
                    labeled.append({
                        "size": cell["size"], "mode": cell["mode"],
                        "strategy": strategy, "execution": execution,
                        "repetition": rep,
                        "peak_memory_mb": peak_mb,
                        "records": collector.to_records(),
                    })
                    if on_run is not None:
                        on_run(labeled)
    return labeled
