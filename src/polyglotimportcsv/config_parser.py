"""Load and validate import configuration JSON."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Union

import jsonschema

from polyglotimportcsv.business_exception import BusinessException


def _load_schema() -> Dict[str, Any]:
    pkg = resources.files("polyglotimportcsv.schemas")
    raw = (pkg / "polyglot_import_config.schema.json").read_text(encoding="utf-8")
    return json.loads(raw)


def load_config(path: Union[str, Path]) -> Dict[str, Any]:
    """Load JSON config from path and validate against the bundled schema."""
    p = Path(path)
    if not p.is_file():
        raise BusinessException(f"Config file not found: {p}")
    with p.open(encoding="utf-8") as f:
        data = json.load(f)
    validate_config(data)
    return data


def validate_config(data: Dict[str, Any]) -> None:
    schema = _load_schema()
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as e:
        raise BusinessException(f"Invalid configuration JSON: {e.message}") from e
