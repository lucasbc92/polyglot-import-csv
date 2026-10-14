"""
Backend importer contract (Interface Segregation / Dependency Inversion).

Concrete importers live in sibling modules; the runner depends only on this
protocol-shaped callable, not on driver-specific types.
"""

from __future__ import annotations

from typing import Any, Dict, List, Protocol

from polyglotimportcsv.mapping_resolver import BoundEntity


class BackendImporterFn(Protocol):
    """Each backend exposes a module-level ``run_*_import`` matching this shape."""

    def __call__(
        self,
        backend_cfg: Dict[str, Any],
        entities: Dict[str, BoundEntity],
        *,
        dry_run: bool,
        create_schema: bool,
    ) -> List[str]:
        ...


ImporterRegistry = Dict[str, BackendImporterFn]
