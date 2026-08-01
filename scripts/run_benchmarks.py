#!/usr/bin/env python3
"""CLI: run the import benchmark matrix over live databases (spec §3).

Prerequisite: the databases must already be up (e.g. `docker compose up --wait`
or via run_example.sh). This script cleans each backend before every import so
each measurement is a cold load.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# scripts/ is on sys.path[0] when run as `python scripts/run_benchmarks.py`.
from inspect_persisted_data import CLEANERS

from polyglotimportcsv.benchmark_results import median_results, write_consolidated
from polyglotimportcsv.benchmark_runner import run_matrix
from polyglotimportcsv.config_parser import load_config
from polyglotimportcsv.metrics import environment_metadata
from polyglotimportcsv.reporting import kv, setup_reporting
from polyglotimportcsv.runner import run_import

_ALL_BACKENDS = ("postgres", "mongodb", "cassandra", "redis", "neo4j")

CHECKPOINT_NAME = "benchmark_checkpoint.json"

#: Metadata that has to agree for a checkpoint to be resumable. Runs measured
#: under different axes describe a different matrix, and mixing them would
#: silently corrupt the medians.
RESUME_KEYS = ("seed", "sizes", "modes", "strategies", "executions", "repetitions",
               "trace_memory")


def resume_runs(path: Path, meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Labeled runs from an interrupted matrix at ``path``, if it matches ``meta``.

    Returns an empty list when there is no checkpoint — asking to resume a matrix
    that never ran just starts it.
    """
    if not Path(path).is_file():
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    saved = payload.get("metadata") or {}
    differing = [k for k in RESUME_KEYS if saved.get(k) != meta.get(k)]
    if differing:
        details = ", ".join(
            f"{k}: checkpoint={saved.get(k)!r} requested={meta.get(k)!r}"
            for k in differing
        )
        raise ValueError(
            f"{path} was written by a different matrix and cannot be resumed "
            f"({details}). Re-run with matching flags, or delete the checkpoint "
            "to start over."
        )
    return payload.get("runs") or []


def _parse_int_list(raw: str) -> List[int]:
    return [int(x) for x in raw.split(",") if x.strip()]


def _parse_str_list(raw: str) -> List[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def _checkpoint_writer(out_dir: Path, metadata: Dict[str, Any]):
    """Return an ``on_run`` callback that rewrites the raw-runs checkpoint file."""
    path = out_dir / CHECKPOINT_NAME

    def write(labeled: List[Dict[str, Any]]) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = {"metadata": metadata, "complete": False, "runs": labeled}
        path.write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
        logging.getLogger(__name__).debug(
            "checkpoint: %d run(s) -> %s", len(labeled), path
        )

    return write


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the import benchmark matrix.")
    parser.add_argument("--sizes", default="10000,100000",
                        help="Comma-separated TOTAL row counts across all sources "
                             "(default: 10000,100000). Split ~1:3:2:2 per source.")
    parser.add_argument("--modes", default="multi,combined",
                        help="Comma-separated input modes (default: multi,combined).")
    parser.add_argument("--repetitions", type=int, default=3,
                        help="Runs per (size, mode); the median is reported (default: 3).")
    parser.add_argument("--only", default="",
                        help=f"Comma-separated backends (default: all). Choices: {', '.join(_ALL_BACKENDS)}.")
    parser.add_argument("--strategies", default="optimized",
                        help="Comma-separated strategies: naive,optimized (default: optimized).")
    parser.add_argument("--executions", default="stream",
                        help="Comma-separated write paths: stream,materialize (default: stream). "
                             "Use 'materialize,stream' to compare peak_memory_mb.")
    parser.add_argument("--seed", type=int, default=42, help="Generator seed (default: 42).")
    parser.add_argument("--no-trace-memory", dest="trace_memory", action="store_false",
                        help="Do not run imports under tracemalloc. peak_memory_mb is then "
                             "not reported, but the timings stop carrying the tracer's cost "
                             "(measured at 8.6x on the read phase and ~6.5x on map, against "
                             "roughly nothing on the database writes -- so it distorts the "
                             "phases against each other, not by one factor). Use a traced run "
                             "for memory and an untraced one for time.")
    parser.add_argument("--sgbd-config", type=Path, default=Path("data/ecommerce/sgbd_config.json"))
    parser.add_argument("--config-dir", type=Path, default=Path("data/ecommerce"),
                        help="Directory holding import_config.json / import_config_combined.json.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/benchmark/generated"),
                        help="Where generated size datasets live (default: data/benchmark/generated).")
    parser.add_argument("--out", type=Path, default=Path("benchmarks"),
                        help="Output directory for consolidated results (default: benchmarks).")
    parser.add_argument("--log-level", default="INFO",
                        help="Terminal log level (default: INFO). The session log file is always DEBUG.")
    parser.add_argument("--resume", action="store_true",
                        help=f"Continue an interrupted matrix from {CHECKPOINT_NAME} in "
                             "--out, re-measuring only the cells it is missing. The axis "
                             "flags must match the interrupted run.")
    args = parser.parse_args(argv)

    log_path = setup_reporting(getattr(logging, args.log_level.upper()))
    if log_path is not None:
        kv("Log file", log_path)

    sizes = _parse_int_list(args.sizes)
    modes = _parse_str_list(args.modes)
    only = _parse_str_list(args.only) or None
    strategies = _parse_str_list(args.strategies)
    executions = _parse_str_list(args.executions)

    meta = environment_metadata(args.config_dir, {})
    meta.update({"seed": args.seed, "sizes": sizes, "modes": modes,
                 "trace_memory": args.trace_memory,
                 "repetitions": args.repetitions, "strategies": strategies,
                 "executions": executions})

    completed: List[Dict[str, Any]] = []
    if args.resume:
        try:
            completed = resume_runs(args.out / CHECKPOINT_NAME, meta)
        except ValueError as e:
            logging.getLogger(__name__).error("%s", e)
            return 2
        kv("Resuming", f"{len(completed)} run(s) already measured")

    try:
        labeled = run_matrix(
            sizes=sizes, modes=modes, repetitions=args.repetitions,
            strategies=strategies, executions=executions,
            sgbd_config_path=args.sgbd_config, config_dir=args.config_dir,
            data_dir=args.data_dir, seed=args.seed, only=only,
            cleaners=CLEANERS, importer=run_import, load_cfg=load_config,
            on_run=_checkpoint_writer(args.out, meta),
            completed=completed,
            trace_memory=args.trace_memory,
        )
    except Exception:
        # A matrix over large sizes runs for tens of minutes: the failure that
        # ends it is the most important thing in the session, so it belongs in
        # the log file next to the runs that led to it. An escaping exception
        # only ever reaches stderr, which the log never sees.
        logging.getLogger(__name__).exception(
            "benchmark matrix aborted; measured runs are kept in %s (re-run with --resume)",
            args.out / CHECKPOINT_NAME,
        )
        return 1

    results = median_results(labeled)
    json_path, csv_path = write_consolidated(results, meta, out_dir=args.out)
    # The matrix completed and is consolidated; the partial copy is now noise.
    (args.out / CHECKPOINT_NAME).unlink(missing_ok=True)
    print(f"benchmark JSON: {json_path}")
    print(f"benchmark CSV:  {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
