#!/usr/bin/env python3
"""CLI: run the import benchmark matrix over live databases (spec §3).

Prerequisite: the databases must already be up (e.g. `docker compose up --wait`
or via run_example.sh). This script cleans each backend before every import so
each measurement is a cold load.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence

# scripts/ is on sys.path[0] when run as `python scripts/run_benchmarks.py`.
from inspect_persisted_data import CLEANERS

from polyglotimportcsv.benchmark_results import median_results, write_consolidated
from polyglotimportcsv.benchmark_runner import run_matrix
from polyglotimportcsv.config_parser import load_config
from polyglotimportcsv.metrics import environment_metadata
from polyglotimportcsv.runner import run_import

_ALL_BACKENDS = ("postgres", "mongodb", "cassandra", "redis", "neo4j")


def _parse_int_list(raw: str) -> List[int]:
    return [int(x) for x in raw.split(",") if x.strip()]


def _parse_str_list(raw: str) -> List[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the import benchmark matrix.")
    parser.add_argument("--sizes", default="1000,10000,100000",
                        help="Comma-separated N (products) sizes (default: 1000,10000,100000).")
    parser.add_argument("--modes", default="multi,combined",
                        help="Comma-separated input modes (default: multi,combined).")
    parser.add_argument("--repetitions", type=int, default=3,
                        help="Runs per (size, mode); the median is reported (default: 3).")
    parser.add_argument("--only", default="",
                        help=f"Comma-separated backends (default: all). Choices: {', '.join(_ALL_BACKENDS)}.")
    parser.add_argument("--seed", type=int, default=42, help="Generator seed (default: 42).")
    parser.add_argument("--sgbd-config", type=Path, default=Path("data/ecommerce/sgbd_config.json"))
    parser.add_argument("--config-dir", type=Path, default=Path("data/ecommerce"),
                        help="Directory holding import_config.json / import_config_combined.json.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/benchmark/generated"),
                        help="Where generated size datasets live (default: data/benchmark/generated).")
    parser.add_argument("--out", type=Path, default=Path("benchmarks"),
                        help="Output directory for consolidated results (default: benchmarks).")
    args = parser.parse_args(argv)

    sizes = _parse_int_list(args.sizes)
    modes = _parse_str_list(args.modes)
    only = _parse_str_list(args.only) or None

    labeled = run_matrix(
        sizes=sizes, modes=modes, repetitions=args.repetitions,
        sgbd_config_path=args.sgbd_config, config_dir=args.config_dir,
        data_dir=args.data_dir, seed=args.seed, only=only,
        cleaners=CLEANERS, importer=run_import, load_cfg=load_config,
    )
    results = median_results(labeled)
    meta = environment_metadata(args.config_dir, {})
    meta.update({"seed": args.seed, "sizes": sizes, "modes": modes,
                 "repetitions": args.repetitions})
    json_path, csv_path = write_consolidated(results, meta, out_dir=args.out)
    print(f"benchmark JSON: {json_path}")
    print(f"benchmark CSV:  {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
