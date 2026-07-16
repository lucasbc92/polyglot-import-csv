# TCC2 Config v2 + Pipeline Implementation Plan (Plano 1 de 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-CSV + `action`-filter import format with the v2 format: a `sources` block (one CSV per entity as the default mode, combined CSV with origin column as the alternative), auto-mapping with type inference, `_source` pseudo-column, and a shallow exception hierarchy.

**Architecture:** A new source-loading layer (`sources.py`) reads every declared CSV once and slices combined files by column 0; a resolver (`mapping_resolver.py`) binds each entity to its source and expands the effective column mapping (auto-map + manual overrides + inferred types); the runner dispatches per-entity typed DataFrames to importers whose signature changes from `(cfg, global_df, kinds, …)` to `(cfg, Dict[str, BoundEntity], …)`.

**Tech Stack:** Python 3.12, pandas, jsonschema, click, pytest. Venv at `.venv/` — run everything with `./.venv/Scripts/python.exe` (Git Bash on Windows).

**Spec:** `docs/superpowers/specs/2026-07-08-tcc2-import-modes-design.md` (approved). Plans 2 (rich logging/metrics) and 3 (benchmarks) come later and are NOT in this plan.

## Global Constraints

- The `version` field is REMOVED from the import config format entirely (schema, examples, code, tests, LaTeX mentions). No v1/v2 coexistence.
- Combined CSV: column 0 IS the origin column (no configuration of its position). Each distinct origin value becomes a source name. Origin values are also reachable via the pseudo-column `_source`.
- Column indexing in configs (`csv_columns` tokens and integer `csv_column`) is **1-based over data columns** (the origin column, when present, is "column 0" and is not indexable; `_source` is not indexable).
- Auto-map excludes `_source`; `_source` participates only when manually cited.
- `csv_columns` is only valid with auto-mapping (no `columns`, or `auto_map: true`); with manual-only `columns` it is a `MappingError`.
- Manual column specs always win over inferred specs (per-column replacement, not deep merge).
- Kind→type table: `integer→BIGINT`, `float→NUMERIC`, `datetime→TIMESTAMPTZ`, `boolean→BOOLEAN`, `string/empty→TEXT`.
- Exception taxonomy (all subclass `BusinessException`): `ConfigError`, `SourceError`, `MappingError`, `ImportExecutionError`.
- Git: commit at the end of every task; do NOT push unless the user asks.
- Test command (Git Bash): `./.venv/Scripts/python.exe -m pytest tests -q` (single file: append path).

---

### Task 1: Exception hierarchy

**Files:**
- Modify: `src/polyglotimportcsv/business_exception.py`
- Test: `tests/test_exceptions.py` (create)

**Interfaces:**
- Produces: `BusinessException`, `ConfigError`, `SourceError`, `MappingError`, `ImportExecutionError` — all importable from `polyglotimportcsv.business_exception`. Later tasks raise these; the CLI keeps catching only `BusinessException`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_exceptions.py`:

```python
"""Shallow exception hierarchy: category types under BusinessException."""

import pytest

from polyglotimportcsv.business_exception import (
    BusinessException,
    ConfigError,
    ImportExecutionError,
    MappingError,
    SourceError,
)


@pytest.mark.parametrize(
    "exc_type", [ConfigError, SourceError, MappingError, ImportExecutionError]
)
def test_categories_subclass_business_exception(exc_type):
    assert issubclass(exc_type, BusinessException)
    with pytest.raises(BusinessException):
        raise exc_type("boom")


def test_message_is_preserved():
    try:
        raise SourceError("file not found: x.csv")
    except BusinessException as e:
        assert "x.csv" in str(e)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_exceptions.py -q`
Expected: FAIL — `ImportError: cannot import name 'ConfigError'`

- [ ] **Step 3: Write minimal implementation**

Replace the whole content of `src/polyglotimportcsv/business_exception.py`:

```python
"""User-facing error taxonomy (shallow hierarchy, one class per failure category)."""


class BusinessException(Exception):
    """Base class for every error reported to the user by the CLI."""


class ConfigError(BusinessException):
    """Invalid JSON, JSON Schema violation, or backend without declared connection."""


class SourceError(BusinessException):
    """Unknown source, missing CSV file, or origin/source name collision."""


class MappingError(BusinessException):
    """Unknown column/index/range, or entity without a resolvable source."""


class ImportExecutionError(BusinessException):
    """Failure while connecting to or writing into a target SGBD."""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_exceptions.py -q`
Expected: PASS (2 tests, parametrized = 5 passing items)

- [ ] **Step 5: Run the full suite to check nothing broke**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: all existing tests still PASS (hierarchy is additive).

- [ ] **Step 6: Commit**

```bash
git add src/polyglotimportcsv/business_exception.py tests/test_exceptions.py
git commit -m "feat: shallow exception hierarchy under BusinessException"
```

---

### Task 2: Casting module + boolean kind inference

**Files:**
- Create: `src/polyglotimportcsv/casting.py`
- Modify: `src/polyglotimportcsv/csv_reader.py`
- Test: `tests/test_casting.py` (create)

**Interfaces:**
- Produces: `casting.KIND_TO_DB_TYPE: Dict[str, str]`; `casting.is_boolean_series(s: pd.Series) -> bool`; `casting.cast_value(val, kind: str) -> Any`; `casting.cast_frame(df: pd.DataFrame, kinds: Dict[str, str]) -> pd.DataFrame`.
- `csv_reader.infer_column_kinds` now may return `"boolean"` as a kind.

- [ ] **Step 1: Write the failing test**

Create `tests/test_casting.py`:

```python
"""Native-value casting and boolean kind detection."""

from datetime import datetime

import pandas as pd

from polyglotimportcsv.casting import KIND_TO_DB_TYPE, cast_frame, cast_value
from polyglotimportcsv.csv_reader import infer_column_kinds


def test_kind_to_db_type_table():
    assert KIND_TO_DB_TYPE == {
        "integer": "BIGINT",
        "float": "NUMERIC",
        "datetime": "TIMESTAMPTZ",
        "boolean": "BOOLEAN",
        "string": "TEXT",
        "empty": "TEXT",
    }


def test_cast_value_scalars():
    assert cast_value("42", "integer") == 42
    assert cast_value("3.5", "float") == 3.5
    assert cast_value("true", "boolean") is True
    assert cast_value("False", "boolean") is False
    assert cast_value("", "integer") is None
    assert cast_value(None, "float") is None
    dt = cast_value("2023-11-02 03:30:00Z", "datetime")
    assert isinstance(dt, datetime) and dt.tzinfo is not None
    # Unparseable values fall back untouched rather than crashing.
    assert cast_value("abc", "integer") == "abc"


def test_infer_kinds_detects_boolean():
    df = pd.DataFrame({"flag": ["true", "FALSE", ""], "n": ["1", "2", "3"]})
    kinds = infer_column_kinds(df)
    assert kinds["flag"] == "boolean"
    assert kinds["n"] == "integer"


