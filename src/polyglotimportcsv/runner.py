"""Orchestrate validation and per-backend import."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Set

from polyglotimportcsv.config_parser import load_config
from polyglotimportcsv.console import (
    banner,
    color_backend_line,
    note,
    section,
    step,
    success,
)
from polyglotimportcsv.csv_reader import load_csv_with_inference
from polyglotimportcsv.importers import default_importer_registry
from polyglotimportcsv.importers.base import ImporterRegistry
from polyglotimportcsv.validation import BACKENDS, validate_import_config


def run_import(
    csv_path: str | Path,
    config_path: str | Path,
    *,
    sgbd_config_path: Optional[str | Path] = None,
    dry_run: bool = False,
    create_schema: bool = True,
    only: Optional[Iterable[str]] = None,
    importers: Optional[ImporterRegistry] = None,
) -> List[str]:
    """
    Load CSV and config, validate, then run configured backends.

    The configuration is split in two files: ``config_path`` points to the
    import (mapping) JSON and ``sgbd_config_path`` to the SGBD connection JSON.
    When ``sgbd_config_path`` is omitted, a ``sgbd_config.json`` file next to
    the import configuration is used.

    ``importers`` defaults to production callables; tests may inject a stub
    registry to avoid real database I/O (Dependency Inversion).
    """
    csv_path = Path(csv_path)
    config_path = Path(config_path)

    mode = "dry-run" if dry_run else "import"
    banner("Polyglot Import CSV", subtitle=f"mode: {mode}")

    step("Load config", str(config_path))
    config = load_config(config_path, sgbd_config_path)
    backends_in_cfg = [b for b in BACKENDS if b in config]
    note(f"{len(backends_in_cfg)} backend(s) configured: {', '.join(backends_in_cfg)}")

    step("Load CSV", str(csv_path))
    df, kinds = load_csv_with_inference(csv_path)
    note(f"{len(df)} data row(s), {len(df.columns)} column(s)")

    step("Validate config × CSV")
    validate_import_config(config, df, kinds)
    success("Validation passed")

    registry = importers or default_importer_registry()

    only_set: Optional[Set[str]] = None
    if only is not None:
        only_set = {x.strip().lower() for x in only if x and str(x).strip()}
        note(f"filter: only {', '.join(sorted(only_set))}")

    if dry_run:
        note("no database connections will be opened")
    elif create_schema:
        note("DDL will be created where applicable (--create-schema)")
    else:
        note("existing schema only (--no-create-schema)")

    log_lines: List[str] = []
    for backend in BACKENDS:
        if backend not in config:
            continue
        if only_set and backend not in only_set:
            continue
        fn = registry.get(backend)
        if fn is None:
            continue
        section(f"Backend · {backend}")
        bcfg = config[backend]
        backend_lines = fn(bcfg, df, kinds, dry_run=dry_run, create_schema=create_schema)
        log_lines.extend(backend_lines)
        for line in backend_lines:
            print(f"  {color_backend_line(line)}")

    success(f"Finished {mode} — {len(log_lines)} log line(s) from importer(s)")
    return log_lines
