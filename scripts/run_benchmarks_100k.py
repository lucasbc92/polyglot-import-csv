#!/usr/bin/env python3
"""CLI: run the 100k benchmark for the backends that sustain a usable rate.

Same matrix engine as ``run_benchmarks.py`` — this only changes the defaults
(one size, a subset of backends, its own output directory) and prints a rough
wall-clock estimate first, because a 100k run over the slowest backends
takes hours rather than minutes.

Cassandra, Redis and Neo4j are the slowest writers at 100k, so they are excluded
by default. Pass ``--only`` to override:

    python scripts/run_benchmarks_100k.py
    python scripts/run_benchmarks_100k.py --only postgres,mongodb,redis
    python scripts/run_benchmarks_100k.py --repetitions 1 --modes multi
"""

from __future__ import annotations

import argparse
import sys
from typing import Dict, List, Optional, Sequence

# scripts/ is on sys.path[0] when run as `python scripts/run_benchmarks_100k.py`.
import run_benchmarks

#: The fastest writers; safe to run at 100k.
FAST_BACKENDS = ("postgres", "mongodb")

#: The slowest writers at 100k. Kept out of the default selection: at 100k
#: they dominate the matrix wall clock.
SLOW_BACKENDS = ("cassandra", "redis", "neo4j")

#: Median rows/s measured per phase on the 1k+10k matrix (benchmark.log,
#: 12 runs). Used only for the pre-run estimate below, never for reporting.
#: These were measured with the row-at-a-time writers, before their removal; the
#: batched writers are faster, so the estimate is an upper bound.
MEASURED_ROWS_PER_S: Dict[str, Dict[str, float]] = {
    "postgres": {"map": 610, "write": 8101},
    "mongodb": {"map": 7.5e6, "write": 20184},
    "cassandra": {"map": 475, "write": 257},
    "redis": {"map": 1182, "write": 507},
    "neo4j": {"map": 4.0e7, "write": 93},
}

#: Total rows the reference measurements below were taken at. Under the
#: total-rows --sizes semantics, 8000 total rows == the old 1000-product point.
_REFERENCE_TOTAL_ROWS = 8000

#: Rows each backend handled per phase at _REFERENCE_TOTAL_ROWS total rows, from
#: the same log. Row counts scale about linearly with size, so
#: size/_REFERENCE_TOTAL_ROWS scales these.
ROWS_AT_1K: Dict[str, Dict[str, int]] = {
    "postgres": {"map": 6000, "write": 5010},
    "mongodb": {"map": 1000, "write": 1000},
    "cassandra": {"map": 8000, "write": 8000},
    "redis": {"map": 4000, "write": 4000},
    "neo4j": {"map": 4000, "write": 4100},
}


def estimate_seconds(backends: Sequence[str], size: int, runs: int) -> Dict[str, float]:
    """Rough per-backend wall clock for the whole matrix, from measured rates.

    Linear extrapolation from small sizes: it ignores DB-side effects that grow
    with the dataset (index maintenance, Neo4j's unindexed MERGE scans), so it
    is a floor, not a forecast.
    """
    scale = size / _REFERENCE_TOTAL_ROWS
    out: Dict[str, float] = {}
    for b in backends:
        rates = MEASURED_ROWS_PER_S.get(b)
        rows = ROWS_AT_1K.get(b)
        if not rates or not rows:
            continue
        per_run = sum(rows[ph] * scale / rates[ph] for ph in ("map", "write"))
        out[b] = per_run * runs
    return out


def _report_estimate(backends: Sequence[str], size: int, runs: int) -> None:
    est = estimate_seconds(backends, size, runs)
    if not est:
        return
    print(f"Estimated wall clock for {runs} run(s) at size {size:,}:")
    for b, secs in sorted(est.items(), key=lambda kv: -kv[1]):
        print(f"  {b:<10} {secs / 60:7.1f} min")
    print(f"  {'total':<10} {sum(est.values()) / 3600:7.1f} h\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the import benchmark at 100k for the fastest backends.",
        epilog="Unrecognised flags are forwarded to run_benchmarks.py unchanged.",
    )
    parser.add_argument("--size", type=int, default=100000,
                        help="Total dataset size in rows (default: 100000).")
    parser.add_argument("--only", default=",".join(FAST_BACKENDS),
                        help=f"Comma-separated backends (default: {','.join(FAST_BACKENDS)}). "
                             f"Slow at 100k: {', '.join(SLOW_BACKENDS)}.")
    parser.add_argument("--modes", default="multi,combined",
                        help="Comma-separated input modes (default: multi,combined).")
    parser.add_argument("--repetitions", type=int, default=3,
                        help="Runs per (size, mode); the median is reported (default: 3).")
    parser.add_argument("--out", default="benchmarks/100k",
                        help="Output directory (default: benchmarks/100k, kept apart "
                             "from the 1k/10k results).")
    parser.add_argument("--estimate-only", action="store_true",
                        help="Print the wall-clock estimate and exit without importing.")
    args, passthrough = parser.parse_known_args(argv)

    backends = [b.strip() for b in args.only.split(",") if b.strip()]
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    runs = len(modes) * args.repetitions

    _report_estimate(backends, args.size, runs)
    if args.estimate_only:
        return 0

    forwarded: List[str] = [
        "--sizes", str(args.size),
        "--modes", ",".join(modes),
        "--repetitions", str(args.repetitions),
        "--only", ",".join(backends),
        "--out", args.out,
        *passthrough,
    ]
    return run_benchmarks.main(forwarded)


if __name__ == "__main__":
    raise SystemExit(main())
