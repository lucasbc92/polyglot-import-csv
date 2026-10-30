"""Form state of the GUI and its local validation.

Pure Python: importing Qt here would make the rules untestable without a
running QApplication, so it is forbidden. The rules answer one question only —
"can we hand this to the CLI?" — They never open the files: reading the
configurations and the CSV headers is ``preflight``'s job.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from polyglotimportcsv.import_plan import DEFAULT_BATCH_SIZE, MAX_BATCH_SIZE, MIN_BATCH_SIZE
from polyglotimportcsv.reporting import DEFAULT_SAMPLE_SIZE
from polyglotimportcsv.stream_source import DEFAULT_CHUNK_MB, MAX_CHUNK_MB, MIN_CHUNK_MB

DBMS_NAMES = ("postgres", "redis", "mongodb", "cassandra", "neo4j")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
MAX_SAMPLE_SIZE = 1000000

__all__ = [
    "DBMS_NAMES", "LOG_LEVELS", "DEFAULT_SAMPLE_SIZE",
    "MAX_SAMPLE_SIZE", "RunOptions", "validate",
]


@dataclass(frozen=True)
class RunOptions:
    """Every CLI option the GUI can set. Defaults mirror ``cli.main``.

    ``show_data`` follows the CLI tri-state: ``None`` is the sample of
    ``sample_size`` rows, ``True`` every row, ``False`` none.
    """

    config_path: Optional[Path] = None
    dbms_config_path: Optional[Path] = None
    only: Tuple[str, ...] = ()
    chunk_size_mb: int = DEFAULT_CHUNK_MB
    batch_size: int = DEFAULT_BATCH_SIZE
    dry_run: bool = False
    create_schema: bool = True
    log_level: str = "INFO"
    show_data: Optional[bool] = None
    sample_size: int = DEFAULT_SAMPLE_SIZE
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

    if options.dbms_config_path is not None and not options.dbms_config_path.is_file():
        errors["dbms_config_path"] = _missing(options.dbms_config_path)

    for name in options.only:
        if name not in DBMS_NAMES:
            errors["only"] = "SGBD desconhecido: {0}".format(name)
            break

    if not MIN_CHUNK_MB <= options.chunk_size_mb <= MAX_CHUNK_MB:
        errors["chunk_size_mb"] = "O bloco deve ter entre 8 e 256 MB."

    if not MIN_BATCH_SIZE <= options.batch_size <= MAX_BATCH_SIZE:
        errors["batch_size"] = "O lote deve ter entre 1024 e 8192 linhas."

    if options.show_data is None and not 1 <= options.sample_size <= MAX_SAMPLE_SIZE:
        errors["sample_size"] = "O tamanho da amostra deve estar entre 1 e {0}.".format(
            MAX_SAMPLE_SIZE
        )

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
