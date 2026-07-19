# TCC2 Benchmarks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic synthetic e-commerce dataset generator and a benchmark runner that measures import throughput across sizes, input modes, and SGBDs.

**Architecture:** Pure, testable logic lives in the `src/polyglotimportcsv/` package (`benchmark_data.py` — generation; `benchmark_results.py` — median/consolidation; `benchmark_runner.py` — matrix orchestration with dependency injection). Two thin `scripts/` CLIs wrap them (`generate_benchmark_data.py`, `run_benchmarks.py`). The runner reuses the Plan-2 seam `run_import(..., collector=MetricsCollector())` for measurement and the per-backend `CLEANERS` from `scripts/inspect_persisted_data.py` for cold-start cleaning — injected as a parameter so `src` never imports `scripts`.

**Tech Stack:** Python ≥3.9, stdlib `random`/`csv`/`uuid`/`statistics` (no new dependency), pandas (already present via the pipeline), pytest.

## Global Constraints

- Python ≥3.9: the `X | Y` union syntax may appear ONLY inside string annotations / under `from __future__ import annotations`, never as runtime code 3.9 rejects.
- No new third-party dependency: the generator uses only the standard library (`random`, `csv`, `uuid`, `datetime`, `statistics`). No `numpy`.
- Determinism: the same `(rows, seed)` MUST produce byte-identical CSV output on any platform. Fix `csv.writer(..., lineterminator="\n")` and open files with `newline=""`.
- `src/` must never import from `scripts/`. The benchmark runner receives the cleaners, importer, and config loader as injected callables.
- Generated CSV headers MUST be byte-identical to the real files in `data/ecommerce/` so the shipped `import_config.json` / `import_config_combined.json` run unchanged over generated data via `--source NAME=PATH` overrides.
- `--rows N` = number of products; cardinalities are stock=N, purchase=3N, select_product=2N, add_to_cart=2N; pools are `num_users = max(1, N//10)`, `num_categories = max(1, N//100)`.
- Streaming generation only: never materialize the full dataset in memory (must scale to 1M+).
- Importer signatures stay frozen; benchmarking rides the existing `collector` parameter of `run_import`.
- Test command: `./.venv/Scripts/python.exe -m pytest tests -q`. The gate is "suite green"; exact counts in this plan are indicative — if a count drifts by a test, green is what matters.
- Spec: `docs/superpowers/specs/2026-07-19-tcc2-benchmarks-design.md`.

---

### Task 1: `benchmark_data.py` — schemas, deterministic derivations, row iterator

**Files:**
- Create: `src/polyglotimportcsv/benchmark_data.py`
- Test: `tests/test_benchmark_data.py`

**Interfaces:**
- Consumes: nothing (leaf module, stdlib only).
- Produces:
  - Column constants `STOCK_COLUMNS`, `PURCHASE_COLUMNS`, `SELECT_COLUMNS`, `CART_COLUMNS`, `JOIN_COLUMNS` (each `Tuple[str, ...]`); `SOURCE_COLUMNS: Dict[str, Tuple[str,...]]`; `SOURCE_FILES: Dict[str,str]`; `JOIN_FILE: str`.
  - `num_users(rows: int) -> int`, `num_categories(rows: int) -> int`.
  - `iter_source_rows(seed: int, rows: int) -> Iterator[Tuple[str, Dict[str, object]]]` yielding `(source_name, row_dict)` in fixed order (all stock, then purchase, then select_product, then add_to_cart), deterministic for a given `(seed, rows)`, with foreign keys drawn from the generated product/user pools.

- [ ] **Step 1: Write the failing test**

Create `tests/test_benchmark_data.py`:

```python
"""Deterministic synthetic dataset generator (spec §2)."""

from collections import Counter

from polyglotimportcsv import benchmark_data as bd


def _rows(seed, rows):
    return list(bd.iter_source_rows(seed, rows))


def test_cardinalities_follow_ratios():
    counts = Counter(src for src, _ in _rows(42, 10))
    assert counts["stock"] == 10
    assert counts["purchase"] == 30
    assert counts["select_product"] == 20
    assert counts["add_to_cart"] == 20


def test_pool_sizes():
    assert bd.num_users(10) == 1
    assert bd.num_users(1000) == 100
    assert bd.num_categories(50) == 1
    assert bd.num_categories(1000) == 10


def test_deterministic_same_seed():
    assert _rows(7, 15) == _rows(7, 15)


def test_different_seed_differs():
    assert _rows(1, 15) != _rows(2, 15)


def test_referential_integrity():
    seed, n = 42, 40
    rows = _rows(seed, n)
    stock_pids = {r["product_id"] for src, r in rows if src == "stock"}
    assert stock_pids == set(range(1, n + 1))
    user_pool = {bd._user(seed, i)["user_id"] for i in range(bd.num_users(n))}
    ncat = bd.num_categories(n)
    for src, r in rows:
        assert r["user_id"] in user_pool
        if src == "purchase":
            assert r["product_id"] in stock_pids
            assert 1 <= r["category_id"] <= ncat
        if src == "select_product":
            assert r["selected_product_id"] in stock_pids
        if src == "add_to_cart":
            assert r["cart_product_id"] in stock_pids


def test_stock_product_id_is_sequential():
    pids = [r["product_id"] for src, r in _rows(42, 12) if src == "stock"]
    assert pids == list(range(1, 13))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_benchmark_data.py -v`
Expected: FAIL with `ModuleNotFoundError` / `AttributeError: iter_source_rows`.

- [ ] **Step 3: Create `src/polyglotimportcsv/benchmark_data.py`**

