"""Form state of the GUI and its local validation.

Pure Python: importing Qt here would make the rules untestable without a
running QApplication, so it is forbidden. The rules answer one question only —
"can we hand this to the CLI?" — and never inspect the JSON contents, which are
the JSON Schema's job.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

DBMS_NAMES = ("postgres", "redis", "mongodb", "cassandra", "neo4j")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
STRATEGIES = ("naive", "optimized")
EXECUTIONS = ("stream", "materialize")


@dataclass(frozen=True)
class RunOptions:
    """Every CLI option the GUI can set. Defaults mirror ``cli.main``."""

    config_path: Optional[Path] = None
    sgbd_config_path: Optional[Path] = None
    only: Tuple[str, ...] = ()
    strategy: str = "optimized"
    execution: str = "stream"
    dry_run: bool = False
    create_schema: bool = True
    benchmark: bool = False
    log_level: str = "INFO"
    show_data: Optional[bool] = None
    sources: Tuple[Tuple[str, Path], ...] = ()


def _missing(path: Path) -> str:
    return "Arquivo não encontrado: {0}".format(path)


def validate(options: RunOptions) -> Dict[str, str]:
    """Return ``{field: message}`` for every violation; empty means runnable."""
    errors = {}  # type: Dict[str, str]

    if options.config_path is None:
        errors["config_path"] = "Selecione a configuração de importação."
    elif not options.config_path.is_file():
        errors["config_path"] = _missing(options.config_path)

    if options.sgbd_config_path is not None and not options.sgbd_config_path.is_file():
        errors["sgbd_config_path"] = _missing(options.sgbd_config_path)

    for name in options.only:
        if name not in DBMS_NAMES:
            errors["only"] = "SGBD desconhecido: {0}".format(name)
            break

    seen = set()
    for name, path in options.sources:
        if not name:
            errors["sources"] = "O nome da fonte não pode ficar vazio."
            break
        if "=" in name:
            errors["sources"] = "O nome da fonte não pode conter '=': {0}".format(name)
            break
        if name in seen:
            errors["sources"] = "Nome de fonte repetido: {0}".format(name)
            break
        seen.add(name)
        if not path.is_file():
            errors["sources"] = _missing(path)
            break

    return errors
