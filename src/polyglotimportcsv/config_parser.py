"""Load and validate the import and SGBD configuration JSON files.

The configuration is split into two files:

* ``sgbd_config.json`` — connection settings for each database backend
  (which SGBDs are available and how to reach them).
* ``import_config.json`` — the entity/relationship/column mapping from the
  CSV to each backend, with no connection details.

``load_config`` validates each file against its own JSON Schema, ensures the
import configuration only targets backends declared in the SGBD configuration,
and returns a single merged structure (the shape the importers expect).
"""

from __future__ import annotations

import copy
import json
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Optional, Union

import jsonschema

from polyglotimportcsv.business_exception import BusinessException

BACKENDS = ("postgres", "mongodb", "cassandra", "redis", "neo4j")

#: Default name of the SGBD configuration file, looked up next to the import
#: configuration when an explicit path is not provided.
DEFAULT_SGBD_CONFIG_NAME = "sgbd_config.json"


def _load_schema(name: str) -> Dict[str, Any]:
    pkg = resources.files("polyglotimportcsv.schemas")
    raw = (pkg / name).read_text(encoding="utf-8")
    return json.loads(raw)


def _read_json(path: Union[str, Path], label: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise BusinessException(f"{label} file not found: {p}")
    with p.open(encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            raise BusinessException(f"Invalid JSON in {label} ({p}): {e}") from e


def load_sgbd_config(path: Union[str, Path]) -> Dict[str, Any]:
    """Load and validate the SGBD connection configuration."""
    data = _read_json(path, "SGBD config")
    validate_sgbd_config(data)
    return data


def load_import_config(path: Union[str, Path]) -> Dict[str, Any]:
    """Load and validate the import (mapping) configuration."""
    data = _read_json(path, "Import config")
    validate_import_config_schema(data)
    return data


def validate_sgbd_config(data: Dict[str, Any]) -> None:
    schema = _load_schema("sgbd_config.schema.json")
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as e:
        raise BusinessException(f"Invalid SGBD configuration JSON: {e.message}") from e


def validate_import_config_schema(data: Dict[str, Any]) -> None:
    schema = _load_schema("import_config.schema.json")
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as e:
        raise BusinessException(f"Invalid import configuration JSON: {e.message}") from e


def merge_configs(
    import_cfg: Dict[str, Any], sgbd_cfg: Dict[str, Any]
) -> Dict[str, Any]:
    """Combine mapping and connection configs into one backend structure.

    Every backend present in the import configuration must also be declared in
    the SGBD configuration, otherwise a :class:`BusinessException` is raised.
    """
    import_backends = [b for b in BACKENDS if b in import_cfg]
    missing = [b for b in import_backends if b not in sgbd_cfg]
    if missing:
        raise BusinessException(
            "Import config targets backend(s) not declared in the SGBD config: "
            f"{', '.join(missing)}. Add them to sgbd_config.json or remove them "
            "from import_config.json."
        )

    merged: Dict[str, Any] = {"version": import_cfg.get("version", 1)}
    for backend in import_backends:
        backend_cfg = copy.deepcopy(import_cfg[backend])
        sgbd_backend = sgbd_cfg.get(backend) or {}
        # Connection settings (and postgres 'schema') come from the SGBD config.
        for key in ("connection", "schema"):
            if key in sgbd_backend:
                backend_cfg[key] = copy.deepcopy(sgbd_backend[key])
        merged[backend] = backend_cfg
    return merged


def load_config(
    import_path: Union[str, Path],
    sgbd_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Load both configuration files and return the merged structure.

    When ``sgbd_path`` is omitted, a file named ``sgbd_config.json`` next to the
    import configuration is used.
    """
    import_path = Path(import_path)
    if sgbd_path is None:
        sgbd_path = import_path.with_name(DEFAULT_SGBD_CONFIG_NAME)

    import_cfg = load_import_config(import_path)
    sgbd_cfg = load_sgbd_config(sgbd_path)
    return merge_configs(import_cfg, sgbd_cfg)