```python
"""Deterministic synthetic e-commerce dataset generator for benchmarks (spec §2).

Streaming and fully deterministic: the same ``(seed, rows)`` yields the same
rows in the same order. Foreign keys are drawn from the generated product/user
pools so every reference resolves. Per-entity attributes are pure functions of
their id/index, so cross-references stay consistent without holding pools in
memory.
"""

from __future__ import annotations

import csv
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterator, Tuple

# --- Column schemas: byte-identical to the real CSVs in data/ecommerce/ ---
STOCK_COLUMNS: Tuple[str, ...] = (
    "timestamp", "user_id", "user_name", "user_email",
    "street", "neighborhood", "state", "country", "zip_code",
    "product_id", "product_name", "product_variant", "product_brand",
    "product_description", "product_image", "category_id", "category_name",
    "quantity_available", "price", "last_restock_date",
)
PURCHASE_COLUMNS: Tuple[str, ...] = (
    "timestamp", "user_id", "user_name", "user_email",
    "street", "neighborhood", "state", "country", "zip_code",
    "order_number", "order_date", "order_status", "traded_with",
    "trader_street", "trader_neighborhood", "trader_state", "trader_country",
    "trader_zip_code", "comment", "rating", "payment_method", "quantity",
    "product_id", "product_name", "product_variant", "product_brand",
    "product_description", "product_image", "category_id", "category_name",
    "quantity_available", "price", "last_restock_date",
)
SELECT_COLUMNS: Tuple[str, ...] = (
    "timestamp", "user_id", "user_name", "user_email",
    "selected_product_id", "suggested_product_count",
)
CART_COLUMNS: Tuple[str, ...] = (
    "timestamp", "user_id", "user_name", "user_email",
    "shopping_cart_id", "cart_product_id", "cart_quantity",
)
# The combined file is action + purchase (a superset of stock's columns) + the
# select/cart-only columns. Derived by concatenation to avoid transcription drift.
JOIN_COLUMNS: Tuple[str, ...] = (
    ("action",)
    + PURCHASE_COLUMNS
    + ("selected_product_id", "suggested_product_count",
       "shopping_cart_id", "cart_product_id", "cart_quantity")
)

SOURCE_COLUMNS: Dict[str, Tuple[str, ...]] = {
    "stock": STOCK_COLUMNS,
    "purchase": PURCHASE_COLUMNS,
    "select_product": SELECT_COLUMNS,
    "add_to_cart": CART_COLUMNS,
}
SOURCE_FILES: Dict[str, str] = {
    "stock": "ecommerce_stock.csv",
    "purchase": "ecommerce_purchase.csv",
    "select_product": "ecommerce_select_product.csv",
    "add_to_cart": "ecommerce_add_to_cart.csv",
}
JOIN_FILE = "ecommerce_join.csv"

_VARIANTS = ("blue", "green", "red", "black", "white")
_BRANDS = ("Microsoft", "Google", "Apple", "Sony", "Samsung")
_NEIGHBORHOODS = ("ABC", "DEF", "GHI", "JKL")
_STATES = ("CA", "SC", "NY", "TX")
_COUNTRIES = ("United States", "Brasil", "Canada")
_STATUSES = ("Completed", "Pending", "Cancelled")
_PAYMENTS = ("cash", "credit", "debit", "pix")
_COMMENTS = ("Bad", "Bom", "Great", "Okay", "Terrible")
_BASE = datetime(2023, 11, 1, 0, 0, 0)
_SPAN_SECONDS = 30 * 24 * 3600


def num_users(rows: int) -> int:
    return max(1, rows // 10)


def num_categories(rows: int) -> int:
    return max(1, rows // 100)


def _product(seed: int, pid: int, ncat: int) -> Dict[str, object]:
    rng = random.Random(f"{seed}:product:{pid}")
    category_id = rng.randint(1, ncat)
    return {
        "product_id": pid,
        "product_name": f"Product{pid}",
        "product_variant": rng.choice(_VARIANTS),
        "product_brand": rng.choice(_BRANDS),
        "product_description": f"Description{pid}",
        "product_image": f"https://example.com/image{pid}.jpg",
        "category_id": category_id,
        "category_name": f"Categoria{category_id}",
        "price": round(rng.uniform(5, 500), 2),
        "quantity_available": rng.randint(0, 100),
    }


def _user(seed: int, uidx: int) -> Dict[str, object]:
    rng = random.Random(f"{seed}:user:{uidx}")
    return {
        "user_id": str(uuid.UUID(int=rng.getrandbits(128))),
        "user_name": f"user{uidx + 1}",
        "user_email": f"user{uidx + 1}@example.com",
        "street": f"Street {uidx + 1}, {rng.randint(1, 999)}",
        "neighborhood": rng.choice(_NEIGHBORHOODS),
        "state": rng.choice(_STATES),
        "country": rng.choice(_COUNTRIES),
        "zip_code": str(rng.randint(10000, 99999)),
    }


def _ts(master: random.Random) -> str:
    dt = _BASE + timedelta(seconds=master.randint(0, _SPAN_SECONDS))
    return dt.strftime("%Y-%m-%d %H:%M:%SZ")


def _order_date(master: random.Random) -> str:
    dt = _BASE + timedelta(seconds=master.randint(0, _SPAN_SECONDS))
    return dt.strftime("%Y-%m-%dT%H:%M:%S-05:00")


def iter_source_rows(seed: int, rows: int) -> Iterator[Tuple[str, Dict[str, object]]]:
    """Yield ``(source_name, row_dict)`` in fixed order for a given ``(seed, rows)``.

    Order: all stock rows, then purchase, then select_product, then add_to_cart.
    Every foreign key references the generated product/user pools.
    """
    n = rows
    nu = num_users(n)
    nc = num_categories(n)
    master = random.Random(f"{seed}:stream")

    for pid in range(1, n + 1):
        usr = _user(seed, master.randrange(nu))
        prod = _product(seed, pid, nc)
        ts = _ts(master)
        yield "stock", {"timestamp": ts, **usr, **prod, "last_restock_date": ts}

    for i in range(1, 3 * n + 1):
        usr = _user(seed, master.randrange(nu))
        other = _user(seed, master.randrange(nu))
        prod = _product(seed, master.randint(1, n), nc)
        ts = _ts(master)
        yield "purchase", {
            "timestamp": ts, **usr,
            "order_number": f"ORD{i}",
            "order_date": _order_date(master),
            "order_status": master.choice(_STATUSES),
            "traded_with": other["user_id"],
            "trader_street": other["street"],
            "trader_neighborhood": other["neighborhood"],
            "trader_state": other["state"],
            "trader_country": other["country"],
            "trader_zip_code": other["zip_code"],
            "comment": master.choice(_COMMENTS),
            "rating": master.randint(1, 5),
            "payment_method": master.choice(_PAYMENTS),
            "quantity": master.randint(1, 5),
            **prod,
            "last_restock_date": ts,
        }

    for _ in range(2 * n):
        usr = _user(seed, master.randrange(nu))
        yield "select_product", {
            "timestamp": _ts(master), **usr,
            "selected_product_id": master.randint(1, n),
            "suggested_product_count": master.randint(1, 5),
        }

    for _ in range(2 * n):
        usr = _user(seed, master.randrange(nu))
        yield "add_to_cart", {
            "timestamp": _ts(master), **usr,
            "shopping_cart_id": f"user:{usr['user_id']}:cart",
            "cart_product_id": master.randint(1, n),
            "cart_quantity": master.randint(1, 5),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_benchmark_data.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: green (123 + 6 new = 129 passed, 1 skipped).

- [ ] **Step 6: Commit**

```bash
git add src/polyglotimportcsv/benchmark_data.py tests/test_benchmark_data.py
git commit -m "feat: deterministic synthetic dataset row generator (schemas, pools, iterator)"
```

---

### Task 2: Multi-CSV writer (`generate_dataset` multi mode)

**Files:**
- Modify: `src/polyglotimportcsv/benchmark_data.py`
- Test: `tests/test_benchmark_data.py`

**Interfaces:**
- Consumes: Task 1's `iter_source_rows`, `SOURCE_COLUMNS`, `SOURCE_FILES`.
- Produces: `generate_dataset(out_dir: "str | Path", rows: int, seed: int = 42, mode: str = "both") -> Dict[str, Path]`. In `"multi"` mode it writes the four per-entity CSVs and returns `{source_name: Path}`. (`"combined"`/`"both"` land in Task 3.)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_benchmark_data.py`:

