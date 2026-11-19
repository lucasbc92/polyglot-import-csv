"""Load and validate the import and DBMS configuration JSON files.

The configuration is split into two files:

* ``dbms_config.json`` — connection settings for each DBMS
  (which DBMSs are available and how to reach them).
* ``import_config.json`` — a ``sources`` block naming the CSV(s) to import,
  plus the entity/relationship/column mapping from those sources to each
  DBMS, with no connection details.

``load_config`` validates each file against its own JSON Schema, ensures the
import configuration only targets DBMSs declared in the DBMS configuration,
and returns a single merged structure: the import configuration with the
connection settings of each DBMS added to its block.
"""

from __future__ import annotations

import copy
import json
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import jsonschema

from polyglotimportcsv.business_exception import ConfigError

DBMS_NAMES = ("postgres", "mongodb", "cassandra", "redis", "neo4j")

#: Default name of the DBMS configuration file, looked up next to the import
#: configuration when an explicit path is not provided.
DEFAULT_DBMS_CONFIG_NAME = "dbms_config.json"


def _load_schema(name: str) -> Dict[str, Any]:
    pkg = resources.files("polyglotimportcsv.schemas")
    raw = (pkg / name).read_text(encoding="utf-8")
    return json.loads(raw)


def _read_json(path: Union[str, Path], label: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise ConfigError(f"{label} file not found: {p}")
    with p.open(encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigError(f"Invalid JSON in {label} ({p}): {e}") from e


#: Name of the pre-1.1.0 DBMS config file. Never loaded, only used to hint at
#: the rename when ``dbms_config.json`` is missing.
_LEGACY_DBMS_CONFIG_NAME = "sgbd_config.json"


def load_dbms_config(path: Union[str, Path]) -> Dict[str, Any]:
    """Load and validate the DBMS connection configuration."""
    p = Path(path)
    if not p.is_file() and p.with_name(_LEGACY_DBMS_CONFIG_NAME).is_file():
        raise ConfigError(
            f"DBMS config file not found: {p} "
            f"({_LEGACY_DBMS_CONFIG_NAME} was renamed to dbms_config.json in 1.1.0)"
        )
    data = _read_json(path, "DBMS config")
    validate_dbms_config(data)
    return data


def load_import_config(path: Union[str, Path]) -> Dict[str, Any]:
    """Load and validate the import (mapping) configuration."""
    data = _read_json(path, "Import config")
    validate_import_config_schema(data)
    return data


_ALTERNATIVES = ("oneOf", "anyOf")


def _branch_rank(errors: List[jsonschema.ValidationError]) -> Tuple[int, int, int]:
    """Order the failed branches of a oneOf/anyOf, most likely intended first.

    The branch the author meant is the one with the fewest failures; on a tie,
    the one whose failures go deepest into the instance, then the one with
    fewer failures that are themselves just another oneOf/anyOf.
    """
    deepest = max(len(error.path) for error in errors)
    vague = sum(error.validator in _ALTERNATIVES for error in errors)
    return (len(errors), -deepest, vague)


def _most_useful_error(
    errors: Iterable[jsonschema.ValidationError],
) -> Optional[jsonschema.ValidationError]:
    """The error to report, descending oneOf/anyOf into the intended branch.

    ``jsonschema.best_match`` descends a failed oneOf into its deepest error,
    whichever branch it came from. A column is either a leaf spec or a MongoDB
    subdocument, so a leaf with a bad ``is_key`` was reported on a sibling
    (``db_type``) that only the subdocument reading rejects.

    When no branch stands out (e.g. a source that is neither a path nor an
    object), the oneOf error itself is kept: it says that every form failed.
    """
    best = max(errors, key=jsonschema.exceptions.relevance, default=None)
    while best is not None and best.validator in _ALTERNATIVES and best.context:
        branches: Dict[Any, List[jsonschema.ValidationError]] = {}
        for error in best.context:
            branches.setdefault(error.relative_schema_path[0], []).append(error)
        ranked = sorted(branches.values(), key=_branch_rank)
        if len(ranked) > 1 and _branch_rank(ranked[0]) == _branch_rank(ranked[1]):
            return best
        best = max(ranked[0], key=jsonschema.exceptions.relevance)
    return best


def _validate(data: Dict[str, Any], schema_name: str, label: str) -> None:
    schema = _load_schema(schema_name)
    validator = jsonschema.validators.validator_for(schema)(schema)
    error = _most_useful_error(validator.iter_errors(data))
    if error is not None:
        raise ConfigError(f"Invalid {label} JSON at {error.json_path}: {error.message}")


def validate_dbms_config(data: Dict[str, Any]) -> None:
    _validate(data, "dbms_config.schema.json", "DBMS configuration")


def validate_import_config_schema(data: Dict[str, Any]) -> None:
    _validate(data, "import_config.schema.json", "import configuration")


def merge_configs(
    import_cfg: Dict[str, Any], dbms_cfg: Dict[str, Any]
) -> Dict[str, Any]:
    """Combine mapping and connection configs into one structure per DBMS.

    Every DBMS present in the import configuration must also be declared in
    the DBMS configuration, otherwise a :class:`BusinessException` is raised.
    """
    import_dbms = [b for b in DBMS_NAMES if b in import_cfg]
    missing = [b for b in import_dbms if b not in dbms_cfg]
    if missing:
        raise ConfigError(
            "Import config targets DBMS not declared in the DBMS config: "
            f"{', '.join(missing)}. Add them to dbms_config.json or remove them "
            "from import_config.json."
        )

    merged: Dict[str, Any] = {"sources": copy.deepcopy(import_cfg.get("sources") or {})}
    for dbms in import_dbms:
        entry = copy.deepcopy(import_cfg[dbms])
        dbms_entry = dbms_cfg.get(dbms) or {}
        # Connection settings (and postgres 'schema') come from the DBMS config.
        for key in ("connection", "schema"):
            if key in dbms_entry:
                entry[key] = copy.deepcopy(dbms_entry[key])
        merged[dbms] = entry
    return merged


def resolve_dbms_config_path(
    import_path: Union[str, Path], dbms_path: Optional[Union[str, Path]] = None
) -> Path:
    """``dbms_path``, or ``dbms_config.json`` next to the import configuration."""
    if dbms_path is None:
        return Path(import_path).with_name(DEFAULT_DBMS_CONFIG_NAME)
    return Path(dbms_path)


def load_config(
    import_path: Union[str, Path],
    dbms_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Load both configuration files and return the merged structure.

    When ``dbms_path`` is omitted, a file named ``dbms_config.json`` next to the
    import configuration is used.
    """
    import_path = Path(import_path)
    dbms_path = resolve_dbms_config_path(import_path, dbms_path)

    import_cfg = load_import_config(import_path)
    dbms_cfg = load_dbms_config(dbms_path)
    return merge_configs(import_cfg, dbms_cfg)