def test_cast_frame_converts_typed_columns_and_keeps_strings():
    df = pd.DataFrame(
        {"n": ["1", "", "3"], "name": ["a", "", "c"], "flag": ["true", "false", ""]}
    )
    kinds = {"n": "integer", "name": "string", "flag": "boolean"}
    out = cast_frame(df, kinds)
    assert list(out["n"]) == [1, None, 3]
    assert list(out["flag"]) == [True, False, None]
    # String columns are untouched (empty string stays empty, not None).
    assert list(out["name"]) == ["a", "", "c"]
    # Original frame is not mutated.
    assert list(df["n"]) == ["1", "", "3"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_casting.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'polyglotimportcsv.casting'`

- [ ] **Step 3: Create `src/polyglotimportcsv/casting.py`**

```python
"""Kind→type table and native-value casting for typed columns."""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

#: Inferred column kind -> DDL type used when auto-mapping (spec §2.5).
KIND_TO_DB_TYPE: Dict[str, str] = {
    "integer": "BIGINT",
    "float": "NUMERIC",
    "datetime": "TIMESTAMPTZ",
    "boolean": "BOOLEAN",
    "string": "TEXT",
    "empty": "TEXT",
}

_BOOL_WORDS = {"true", "false"}


def is_boolean_series(non_empty: pd.Series) -> bool:
    """True when every non-empty value is 'true'/'false' (case-insensitive)."""
    vals = {str(v).strip().lower() for v in non_empty}
    return bool(vals) and vals <= _BOOL_WORDS


def cast_value(val: Any, kind: str) -> Any:
    """Convert one CSV string to a native Python value; '' and None become None."""
    if val is None or val == "":
        return None
    if kind == "integer":
        try:
            return int(val)
        except (TypeError, ValueError):
            return val
    if kind == "float":
        try:
            return float(val)
        except (TypeError, ValueError):
            return val
    if kind == "boolean":
        return str(val).strip().lower() == "true"
    if kind == "datetime":
        ts = pd.to_datetime(val, errors="coerce", utc=True)
        return None if pd.isna(ts) else ts.to_pydatetime()
    return val


def cast_frame(df: pd.DataFrame, kinds: Dict[str, str]) -> pd.DataFrame:
    """Return a copy with typed columns converted to native values.

    Only integer/float/boolean/datetime columns are converted (empty cells
    become None); string columns keep their raw values, including ''.
    """
    out = df.copy()
    for col in out.columns:
        kind = kinds.get(col, "string")
        if kind in ("integer", "float", "boolean", "datetime"):
            out[col] = out[col].map(lambda v, k=kind: cast_value(v, k)).astype(object)
    return out
```

- [ ] **Step 4: Extend `infer_column_kinds` in `src/polyglotimportcsv/csv_reader.py`**

Add the import at the top (after `import pandas as pd`):

```python
from polyglotimportcsv.casting import is_boolean_series
```

Inside `infer_column_kinds`, right after the `if s2.empty:` block (which sets `kinds[col] = "empty"`), insert the boolean check BEFORE the datetime parsing:

```python
        if is_boolean_series(s2):
            kinds[col] = "boolean"
            continue
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_casting.py tests -q`
Expected: PASS (new tests and full suite — boolean detection must not change kinds for the e-commerce CSV, which has no true/false columns).

- [ ] **Step 6: Commit**

```bash
git add src/polyglotimportcsv/casting.py src/polyglotimportcsv/csv_reader.py tests/test_casting.py
git commit -m "feat: casting module with kind->type table and boolean kind inference"
```

---

### Task 3: Column selector (names, 1-based indices, ranges)

**Files:**
- Create: `src/polyglotimportcsv/column_selector.py`
- Test: `tests/test_column_selector.py` (create)

**Interfaces:**
- Produces: `column_selector.select_columns(tokens: Sequence, header: Sequence[str], *, context: str = "") -> List[str]` — resolves a `csv_columns` list against a source's data-column header; raises `MappingError`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_column_selector.py`:

```python
"""csv_columns tokens: names, 1-based indices, ranges, mixed and overlapping."""

import pytest

from polyglotimportcsv.business_exception import MappingError
from polyglotimportcsv.column_selector import select_columns

HEADER = ["a", "b", "c", "d", "e"]


def test_range_is_one_based_inclusive():
    assert select_columns(["1-3"], HEADER) == ["a", "b", "c"]


def test_mixed_tokens_and_integer_index():
    # JSON integers and strings are both accepted; duplicates collapse.
    assert select_columns(["2-3", "e", 1, "b"], HEADER) == ["a", "b", "c", "e"]


def test_result_keeps_header_order():
    assert select_columns(["e", "a"], HEADER) == ["a", "e"]


@pytest.mark.parametrize("token", ["0", "6", "0-2", "4-9", "3-2"])
def test_out_of_bounds_raises_mapping_error(token):
    with pytest.raises(MappingError):
        select_columns([token], HEADER)


def test_unknown_name_raises_with_context():
    with pytest.raises(MappingError, match="entity 'x'"):
        select_columns(["nope"], HEADER, context="entity 'x'")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_column_selector.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'polyglotimportcsv.column_selector'`

- [ ] **Step 3: Create `src/polyglotimportcsv/column_selector.py`**

```python
"""Resolve csv_columns selections (names, 1-based indices, ranges) to header names."""

from __future__ import annotations

import re
from typing import List, Sequence

from polyglotimportcsv.business_exception import MappingError

_RANGE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")
_INDEX = re.compile(r"^\s*(\d+)\s*$")


def select_columns(
    tokens: Sequence, header: Sequence[str], *, context: str = ""
) -> List[str]:
    """Resolve tokens against `header` (data columns only; index 1 = first).

    Returns the selected column names in header order, without duplicates.
    Raises MappingError for out-of-bounds indices/ranges or unknown names.
    """
    header = list(header)
    where = f" in {context}" if context else ""
    chosen: set[int] = set()
    for token in tokens:
        t = str(token)
        m = _RANGE.match(t)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo < 1 or hi > len(header) or lo > hi:
                raise MappingError(
                    f"csv_columns range '{t}'{where} out of bounds (valid: 1-{len(header)})."
                )
            chosen.update(range(lo - 1, hi))
            continue
        m = _INDEX.match(t)
        if m:
            i = int(m.group(1))
            if i < 1 or i > len(header):
                raise MappingError(
                    f"csv_columns index '{t}'{where} out of bounds (valid: 1-{len(header)})."
                )
            chosen.add(i - 1)
            continue
        if t not in header:
            raise MappingError(
                f"csv_columns name '{t}'{where} not found in the source header."
            )
        chosen.add(header.index(t))
    return [header[i] for i in sorted(chosen)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_column_selector.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/column_selector.py tests/test_column_selector.py
git commit -m "feat: csv_columns selector with names, 1-based indices and ranges"
```

---

### Task 4: Source loading (`sources.py`)

**Files:**
- Create: `src/polyglotimportcsv/sources.py`
- Test: `tests/test_sources.py` (create)

**Interfaces:**
- Produces: `sources.SOURCE_COLUMN = "_source"`; `sources.SourceData` dataclass with fields `name: str`, `df: pd.DataFrame` (data columns + trailing `_source` column, values still raw strings), `kinds: Dict[str, str]`, `file_header: List[str]` (data columns only — the 1-based index space); `sources.load_sources(sources_cfg: Dict[str, Any], base_dir: Path, overrides: Dict[str, str] | None = None) -> Dict[str, SourceData]`.
- A combined declaration registers BOTH the declared name (whole file, per-row `_source` = origin value) AND one source per distinct origin value (slice, constant `_source`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_sources.py`:

```python
"""Named source loading: per-entity files, combined files, collisions."""

from pathlib import Path

import pytest

from polyglotimportcsv.business_exception import SourceError
from polyglotimportcsv.sources import SOURCE_COLUMN, load_sources


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_file_source_gets_constant_source_column(tmp_path):
    _write(tmp_path, "stock.csv", "product_id,price\n1,10.5\n2,20\n")
    reg = load_sources({"stock": "stock.csv"}, tmp_path)
    sd = reg["stock"]
    assert sd.file_header == ["product_id", "price"]
    assert list(sd.df[SOURCE_COLUMN]) == ["stock", "stock"]
    assert sd.kinds["product_id"] == "integer"
    assert sd.kinds[SOURCE_COLUMN] == "string"


def test_combined_source_slices_by_column_zero(tmp_path):
    _write(
        tmp_path,
        "join.csv",
        "action,user_id,product_id\nstock,u1,1\npurchase,u2,2\nstock,u3,3\n",
    )
    reg = load_sources(
        {"eventos": {"file": "join.csv", "origin_column": True}}, tmp_path
    )
    # Whole-file source keeps every row; origin values become _source.
    assert sorted(reg) == ["eventos", "purchase", "stock"]
    assert list(reg["eventos"].df[SOURCE_COLUMN]) == ["stock", "purchase", "stock"]
    # Slices: origin column consumed, _source constant, data columns shared.
    assert reg["stock"].file_header == ["user_id", "product_id"]
    assert len(reg["stock"].df) == 2
    assert len(reg["purchase"].df) == 1
    assert list(reg["purchase"].df["user_id"]) == ["u2"]


def test_collision_between_declared_name_and_origin_value(tmp_path):
    _write(tmp_path, "join.csv", "action,x\nstock,1\n")
    _write(tmp_path, "stock.csv", "x\n2\n")
    with pytest.raises(SourceError, match="collision"):
        load_sources(
            {
                "stock": "stock.csv",
                "eventos": {"file": "join.csv", "origin_column": True},
            },
            tmp_path,
        )


def test_missing_file_raises_source_error(tmp_path):
    with pytest.raises(SourceError, match="not found"):
        load_sources({"stock": "nope.csv"}, tmp_path)


def test_empty_origin_value_raises(tmp_path):
    _write(tmp_path, "join.csv", "action,x\n,1\n")
    with pytest.raises(SourceError, match="empty origin"):
        load_sources({"e": {"file": "join.csv", "origin_column": True}}, tmp_path)


def test_override_replaces_path(tmp_path):
    _write(tmp_path, "real.csv", "a\n1\n")
    reg = load_sources({"stock": "nope.csv"}, tmp_path, overrides={"stock": str(tmp_path / "real.csv")})
    assert len(reg["stock"].df) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_sources.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'polyglotimportcsv.sources'`

- [ ] **Step 3: Create `src/polyglotimportcsv/sources.py`**

```python
"""Load named data sources: per-entity CSV files and combined CSVs with origin column."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from polyglotimportcsv.business_exception import SourceError
from polyglotimportcsv.csv_reader import infer_column_kinds, read_csv

#: Pseudo-column carrying each row's origin (source name or origin value).
SOURCE_COLUMN = "_source"


@dataclass
class SourceData:
    name: str
    df: pd.DataFrame          # data columns + trailing SOURCE_COLUMN (raw strings)
    kinds: Dict[str, str]     # per data column, plus SOURCE_COLUMN -> "string"
    file_header: List[str]    # data columns only: the 1-based index space


def _register(
    registry: Dict[str, SourceData],
    name: str,
    df: pd.DataFrame,
    file_header: List[str],
) -> None:
    if name in registry:
        raise SourceError(
            f"Source name collision: '{name}' is defined more than once "
            "(declared source names and origin values must all be distinct)."
        )
    kinds = infer_column_kinds(df[file_header])
    kinds[SOURCE_COLUMN] = "string"
    registry[name] = SourceData(name=name, df=df, kinds=kinds, file_header=file_header)


def _resolve_path(
    name: str, declared: str, base_dir: Path, overrides: Dict[str, str]
) -> Path:
    path = Path(overrides.get(name, declared))
    if not path.is_absolute():
        path = base_dir / path
    if not path.is_file():
        raise SourceError(f"Source '{name}': CSV file not found: {path}")
    return path


def load_sources(
    sources_cfg: Dict[str, Any],
    base_dir: Path,
    overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, SourceData]:
    """Read every declared source once; combined files also register per-origin slices."""
    registry: Dict[str, SourceData] = {}
    overrides = overrides or {}
    base_dir = Path(base_dir)

    for name, decl in (sources_cfg or {}).items():
        if isinstance(decl, str):
            path = _resolve_path(name, decl, base_dir, overrides)
            df = read_csv(path)
            header = list(df.columns)
            df = df.copy()
            df[SOURCE_COLUMN] = name
            _register(registry, name, df, header)
            continue

        # Combined file: column 0 is the origin column (spec §2.2).
        path = _resolve_path(name, decl["file"], base_dir, overrides)
        raw = read_csv(path)
        if len(raw.columns) < 2:
            raise SourceError(
                f"Source '{name}': combined CSV needs an origin column plus data columns: {path}"
            )
        origin_col = raw.columns[0]
        origins = raw[origin_col].astype(str)
        if (origins.str.strip() == "").any():
            raise SourceError(
                f"Source '{name}': combined CSV has row(s) with empty origin value (column '{origin_col}')."
            )
        data = raw.drop(columns=[origin_col])
        header = list(data.columns)
        data = data.copy()
        data[SOURCE_COLUMN] = origins
        _register(registry, name, data, header)
        for value, group in data.groupby(origins, sort=True):
            _register(registry, str(value), group.reset_index(drop=True), header)

    return registry
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_sources.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/sources.py tests/test_sources.py
git commit -m "feat: named source loading with combined-CSV origin slicing"
```

---

### Task 5: Mapping resolver (`mapping_resolver.py`)

**Files:**
- Create: `src/polyglotimportcsv/mapping_resolver.py`
- Test: `tests/test_mapping_resolver.py` (create)

**Interfaces:**
- Consumes: `SourceData`/`SOURCE_COLUMN` (Task 4), `select_columns` (Task 3), `cast_frame`/`KIND_TO_DB_TYPE` (Task 2), `MappingError` (Task 1).
- Produces: `mapping_resolver.BoundEntity` dataclass (`name: str`, `cfg: Dict[str, Any]` with EXPANDED `columns` and without `source`/`csv_columns`/`auto_map` keys, `df: pd.DataFrame` cast to native values, `kinds: Dict[str, str]`); `mapping_resolver.bind_entity_source(entity_name, entity_cfg, sources) -> SourceData`; `mapping_resolver.expand_entity_columns(entity_name, entity_cfg, source) -> Dict[str, Any]`; `mapping_resolver.resolve_backend_entities(backend_cfg, sources, cast_cache=None) -> Dict[str, BoundEntity]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_mapping_resolver.py`:

```python
"""Entity->source binding and effective column mapping expansion."""

import pandas as pd
import pytest

from polyglotimportcsv.business_exception import MappingError
from polyglotimportcsv.mapping_resolver import (
    bind_entity_source,
    expand_entity_columns,
    resolve_backend_entities,
)
from polyglotimportcsv.sources import SOURCE_COLUMN, SourceData


def _source(name, data, kinds=None):
    df = pd.DataFrame(data)
    header = [c for c in df.columns if c != SOURCE_COLUMN]
    if SOURCE_COLUMN not in df.columns:
        df[SOURCE_COLUMN] = name
    from polyglotimportcsv.csv_reader import infer_column_kinds

    k = kinds or infer_column_kinds(df[header])
    k[SOURCE_COLUMN] = "string"
    return SourceData(name=name, df=df, kinds=k, file_header=header)


@pytest.fixture()
def sources():
    return {
        "stock": _source("stock", {"product_id": ["1", "2"], "price": ["10.5", "20"]}),
        "purchase": _source("purchase", {"order": ["o1"], "product_id": ["1"]}),
    }


def test_binding_by_entity_key_name(sources):
    assert bind_entity_source("stock", {}, sources).name == "stock"


def test_binding_by_explicit_source(sources):
    assert bind_entity_source("inventory", {"source": "stock"}, sources).name == "stock"


def test_binding_unresolvable_raises(sources):
    with pytest.raises(MappingError, match="no source"):
        bind_entity_source("inventory", {}, sources)


def test_binding_unknown_source_raises(sources):
    with pytest.raises(MappingError, match="unknown source"):
        bind_entity_source("x", {"source": "nope"}, sources)


def test_list_source_unions_columns_and_tags_source(sources):
    sd = bind_entity_source("log", {"source": ["stock", "purchase"]}, sources)
    assert sd.file_header == ["product_id", "price", "order"]
    assert len(sd.df) == 3
    assert list(sd.df[SOURCE_COLUMN]) == ["stock", "stock", "purchase"]
    # Missing columns are filled with empty strings.
    assert list(sd.df["order"]) == ["", "", "o1"]


def test_auto_map_infers_types_and_excludes_source_column(sources):
    cols = expand_entity_columns("stock", {}, sources["stock"])
    assert cols == {
        "product_id": {"db_type": "BIGINT"},
        "price": {"db_type": "NUMERIC"},
    }


def test_hybrid_manual_overrides_win(sources):
    ecfg = {"auto_map": True, "columns": {"product_id": {"is_key": True}}}
    cols = expand_entity_columns("stock", ecfg, sources["stock"])
    assert cols["product_id"] == {"is_key": True}
    assert cols["price"] == {"db_type": "NUMERIC"}


def test_csv_columns_restricts_auto_map(sources):
    ecfg = {"csv_columns": ["1"]}
    cols = expand_entity_columns("stock", ecfg, sources["stock"])
    assert list(cols) == ["product_id"]


def test_csv_columns_with_manual_only_raises(sources):
    ecfg = {"columns": {"product_id": {}}, "csv_columns": ["1"]}
    with pytest.raises(MappingError, match="csv_columns"):
        expand_entity_columns("stock", ecfg, sources["stock"])


def test_resolve_backend_entities_casts_and_strips_keys(sources):
    bcfg = {"entities": {"inventory": {"source": "stock", "auto_map": True,
                                       "columns": {"product_id": {"is_key": True}}}}}
    bound = resolve_backend_entities(bcfg, sources)
    be = bound["inventory"]
    assert be.name == "inventory"
    assert "source" not in be.cfg and "auto_map" not in be.cfg
    assert be.cfg["columns"]["product_id"] == {"is_key": True}
    assert list(be.df["product_id"]) == [1, 2]  # cast to int
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_mapping_resolver.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'polyglotimportcsv.mapping_resolver'`

- [ ] **Step 3: Create `src/polyglotimportcsv/mapping_resolver.py`**

```python
"""Bind entities to sources and expand effective column mappings (spec §2.3-§2.6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

from polyglotimportcsv.business_exception import MappingError
from polyglotimportcsv.casting import KIND_TO_DB_TYPE, cast_frame
from polyglotimportcsv.column_selector import select_columns
from polyglotimportcsv.csv_reader import infer_column_kinds
from polyglotimportcsv.sources import SOURCE_COLUMN, SourceData


@dataclass
class BoundEntity:
    """An entity bound to its source: expanded config + typed data frame."""

    name: str
    cfg: Dict[str, Any]       # entity cfg with expanded 'columns'
    df: pd.DataFrame          # cast source frame (data columns + _source)
    kinds: Dict[str, str]


def _union_source(
    entity_name: str, names: List[str], sources: Dict[str, SourceData]
) -> SourceData:
    parts: List[SourceData] = []
    for n in names:
        if n not in sources:
            raise MappingError(f"Entity '{entity_name}': unknown source '{n}'.")
        parts.append(sources[n])
    data_cols: List[str] = []
    for p in parts:
        for c in p.file_header:
            if c not in data_cols:
                data_cols.append(c)
    all_cols = data_cols + [SOURCE_COLUMN]
    frames = [p.df.reindex(columns=all_cols, fill_value="") for p in parts]
    df = pd.concat(frames, ignore_index=True)
    kinds = infer_column_kinds(df[data_cols])
    kinds[SOURCE_COLUMN] = "string"
    return SourceData(name="+".join(names), df=df, kinds=kinds, file_header=data_cols)


def bind_entity_source(
    entity_name: str, entity_cfg: Dict[str, Any], sources: Dict[str, SourceData]
) -> SourceData:
    """Resolve the entity's source: explicit name, list union, or key-name match."""
    ref = entity_cfg.get("source")
    if ref is None:
        if entity_name in sources:
            return sources[entity_name]
        raise MappingError(
            f"Entity '{entity_name}' declares no 'source' and no source is named after it."
        )
    if isinstance(ref, str):
        if ref not in sources:
            raise MappingError(f"Entity '{entity_name}': unknown source '{ref}'.")
        return sources[ref]
    return _union_source(entity_name, list(ref), sources)


def expand_entity_columns(
    entity_name: str, entity_cfg: Dict[str, Any], source: SourceData
) -> Dict[str, Any]:
    """Effective columns: manual-only, full auto-map, or hybrid (spec §2.4)."""
    manual = entity_cfg.get("columns") or {}
    auto = bool(entity_cfg.get("auto_map")) or not manual
    if not auto:
        if entity_cfg.get("csv_columns"):
            raise MappingError(
                f"Entity '{entity_name}': 'csv_columns' requires auto-mapping "
                "(omit 'columns' or set \"auto_map\": true)."
            )
        return manual
    selection = entity_cfg.get("csv_columns")
    if selection:
        base_cols = select_columns(
            selection, source.file_header, context=f"entity '{entity_name}'"
        )
    else:
        base_cols = list(source.file_header)
    expanded: Dict[str, Any] = {}
    for col in base_cols:
        kind = source.kinds.get(col, "string")
        expanded[col] = {"db_type": KIND_TO_DB_TYPE.get(kind, "TEXT")}
    expanded.update(manual)
    return expanded


def resolve_backend_entities(
    backend_cfg: Dict[str, Any],
    sources: Dict[str, SourceData],
    cast_cache: Optional[Dict[str, pd.DataFrame]] = None,
) -> Dict[str, BoundEntity]:
    """Bind every entity of one backend and cast its frame to native values."""
    cast_cache = cast_cache if cast_cache is not None else {}
    out: Dict[str, BoundEntity] = {}
    for ename, ecfg in (backend_cfg.get("entities") or {}).items():
        src = bind_entity_source(ename, ecfg, sources)
        cfg = dict(ecfg)
        cfg["columns"] = expand_entity_columns(ename, ecfg, src)
        cfg.pop("source", None)
        cfg.pop("csv_columns", None)
        cfg.pop("auto_map", None)
        if src.name not in cast_cache:
            cast_cache[src.name] = cast_frame(src.df, src.kinds)
        out[ename] = BoundEntity(
            name=ename, cfg=cfg, df=cast_cache[src.name], kinds=src.kinds
        )
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_mapping_resolver.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/mapping_resolver.py tests/test_mapping_resolver.py
git commit -m "feat: entity-source binding and effective mapping expansion"
```

---

### Task 6: JSON Schema v2 + config_parser

**Files:**
- Modify: `src/polyglotimportcsv/schemas/import_config.schema.json`
- Modify: `src/polyglotimportcsv/config_parser.py`
- Modify: `tests/test_config_parser.py`

**Interfaces:**
- Produces: schema v2 requiring `sources` and rejecting `version`; `merge_configs` carries `merged["sources"]` and no longer emits `merged["version"]`; `ConfigError` raised for schema violations (still a `BusinessException`).

- [ ] **Step 1: Update the tests first**

In `tests/test_config_parser.py`, apply ALL of the following (this makes the suite fail until schema and parser change):

Replace every `"version": 1,` line inside `data = {...}` / `import_cfg` / `sgbd_cfg` literals of the import-config tests by a `"sources": {"s": "s.csv"},` line. The SGBD-config tests keep their own shape (leave `test_sgbd_schema_rejects_entities_block` alone except removing `"version": 1,` if present — the sgbd schema is untouched by this plan, keep whatever it accepts today).

Add these two new tests at the end:

```python
def test_import_schema_rejects_version_field():
    data = {"sources": {"s": "s.csv"}}
    validate_import_config_schema(data)  # baseline OK
    with pytest.raises(BusinessException):
        validate_import_config_schema({"version": 1, "sources": {"s": "s.csv"}})


def test_import_schema_requires_sources():
    with pytest.raises(BusinessException):
        validate_import_config_schema({"redis": {"entities": {"x": {}}}})
```

And replace `test_merge_injects_connection_and_schema` and `test_load_config_accepts_ecommerce_fixture` with:

```python
def test_merge_injects_connection_and_schema_and_sources():
    import_cfg = {
        "sources": {"t": "t.csv"},
        "postgres": {"entities": {"t": {"columns": {"id": {"is_key": True}}}}},
    }
    sgbd_cfg = {"postgres": {"connection": {"host": "db"}, "schema": "shop"}}
    merged = merge_configs(import_cfg, sgbd_cfg)
    assert merged["sources"] == {"t": "t.csv"}
    assert "version" not in merged
    assert merged["postgres"]["connection"] == {"host": "db"}
    assert merged["postgres"]["schema"] == "shop"


def test_load_config_accepts_ecommerce_fixture():
    root = Path(__file__).resolve().parents[1]
    cfg = root / "data" / "ecommerce" / "import_config.json"
    data = load_config(cfg)
    assert "sources" in data and "version" not in data
    assert "postgres" in data
    assert data["postgres"]["connection"]["database"] == "ecommerce"
```

NOTE: `test_load_config_accepts_ecommerce_fixture` will only pass after Task 13 migrates the example config — mark it now with `@pytest.mark.xfail(reason="example migrates in Task 13", strict=False)` and REMOVE the marker in Task 13.

- [ ] **Step 2: Run to verify failures**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config_parser.py -q`
Expected: FAIL — schema still requires `version` and rejects `sources`.

- [ ] **Step 3: Rewrite the root of `import_config.schema.json`**

Replace the top-level `"required"`/`"properties"` block (keep `$schema`, `$id`, `title`, update `description`) with:

```json
  "description": "Declarative mapping from named CSV sources to entities and relationships of one or more SGBDs. Connection settings live in the separate SGBD configuration.",
  "type": "object",
  "required": ["sources"],
  "properties": {
    "sources": {
      "type": "object",
      "minProperties": 1,
      "description": "Named data sources: a CSV path per entity, or a combined CSV whose column 0 holds each row's origin.",
      "additionalProperties": {
        "oneOf": [
          { "type": "string", "minLength": 1 },
          {
            "type": "object",
            "required": ["file", "origin_column"],
            "properties": {
              "file": { "type": "string", "minLength": 1 },
              "origin_column": { "const": true }
            },
            "additionalProperties": false
          }
        ]
      }
    },
    "postgres": { "$ref": "#/$defs/postgresMapping" },
    "mongodb": { "$ref": "#/$defs/mongoMapping" },
    "cassandra": { "$ref": "#/$defs/cassandraMapping" },
    "redis": { "$ref": "#/$defs/redisMapping" },
    "neo4j": { "$ref": "#/$defs/neo4jMapping" }
  },
  "additionalProperties": false,
```

In `$defs.columnSpec`, change the integer branch of `csv_column` to 1-based:

```json
            { "type": "integer", "minimum": 1 }
```

and its description to `"CSV header name or 1-based data-column index when it differs from the JSON key."`.

In `$defs.entity`, remove `"required": ["columns"]` and add three properties alongside `columns`/`filters`/`cassandra_*`:

```json
        "source": {
          "description": "Source name, or list of source names (union with _source per row). Omit to bind by the entity key name.",
          "oneOf": [
            { "type": "string", "minLength": 1 },
            { "type": "array", "minItems": 1, "items": { "type": "string", "minLength": 1 } }
          ]
        },
        "csv_columns": {
          "type": "array",
          "minItems": 1,
          "description": "Auto-map restriction: column names, 1-based indices, or ranges like \"1-5\". Only valid with auto-mapping.",
          "items": {
            "oneOf": [
              { "type": "string", "minLength": 1 },
              { "type": "integer", "minimum": 1 }
            ]
          }
        },
        "auto_map": {
          "type": "boolean",
          "description": "With 'columns' present, auto-map the whole source and let the manual entries override per column."
        },
```

- [ ] **Step 4: Update `config_parser.py`**

1. Change the import to `from polyglotimportcsv.business_exception import BusinessException, ConfigError` and raise `ConfigError` (instead of bare `BusinessException`) in `_read_json`, `validate_sgbd_config`, `validate_import_config_schema`, and `merge_configs`.
2. In `merge_configs`, replace the line `merged: Dict[str, Any] = {"version": import_cfg.get("version", 1)}` with:

```python
    merged: Dict[str, Any] = {"sources": copy.deepcopy(import_cfg.get("sources") or {})}
```

3. Update the module docstring's `import_config.json` bullet to mention the `sources` block.

- [ ] **Step 5: Run tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config_parser.py -q`
Expected: PASS (with the one xfail for the fixture). The rest of the suite is still red in places that Task 8+ fixes — run only this file here.

- [ ] **Step 6: Commit**

```bash
git add src/polyglotimportcsv/schemas/import_config.schema.json src/polyglotimportcsv/config_parser.py tests/test_config_parser.py
git commit -m "feat: import config schema v2 (sources block, no version field)"
```

---

### Task 7: 1-based `csv_column` + validation rewrite

**Files:**
- Modify: `src/polyglotimportcsv/entity_utils.py:33-46` (`resolve_csv_column`)
- Modify: `src/polyglotimportcsv/validation.py` (full rewrite)
- Modify: `tests/test_entity_utils.py` (adjust any 0-based `csv_column` index expectations to 1-based — read the file; if it only uses names, no change)
- Test: `tests/test_validation.py` (create; the old `tests/test_validation_dry_run.py` is rewritten in Task 13)

**Interfaces:**
- Consumes: `BoundEntity` (Task 5), `MappingError` (Task 1).
- Produces: `validation.BACKENDS` (unchanged tuple) and `validation.validate_backend_entities(backend: str, backend_cfg: Dict[str, Any], bound: Dict[str, BoundEntity]) -> None`. The old `validate_import_config(config, df, kinds)` is DELETED.

- [ ] **Step 1: Make `resolve_csv_column` 1-based**

In `src/polyglotimportcsv/entity_utils.py`, replace the integer branch of `resolve_csv_column`:

```python
    if isinstance(csv, int):
        if csv < 1 or csv > len(csv_columns):
            raise ValueError(
                f"csv_column index {csv} out of range (valid: 1-{len(csv_columns)})."
            )
        return csv_columns[csv - 1]
```

Update the docstring to `"Resolve csv_column (name or 1-based index) to the actual CSV header."`

- [ ] **Step 2: Write the failing validation test**

Create `tests/test_validation.py`:

```python
"""validate_backend_entities: per-entity columns, filters, keys, relationships."""

import pandas as pd
import pytest

from polyglotimportcsv.business_exception import MappingError
from polyglotimportcsv.mapping_resolver import BoundEntity
from polyglotimportcsv.validation import validate_backend_entities


def _be(name, cfg, columns):
    df = pd.DataFrame({c: ["v"] for c in columns})
    kinds = {c: "string" for c in columns}
    return BoundEntity(name=name, cfg=cfg, df=df, kinds=kinds)


def test_unknown_column_raises():
    be = _be("t", {"columns": {"nope": {}}}, ["a", "_source"])
    with pytest.raises(MappingError, match="unknown column"):
        validate_backend_entities("redis", {}, {"t": be})


def test_source_pseudo_column_is_valid():
    be = _be("t", {"columns": {"_source": {"schema_column": "event_type"}}}, ["a", "_source"])
    validate_backend_entities("redis", {}, {"t": be})


def test_nested_columns_rejected_for_flat_backend():
    be = _be("t", {"columns": {"outer": {"inner": {}}}}, ["inner", "_source"])
    with pytest.raises(MappingError, match="nested"):
        validate_backend_entities("postgres", {}, {"t": be})


def test_filter_on_unknown_column_raises():
    be = _be("t", {"columns": {"a": {}}, "filters": [{"column": "x", "operator": "==", "value": 1}]},
             ["a", "_source"])
    with pytest.raises(MappingError, match="Filter column"):
        validate_backend_entities("redis", {}, {"t": be})


def test_cassandra_partition_must_exist():
    be = _be("t", {"columns": {"a": {}}, "cassandra_partition": ["missing"]}, ["a", "_source"])
    with pytest.raises(MappingError, match="partition"):
        validate_backend_entities("cassandra", {}, {"t": be})


def test_postgres_relationship_targets_checked():
    frm = _be("orders", {"columns": {"product_id": {}}}, ["product_id", "_source"])
    to = _be("products", {"columns": {"product_id": {"is_key": True}}}, ["product_id", "_source"])
    bcfg = {"relationships": {"r": {"from": "orders", "to": "products", "foreign_key": "product_id"}}}
    validate_backend_entities("postgres", bcfg, {"orders": frm, "products": to})
    bad = {"relationships": {"r": {"from": "orders", "to": "products", "foreign_key": "zzz"}}}
    with pytest.raises(MappingError, match="foreign_key"):
        validate_backend_entities("postgres", bad, {"orders": frm, "products": to})
```

- [ ] **Step 3: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_validation.py -q`
Expected: FAIL — `ImportError: cannot import name 'validate_backend_entities'`

- [ ] **Step 4: Rewrite `src/polyglotimportcsv/validation.py`**

Replace the whole file:

```python
"""Cross-validate resolved (bound) entities against their sources."""

from __future__ import annotations

from typing import Any, Dict, List, Set

from polyglotimportcsv.business_exception import MappingError
from polyglotimportcsv.entity_utils import (
    FLAT_BACKENDS,
    entity_has_nested_branches,
    iter_leaf_columns,
    resolve_csv_column,
    target_field_name,
)
from polyglotimportcsv.mapping_resolver import BoundEntity

BACKENDS = ("postgres", "mongodb", "cassandra", "redis", "neo4j")


def _validate_filters(
    ename: str, backend: str, filters: List[Dict[str, Any]], columns: Set[str]
) -> None:
    for flt in filters or []:
        c = flt.get("column")
        if not c:
            raise MappingError(f"Entity '{ename}' in '{backend}': filter missing 'column'.")
        if c not in columns:
            raise MappingError(
                f"Entity '{ename}' in '{backend}': Filter column not found in source: {c}"
            )
        op = flt.get("operator")
        if op not in ("==", "!=", ">", "<", ">=", "<=", "in", "not_in", "each"):
            raise MappingError(f"Unsupported filter operator: {op}")
        if op in ("in", "not_in") and not isinstance(flt.get("value"), list):
            raise MappingError(f"Filter '{op}' requires 'value' to be a list.")
        if op == "each":
            continue
        if op not in ("in", "not_in") and "value" not in flt:
            raise MappingError(f"Filter with operator {op} requires 'value'.")


def _entity_targets(cfg: Dict[str, Any]) -> Set[str]:
    return {target_field_name(fk, spec) for _, fk, spec in iter_leaf_columns(cfg)}


def validate_backend_entities(
    backend: str, backend_cfg: Dict[str, Any], bound: Dict[str, BoundEntity]
) -> None:
    """Validate every bound entity (and relationships) of one backend."""
    for ename, be in bound.items():
        cols = list(be.df.columns)
        colset = set(cols)
        if backend in FLAT_BACKENDS and entity_has_nested_branches(be.cfg):
            raise MappingError(
                f"Entity '{ename}' in '{backend}' uses nested columns; "
                f"only flat column mappings are allowed for this backend."
            )
        for _, field_key, spec in iter_leaf_columns(be.cfg):
            try:
                resolved = resolve_csv_column(field_key, spec, cols)
            except ValueError as e:
                raise MappingError(f"Entity '{ename}' in '{backend}': {e}") from e
            if resolved not in colset:
                raise MappingError(
                    f"Entity '{ename}' in '{backend}' references unknown column: {resolved}"
                )
        _validate_filters(ename, backend, be.cfg.get("filters") or [], colset)
        for pk in be.cfg.get("cassandra_partition") or []:
            if pk not in colset:
                raise MappingError(
                    f"Cassandra partition column '{pk}' not in source (entity {ename})."
                )
        for ck in be.cfg.get("cassandra_cluster") or []:
            if ck not in colset:
                raise MappingError(
                    f"Cassandra cluster column '{ck}' not in source (entity {ename})."
                )

    if backend == "postgres":
        for rname, rspec in (backend_cfg.get("relationships") or {}).items():
            fr, to = rspec.get("from"), rspec.get("to")
            if fr not in bound or to not in bound:
                raise MappingError(
                    f"Relationship '{rname}' references unknown entity (from={fr}, to={to})."
                )
            fk = rspec.get("foreign_key")
            refk = rspec.get("references_key") or fk
            if fk not in _entity_targets(bound[fr].cfg):
                raise MappingError(
                    f"Relationship '{rname}': foreign_key '{fk}' not mapped in entity '{fr}'."
                )
            if refk not in _entity_targets(bound[to].cfg):
                raise MappingError(
                    f"Relationship '{rname}': references_key '{refk}' not mapped in entity '{to}'."
                )

    if backend == "neo4j":
        for rname, rspec in (backend_cfg.get("relationships") or {}).items():
            if rspec.get("from") not in bound or rspec.get("to") not in bound:
                raise MappingError(
                    f"Neo4j relationship '{rname}' references unknown node entity."
                )
            from_be = bound[rspec["from"]]
            cols = list(from_be.df.columns)
            colset = set(cols)
            for field_key, spec in (rspec.get("columns") or {}).items():
                try:
                    resolved = resolve_csv_column(field_key, spec, cols)
                except ValueError as e:
                    raise MappingError(f"Neo4j relationship '{rname}': {e}") from e
                if resolved not in colset:
                    raise MappingError(
                        f"Neo4j relationship '{rname}' property column '{resolved}' not in source."
                    )
```

- [ ] **Step 5: Adjust `tests/test_entity_utils.py`**

Read the file. If any test passes an integer `csv_column` and asserts a 0-based resolution, shift the expected index by one (e.g. `csv_column: 0` resolving to the first header becomes `csv_column: 1`). If only names are used, no change.

- [ ] **Step 6: Run tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_validation.py tests/test_entity_utils.py -q`
Expected: PASS. (`tests/test_validation_dry_run.py` now fails to import `validate_import_config` — delete its `validate_import_config` import and the three tests `test_validate_config_and_csv`, `test_invalid_column_raises`, `test_postgres_rejects_nested_columns`, `test_csv_column_index_out_of_range`, `test_csv_column_by_name_resolves` for now; Task 13 rewrites the file completely.)

- [ ] **Step 7: Commit**

```bash
git add src/polyglotimportcsv/entity_utils.py src/polyglotimportcsv/validation.py tests/test_validation.py tests/test_entity_utils.py tests/test_validation_dry_run.py
git commit -m "feat: per-entity validation over bound sources; 1-based csv_column"
```

---

### Task 8: Importer contract + runner rewrite

**Files:**
- Modify: `src/polyglotimportcsv/importers/base.py`
- Modify: `src/polyglotimportcsv/runner.py`
- Modify: `tests/test_runner_registry.py`

**Interfaces:**
- Produces: `BackendImporterFn.__call__(backend_cfg: Dict[str, Any], entities: Dict[str, BoundEntity], *, dry_run: bool, create_schema: bool) -> List[str]`; `runner.run_import(config_path, *, sgbd_config_path=None, dry_run=False, create_schema=True, only=None, importers=None, source_overrides=None) -> List[str]` — NOTE: no `csv_path` parameter anymore.

- [ ] **Step 1: Update the registry test first**

Replace `tests/test_runner_registry.py` content:

```python
"""Runner uses an injectable importer registry (mock-friendly)."""

from pathlib import Path

import pytest

from polyglotimportcsv.business_exception import BusinessException
from polyglotimportcsv.runner import run_import

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "data" / "ecommerce" / "import_config.json"


def test_run_import_with_stub_registry():
    calls: list[str] = []

    def stub_postgres(cfg, entities, *, dry_run, create_schema):
        calls.append("postgres")
        assert isinstance(entities, dict) and entities, "expected bound entities"
        return ["[postgres] stub"]

    registry = {"postgres": stub_postgres}
    lines = run_import(
        CFG, dry_run=True, create_schema=False, only=["postgres"], importers=registry
    )
    assert calls == ["postgres"]
    assert "[postgres] stub" in lines


def test_run_import_rejects_invalid_config_even_with_stub():
    def never_called(*a, **k):
        raise AssertionError("importer should not run if validation fails")

    bad_cfg = ROOT / "data" / "db.json"
    if not bad_cfg.is_file():
        pytest.skip("data/db.json missing")
    with pytest.raises(BusinessException):
        run_import(bad_cfg, dry_run=True, importers={"postgres": never_called})
```

NOTE: this passes only after Task 13 migrates `import_config.json`; until then mark `test_run_import_with_stub_registry` with `@pytest.mark.xfail(reason="example migrates in Task 13", strict=False)` and remove the marker in Task 13.

- [ ] **Step 2: Update `src/polyglotimportcsv/importers/base.py`**

```python
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
```

- [ ] **Step 3: Rewrite `src/polyglotimportcsv/runner.py`**

```python
"""Orchestrate source loading, entity resolution, validation, and per-backend import."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

import pandas as pd

from polyglotimportcsv.config_parser import load_config
from polyglotimportcsv.console import (
    banner,
    color_backend_line,
    note,
    section,
    step,
    success,
)
from polyglotimportcsv.importers import default_importer_registry
from polyglotimportcsv.importers.base import ImporterRegistry
from polyglotimportcsv.mapping_resolver import resolve_backend_entities
from polyglotimportcsv.sources import load_sources
from polyglotimportcsv.validation import BACKENDS, validate_backend_entities


def run_import(
    config_path: str | Path,
    *,
    sgbd_config_path: Optional[str | Path] = None,
    dry_run: bool = False,
    create_schema: bool = True,
    only: Optional[Iterable[str]] = None,
    importers: Optional[ImporterRegistry] = None,
    source_overrides: Optional[Dict[str, str]] = None,
) -> List[str]:
    """
    Load config and sources, bind entities, validate, then run configured backends.

    Data comes from the config's ``sources`` block (one CSV per entity, or a
    combined CSV with the origin in column 0). ``source_overrides`` remaps a
    source name to another CSV path without editing the config (CLI --source).
    """
    config_path = Path(config_path)

    mode = "dry-run" if dry_run else "import"
    banner("Polyglot Import CSV", subtitle=f"mode: {mode}")

    step("Load config", str(config_path))
    config = load_config(config_path, sgbd_config_path)
    backends_in_cfg = [b for b in BACKENDS if b in config]
    note(f"{len(backends_in_cfg)} backend(s) configured: {', '.join(backends_in_cfg)}")

    step("Load sources")
    sources = load_sources(
        config.get("sources") or {}, config_path.parent, overrides=source_overrides
    )
    for name in sorted(sources):
        sd = sources[name]
        note(f"source {name}: {len(sd.df)} row(s), {len(sd.file_header)} data column(s)")

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

    cast_cache: Dict[str, pd.DataFrame] = {}
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
        bound = resolve_backend_entities(bcfg, sources, cast_cache)
        validate_backend_entities(backend, bcfg, bound)
        backend_lines = fn(bcfg, bound, dry_run=dry_run, create_schema=create_schema)
        log_lines.extend(backend_lines)
        for line in backend_lines:
            print(f"  {color_backend_line(line)}")

    success(f"Finished {mode} — {len(log_lines)} log line(s) from importer(s)")
    return log_lines
```

- [ ] **Step 4: Run tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_runner_registry.py -q`
Expected: xfail + pass/skip (fixture migrates in Task 13). No import errors.

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/importers/base.py src/polyglotimportcsv/runner.py tests/test_runner_registry.py
git commit -m "feat: sources-driven runner and BoundEntity importer contract"
```

---

### Task 9: PostgreSQL importer on BoundEntity

**Files:**
- Modify: `src/polyglotimportcsv/importers/postgres_importer.py`
- Test: `tests/test_postgres_importer_dry_run.py` (create)

**Interfaces:**
- Consumes: `BoundEntity` (Task 5). `flatten_entity_dataframe`, `apply_filters`, `expand_each`, `schema_generator` are all unchanged.
- Produces: `run_postgres_import(backend_cfg, entities: Dict[str, BoundEntity], *, dry_run, create_schema) -> List[str]` — connection failures raise `ImportExecutionError`.

- [ ] **Step 1: Write the failing dry-run test**

Create `tests/test_postgres_importer_dry_run.py`:

```python
"""Postgres importer consumes per-entity bound frames (dry-run, no DB)."""

import pandas as pd

from polyglotimportcsv.importers.postgres_importer import run_postgres_import
from polyglotimportcsv.mapping_resolver import BoundEntity


def test_dry_run_counts_per_entity():
    df = pd.DataFrame(
        {"product_id": [1, 2, 2], "price": [10.0, 20.0, 20.0], "_source": ["stock"] * 3}
    )
    kinds = {"product_id": "integer", "price": "float", "_source": "string"}
    be = BoundEntity(
        name="inventory",
        cfg={"columns": {"product_id": {"is_key": True}, "price": {}}},
        df=df,
        kinds=kinds,
    )
    lines = run_postgres_import({}, {"inventory": be}, dry_run=True, create_schema=False)
    assert any("inventory: 2 row(s) after dedupe" in L for L in lines)
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_postgres_importer_dry_run.py -q`
Expected: FAIL — current signature takes `(backend_cfg, df, column_kinds, ...)`.

- [ ] **Step 3: Rewrite `run_postgres_import`**

Keep imports, `_DEFAULT_INSERT_ORDER`, and `_connect`; add `from polyglotimportcsv.mapping_resolver import BoundEntity` and change `BusinessException` to `ImportExecutionError` in the import from `business_exception`. Replace the function:

```python
def run_postgres_import(
    backend_cfg: Dict[str, Any],
    entities: Dict[str, "BoundEntity"],
    *,
    dry_run: bool,
    create_schema: bool,
) -> List[str]:
    """Execute Postgres import; return log lines."""
    lines: List[str] = []
    conn_cfg = backend_cfg.get("connection") or {}
    schema = backend_cfg.get("schema") or "public"
    relationships = backend_cfg.get("relationships") or {}
    entity_cfgs = {name: be.cfg for name, be in entities.items()}

    if dry_run:
        lines.append("[postgres] dry-run: would connect and import entities.")
        for ename, be in entities.items():
            non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
            dff = apply_filters(be.df, non_each, be.kinds)
            for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
                mat = flatten_entity_dataframe(part_df, be.cfg)
                lines.append(f"  entity {part_name}: {len(mat)} row(s) after dedupe")
        return lines

    create_stmts = build_postgres_create_tables(schema, entity_cfgs, relationships)
    fk_stmts = build_postgres_foreign_keys(schema, entity_cfgs, relationships)

    try:
        cx = _connect(conn_cfg)
    except Exception as e:
        raise ImportExecutionError(f"PostgreSQL connection failed: {e}") from e

    cx.autocommit = True
    with cx.cursor() as cur:
        if create_schema:
            for stmt in create_stmts:
                cur.execute(stmt)
            for stmt in fk_stmts:
                for sub in stmt.split(";"):
                    sub = sub.strip()
                    if sub:
                        cur.execute(sub + ";")
        ordered_names = [n for n in _DEFAULT_INSERT_ORDER if n in entities] + [
            n for n in sorted(entities.keys()) if n not in _DEFAULT_INSERT_ORDER
        ]
        for ename in ordered_names:
            be = entities[ename]
            non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
            dff = apply_filters(be.df, non_each, be.kinds)
            for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
                mat = flatten_entity_dataframe(part_df, be.cfg)
                if mat.empty:
                    continue
                cols = list(mat.columns)
                fq = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(part_name))
                col_sql = sql.SQL(", ").join(map(sql.Identifier, cols))
                pks = [
                    target_field_name(fk, spec)
                    for fk, _, spec in flat_leaf_columns(be.cfg)
                    if spec.get("is_key")
                ]
                base = sql.SQL("INSERT INTO {} ({}) VALUES %s").format(fq, col_sql)
                if pks:
                    full = base + sql.SQL(" ON CONFLICT ({}) DO NOTHING").format(
                        sql.SQL(", ").join(map(sql.Identifier, pks))
                    )
                else:
                    full = base
                tuples = [tuple(row) for row in mat.itertuples(index=False, name=None)]
                execute_values(cur, full.as_string(cx), tuples, page_size=500)
                lines.append(f"[postgres] inserted {len(tuples)} row(s) into {schema}.{part_name}")
    cx.close()
    return lines
```

Also update `flatten_entity_dataframe` in `src/polyglotimportcsv/materialize.py` so key emptiness handles cast values — replace the two key-cleanup lines with:

```python
        for kc in key_outs:
            sub[kc] = sub[kc].replace("", pd.NA)
        sub = sub.dropna(subset=key_outs, how="any")
```

(unchanged code shown for anchoring; None values from cast frames are already treated as missing by `dropna` — verify no edit is actually needed and skip if identical).

- [ ] **Step 4: Run tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_postgres_importer_dry_run.py tests/test_materialize.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/importers/postgres_importer.py src/polyglotimportcsv/materialize.py tests/test_postgres_importer_dry_run.py
git commit -m "feat: postgres importer consumes BoundEntity frames"
```

---

### Task 10: MongoDB + Redis importers on BoundEntity

**Files:**
- Modify: `src/polyglotimportcsv/importers/mongodb_importer.py`
- Modify: `src/polyglotimportcsv/importers/redis_importer.py`
- Test: `tests/test_doc_kv_importers_dry_run.py` (create)

**Interfaces:**
- Same pattern as Task 9: `run_mongodb_import(backend_cfg, entities, *, dry_run, create_schema)`, `run_redis_import(...)`; connection failures raise `ImportExecutionError`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_doc_kv_importers_dry_run.py`:

```python
"""Mongo/Redis importers consume per-entity bound frames (dry-run, no DB)."""

import pandas as pd

from polyglotimportcsv.importers.mongodb_importer import run_mongodb_import
from polyglotimportcsv.importers.redis_importer import run_redis_import
from polyglotimportcsv.mapping_resolver import BoundEntity


def _be(name, cfg, data):
    df = pd.DataFrame(data)
    kinds = {c: "string" for c in df.columns}
    return BoundEntity(name=name, cfg=cfg, df=df, kinds=kinds)


def test_mongodb_dry_run_counts():
    be = _be("catalog", {"columns": {"a": {}}}, {"a": ["1", "2"], "_source": ["s", "s"]})
    lines = run_mongodb_import({}, {"catalog": be}, dry_run=True, create_schema=False)
    assert any("collection catalog: 2 document(s)" in L for L in lines)


def test_redis_dry_run_counts():
    be = _be(
        "cart",
        {"columns": {"k": {"is_key": True}, "v": {}}},
        {"k": ["a", "b"], "v": ["1", "2"], "_source": ["s", "s"]},
    )
    lines = run_redis_import({}, {"cart": be}, dry_run=True, create_schema=False)
    assert any("entity cart: 2 row(s)" in L for L in lines)
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_doc_kv_importers_dry_run.py -q`
Expected: FAIL (old signatures).

- [ ] **Step 3: Rewrite both importer functions**

`mongodb_importer.py` — change the `business_exception` import to `ImportExecutionError`, add `from polyglotimportcsv.mapping_resolver import BoundEntity`, replace the function:

```python
def run_mongodb_import(
    backend_cfg: Dict[str, Any],
    entities: Dict[str, "BoundEntity"],
    *,
    dry_run: bool,
    create_schema: bool,
) -> List[str]:
    lines: List[str] = []
    conn = backend_cfg.get("connection") or {}
    _ = create_schema

    if dry_run:
        lines.append("[mongodb] dry-run: would insert documents.")
        for ename, be in entities.items():
            non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
            dff = apply_filters(be.df, non_each, be.kinds)
            for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
                lines.append(f"  collection {part_name}: {len(part_df)} document(s)")
        return lines

    uri = conn.get("uri", "mongodb://127.0.0.1:27017")
    database = conn.get("database", "test")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
    except Exception as e:
        raise ImportExecutionError(f"MongoDB connection failed: {e}") from e

    db = client[database]
    for ename, be in entities.items():
        non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
        dff = apply_filters(be.df, non_each, be.kinds)
        for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
            docs = [mongo_document_from_row(row, be.cfg) for _, row in part_df.iterrows()]
            if docs:
                db[part_name].insert_many(docs)
            lines.append(f"[mongodb] inserted {len(docs)} document(s) into {part_name}")
    client.close()
    return lines
```

`redis_importer.py` — same import changes, replace the function:

```python
def run_redis_import(
    backend_cfg: Dict[str, Any],
    entities: Dict[str, "BoundEntity"],
    *,
    dry_run: bool,
    create_schema: bool,
) -> List[str]:
    lines: List[str] = []
    conn = backend_cfg.get("connection") or {}
    _ = create_schema  # Redis has no DDL

    if dry_run:
        lines.append("[redis] dry-run: would SET keys for entities.")
        for ename, be in entities.items():
            non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
            dff = apply_filters(be.df, non_each, be.kinds)
            for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
                lines.append(f"  entity {part_name}: {len(part_df)} row(s)")
        return lines

    r = redis.Redis(
        host=conn.get("host", "127.0.0.1"),
        port=int(conn.get("port", 6379)),
        db=int(conn.get("db", 0)),
        password=conn.get("password") or None,
        decode_responses=True,
    )
    try:
        r.ping()
    except Exception as e:
        raise ImportExecutionError(f"Redis connection failed: {e}") from e

    for ename, be in entities.items():
        non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
        dff = apply_filters(be.df, non_each, be.kinds)
        for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
            count = 0
            for _, row in part_df.iterrows():
                try:
                    k, v = redis_payload_from_row(row, be.cfg)
                except ValueError:
                    continue
                r.set(k, v)
                count += 1
            lines.append(f"[redis] SET {count} key(s) for {part_name}")
    return lines
```

Also in `materialize.py:redis_payload_from_row`, `pd.isna(key_val)` receives cast values — `None` is na, ints are fine; no change needed (verify).

- [ ] **Step 4: Run tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_doc_kv_importers_dry_run.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/importers/mongodb_importer.py src/polyglotimportcsv/importers/redis_importer.py tests/test_doc_kv_importers_dry_run.py
git commit -m "feat: mongodb and redis importers consume BoundEntity frames"
```

---

### Task 11: Cassandra + Neo4j importers on BoundEntity

**Files:**
- Modify: `src/polyglotimportcsv/importers/cassandra_importer.py`
- Modify: `src/polyglotimportcsv/importers/neo4j_importer.py`
- Test: `tests/test_graph_wide_importers_dry_run.py` (create)

**Interfaces:**
- `run_cassandra_import(backend_cfg, entities, *, dry_run, create_schema)`; `run_neo4j_import(...)`. Neo4j relationships read rows from the FROM entity's `BoundEntity.df`. Driver/connection failures raise `ImportExecutionError`. `_cassandra_type_for` gains `BOOLEAN -> boolean`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_graph_wide_importers_dry_run.py`:

```python
"""Cassandra/Neo4j importers consume per-entity bound frames (dry-run, no DB)."""

import pandas as pd

from polyglotimportcsv.importers.cassandra_importer import run_cassandra_import
from polyglotimportcsv.importers.neo4j_importer import run_neo4j_import
from polyglotimportcsv.mapping_resolver import BoundEntity


def _be(name, cfg, data):
    df = pd.DataFrame(data)
    kinds = {c: "string" for c in df.columns}
    return BoundEntity(name=name, cfg=cfg, df=df, kinds=kinds)


def test_cassandra_dry_run_counts():
    be = _be(
        "log",
        {
            "columns": {"user_id": {}, "_source": {"schema_column": "event_type"}},
            "cassandra_partition": ["user_id"],
        },
        {"user_id": ["u1", "u2", "u3"], "_source": ["a", "b", "a"]},
    )
    lines = run_cassandra_import({}, {"log": be}, dry_run=True, create_schema=False)
    assert any("table log: 3 row(s)" in L for L in lines)


def test_neo4j_dry_run_counts_nodes_and_relationships():
    user = _be(
        "User",
        {"columns": {"user_id": {"is_key": True}}},
        {"user_id": ["u1", "u2"], "product_id": ["p1", "p2"], "_source": ["purchase"] * 2},
    )
    prod = _be(
        "Product",
        {"columns": {"product_id": {"is_key": True}}},
        {"product_id": ["p1"], "_source": ["stock"]},
    )
    bcfg = {
        "relationships": {
            "PURCHASED": {"from": "User", "to": "Product", "type": "PURCHASED", "columns": {}}
        }
    }
    lines = run_neo4j_import(bcfg, {"User": user, "Product": prod}, dry_run=True, create_schema=False)
    assert any("label User: 2 row(s)" in L for L in lines)
    assert any("relationship type PURCHASED" in L for L in lines)
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_graph_wide_importers_dry_run.py -q`
Expected: FAIL (old signatures).

- [ ] **Step 3: Rewrite `run_cassandra_import`**

Change the `business_exception` import to `ImportExecutionError`; add `from polyglotimportcsv.mapping_resolver import BoundEntity`. In `_cassandra_type_for`, add before the final `return "text"`:

```python
    if t in ("BOOLEAN", "BOOL"):
        return "boolean"
```

Replace the function body pattern — signature and every `entities.items()` loop swap `df`→`be.df`, `column_kinds`→`be.kinds`, `ecfg`→`be.cfg`; `csv_columns = list(df.columns)` becomes `csv_columns = list(be.df.columns)`. Full replacement of the loops:

```python
def run_cassandra_import(
    backend_cfg: Dict[str, Any],
    entities: Dict[str, "BoundEntity"],
    *,
    dry_run: bool,
    create_schema: bool,
) -> List[str]:
    lines: List[str] = []
    conn = backend_cfg.get("connection") or {}
    hosts = conn.get("hosts") or ["127.0.0.1"]
    port = int(conn.get("port", 9042))
    keyspace = conn.get("keyspace", "ecommerce")

    if dry_run:
        lines.append("[cassandra] dry-run: would create tables and insert rows.")
        for ename, be in entities.items():
            non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
            dff = apply_filters(be.df, non_each, be.kinds)
            for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
                lines.append(f"  table {part_name}: {len(part_df)} row(s)")
        return lines
```

then keep the driver-loading block unchanged (only the two `raise BusinessException(` become `raise ImportExecutionError(`), and the per-entity loop becomes:

```python
    for ename, be in entities.items():
        csv_columns = list(be.df.columns)
        pmap = _source_to_db_map(be.cfg, csv_columns)
        part_src = be.cfg.get("cassandra_partition") or []
        clust_src = be.cfg.get("cassandra_cluster") or []
        part_db = [pmap[c] for c in part_src]
        clust_db = [pmap[c] for c in clust_src]
        all_src = [
            resolve_csv_column(fk, spec, csv_columns)
            for fk, _, spec in flat_leaf_columns(be.cfg)
        ]
        other_src = [s for s in all_src if s not in list(part_src) + list(clust_src)]
        ordered_src = list(part_src) + list(clust_src) + other_src
        ordered_db: List[str] = [pmap[s] for s in ordered_src]
        spec_by_src = {
            resolve_csv_column(fk, spec, csv_columns): spec
            for fk, _, spec in flat_leaf_columns(be.cfg)
        }
        pk_clause = _primary_key_clause(part_db, clust_db)

        non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
        dff = apply_filters(be.df, non_each, be.kinds)
        for table, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
            if create_schema:
                col_defs = []
                for src in ordered_src:
                    spec = spec_by_src[src]
                    col_defs.append(f'"{pmap[src]}" {_cassandra_type_for(spec)}')
                ddl = f'CREATE TABLE IF NOT EXISTS "{table}" (' + ", ".join(col_defs) + f", {pk_clause});"
                session.execute(ddl)

            cols_cql = ", ".join(f'"{c}"' for c in ordered_db)
            placeholders = ", ".join(["?"] * len(ordered_db))
            cql = f'INSERT INTO "{table}" ({cols_cql}) VALUES ({placeholders})'
            prep = session.prepare(cql)
            count = 0
            for _, row in part_df.iterrows():
                values = []
                for src in ordered_src:
                    val = row.get(src)
                    values.append(None if pd.isna(val) else val)
                session.execute(prep, values)
                count += 1
            lines.append(f"[cassandra] inserted {count} row(s) into {keyspace}.{table}")
```

- [ ] **Step 4: Rewrite `run_neo4j_import`**

Same import swaps. Signature `(backend_cfg, entities, *, dry_run, create_schema)`. In the dry-run block and node loop, swap to `be.df`/`be.kinds`/`be.cfg` exactly as in Step 3. In the relationships loop, the source frame comes from the FROM entity:

```python
        for rname, rspec in (relationships or {}).items():
            from_label = _sanitize_label(rspec["from"])
            to_label = _sanitize_label(rspec["to"])
            rel_type = _sanitize_label(rspec.get("type") or rname)
            from_be = entities[rspec["from"]]
            to_be = entities[rspec["to"]]
            fk_from = [(fk, sp) for fk, _, sp in flat_leaf_columns(from_be.cfg) if sp.get("is_key")][0]
            fk_to = [(fk, sp) for fk, _, sp in flat_leaf_columns(to_be.cfg) if sp.get("is_key")][0]
            from_key = target_field_name(fk_from[0], fk_from[1])
            to_key = target_field_name(fk_to[0], fk_to[1])
            from_src = resolve_csv_column(fk_from[0], fk_from[1], list(from_be.df.columns))
            to_src = resolve_csv_column(fk_to[0], fk_to[1], list(from_be.df.columns))
            rel_cols = rspec.get("columns") or {}
            merge_key_cols = [
                (fk, target_field_name(fk, spec))
                for fk, spec in rel_cols.items()
                if spec.get("is_key")
            ]
            f1 = [x for x in (from_be.cfg.get("filters") or []) if x.get("operator") != "each"]
            dff = apply_filters(from_be.df, f1, from_be.kinds)
```

(the inner per-row MERGE loop is unchanged from the current file). Note `to_src` resolves against the FROM frame — the relationship row carries both endpoint ids, as in v1.

Also update `entities = backend_cfg.get("entities") or {}` occurrences: delete them; `entities` is now the parameter, and `relationships = backend_cfg.get("relationships") or {}` stays.

- [ ] **Step 5: Run tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_graph_wide_importers_dry_run.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/polyglotimportcsv/importers/cassandra_importer.py src/polyglotimportcsv/importers/neo4j_importer.py tests/test_graph_wide_importers_dry_run.py
git commit -m "feat: cassandra and neo4j importers consume BoundEntity frames"
```

---

### Task 12: CLI v2 (`--source` overrides, no CSV argument)

**Files:**
- Modify: `src/polyglotimportcsv/cli.py`
- Test: `tests/test_cli.py` (create)

**Interfaces:**
- Produces: CLI `polyglotimportcsv --config CFG [--sgbd-config X] [--dry-run] [--create-schema/--no-create-schema] [--only ...] [--source NAME=PATH ...]`. `--source` is repeatable; malformed values (no `=`) exit with code 2 (click usage error). `__main__.py` needs no change.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`:

```python
"""CLI v2: config-driven sources, repeatable --source overrides."""

from click.testing import CliRunner

from polyglotimportcsv.cli import main


def test_cli_requires_config_and_takes_no_csv_argument(tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, ["some.csv"])
    assert result.exit_code == 2  # unexpected extra argument


def test_cli_source_override_is_parsed(tmp_path, monkeypatch):
    captured = {}

    def fake_run_import(config_path, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr("polyglotimportcsv.cli.run_import", fake_run_import)
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--config", str(cfg), "--dry-run", "--source", "stock=a.csv", "--source", "purchase=b.csv"],
    )
    assert result.exit_code == 0, result.output
    assert captured["source_overrides"] == {"stock": "a.csv", "purchase": "b.csv"}


def test_cli_rejects_malformed_source(tmp_path):
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(cfg), "--source", "nopath"])
    assert result.exit_code == 2
    assert "NAME=PATH" in result.output
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_cli.py -q`
Expected: FAIL — current CLI requires a CSV_PATH argument.

- [ ] **Step 3: Rewrite `src/polyglotimportcsv/cli.py`**

```python
"""Command-line interface for PolyglotImportCSV."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Dict, Tuple

import click

from polyglotimportcsv.business_exception import BusinessException
from polyglotimportcsv.console import error, init_session_log, setup_logging
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
def main(
    config_path: Path,
    sgbd_config_path: Path,
    dry_run: bool,
    create_schema: bool,
    only: str,
    source_pairs: Tuple[str, ...],
) -> None:
    """Import CSV sources into multiple databases according to --config."""
    setup_logging()
    log_path = init_session_log(prefix="polyglotimportcsv")
    if log_path is not None:
        from polyglotimportcsv.console import kv

        kv("Log file", str(log_path))
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
        )
    except BusinessException as e:
        error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
```

NOTE for the second test: `run_import` on an empty `{}` config raises `ConfigError` via schema (no `sources`) — the monkeypatch replaces it, so exit code is 0. Keep the monkeypatch import path exactly `polyglotimportcsv.cli.run_import`.

- [ ] **Step 4: Run tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_cli.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/cli.py tests/test_cli.py
git commit -m "feat: CLI v2 with config-driven sources and --source overrides"
```

---

### Task 13: Migrate the e-commerce example (configs, CSVs, scripts, smoke tests)

**Files:**
- Modify: `data/ecommerce/ecommerce_stock.csv`, `data/ecommerce/ecommerce_purchase.csv`, `data/ecommerce/ecommerce_select_product.csv`, `data/ecommerce/ecommerce_add_to_cart.csv` (regenerate WITHOUT the `action` column)
- Modify: `data/ecommerce/import_config.json` (v2, multi-CSV)
- Create: `data/ecommerce/import_config_combined.json` (v2, combined mode)
- Modify: `data/ecommerce/import_config_duplicate_csv_column_example.json`
- Modify: `run_example.sh`
- Modify: `tests/test_validation_dry_run.py` (rewrite), `tests/test_config_parser.py` + `tests/test_runner_registry.py` (remove xfail markers)
- Create: `tests/test_mode_equivalence.py`
- Verify: `scripts/inspect_persisted_data.py`

- [ ] **Step 1: Regenerate the four per-entity CSVs without the `action` column**

Run this from the repo root (Git Bash):

```bash
./.venv/Scripts/python.exe - <<'PY'
import pandas as pd

df = pd.read_csv("data/ecommerce/ecommerce_join.csv", dtype=str,
                 keep_default_na=False, encoding="utf-8-sig")
for action, group in df.groupby("action"):
    sub = group.drop(columns=["action"])
    sub = sub.loc[:, [c for c in sub.columns if (sub[c] != "").any()]]
    out = f"data/ecommerce/ecommerce_{action}.csv"
    sub.to_csv(out, index=False, encoding="utf-8", lineterminator="\n")
    print(out, len(sub), "rows,", len(sub.columns), "cols")
PY
```

Expected output: 4 files, 8 rows each; stock=20 cols, purchase=33, select_product=6, add_to_cart=7.

- [ ] **Step 2: Rewrite `data/ecommerce/import_config.json` (v2 multi-CSV)**

```json
{
  "sources": {
    "stock": "ecommerce_stock.csv",
    "purchase": "ecommerce_purchase.csv",
    "select_product": "ecommerce_select_product.csv",
    "add_to_cart": "ecommerce_add_to_cart.csv"
  },

  "postgres": {
    "entities": {
      "categories": {
        "source": "stock",
        "columns": {
          "category_id": { "is_key": true, "db_type": "BIGINT" },
          "category_name": { "db_type": "TEXT" }
        }
      },
      "products": {
        "source": "stock",
        "columns": {
          "product_id": { "is_key": true, "db_type": "BIGINT" },
          "product_name": { "db_type": "TEXT" },
          "product_variant": { "db_type": "TEXT" },
          "product_brand": { "db_type": "TEXT" },
          "category_id": { "db_type": "BIGINT" },
          "price": { "db_type": "NUMERIC(14,2)" }
        }
      },
      "inventory": {
        "source": "stock",
        "columns": {
          "product_id": { "is_key": true, "db_type": "BIGINT" },
          "quantity_available": { "db_type": "BIGINT" },
          "last_restock_date": { "db_type": "TIMESTAMPTZ" },
          "price": { "db_type": "NUMERIC(14,2)" }
        }
      },
      "orders": {
        "source": "purchase",
        "columns": {
          "order_number": { "is_key": true, "db_type": "TEXT" },
          "user_id": { "db_type": "TEXT" },
          "order_date": { "db_type": "TIMESTAMPTZ" },
          "order_status": { "db_type": "TEXT" },
          "payment_method": { "db_type": "TEXT" },
          "quantity": { "db_type": "BIGINT" },
          "product_id": { "db_type": "BIGINT" },
          "price": { "db_type": "NUMERIC(14,2)" },
          "comment": { "db_type": "TEXT" },
          "rating": { "db_type": "BIGINT" }
        }
      }
    },
    "relationships": {
      "product_category": {
        "from": "products",
        "to": "categories",
        "foreign_key": "category_id",
        "references_key": "category_id"
      },
      "order_product": {
        "from": "orders",
        "to": "products",
        "foreign_key": "product_id",
        "references_key": "product_id"
      }
    }
  },

  "mongodb": {
    "entities": {
      "product_catalog": {
        "source": "stock",
        "columns": {
          "product_id": {},
          "product_name": {},
          "product_variant": {},
          "product_brand": {},
          "product_description": {},
          "product_image": {},
          "price": {},
          "category": {
            "category_id": {},
            "category_name": {}
          },
          "stock": {
            "quantity_available": {},
            "last_restock_date": {}
          }
        }
      }
    }
  },

  "cassandra": {
    "entities": {
      "user_activity_log": {
        "source": ["stock", "purchase", "select_product", "add_to_cart"],
        "columns": {
          "user_id": {},
          "timestamp": { "schema_column": "event_time" },
          "_source": { "schema_column": "event_type" },
          "product_id": {},
          "order_number": {},
          "selected_product_id": {},
          "shopping_cart_id": {}
        },
        "cassandra_partition": ["user_id"],
        "cassandra_cluster": ["timestamp"]
      }
    }
  },

  "redis": {
    "entities": {
      "shopping_cart": {
        "source": "add_to_cart",
        "auto_map": true,
        "columns": {
          "shopping_cart_id": { "is_key": true }
        }
      },
      "user_session": {
        "source": "select_product",
        "columns": {
          "user_id": { "is_key": true },
          "user_name": {},
          "user_email": {},
          "timestamp": { "schema_column": "last_seen" }
        }
      }
    }
  },

  "neo4j": {
    "entities": {
      "User": {
        "source": "purchase",
        "columns": {
          "user_id": { "is_key": true },
          "user_name": {},
          "user_email": {}
        }
      },
      "Product": {
        "source": "stock",
        "columns": {
          "product_id": { "is_key": true },
          "product_name": {},
          "product_brand": {}
        }
      }
    },
    "relationships": {
      "PURCHASED": {
        "from": "User",
        "to": "Product",
        "type": "PURCHASED",
        "columns": {
          "order_number": { "is_key": true },
          "quantity": {},
          "price": {},
          "rating": {}
        }
      }
    }
  }
}
```

Note the deliberate showcase: `shopping_cart` uses hybrid auto-map (level 2); everything else is a faithful v1 migration with `filters` removed and `source` added.

- [ ] **Step 3: Create `data/ecommerce/import_config_combined.json`**

Same file as Step 2 EXCEPT the `sources` block, which becomes:

```json
  "sources": {
    "ecommerce": { "file": "ecommerce_join.csv", "origin_column": true }
  },
```

Every SGBD block is byte-identical to `import_config.json` — that identity IS the demonstration of spec §2.3 ("origens viram fontes"). Copy the file and swap the block.

- [ ] **Step 4: Rewrite `data/ecommerce/import_config_duplicate_csv_column_example.json`**

(The current file is invalid JSON — trailing comma. The v2 version also demonstrates origin-derived sources.)

```json
{
  "sources": {
    "ecommerce": { "file": "ecommerce_join.csv", "origin_column": true }
  },
  "postgres": {
    "entities": {
      "categories": {
        "source": "stock",
        "columns": {
          "category_id_1": { "is_key": true, "db_type": "BIGINT", "csv_column": "category_id", "schema_column": "category_id_1" },
          "category_id_2": { "db_type": "BIGINT", "csv_column": "category_id", "schema_column": "category_id_2" },
          "category_name": { "db_type": "TEXT" }
        }
      }
    }
  }
}
```

- [ ] **Step 5: Update `run_example.sh`**

1. Delete the `CSV="data/ecommerce/ecommerce_join.csv"` default, the `--csv` case in the option parser, the `[[ ! -f "${CSV}" ]]` guard, and the `log_kv "CSV" "${CSV}"` line.
2. In `run_polyglot`, change the args line to:

```bash
  local -a args=(-m polyglotimportcsv --config "${CONFIG}" --sgbd-config "${SGBD_CONFIG}")
```

3. Update the help header comment: remove the `--csv PATH` option line and the `--csv` example; add an example `./run_example.sh --config data/ecommerce/import_config_combined.json` ("combined CSV mode").

- [ ] **Step 6: Rewrite `tests/test_validation_dry_run.py`**

```python
"""Smoke tests: v2 config dry-run pipeline over the e-commerce example."""

from pathlib import Path

import pytest

from polyglotimportcsv.business_exception import MappingError, SourceError
from polyglotimportcsv.runner import run_import

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "data" / "ecommerce" / "import_config.json"


def test_dry_run_smoke():
    lines = run_import(CFG, dry_run=True, create_schema=False, only=["postgres"])
    assert any("postgres" in L for L in lines)


def test_dry_run_all_backends():
    """All 5 backends appear in dry-run output with expected row counts."""
    lines = run_import(CFG, dry_run=True)
    text = "\n".join(lines)
    assert "entity orders: 8 row(s)" in text
    assert "entity inventory: 8 row(s)" in text
    assert "entity categories: 8 row(s)" in text
    assert "entity products: 8 row(s)" in text
    assert "collection product_catalog: 8 document(s)" in text
    assert "table user_activity_log: 32 row(s)" in text
    assert "entity shopping_cart: 8 row(s)" in text
    assert "entity user_session: 8 row(s)" in text
    assert "label User: 8 row(s)" in text
    assert "label Product: 8 row(s)" in text
    assert "relationship type PURCHASED" in text


def test_unknown_source_raises(tmp_path):
    cfg = tmp_path / "cfg.json"
    cfg.write_text(
        '{"sources": {"s": "missing.csv"}, "redis": {"entities": {"x": {}}}}',
        encoding="utf-8",
    )
    (tmp_path / "sgbd_config.json").write_text(
        '{"redis": {"connection": {"host": "h"}}}', encoding="utf-8"
    )
    with pytest.raises(SourceError):
        run_import(cfg, dry_run=True)


def test_unresolvable_entity_raises(tmp_path):
    src = tmp_path / "s.csv"
    src.write_text("a\n1\n", encoding="utf-8")
    cfg = tmp_path / "cfg.json"
    cfg.write_text(
        '{"sources": {"s": "s.csv"}, "redis": {"entities": {"nomatch": {}}}}',
        encoding="utf-8",
    )
    (tmp_path / "sgbd_config.json").write_text(
        '{"redis": {"connection": {"host": "h"}}}', encoding="utf-8"
    )
    with pytest.raises(MappingError):
        run_import(cfg, dry_run=True)
```

(Check the real `sgbd_config.schema.json` accepted shape before writing the two tmp-path sgbd configs — mirror `data/ecommerce/sgbd_config.json`'s `redis` block instead if the schema requires more fields.)

- [ ] **Step 7: Create `tests/test_mode_equivalence.py`**

```python
"""Multi-CSV mode and combined mode produce identical dry-run counts (spec §7)."""

import re
from pathlib import Path

from polyglotimportcsv.runner import run_import

ROOT = Path(__file__).resolve().parents[1]
MULTI = ROOT / "data" / "ecommerce" / "import_config.json"
COMBINED = ROOT / "data" / "ecommerce" / "import_config_combined.json"

_COUNT_LINE = re.compile(r"^\s*(entity|collection|table|label)\s+(\S+): (\d+)")


def _counts(lines):
    out = {}
    for line in lines:
        m = _COUNT_LINE.match(line)
        if m:
            out[f"{m.group(1)} {m.group(2)}"] = int(m.group(3))
    return out


def test_both_modes_yield_identical_entity_counts():
    multi = _counts(run_import(MULTI, dry_run=True))
    combined = _counts(run_import(COMBINED, dry_run=True))
    assert multi == combined
    assert multi, "expected at least one counted entity"
```

- [ ] **Step 8: Remove the Task 6/8 xfail markers**

Delete the `@pytest.mark.xfail(...)` lines added in `tests/test_config_parser.py` (fixture test) and `tests/test_runner_registry.py`.

- [ ] **Step 9: Verify `scripts/inspect_persisted_data.py`**

Run: `grep -n -E "version|csv" scripts/inspect_persisted_data.py`
If the script only reads `entities`/`connection` blocks (expected), no change. If it reads `version` or a CSV path, delete that usage — its clean/inspect logic needs only entity names and connections.

- [ ] **Step 10: Run the FULL suite**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: ALL tests pass, no xfails left related to the migration.

- [ ] **Step 11: End-to-end check (optional if Docker available)**

Run: `./run_example.sh --dry-run` — expect the banner, per-source row counts (8/8/8/8), and the same entity counts as `test_dry_run_all_backends`. If Docker is running, `./run_example.sh` for the full flow.

- [ ] **Step 12: Commit**

```bash
git add data/ecommerce/ run_example.sh tests/
git commit -m "feat: migrate e-commerce example to config v2 (multi-CSV default + combined variant)"
```

---

### Task 14: Documentation (READMEs + LaTeX `version` removal)

**Files:**
- Modify: `README.md` (repo root)
- Modify: `data/ecommerce/README.md`
- Modify: `docs-tcc/polyglot-tcc-latex-final/chapters/ch4proposta.tex`
- Modify: `docs-tcc/polyglot-tcc-latex-final/chapters/apendiceconfig.tex`

- [ ] **Step 1: Update `data/ecommerce/README.md`**

Rewrite the file table and prose:

```markdown
# E-commerce example data

| File | Purpose |
|------|---------|
| `ecommerce_stock.csv`, `ecommerce_purchase.csv`, `ecommerce_select_product.csv`, `ecommerce_add_to_cart.csv` | One CSV per entity (default input mode). Each file IS the origin of its rows — no discriminator column needed. |
| `ecommerce_join.csv` | Combined CSV (alternative input mode): column 0 (`action`) is the origin column; each distinct value becomes a source. |
| `import_config.json` | v2 mapping config (multi-CSV `sources`). Default for `./run_example.sh`. |
| `import_config_combined.json` | Same SGBD blocks, `sources` pointing at the combined CSV — demonstrates that switching input modes changes nothing in the per-SGBD mapping. |
| `import_config_duplicate_csv_column_example.json` | Mapping one CSV column into two destination columns via `csv_column`. |
| `sgbd_config.json` | Connection settings per SGBD. |

## Knowing each row's origin

Knowing the **source (entity) of every row** is an essential requirement of the
import process. In the per-entity files the file itself designates the origin.
In the combined `ecommerce_join.csv`, column 0 plays that role: the importer
slices the file by its distinct values and each value becomes a named source
(also exposed to mappings as the `_source` pseudo-column).
```

Keep the stress-test paragraph, updating the command to `--source stock=path.csv` style overrides.

- [ ] **Step 2: Update the root `README.md`**

Read it; update every CLI invocation that passes a CSV positional argument to the v2 form (`polyglotimportcsv --config ... [--source NAME=PATH]`), describe the `sources` block briefly (two modes), and remove any mention of the `version` field. Keep the document's existing structure and tone.

- [ ] **Step 3: LaTeX — remove `version` field mentions**

Run: `grep -n "version" docs-tcc/polyglot-tcc-latex-final/chapters/ch4proposta.tex docs-tcc/polyglot-tcc-latex-final/chapters/apendiceconfig.tex`

- In `ch4proposta.tex`: delete the `"version": 1,` line from any JSON listing and the sentence(s) describing the mandatory `version` root field (section "raiz", around `\label{sec:raiz}`).
- In `apendiceconfig.tex`: replace the body of Listagem `lst:import-config-full` with the NEW `data/ecommerce/import_config.json` content verbatim (it is a faithful reproduction by definition — advisor preference). Escape nothing beyond what the existing `lstlisting` style already handles.
- Do NOT rewrite other ch4 prose/listings (e.g. `filters` examples) — that is TCC2 report writing, out of scope. Leave a `% TODO(TCC2): atualizar listagens de filters/sources na reescrita do capítulo` comment at the top of ch4proposta.tex so the divergence is tracked.

- [ ] **Step 4: Full suite + compile check**

Run: `./.venv/Scripts/python.exe -m pytest tests -q` — all green.
If a LaTeX toolchain is configured in the repo (check `docs-tcc/polyglot-tcc-latex-final/` for a build script or Makefile), compile `main.tex` and confirm no new errors; otherwise skip compilation and note it in the commit message.

- [ ] **Step 5: Commit**

```bash
git add README.md data/ecommerce/README.md docs-tcc/polyglot-tcc-latex-final/chapters/ch4proposta.tex docs-tcc/polyglot-tcc-latex-final/chapters/apendiceconfig.tex
git commit -m "docs: v2 sources format in READMEs; drop version field from report"
```

---

## Self-review notes (already applied)

- **Spec coverage:** §2.1→Task 6; §2.2→Task 4; §2.3→Tasks 5/13; §2.4→Tasks 3/5/6; §2.5→Task 2; §2.6→Tasks 4/5/7/13 (cassandra `_source` mapping); §2.7→filters kept in importers, `sgbd_config` untouched; §3 table→Tasks 2/4/5/7/8/9-11; §3.1→Task 12 (`--log-level`, `--show-data`, `--benchmark` belong to Plans 2/3, NOT here); §3.2→Task 1; §6→Task 13; §7→Tasks 1-13 tests + equivalence; §8→Task 14. §4 (rich logging) and §5 (benchmarks) are Plans 2 and 3.
- **Type consistency:** `BoundEntity(name, cfg, df, kinds)` used identically in Tasks 5, 7, 8, 9, 10, 11; `SourceData(name, df, kinds, file_header)` in Tasks 4, 5; importer signature `(backend_cfg, entities, *, dry_run, create_schema)` in Tasks 8-11; `run_import(config_path, *, ..., source_overrides)` in Tasks 8, 12, 13.
- **Known intentional behavior changes vs v1:** `csv_column` integer indices are now 1-based; postgres FK validation checks mapped target names instead of raw CSV headers; MongoDB/Redis/Neo4j receive native-typed values; the CLI lost its positional CSV argument.