```python
import csv as _csv
from pathlib import Path

REAL = Path(__file__).resolve().parents[1] / "data" / "ecommerce"


def _header(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return next(_csv.reader(fh))


def test_multi_writes_four_files_with_real_headers(tmp_path):
    written = bd.generate_dataset(tmp_path, rows=15, seed=42, mode="multi")
    assert set(written) == {"stock", "purchase", "select_product", "add_to_cart"}
    for src, fname in bd.SOURCE_FILES.items():
        gen_header = _header(tmp_path / fname)
        real_header = _header(REAL / fname)
        assert gen_header == real_header, src
        assert tuple(gen_header) == bd.SOURCE_COLUMNS[src]


def test_multi_row_counts(tmp_path):
    bd.generate_dataset(tmp_path, rows=15, seed=42, mode="multi")

    def n(fname):
        with open(tmp_path / fname, encoding="utf-8") as fh:
            return sum(1 for _ in fh) - 1  # minus header

    assert n("ecommerce_stock.csv") == 15
    assert n("ecommerce_purchase.csv") == 45
    assert n("ecommerce_select_product.csv") == 30
    assert n("ecommerce_add_to_cart.csv") == 30


def test_multi_byte_identical_for_same_seed(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    bd.generate_dataset(a, rows=20, seed=42, mode="multi")
    bd.generate_dataset(b, rows=20, seed=42, mode="multi")
    for fname in bd.SOURCE_FILES.values():
        assert (a / fname).read_bytes() == (b / fname).read_bytes(), fname


def test_multi_foreign_keys_resolve_across_files(tmp_path):
    bd.generate_dataset(tmp_path, rows=30, seed=42, mode="multi")

    def col(fname, name):
        with open(tmp_path / fname, newline="", encoding="utf-8") as fh:
            return [row[name] for row in _csv.DictReader(fh)]

    stock_pids = set(col("ecommerce_stock.csv", "product_id"))
    assert set(col("ecommerce_purchase.csv", "product_id")) <= stock_pids
    assert set(col("ecommerce_select_product.csv", "selected_product_id")) <= stock_pids
    assert set(col("ecommerce_add_to_cart.csv", "cart_product_id")) <= stock_pids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_benchmark_data.py -k multi -v`
Expected: FAIL with `AttributeError: generate_dataset`.

- [ ] **Step 3: Add `generate_dataset` to `src/polyglotimportcsv/benchmark_data.py`**

Append at the end of the file:

```python
def generate_dataset(
    out_dir: "str | Path", rows: int, seed: int = 42, mode: str = "both"
) -> Dict[str, Path]:
    """Write the synthetic dataset. ``mode`` is ``multi``, ``combined``, or ``both``.

    Returns a mapping of written keys (source names and/or ``"combined"``) to Paths.
    """
    if mode not in ("multi", "combined", "both"):
        raise ValueError(f"unknown mode: {mode!r}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: Dict[str, Path] = {}

    if mode in ("multi", "both"):
        handles = {}
        writers = {}
        for src, fname in SOURCE_FILES.items():
            path = out / fname
            fh = path.open("w", encoding="utf-8", newline="")
            handles[src] = fh
            writer = csv.writer(fh, lineterminator="\n")
            writer.writerow(SOURCE_COLUMNS[src])
            writers[src] = writer
            written[src] = path
        try:
            for src, row in iter_source_rows(seed, rows):
                writers[src].writerow([row.get(c, "") for c in SOURCE_COLUMNS[src]])
        finally:
            for fh in handles.values():
                fh.close()

    return written
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_benchmark_data.py -k multi -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: green (~133 passed, 1 skipped).

- [ ] **Step 6: Commit**

```bash
git add src/polyglotimportcsv/benchmark_data.py tests/test_benchmark_data.py
git commit -m "feat: streaming multi-CSV writer for synthetic dataset"
```

---

### Task 3: Combined-CSV writer (`combined`/`both` modes)

**Files:**
- Modify: `src/polyglotimportcsv/benchmark_data.py`
- Test: `tests/test_benchmark_data.py`

**Interfaces:**
- Consumes: Task 2's `generate_dataset`, Task 1's `iter_source_rows`, `JOIN_COLUMNS`, `JOIN_FILE`.
- Produces: `generate_dataset(..., mode="combined")` writes `ecommerce_join.csv` (returns `{"combined": Path}`); `mode="both"` writes all five files. Combined rows encode the same data as multi (mode data-equivalence by construction).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_benchmark_data.py`:

