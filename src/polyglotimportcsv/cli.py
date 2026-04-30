"""Command-line interface for PolyglotImportCSV."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from polyglotimportcsv.business_exception import BusinessException
from polyglotimportcsv.runner import run_import

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("csv_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="JSON import configuration (validated against bundled JSON Schema).",
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
def main(
    csv_path: Path,
    config_path: Path,
    dry_run: bool,
    create_schema: bool,
    only: str,
) -> None:
    """Import CSV rows into multiple databases according to CONFIG."""
    only_list = [x.strip() for x in only.split(",") if x.strip()] if only else None
    try:
        run_import(
            csv_path,
            config_path,
            dry_run=dry_run,
            create_schema=create_schema,
            only=only_list,
        )
    except BusinessException as e:
        logger.error("%s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
