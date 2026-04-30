"""Orchestrate validation and per-backend import."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, List, Optional, Set

from polyglotimportcsv.config_parser import load_config
from polyglotimportcsv.csv_reader import load_csv_with_inference
from polyglotimportcsv.importers import default_importer_registry
from polyglotimportcsv.importers.base import ImporterRegistry
from polyglotimportcsv.validation import BACKENDS, validate_import_config

logger = logging.getLogger(__name__)


def run_import(
    csv_path: str | Path,
    config_path: str | Path,
    *,
    dry_run: bool = False,
    create_schema: bool = True,
    only: Optional[Iterable[str]] = None,
    importers: Optional[ImporterRegistry] = None,
) -> List[str]:
    """
    Load CSV and config, validate, then run configured backends.

    ``importers`` defaults to production callables; tests may inject a stub
    registry to avoid real database I/O (Dependency Inversion).
    """
    config = load_config(config_path)
    df, kinds = load_csv_with_inference(csv_path)
    validate_import_config(config, df, kinds)

    registry = importers or default_importer_registry()

    only_set: Optional[Set[str]] = None
    if only is not None:
        only_set = {x.strip().lower() for x in only if x and str(x).strip()}

    log_lines: List[str] = []
    for backend in BACKENDS:
        if backend not in config:
            continue
        if only_set and backend not in only_set:
            continue
        fn = registry.get(backend)
        if fn is None:
            continue
        bcfg = config[backend]
        log_lines.extend(fn(bcfg, df, kinds, dry_run=dry_run, create_schema=create_schema))

    for line in log_lines:
        logger.info("%s", line)
    return log_lines