```python
def test_combined_header_matches_real_join(tmp_path):
    written = bd.generate_dataset(tmp_path, rows=15, seed=42, mode="combined")
    assert set(written) == {"combined"}
    gen_header = _header(tmp_path / bd.JOIN_FILE)
    real_header = _header(REAL / bd.JOIN_FILE)
    assert gen_header == real_header
    assert tuple(gen_header) == bd.JOIN_COLUMNS


def test_combined_action_counts(tmp_path):
    bd.generate_dataset(tmp_path, rows=15, seed=42, mode="combined")
    with open(tmp_path / bd.JOIN_FILE, newline="", encoding="utf-8") as fh:
        actions = Counter(row["action"] for row in _csv.DictReader(fh))
    assert actions == {"stock": 15, "purchase": 45, "select_product": 30, "add_to_cart": 30}


def test_both_writes_five_files(tmp_path):
    written = bd.generate_dataset(tmp_path, rows=12, seed=42, mode="both")
    assert set(written) == {"stock", "purchase", "select_product", "add_to_cart", "combined"}
    for fname in list(bd.SOURCE_FILES.values()) + [bd.JOIN_FILE]:
        assert (tmp_path / fname).is_file()


def test_combined_equals_multi_data(tmp_path):
    """A combined row's populated cells match the corresponding multi row."""
    bd.generate_dataset(tmp_path, rows=10, seed=42, mode="both")
    with open(tmp_path / bd.JOIN_FILE, newline="", encoding="utf-8") as fh:
        join = list(_csv.DictReader(fh))
    stock_join = [r for r in join if r["action"] == "stock"]
    with open(tmp_path / "ecommerce_stock.csv", newline="", encoding="utf-8") as fh:
        stock = list(_csv.DictReader(fh))
    assert len(stock_join) == len(stock)
    for jrow, srow in zip(stock_join, stock):
        for col in bd.STOCK_COLUMNS:
            assert jrow[col] == srow[col], col


def test_combined_byte_identical_for_same_seed(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    bd.generate_dataset(a, rows=20, seed=42, mode="combined")
    bd.generate_dataset(b, rows=20, seed=42, mode="combined")
    assert (a / bd.JOIN_FILE).read_bytes() == (b / bd.JOIN_FILE).read_bytes()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_benchmark_data.py -k combined -v`
Expected: FAIL (`written` has no `"combined"` key; join file absent).

- [ ] **Step 3: Extend `generate_dataset`**

In `src/polyglotimportcsv/benchmark_data.py`, insert this block **before** the final `return written` in `generate_dataset`:

```python
    if mode in ("combined", "both"):
        path = out / JOIN_FILE
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, lineterminator="\n")
            writer.writerow(JOIN_COLUMNS)
            for src, row in iter_source_rows(seed, rows):
                writer.writerow([src] + [row.get(c, "") for c in JOIN_COLUMNS[1:]])
        written["combined"] = path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_benchmark_data.py -k combined -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: green (~138 passed, 1 skipped).

- [ ] **Step 6: Commit**

```bash
git add src/polyglotimportcsv/benchmark_data.py tests/test_benchmark_data.py
git commit -m "feat: combined-CSV (origin-column) writer + both mode"
```

---

### Task 4: Generator CLI, versioned reference dataset, gitignore & data README

**Files:**
- Create: `scripts/generate_benchmark_data.py`
- Create: `data/benchmark/README.md`
- Create (generated + committed): `data/benchmark/ecommerce_stock.csv`, `ecommerce_purchase.csv`, `ecommerce_select_product.csv`, `ecommerce_add_to_cart.csv`, `ecommerce_join.csv`
- Modify: `.gitignore`
- Test: `tests/test_generate_benchmark_data_cli.py` (new), `tests/test_benchmark_example.py` (new)

**Interfaces:**
- Consumes: Task 3's `generate_dataset`; the shipped `data/ecommerce/import_config.json` and `import_config_combined.json`; `run_import` (Plan 2) and `MetricsCollector`.
- Produces: `scripts/generate_benchmark_data.py` with `main(argv: Optional[Sequence[str]] = None) -> int`; a committed 1k-row reference dataset under `data/benchmark/` in both modes; `.gitignore` entry for `data/benchmark/generated/`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_generate_benchmark_data_cli.py`:

```python
"""CLI wrapper for the dataset generator."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_benchmark_data.py"


def _load_main():
    spec = importlib.util.spec_from_file_location("generate_benchmark_data", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.main


def test_cli_writes_multi(tmp_path):
    main = _load_main()
    rc = main(["--rows", "20", "--seed", "42", "--out", str(tmp_path), "--mode", "multi"])
    assert rc == 0
    for fname in ("ecommerce_stock.csv", "ecommerce_purchase.csv",
                  "ecommerce_select_product.csv", "ecommerce_add_to_cart.csv"):
        assert (tmp_path / fname).is_file()


def test_cli_writes_both(tmp_path):
    main = _load_main()
    rc = main(["--rows", "20", "--out", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "ecommerce_join.csv").is_file()
```

Create `tests/test_benchmark_example.py`:

```python
"""The committed reference dataset drives dry-run smoke + mode-equivalence."""

from pathlib import Path

from polyglotimportcsv import benchmark_data as bd
from polyglotimportcsv.metrics import MetricsCollector
from polyglotimportcsv.runner import run_import

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "data" / "benchmark"
ECOM = ROOT / "data" / "ecommerce"


def test_reference_dataset_committed_and_1k():
    def n(fname):
        with open(BENCH / fname, encoding="utf-8") as fh:
            return sum(1 for _ in fh) - 1
    assert n("ecommerce_stock.csv") == 125
    assert n("ecommerce_purchase.csv") == 375
    assert n("ecommerce_select_product.csv") == 250
    assert n("ecommerce_add_to_cart.csv") == 250
    assert n("ecommerce_join.csv") == 1000  # 125 + 375 + 250 + 250


def _filter_rows(config, overrides):
    c = MetricsCollector()
    run_import(config, dry_run=True, collector=c, source_overrides=overrides)
    return {(m.entity): m.rows for m in c.entries() if m.phase == "filter"}


def test_dry_run_smoke_on_reference():
    overrides = {src: str(BENCH / fname) for src, fname in bd.SOURCE_FILES.items()}
    lines = run_import(ECOM / "import_config.json", dry_run=True, source_overrides=overrides)
    assert lines  # produced output, no exception


def test_mode_equivalence_entity_counts():
    multi = _filter_rows(
        ECOM / "import_config.json",
        {src: str(BENCH / fname) for src, fname in bd.SOURCE_FILES.items()},
    )
    combined = _filter_rows(
        ECOM / "import_config_combined.json",
        {"ecommerce": str(BENCH / bd.JOIN_FILE)},
    )
    assert multi == combined
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_generate_benchmark_data_cli.py tests/test_benchmark_example.py -v`
Expected: FAIL (script missing; `data/benchmark/` not yet generated).

- [ ] **Step 3: Create `scripts/generate_benchmark_data.py`**

