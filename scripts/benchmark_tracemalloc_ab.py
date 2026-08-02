#!/usr/bin/env python3
"""CLI: measure what ``tracemalloc`` costs the benchmark, per execution path.

The matrix records ``peak_memory_mb`` by running every import under
``tracemalloc``, which instruments each allocation. Its cost therefore scales
with how many allocations a path makes, and ``materialize`` (few large pandas
allocations) and ``stream`` (many small per-chunk ones) do not allocate alike —
so the overhead cannot be assumed to cancel out between the two. This runs one
cell of the matrix both ways and reports the difference.

Traced and untraced runs are interleaved pass by pass, so warm-up (JVM JIT, DB
buffers, page cache) lands on both arms equally instead of favouring whichever
runs second.

Prerequisite: the databases must already be up (e.g. `docker compose up --wait`).
"""

from __future__ import annotations

import argparse
import logging
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from rich.table import Table
from rich.text import Text

# scripts/ is on sys.path[0] when run as `python scripts/benchmark_tracemalloc_ab.py`.
from inspect_persisted_data import CLEANERS

from polyglotimportcsv.benchmark_runner import run_matrix
from polyglotimportcsv.config_parser import load_config
from polyglotimportcsv.metrics import EXCLUDED_PHASES
from polyglotimportcsv.reporting import print_rich, setup_reporting
from polyglotimportcsv.runner import run_import

_ALL_BACKENDS = ("postgres", "mongodb", "cassandra", "redis", "neo4j")

#: The imports themselves are noisy, so this script runs at a quiet log level.
#: Its own progress and result are the point of running it, so they print above
#: that level rather than being filtered out with the import chatter.
_ALWAYS = logging.CRITICAL


def _parse_str_list(raw: str) -> List[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def reported_seconds(run: Dict[str, Any]) -> float:
    """Total seconds a labeled run contributes to the report.

    Sums the phases the consolidated report keeps, so the number compared here is
    the one that ends up in the results, not some separate wall-clock measure.
    """
    return sum(
        rec["seconds"] for rec in run["records"]
        if rec["phase"] not in EXCLUDED_PHASES
    )


def summarize(
    traced: List[Dict[str, Any]], untraced: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Per execution path, the median reported seconds of each arm and the overhead.

    ``overhead_pct`` is how much longer the traced arm reports; ``None`` when an
    execution path is missing from one of the arms or the untraced median is 0.
    """
    def medians(runs: List[Dict[str, Any]]) -> Dict[str, float]:
        by_exec: Dict[str, List[float]] = {}
        for run in runs:
            by_exec.setdefault(str(run["execution"]), []).append(reported_seconds(run))
        return {e: statistics.median(v) for e, v in by_exec.items()}

    on, off = medians(traced), medians(untraced)
    rows: List[Dict[str, Any]] = []
    for execution in sorted(set(on) | set(off)):
        t, u = on.get(execution), off.get(execution)
        overhead: Optional[float] = None
        if t is not None and u:
            overhead = (t / u - 1.0) * 100.0
        rows.append({
            "execution": execution,
            "traced_seconds": t,
            "untraced_seconds": u,
            "overhead_pct": overhead,
        })
    return rows


def _table(rows: List[Dict[str, Any]]) -> Table:
    table = Table(title="tracemalloc overhead", header_style="bold")
    table.add_column("execution")
    table.add_column("traced s", justify="right")
    table.add_column("untraced s", justify="right")
    table.add_column("overhead", justify="right")
    for r in rows:
        t, u, o = r["traced_seconds"], r["untraced_seconds"], r["overhead_pct"]
        table.add_row(
            r["execution"],
            "-" if t is None else f"{t:.3f}",
            "-" if u is None else f"{u:.3f}",
            "-" if o is None else f"{o:+.1f}%",
        )
    return table


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure the tracemalloc overhead per execution path."
    )
    parser.add_argument("--size", type=int, default=10000,
                        help="TOTAL row count across all sources (default: 10000).")
    parser.add_argument("--mode", default="multi",
                        help="Input mode: multi or combined (default: multi).")
    parser.add_argument("--executions", default="materialize,stream",
                        help="Comma-separated write paths (default: materialize,stream).")
    parser.add_argument("--repetitions", type=int, default=3,
                        help="Passes per arm; the median is reported (default: 3).")
    parser.add_argument("--only", default="",
                        help=f"Comma-separated backends (default: all). Choices: {', '.join(_ALL_BACKENDS)}.")
    parser.add_argument("--strategy", default="optimized",
                        help="Strategy: naive or optimized (default: optimized).")
    parser.add_argument("--seed", type=int, default=42, help="Generator seed (default: 42).")
    parser.add_argument("--sgbd-config", type=Path, default=Path("data/ecommerce/sgbd_config.json"))
    parser.add_argument("--config-dir", type=Path, default=Path("data/ecommerce"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/benchmark/generated"))
    parser.add_argument("--log-level", default="WARNING",
                        help="Terminal log level (default: WARNING — the imports are noisy).")
    args = parser.parse_args(argv)

    setup_reporting(getattr(logging, args.log_level.upper()))
    executions = _parse_str_list(args.executions)
    only = _parse_str_list(args.only) or None

    def one_pass(trace_memory: bool) -> List[Dict[str, Any]]:
        return run_matrix(
            sizes=[args.size], modes=[args.mode], repetitions=1,
            strategies=[args.strategy], executions=executions,
            sgbd_config_path=args.sgbd_config, config_dir=args.config_dir,
            data_dir=args.data_dir, seed=args.seed, only=only,
            cleaners=CLEANERS, importer=run_import, load_cfg=load_config,
            trace_memory=trace_memory,
        )

    traced: List[Dict[str, Any]] = []
    untraced: List[Dict[str, Any]] = []
    for rep in range(args.repetitions):
        # Alternate arms within each pass: whichever runs first pays the colder
        # caches, and swapping the order per pass keeps that from favouring one arm.
        first_is_traced = rep % 2 == 0
        print_rich(Text(f"pass {rep + 1}/{args.repetitions}", style="dim"), level=_ALWAYS)
        for trace_memory in (first_is_traced, not first_is_traced):
            (traced if trace_memory else untraced).extend(one_pass(trace_memory))

    rows = summarize(traced, untraced)
    print_rich(
        Text(f"cell: size={args.size} mode={args.mode} strategy={args.strategy}, "
             f"{args.repetitions} pass(es) per arm", style="dim"),
        level=_ALWAYS,
    )
    print_rich(_table(rows), level=_ALWAYS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
