"""Command-line interface for PolyglotImportCSV."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

import click

from polyglotimportcsv.business_exception import BusinessException
from polyglotimportcsv.reporting import error, kv, setup_reporting
from polyglotimportcsv.runner import run_import

logger = logging.getLogger(__name__)


def _parse_source_overrides(pairs: Tuple[str, ...]) -> Dict[str, str]:
    overrides: Dict[str, str] = {}
    for pair in pairs:
        name, sep, path = pair.partition("=")
        if not sep or not name.strip() or not path.strip():
            raise click.UsageError(
                f"--source expects NAME=PATH, got: {pair!r}"
            )
        overrides[name.strip()] = path.strip()
    return overrides


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="JSON import (mapping) configuration with the 'sources' block.",
)
@click.option(
    "--sgbd-config",
    "sgbd_config_path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="JSON SGBD connection configuration. Defaults to sgbd_config.json next to --config.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate and print planned row counts; do not connect to databases.",
)
@click.option(
    "--create-schema/--no-create-schema",
    default=True,
    show_default=True,
    help="Create keyspace/tables/collections where applicable.",
)
@click.option(
    "--only",
    default="",
    help="Comma-separated backends to run (postgres,redis,mongodb,cassandra,neo4j). Empty = all configured.",
)
@click.option(
    "--source",
    "source_pairs",
    multiple=True,
    metavar="NAME=PATH",
    help="Override the CSV path of a source declared in the config (repeatable).",
)
@click.option(
    "--log-level",
    "log_level",
    default="INFO",
    show_default=True,
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    help="Terminal log level; the session log file always records DEBUG.",
)
@click.option(
    "--show-data/--no-data",
    "show_data",
    default=None,
    help="Force or suppress per-entity data dumps (default: dump entities up to 50 rows).",
)
@click.option(
    "--benchmark",
    is_flag=True,
    help="Record per-phase metrics to benchmarks/ after the run (implies --no-data).",
)
def main(
    config_path: Path,
    sgbd_config_path: Path,
    dry_run: bool,
    create_schema: bool,
    only: str,
    source_pairs: Tuple[str, ...],
    log_level: str,
    show_data: Optional[bool],
    benchmark: bool,
) -> None:
    """Import CSV sources into multiple databases according to --config."""
    log_path = setup_reporting(getattr(logging, log_level.upper()))
    if log_path is not None:
        kv("Log file", log_path)
    only_list = [x.strip() for x in only.split(",") if x.strip()] if only else None
    overrides = _parse_source_overrides(source_pairs)
    try:
        run_import(
            config_path,
            sgbd_config_path=sgbd_config_path,
            dry_run=dry_run,
            create_schema=create_schema,
            only=only_list,
            source_overrides=overrides or None,
            show_data=show_data,
            benchmark=benchmark,
        )
    except BusinessException as e:
        error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