```python
#!/usr/bin/env python3
"""CLI: generate a synthetic benchmark dataset (spec §2.5)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from polyglotimportcsv.benchmark_data import generate_dataset


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic synthetic e-commerce dataset."
    )
    parser.add_argument("--rows", type=int, required=True, help="Number of products (N).")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42).")
    parser.add_argument("--out", type=Path, required=True, help="Output directory.")
    parser.add_argument(
        "--mode", choices=("both", "multi", "combined"), default="both",
        help="Which formats to write (default: both).",
    )
    args = parser.parse_args(argv)
    written = generate_dataset(args.out, args.rows, seed=args.seed, mode=args.mode)
    for key, path in written.items():
        print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Generate the committed reference dataset**

Run: `./.venv/Scripts/python.exe scripts/generate_benchmark_data.py --rows 125 --seed 42 --out data/benchmark --mode both`
Expected: prints five `key: path` lines; creates the five CSVs under `data/benchmark/`.

- [ ] **Step 5: Add the `.gitignore` entry**

In `.gitignore`, right after the `benchmarks/` block:

```
# Benchmark outputs (--benchmark); consolidated results are cited in the report
benchmarks/

# Large benchmark datasets generated on demand (the small reference under
# data/benchmark/ IS committed; only generated/ is ignored)
data/benchmark/generated/
```

- [ ] **Step 6: Create `data/benchmark/README.md`**

```markdown
# Benchmark reference dataset

Small, **versioned** synthetic e-commerce dataset for fast tests, CI, and the
mode-equivalence check. Generated deterministically with:

    python scripts/generate_benchmark_data.py --rows 125 --seed 42 --out data/benchmark --mode both

Size: N = 125 products → exactly 1 000 rows total.

| File | Rows | Notes |
|---|---|---|
| `ecommerce_stock.csv` | 125 | one row per product (`product_id` 1..125) |
| `ecommerce_purchase.csv` | 375 | orders (3N); FKs reference the product/user pools |
| `ecommerce_select_product.csv` | 250 | selection events (2N) |
| `ecommerce_add_to_cart.csv` | 250 | cart events (2N) |
| `ecommerce_join.csv` | 1 000 | combined format (origin column 0); same data as the four above |

Headers are byte-identical to the real `data/ecommerce/` CSVs, so
`import_config.json` and `import_config_combined.json` run unchanged over this
data via `--source NAME=PATH`.

Large sizes (10k, 100k, 1M) are generated on demand into
`data/benchmark/generated/` (git-ignored) by `scripts/run_benchmarks.py`.
```

- [ ] **Step 7: Run the tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_generate_benchmark_data_cli.py tests/test_benchmark_example.py -v`
Expected: PASS (5 tests).

- [ ] **Step 8: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: green (~143 passed, 1 skipped).

- [ ] **Step 9: Commit**

```bash
git add scripts/generate_benchmark_data.py data/benchmark .gitignore \
  tests/test_generate_benchmark_data_cli.py tests/test_benchmark_example.py
git commit -m "feat: generator CLI + committed 1k reference dataset (both modes)"
```

---

### Task 5: `benchmark_results.py` — median aggregation + consolidated output

**Files:**
- Create: `src/polyglotimportcsv/benchmark_results.py`
- Test: `tests/test_benchmark_results.py`

**Interfaces:**
- Consumes: labeled run dicts of shape `{"size": int, "mode": str, "repetition": int, "records": List[dict]}` where each record is a `PhaseMetric.to_record()` (`backend`, `entity`, `phase`, `rows`, `seconds`, `rows_per_second`).
- Produces:
  - `median_results(labeled_runs: List[Dict[str, object]]) -> List[Dict[str, object]]` — median `seconds` per `(size, mode, backend, entity, phase)`; `rows_per_second` recomputed from the median.
  - `write_consolidated(results, metadata, out_dir="benchmarks") -> Tuple[Path, Path]` — writes `benchmark_run_<timestamp>.json` and appends `benchmark_results.csv`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_benchmark_results.py`:

```python
"""Median aggregation + consolidated benchmark output (spec §3.2, §3.4)."""

import csv
import json

from polyglotimportcsv import benchmark_results as br


def _run(size, mode, rep, seconds):
    return {
        "size": size, "mode": mode, "repetition": rep,
        "records": [{
            "backend": "postgres", "entity": "products", "phase": "write",
            "rows": 100, "seconds": seconds, "rows_per_second": 100 / seconds,
        }],
    }


def test_median_across_repetitions():
    runs = [_run(1000, "multi", 0, 0.2), _run(1000, "multi", 1, 0.4), _run(1000, "multi", 2, 0.3)]
    results = br.median_results(runs)
    assert len(results) == 1
    r = results[0]
    assert r["size"] == 1000 and r["mode"] == "multi"
    assert r["backend"] == "postgres" and r["entity"] == "products" and r["phase"] == "write"
    assert r["rows"] == 100
    assert r["median_seconds"] == 0.3
    assert abs(r["rows_per_second"] - 100 / 0.3) < 1e-9


def test_distinct_size_mode_kept_separate():
    runs = [_run(1000, "multi", 0, 0.2), _run(1000, "combined", 0, 0.5)]
    results = br.median_results(runs)
    keys = {(r["size"], r["mode"]) for r in results}
    assert keys == {(1000, "multi"), (1000, "combined")}


