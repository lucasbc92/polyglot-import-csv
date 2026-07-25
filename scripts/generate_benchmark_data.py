#!/usr/bin/env python3
"""CLI: generate a synthetic benchmark dataset (spec §2.5)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from polyglotimportcsv.benchmark_data import generate_dataset


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic synthetic e-commerce dataset."
    )
    parser.add_argument("--rows", type=int, required=True,
                        help="Total number of rows across all sources (split ~1:3:2:2).")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42).")
    parser.add_argument("--out", type=Path, required=True, help="Output directory.")
    parser.add_argument(
        "--mode", choices=("both", "multi", "combined"), default="both",
        help="Which formats to write (default: both).",
    )
    args = parser.parse_args(argv)
    written = generate_dataset(args.out, args.rows, seed=args.seed, mode=args.mode)
    for key, path in written.items():
        print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
