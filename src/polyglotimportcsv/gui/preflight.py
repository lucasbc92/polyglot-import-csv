"""Checks run before an import, with the CLI's own code, on CSV headers only.

Pure Python: no Qt. Nothing here re-implements a CLI rule. The configuration
files go through ``config_parser`` exactly as ``run_import`` loads them, and
each entity is bound and validated by ``mapping_resolver`` and ``validation``,
the same functions the materialize path calls, over sources that hold only a
header. A column the configuration names but the CSV lacks therefore produces
the very message the CLI would print, before anything runs.

What is not checked here is anything needing a database connection or the
data rows themselves. In particular the origin values of a combined CSV are
never read: that would mean scanning a file that may be larger than memory.
The CLI still checks all of it when the import runs.

Every file read is cached by (path, mtime, size), because the window calls
``check`` on every click; in steady state a call costs a few ``stat``s.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from polyglotimportcsv.business_exception import BusinessException
from polyglotimportcsv.config_parser import (
    BACKENDS,
    DEFAULT_SGBD_CONFIG_NAME,
    load_import_config,
    load_sgbd_config,
    merge_configs,
)
from polyglotimportcsv.gui.state import RunOptions
from polyglotimportcsv.mapping_resolver import resolve_backend_entities
from polyglotimportcsv.sources import SOURCE_COLUMN, SourceData
from polyglotimportcsv.validation import validate_backend_entities

MULTI = "multi"
COMBINED = "combined"

_Stamp = Tuple[int, int]
_cache = {}  # type: Dict[Tuple[str, str], Tuple[_Stamp, Any]]


@dataclass(frozen=True)
class Preflight:
    """What the form needs to know about the chosen configuration.

    ``kind`` is None until the import configuration has passed its own schema;
    the sources card refuses new files until then.
    """

    kind: Optional[str] = None
    declared: Optional[Dict[str, str]] = None
    errors: Dict[str, str] = field(default_factory=dict)


def clear_cache() -> None:
    _cache.clear()


def classify_sources(sources: Dict[str, Any]) -> str:
    """``combined`` for exactly one source declared as ``{"file": ...}``.

    Every other shape, including the mixed one the schema allows, is
    ``multi``: each override row then maps to one declared source.
    """
    if len(sources) == 1 and isinstance(next(iter(sources.values())), dict):
        return COMBINED
    return MULTI


def check(options: RunOptions) -> Preflight:
    path = options.config_path
    if path is None or not path.is_file():
        return Preflight()  # state.validate already reports this

    try:
        import_cfg = _cached("import", path, load_import_config)
    except BusinessException as exc:
        return Preflight(errors={"config_path": str(exc)})

    sources_cfg = import_cfg.get("sources") or {}
    kind = classify_sources(sources_cfg)
    declared = {
        name: (decl if isinstance(decl, str) else decl.get("file", ""))
        for name, decl in sources_cfg.items()
    }
    errors = {}  # type: Dict[str, str]

    sgbd_error = _check_sgbd(options, path, import_cfg)
    if sgbd_error:
        errors["sgbd_config_path"] = sgbd_error

    sources_error = _check_overrides(options, kind, declared)
    if sources_error:
        errors["sources"] = sources_error
    else:
        key, message = _check_headers(options, path.parent, import_cfg, sources_cfg)
        if message:
            errors[key] = message

    return Preflight(kind=kind, declared=declared, errors=errors)


# -- steps ----------------------------------------------------------------


def _check_sgbd(options: RunOptions, import_path: Path, import_cfg: Dict[str, Any]) -> str:
    sgbd_path = options.sgbd_config_path
    if sgbd_path is None:
        sgbd_path = import_path.with_name(DEFAULT_SGBD_CONFIG_NAME)
        if not sgbd_path.is_file():
            return (
                "Configuração de SGBDs não informada e {0} não encontrado ao lado "
                "da configuração de importação.".format(DEFAULT_SGBD_CONFIG_NAME)
            )
    elif not sgbd_path.is_file():
        return ""  # state.validate already reports this
    try:
        sgbd_cfg = _cached("sgbd", sgbd_path, load_sgbd_config)
        merge_configs(import_cfg, sgbd_cfg)
    except BusinessException as exc:
        return str(exc)
    return ""


def _check_overrides(options: RunOptions, kind: str, declared: Dict[str, str]) -> str:
    if kind == COMBINED and len(options.sources) > 1:
        return "A configuração combinada aceita um único arquivo CSV."
    for name, _path in options.sources:
        if name and name not in declared:
            return "Fonte não declarada na configuração de importação: {0}".format(name)
    return ""


def _check_headers(
    options: RunOptions,
    base_dir: Path,
    import_cfg: Dict[str, Any],
    sources_cfg: Dict[str, Any],
) -> Tuple[str, str]:
    """Bind and validate every entity against header-only sources.

    Returns ``(error key, message)``; the message is empty when all is well.
    Problems are shown under the sources card when the person has overridden
    a path, and under the configuration card otherwise.
    """
    key = "sources" if options.sources else "config_path"
    overrides = {name: path for name, path in options.sources}
    registry = {}  # type: Dict[str, SourceData]
    combined_header = None  # type: Optional[List[str]]
    for name, decl in sources_cfg.items():
        file_name = decl if isinstance(decl, str) else decl.get("file", "")
        # Same resolution as sources._resolve_path: an override follows the
        # working directory, a declared path the configuration's folder.
        if name in overrides:
            csv_path = Path(overrides[name])
        else:
            csv_path = Path(file_name)
            if not csv_path.is_absolute():
                csv_path = base_dir / csv_path
        if not csv_path.is_file():
            return key, "Fonte '{0}': arquivo CSV não encontrado: {1}".format(name, csv_path)
        try:
            header = _cached("header", csv_path, _read_header)
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            return key, "Fonte '{0}': não foi possível ler o cabeçalho de {1}: {2}".format(
                name, csv_path, exc
            )
        if isinstance(decl, str):
            registry[name] = _header_only(name, header)
            continue
        if len(header) < 2:
            return key, (
                "Source '{0}': combined CSV needs an origin column plus data "
                "columns: {1}".format(name, csv_path)
            )
        combined_header = header[1:]
        registry[name] = _header_only(name, combined_header)

    only = set(options.only) if options.only else None
    dbms_names = [b for b in BACKENDS if b in import_cfg and (only is None or b in only)]
    if combined_header is not None:
        # The origin values that name each slice are in the rows, which are
        # not read. Every name an entity refers to stands for one slice.
        for dbms in dbms_names:
            for ename, ecfg in (import_cfg[dbms].get("entities") or {}).items():
                ref = (ecfg or {}).get("source", ename)
                for name in ref if isinstance(ref, list) else [ref]:
                    registry.setdefault(name, _header_only(name, combined_header))
    try:
        for dbms in dbms_names:
            bound = resolve_backend_entities(import_cfg[dbms], registry)
            validate_backend_entities(dbms, import_cfg[dbms], bound)
    except BusinessException as exc:
        return key, str(exc)
    except ValueError as exc:
        return key, str(exc)
    return key, ""


# -- file access ----------------------------------------------------------


def _read_header(path: Path) -> List[str]:
    """The column names only, read the way csv_reader.read_csv reads them."""
    frame = pd.read_csv(path, dtype=str, nrows=0, keep_default_na=False, encoding="utf-8-sig")
    return [str(column) for column in frame.columns]


def _header_only(name: str, columns: List[str]) -> SourceData:
    frame = pd.DataFrame({column: pd.Series(dtype=str) for column in columns + [SOURCE_COLUMN]})
    kinds = {column: "string" for column in columns}
    kinds[SOURCE_COLUMN] = "string"
    return SourceData(name=name, df=frame, kinds=kinds, file_header=list(columns))


def _cached(kind: str, path: Path, load: Callable[[Path], Any]) -> Any:
    """``load(path)``, reused while the file's mtime and size are unchanged.

    A failure is cached too, so a broken file is not re-parsed on every click;
    rewriting the file changes its stamp and clears the entry.
    """
    stat = path.stat()
    stamp = (stat.st_mtime_ns, stat.st_size)
    entry = (kind, str(path.resolve()))
    hit = _cache.get(entry)
    if hit is not None and hit[0] == stamp:
        value = hit[1]
    else:
        try:
            value = load(path)
        except Exception as exc:  # noqa: BLE001 - re-raised below, from the cache too
            value = exc
        _cache[entry] = (stamp, value)
    if isinstance(value, Exception):
        raise value
    return value