def test_write_consolidated(tmp_path):
    results = br.median_results([_run(1000, "multi", 0, 0.25)])
    meta = {"timestamp": "2026-07-19T10:00:00", "python": "3.11.0"}
    json_path, csv_path = br.write_consolidated(results, meta, out_dir=tmp_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["metadata"]["python"] == "3.11.0"
    assert data["results"][0]["phase"] == "write"
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["size"] == "1000"
    assert rows[0]["mode"] == "multi"
    assert rows[0]["timestamp"] == "2026-07-19T10:00:00"


def test_csv_appends(tmp_path):
    results = br.median_results([_run(1000, "multi", 0, 0.25)])
    meta = {"timestamp": "t"}
    br.write_consolidated(results, meta, out_dir=tmp_path)
    _, csv_path = br.write_consolidated(results, meta, out_dir=tmp_path)
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3  # header + two runs
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_benchmark_results.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `src/polyglotimportcsv/benchmark_results.py`**

```python
"""Consolidate benchmark runs: median across repetitions + JSON/CSV output (spec §3.4)."""

from __future__ import annotations

import csv
import json
import statistics
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

_RESULT_FIELDS = (
    "timestamp", "size", "mode", "backend", "entity", "phase",
    "rows", "median_seconds", "rows_per_second",
)


def median_results(labeled_runs: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """Median ``seconds`` per ``(size, mode, backend, entity, phase)``.

    ``rows`` is constant across repetitions (same dataset); ``rows_per_second``
    is recomputed from the median.
    """
    groups: Dict[Tuple, Dict[str, object]] = {}
    order: List[Tuple] = []
    for run in labeled_runs:
        for rec in run["records"]:
            key = (run["size"], run["mode"], rec["backend"], rec["entity"], rec["phase"])
            if key not in groups:
                groups[key] = {"rows": rec["rows"], "seconds": []}
                order.append(key)
            groups[key]["seconds"].append(rec["seconds"])

    results: List[Dict[str, object]] = []
    for key in order:
        size, mode, backend, entity, phase = key
        g = groups[key]
        med = statistics.median(g["seconds"])
        rps = (g["rows"] / med) if med > 0 else None
        results.append({
            "size": size, "mode": mode, "backend": backend,
            "entity": entity, "phase": phase, "rows": g["rows"],
            "median_seconds": med, "rows_per_second": rps,
        })
    return results


def write_consolidated(
    results: List[Dict[str, object]],
    metadata: Dict[str, object],
    out_dir: "str | Path" = "benchmarks",
) -> Tuple[Path, Path]:
    """Write ``benchmark_run_<timestamp>.json`` and append ``benchmark_results.csv``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out / f"benchmark_run_{stamp}.json"
    json_path.write_text(
        json.dumps({"metadata": metadata, "results": results}, indent=2, default=str),
        encoding="utf-8",
    )
    csv_path = out / "benchmark_results.csv"
    new_file = not csv_path.exists()
    ts = metadata.get("timestamp", "")
    with csv_path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_RESULT_FIELDS)
        if new_file:
            writer.writeheader()
        for rec in results:
            row = {k: rec[k] for k in _RESULT_FIELDS if k != "timestamp"}
            row["timestamp"] = ts
            writer.writerow(row)
    return json_path, csv_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_benchmark_results.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: green (~147 passed, 1 skipped).

- [ ] **Step 6: Commit**

```bash
git add src/polyglotimportcsv/benchmark_results.py tests/test_benchmark_results.py
git commit -m "feat: benchmark median aggregation + consolidated JSON/CSV output"
```

---

### Task 6: `benchmark_runner.py` matrix (DI) + `scripts/run_benchmarks.py` CLI

**Files:**
- Create: `src/polyglotimportcsv/benchmark_runner.py`
- Create: `scripts/run_benchmarks.py`
- Test: `tests/test_benchmark_runner.py`

**Interfaces:**
- Consumes: Task 3's `generate_dataset`, `SOURCE_FILES`, `JOIN_FILE`; `MetricsCollector`; injected `cleaners` (`Dict[str, Callable[[dict], None]]`), `importer` (a `run_import`-like callable), and `load_cfg` (a `load_config`-like callable). The script wires `CLEANERS` (from `scripts/inspect_persisted_data.py`), `run_import`, and `load_config`.
- Produces: `run_matrix(*, sizes, modes, repetitions, sgbd_config_path, config_dir, data_dir, seed, only, cleaners, importer, load_cfg, generate=generate_dataset) -> List[Dict[str, object]]` returning labeled runs (feeds `median_results`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_benchmark_runner.py`:

```python
"""Matrix orchestration is DB-free via dependency injection."""

from pathlib import Path

from polyglotimportcsv import benchmark_runner as brun
from polyglotimportcsv.benchmark_results import median_results


def test_run_matrix_iterates_and_cleans_before_import(tmp_path):
    events = []

    def make_cleaner(name):
        def _clean(block):
            events.append(("clean", name))
        return _clean

    cleaners = {"postgres": make_cleaner("postgres")}

    def fake_importer(config_path, *, sgbd_config_path, collector, show_data,
                      only, create_schema, source_overrides):
        events.append(("import", str(config_path), tuple(sorted(source_overrides))))
        collector.record("postgres", "products", "write", rows=100, seconds=0.1)
        return []

    def fake_load_cfg(config_path, sgbd_path):
        return {"postgres": {"schema": "public"}}

    def fake_generate(out_dir, rows, seed, mode):
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        return {}

    labeled = brun.run_matrix(
        sizes=[1000], modes=["multi", "combined"], repetitions=2,
        sgbd_config_path="sgbd.json", config_dir="data/ecommerce",
        data_dir=tmp_path, seed=42, only=["postgres"],
        cleaners=cleaners, importer=fake_importer, load_cfg=fake_load_cfg,
        generate=fake_generate,
    )

    # 1 size x 2 modes x 2 reps = 4 labeled runs, each with 1 record
    assert len(labeled) == 4
    assert {(r["size"], r["mode"], r["repetition"]) for r in labeled} == {
        (1000, "multi", 0), (1000, "multi", 1),
        (1000, "combined", 0), (1000, "combined", 1),
    }
    # every import is immediately preceded by a clean
    imp_idx = [i for i, e in enumerate(events) if e[0] == "import"]
    for i in imp_idx:
        assert events[i - 1] == ("clean", "postgres")
    # median aggregation consumes the labeled output
    results = median_results(labeled)
    assert results[0]["rows"] == 100


def test_run_matrix_builds_mode_overrides(tmp_path):
    seen = []

    def fake_importer(config_path, *, sgbd_config_path, collector, show_data,
                      only, create_schema, source_overrides):
        seen.append((Path(config_path).name, set(source_overrides)))
        return []

    brun.run_matrix(
        sizes=[10], modes=["multi", "combined"], repetitions=1,
        sgbd_config_path=None, config_dir="data/ecommerce", data_dir=tmp_path,
        seed=1, only=["postgres"], cleaners={},
        importer=fake_importer, load_cfg=lambda c, s: {"postgres": {}},
        generate=lambda out_dir, rows, seed, mode: None,
    )
    by_name = dict(seen)
    assert by_name["import_config.json"] == {
        "stock", "purchase", "select_product", "add_to_cart"}
    assert by_name["import_config_combined.json"] == {"ecommerce"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_benchmark_runner.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `src/polyglotimportcsv/benchmark_runner.py`**

```python
"""Benchmark matrix orchestration — dependency-injected so src never imports scripts.

The script layer wires the real ``CLEANERS`` (from scripts/inspect_persisted_data.py),
``run_import``, and ``load_config``; tests inject stubs and run without databases.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from polyglotimportcsv import benchmark_data
from polyglotimportcsv.metrics import MetricsCollector

_ALL_BACKENDS = ("postgres", "mongodb", "cassandra", "redis", "neo4j")

# mode -> (import config filename, combined source name or None)
_MODE_CONFIG = {
    "multi": ("import_config.json", None),
    "combined": ("import_config_combined.json", "ecommerce"),
}


def _ensure_dataset(data_dir: Path, size: int, seed: int, mode: str, generate) -> Path:
    """Generate the dataset for ``size`` under ``data_dir/<size>/`` if files are missing."""
    dpath = data_dir / str(size)
    if mode == "combined":
        needed = [benchmark_data.JOIN_FILE]
        gen_mode = "combined"
    else:
        needed = list(benchmark_data.SOURCE_FILES.values())
        gen_mode = "multi"
    if not all((dpath / fname).is_file() for fname in needed):
        generate(dpath, rows=size, seed=seed, mode=gen_mode)
    return dpath


def _overrides(mode: str, dpath: Path) -> Dict[str, str]:
    if mode == "combined":
        return {"ecommerce": str(dpath / benchmark_data.JOIN_FILE)}
    return {src: str(dpath / fname) for src, fname in benchmark_data.SOURCE_FILES.items()}


def run_matrix(
    *,
    sizes: Iterable[int],
    modes: Iterable[str],
    repetitions: int,
    sgbd_config_path: "Optional[str | Path]",
    config_dir: "str | Path",
    data_dir: "str | Path",
    seed: int,
    only: Optional[Iterable[str]],
    cleaners: Dict[str, Callable[[dict], None]],
    importer: Callable[..., List[str]],
    load_cfg: Callable[..., Dict[str, object]],
    generate: Callable[..., object] = benchmark_data.generate_dataset,
) -> List[Dict[str, object]]:
    """Run sizes x modes x repetitions, cleaning before each import. Returns labeled runs."""
    config_dir = Path(config_dir)
    data_dir = Path(data_dir)
    requested = list(only) if only else None
    labeled: List[Dict[str, object]] = []

    for size in sizes:
        for mode in modes:
            cfg_name, _ = _MODE_CONFIG[mode]
            config_path = config_dir / cfg_name
            dpath = _ensure_dataset(data_dir, size, seed, mode, generate)
            overrides = _overrides(mode, dpath)
            merged = load_cfg(config_path, sgbd_config_path)
            selected = requested or [b for b in _ALL_BACKENDS if b in merged]
            for rep in range(repetitions):
                for backend in selected:
                    block = merged.get(backend)
                    if block is not None and backend in cleaners:
                        cleaners[backend](block)
                collector = MetricsCollector()
                importer(
                    config_path,
                    sgbd_config_path=sgbd_config_path,
                    collector=collector,
                    show_data=False,
                    only=selected,
                    create_schema=True,
                    source_overrides=overrides,
                )
                labeled.append({
                    "size": size, "mode": mode, "repetition": rep,
                    "records": collector.to_records(),
                })
    return labeled
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_benchmark_runner.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Create `scripts/run_benchmarks.py`**

```python
#!/usr/bin/env python3
"""CLI: run the import benchmark matrix over live databases (spec §3).

Prerequisite: the databases must already be up (e.g. `docker compose up --wait`
or via run_example.sh). This script cleans each backend before every import so
each measurement is a cold load.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence

# scripts/ is on sys.path[0] when run as `python scripts/run_benchmarks.py`.
from inspect_persisted_data import CLEANERS

from polyglotimportcsv.benchmark_results import median_results, write_consolidated
from polyglotimportcsv.benchmark_runner import run_matrix
from polyglotimportcsv.config_parser import load_config
from polyglotimportcsv.metrics import environment_metadata
from polyglotimportcsv.runner import run_import

_ALL_BACKENDS = ("postgres", "mongodb", "cassandra", "redis", "neo4j")


def _parse_int_list(raw: str) -> List[int]:
    return [int(x) for x in raw.split(",") if x.strip()]


def _parse_str_list(raw: str) -> List[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the import benchmark matrix.")
    parser.add_argument("--sizes", default="1000,10000,100000",
                        help="Comma-separated N (products) sizes (default: 1000,10000,100000).")
    parser.add_argument("--modes", default="multi,combined",
                        help="Comma-separated input modes (default: multi,combined).")
    parser.add_argument("--repetitions", type=int, default=3,
                        help="Runs per (size, mode); the median is reported (default: 3).")
    parser.add_argument("--only", default="",
                        help=f"Comma-separated backends (default: all). Choices: {', '.join(_ALL_BACKENDS)}.")
    parser.add_argument("--seed", type=int, default=42, help="Generator seed (default: 42).")
    parser.add_argument("--sgbd-config", type=Path, default=Path("data/ecommerce/sgbd_config.json"))
    parser.add_argument("--config-dir", type=Path, default=Path("data/ecommerce"),
                        help="Directory holding import_config.json / import_config_combined.json.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/benchmark/generated"),
                        help="Where generated size datasets live (default: data/benchmark/generated).")
    parser.add_argument("--out", type=Path, default=Path("benchmarks"),
                        help="Output directory for consolidated results (default: benchmarks).")
    args = parser.parse_args(argv)

    sizes = _parse_int_list(args.sizes)
    modes = _parse_str_list(args.modes)
    only = _parse_str_list(args.only) or None

    labeled = run_matrix(
        sizes=sizes, modes=modes, repetitions=args.repetitions,
        sgbd_config_path=args.sgbd_config, config_dir=args.config_dir,
        data_dir=args.data_dir, seed=args.seed, only=only,
        cleaners=CLEANERS, importer=run_import, load_cfg=load_config,
    )
    results = median_results(labeled)
    meta = environment_metadata(args.config_dir, {})
    meta.update({"seed": args.seed, "sizes": sizes, "modes": modes,
                 "repetitions": args.repetitions})
    json_path, csv_path = write_consolidated(results, meta, out_dir=args.out)
    print(f"benchmark JSON: {json_path}")
    print(f"benchmark CSV:  {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Syntax-check the script (no DB touched)**

Run: `./.venv/Scripts/python.exe -c "import ast; ast.parse(open('scripts/run_benchmarks.py', encoding='utf-8').read())"`
Expected: no output (parses cleanly).

- [ ] **Step 7: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: green (~149 passed, 1 skipped).

- [ ] **Step 8: Commit**

```bash
git add src/polyglotimportcsv/benchmark_runner.py scripts/run_benchmarks.py tests/test_benchmark_runner.py
git commit -m "feat: benchmark matrix runner (DI core + live-DB CLI)"
```

---

### Task 7: Documentation (README EN+PT) + final verification

**Files:**
- Modify: `README.md`
- Test: full suite (no new test file)

**Interfaces:**
- Consumes: everything above.
- Produces: a "Benchmarks" section in both language blocks of `README.md`.

- [ ] **Step 1: Locate the insertion point**

Run: `./.venv/Scripts/python.exe -c "import re,io; t=open('README.md',encoding='utf-8').read(); print([i for i,l in enumerate(t.splitlines()) if l.startswith('## ')][:40])"`
Expected: prints the line indices of `## ` headings — use them to find the end of the English usage section and the end of the Portuguese one. Read the surrounding lines with the Read tool before editing.

- [ ] **Step 2: Add the English "Benchmarks" section**

After the English flags list / usage section (before the Portuguese block begins), insert:

```markdown
## Benchmarks

Generate a deterministic synthetic e-commerce dataset (N = number of products;
sources scale N / 3N / 2N / 2N; the same `--seed` reproduces byte-identical files):

    python scripts/generate_benchmark_data.py --rows 100000 --seed 42 \
      --out data/benchmark/generated/100000 --mode both

A small 1 000-row reference dataset is committed under `data/benchmark/` (both
input modes) for quick tests and CI.

Run the benchmark matrix (sizes × modes × repetitions) over **live** databases —
bring them up first (`docker compose up --wait` or `./run_example.sh`). Each
import is preceded by a clean, so every measurement is a cold load:

    python scripts/run_benchmarks.py --sizes 1000,10000,100000 \
      --modes multi,combined --repetitions 3

Results land in `benchmarks/`: a `benchmark_run_<timestamp>.json` plus an
append-only `benchmark_results.csv` (`size,mode,backend,entity,phase,rows,
median_seconds,rows_per_second`) for the report graphs.
```

- [ ] **Step 3: Add the Portuguese "Benchmarks" section**

After the Portuguese usage section, insert:

```markdown
## Benchmarks

Gere um dataset e-commerce sintético determinístico (N = número de produtos; as
fontes escalam N / 3N / 2N / 2N; a mesma `--seed` reproduz arquivos byte-idênticos):

    python scripts/generate_benchmark_data.py --rows 100000 --seed 42 \
      --out data/benchmark/generated/100000 --mode both

Um dataset de referência pequeno (1 000 linhas) está versionado em
`data/benchmark/` (ambos os modos) para testes rápidos e CI.

Rode a matriz de benchmark (tamanhos × modos × repetições) sobre bancos **vivos** —
suba-os antes (`docker compose up --wait` ou `./run_example.sh`). Cada importação é
precedida de uma limpeza, então cada medição é uma carga a frio:

    python scripts/run_benchmarks.py --sizes 1000,10000,100000 \
      --modes multi,combined --repetitions 3

Os resultados vão para `benchmarks/`: um `benchmark_run_<timestamp>.json` e um
`benchmark_results.csv` append-only (`size,mode,backend,entity,phase,rows,
median_seconds,rows_per_second`) para os gráficos do relatório.
```

- [ ] **Step 4: Final full-suite verification**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: green (~149 passed, 1 skipped).

- [ ] **Step 5: End-to-end generator smoke (real files, no DB)**

Run: `./.venv/Scripts/python.exe scripts/generate_benchmark_data.py --rows 1000 --seed 42 --out "$TEMP/bench_smoke" --mode both && ./.venv/Scripts/python.exe -c "import pathlib; d=pathlib.Path('$TEMP/bench_smoke'); print(sorted(p.name for p in d.glob('*.csv')))"`
Expected: prints the five CSV filenames; exit 0. (This writes to a temp dir, not the repo.)

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: benchmark generator + runner usage (README EN/PT)"
```

---

## Self-Review

**1. Spec coverage:**
- §2.1 schema fidelity → Task 1 column constants + Task 2/3 header-equality tests against `data/ecommerce/`.
- §2.2 cardinalities & pools → Task 1 (`num_users`/`num_categories`, iterator ratios) + tests.
- §2.3 referential integrity → Task 1 FK-from-pool derivation + `test_referential_integrity`; Task 2 cross-file FK test.
- §2.4 determinism → `lineterminator="\n"`, string-seeded per-id RNGs; byte-identical tests in Tasks 2, 3.
- §2.5 generator CLI → Task 4.
- §3.1–3.3 runner (Python-pure, reuses run_import + CLEANERS via injection, clean-before-import, median) → Task 6 (`run_matrix`) + Task 5 (median).
- §3.4 consolidated JSON+CSV → Task 5.
- §4 versioned reference dataset (N=125, 1k rows, both modes) + gitignore generated/ → Task 4.
- §5 tests (determinism, integrity, cardinalities, headers, mode-equivalence, median, generator smoke) → Tasks 1–6; mode-equivalence + dry-run smoke via committed dataset → Task 4 (`test_benchmark_example.py`).
- §6 docs (README EN+PT, data/benchmark README) → Tasks 4, 7.
- §7 out of scope (docker lifecycle, CI benchmarks, GUI) → respected: runner assumes DBs up; no CI benchmark job added.

**2. Placeholder scan:** every code step carries complete code; no TBD/TODO; the one README insertion (Task 7) shows the exact markdown and a step to locate the anchor with the Read tool first.

**3. Type consistency:** `generate_dataset(out_dir, rows, seed=42, mode="both") -> Dict[str, Path]` is defined in Task 2 and only extended (not re-signed) in Task 3; `iter_source_rows(seed, rows)` is stable across Tasks 1–3; `run_matrix(...)` keyword names match between `benchmark_runner.py` (Task 6 def), its test, and `scripts/run_benchmarks.py` (Task 6 caller); `median_results` / `write_consolidated` signatures match between Task 5 def, its tests, and the Task 6 script; the injected `importer` is called with exactly the keyword set `run_import` accepts (`sgbd_config_path`, `collector`, `show_data`, `only`, `create_schema`, `source_overrides`). Labeled-run dict shape (`size`/`mode`/`repetition`/`records`) is identical in Task 5 tests and Task 6 output.
