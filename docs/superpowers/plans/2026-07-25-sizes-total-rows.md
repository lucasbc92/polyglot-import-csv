# `--sizes` = Total Rows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the benchmark `--sizes` parameter mean **total rows across all sources** (not product count), splitting the total ~1:3:2:2 among the four sources with seeded ±10% jitter that sums to exactly the requested total.

**Architecture:** A new `_split_rows(total_rows, seed)` helper resolves per-source counts; `iter_source_rows`/`generate_dataset` consume it (the `rows` parameter now means total rows). `stock` still defines the product key space (`n_stock` unique product ids); the other sources reference ids in `[1, n_stock]`. The benchmark scripts and the committed reference dataset/docs follow the new semantics.

**Tech Stack:** Python 3.12, stdlib `random`/`csv`, pytest.

## Global Constraints

- No new third-party dependencies.
- **Determinism preserved:** the same `(seed, total_rows)` yields byte-identical files (the jitter derives from the seed); different seeds yield different splits.
- Base ratio is **stock:purchase:select_product:add_to_cart = 1:3:2:2**; jitter is **±10%** on the weights; the per-source counts sum to **exactly** `total_rows`.
- `stock` count (`n_stock`) is the product key space and must be ≥ 1; `purchase`/`select_product`/`add_to_cart` reference product ids in `[1, n_stock]`.
- Code/identifiers/comments in English; specs/plans in Portuguese.
- Commit after each task; push after each commit (current policy).
- Test command: `./.venv/Scripts/python.exe -m pytest tests -q` (baseline before this plan: 174 passed, 1 skipped).

---

## File Structure

**Modified:**
- `src/polyglotimportcsv/benchmark_data.py` — add `_split_rows`; `iter_source_rows`/`generate_dataset` use total-rows semantics; internal pool sizing keys on `n_stock`.
- `scripts/run_benchmarks.py` — `--sizes` help/defaults = total rows.
- `scripts/run_benchmarks_100k.py` — `--size` help = total rows; estimate rebased to a total-rows reference.
- `tests/test_benchmark_data.py` — rewrite count/cardinality assertions to the split; keep determinism/FK/header tests.
- `README.md` (EN + PT) — Benchmarks section: `--sizes` = total rows; regenerated reference dataset command.
- `data/benchmark/README.md` — generation command note.

**Regenerated (committed data):**
- `data/benchmark/ecommerce_*.csv` + `ecommerce_join.csv` — via the new generator at `--sizes 1000`.

---

## Task 1: `_split_rows` helper

**Files:**
- Modify: `src/polyglotimportcsv/benchmark_data.py`
- Test: `tests/test_benchmark_data.py`

**Interfaces:**
- Produces: `_split_rows(total_rows: int, seed: int) -> Dict[str, int]` with keys `"stock"`, `"purchase"`, `"select_product"`, `"add_to_cart"`; values sum to exactly `total_rows`; each ≥ 1; deterministic in `(seed, total_rows)`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_benchmark_data.py`:

```python
def test_split_rows_sums_exactly_and_respects_ratio():
    split = bd._split_rows(80_000, seed=42)
    assert set(split) == {"stock", "purchase", "select_product", "add_to_cart"}
    assert sum(split.values()) == 80_000                 # exact total
    assert all(v >= 1 for v in split.values())
    # within +/-15% of the exact 1:3:2:2 share (10% jitter + rounding slack)
    for src, ratio in (("stock", 1), ("purchase", 3),
                       ("select_product", 2), ("add_to_cart", 2)):
        exact = 80_000 * ratio / 8
        assert abs(split[src] - exact) <= 0.15 * exact, src


def test_split_rows_deterministic_and_seed_sensitive():
    assert bd._split_rows(80_000, 42) == bd._split_rows(80_000, 42)
    assert bd._split_rows(80_000, 1) != bd._split_rows(80_000, 2)
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_benchmark_data.py::test_split_rows_sums_exactly_and_respects_ratio -v`
Expected: FAIL — `module 'polyglotimportcsv.benchmark_data' has no attribute '_split_rows'`.

- [ ] **Step 3: Implement**

In `benchmark_data.py`, near the top (after the constants), add:

```python
_BASE_RATIO: Dict[str, int] = {
    "stock": 1, "purchase": 3, "select_product": 2, "add_to_cart": 2,
}
_SPLIT_ORDER: Tuple[str, ...] = ("stock", "purchase", "select_product", "add_to_cart")


def _split_rows(total_rows: int, seed: int) -> Dict[str, int]:
    """Split ``total_rows`` across the four sources ~1:3:2:2 with seeded +/-10%
    jitter, summing to exactly ``total_rows``. ``stock`` (the product key space)
    is at least 1. Deterministic in ``(seed, total_rows)``."""
    if total_rows < len(_SPLIT_ORDER):
        raise ValueError(f"total_rows must be >= {len(_SPLIT_ORDER)}")
    rng = random.Random(f"{seed}:split")
    weights = {k: _BASE_RATIO[k] * (1.0 + rng.uniform(-0.10, 0.10)) for k in _SPLIT_ORDER}
    wsum = sum(weights.values())
    counts = {k: max(1, round(total_rows * weights[k] / wsum)) for k in _SPLIT_ORDER}
    # Reconcile rounding drift onto the largest source (purchase) so the counts
    # sum to exactly total_rows.
    counts["purchase"] += total_rows - sum(counts.values())
    if counts["purchase"] < 1:
        raise ValueError(f"total_rows={total_rows} too small for a valid 1:3:2:2 split")
    return counts
```

- [ ] **Step 4: Run to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_benchmark_data.py -k split_rows -v`
Expected: PASS (both new tests).

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/benchmark_data.py tests/test_benchmark_data.py
git commit -m "feat(benchmark-data): _split_rows total->per-source with seeded jitter"
```

---

## Task 2: Generator uses total-rows semantics

**Files:**
- Modify: `src/polyglotimportcsv/benchmark_data.py:129-185` (`iter_source_rows`)
- Test: `tests/test_benchmark_data.py`

**Interfaces:**
- Consumes: `_split_rows` (Task 1).
- Produces: `iter_source_rows(seed, rows)` where `rows` is now the **total** row count; emits `_split_rows(rows, seed)["stock"]` stock rows (product ids `1..n_stock`), then that many purchase/select/cart rows, all FKs in `[1, n_stock]`. `generate_dataset(out_dir, rows, seed, mode)` unchanged signature (its `rows` is now total).

- [ ] **Step 1: Rewrite the existing count/cardinality tests to the split**

In `tests/test_benchmark_data.py`, REPLACE these tests with the versions below (they now tie generation to `_split_rows`):

```python
def test_cardinalities_follow_split():
    split = bd._split_rows(80_000, 42)
    counts = Counter(src for src, _ in _rows(42, 80_000))
    assert dict(counts) == split


def test_referential_integrity():
    seed, total = 42, 8_000
    split = bd._split_rows(total, seed)
    n_stock = split["stock"]
    rows = _rows(seed, total)
    stock_pids = {r["product_id"] for src, r in rows if src == "stock"}
    assert stock_pids == set(range(1, n_stock + 1))
    user_pool = {bd._user(seed, i)["user_id"] for i in range(bd.num_users(n_stock))}
    ncat = bd.num_categories(n_stock)
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
    n_stock = bd._split_rows(8_000, 42)["stock"]
    pids = [r["product_id"] for src, r in _rows(42, 8_000) if src == "stock"]
    assert pids == list(range(1, n_stock + 1))


def test_multi_row_counts(tmp_path):
    total = 8_000
    split = bd._split_rows(total, 42)
    bd.generate_dataset(tmp_path, rows=total, seed=42, mode="multi")

    def n(fname):
        with open(tmp_path / fname, encoding="utf-8") as fh:
            return sum(1 for _ in fh) - 1  # minus header

    assert n("ecommerce_stock.csv") == split["stock"]
    assert n("ecommerce_purchase.csv") == split["purchase"]
    assert n("ecommerce_select_product.csv") == split["select_product"]
    assert n("ecommerce_add_to_cart.csv") == split["add_to_cart"]


def test_combined_action_counts(tmp_path):
    total = 8_000
    split = bd._split_rows(total, 42)
    bd.generate_dataset(tmp_path, rows=total, seed=42, mode="combined")
    with open(tmp_path / bd.JOIN_FILE, newline="", encoding="utf-8") as fh:
        actions = Counter(row["action"] for row in _csv.DictReader(fh))
    assert dict(actions) == split
```

Leave `test_pool_sizes`, `test_deterministic_same_seed`, `test_different_seed_differs`, `test_multi_writes_four_files_with_real_headers`, `test_multi_byte_identical_for_same_seed`, `test_multi_foreign_keys_resolve_across_files`, `test_combined_header_matches_real_join`, `test_both_writes_five_files`, `test_combined_equals_multi_data`, `test_combined_byte_identical_for_same_seed` unchanged (still valid; the byte-identical/FK ones just use `rows` as a total now).

Delete the old `test_cardinalities_follow_ratios` (replaced by `test_cardinalities_follow_split`).

- [ ] **Step 2: Run to verify the rewritten tests fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_benchmark_data.py -k "cardinalities_follow_split or referential_integrity or stock_product_id or multi_row_counts or combined_action_counts" -v`
Expected: FAIL — `iter_source_rows` still treats `rows` as products (e.g. `test_multi_row_counts` expects the split but gets `rows`/3·`rows`/… ).

- [ ] **Step 3: Implement**

In `benchmark_data.py`, replace the body of `iter_source_rows` (currently keyed on `n = rows` products) with a split-driven version:

```python
def iter_source_rows(seed: int, rows: int) -> Iterator[Tuple[str, Dict[str, object]]]:
    """Yield ``(source_name, row_dict)`` in fixed order for a given ``(seed, rows)``.

    ``rows`` is the TOTAL row count across the four sources; the per-source split
    (~1:3:2:2 with seeded jitter) comes from ``_split_rows``. Order: all stock
    rows, then purchase, then select_product, then add_to_cart. ``stock`` defines
    the product key space; every foreign key references product ids in
    ``[1, n_stock]`` and users from the generated pool.
    """
    split = _split_rows(rows, seed)
    n_stock = split["stock"]
    nu = num_users(n_stock)
    nc = num_categories(n_stock)
    master = random.Random(f"{seed}:stream")

    for pid in range(1, n_stock + 1):
        usr = _user(seed, master.randrange(nu))
        prod = _product(seed, pid, nc)
        ts = _ts(master)
        yield "stock", {"timestamp": ts, **usr, **prod, "last_restock_date": ts}

    for i in range(1, split["purchase"] + 1):
        usr = _user(seed, master.randrange(nu))
        other = _user(seed, master.randrange(nu))
        prod = _product(seed, master.randint(1, n_stock), nc)
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

    for _ in range(split["select_product"]):
        usr = _user(seed, master.randrange(nu))
        yield "select_product", {
            "timestamp": _ts(master), **usr,
            "selected_product_id": master.randint(1, n_stock),
            "suggested_product_count": master.randint(1, 5),
        }

    for _ in range(split["add_to_cart"]):
        usr = _user(seed, master.randrange(nu))
        yield "add_to_cart", {
            "timestamp": _ts(master), **usr,
            "shopping_cart_id": f"user:{usr['user_id']}:cart",
            "cart_product_id": master.randint(1, n_stock),
            "cart_quantity": master.randint(1, 5),
        }
```

Update the module docstring line about `(seed, rows)` to note `rows` is the total row count.

- [ ] **Step 4: Run the generator tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_benchmark_data.py -v`
Expected: PASS (all — rewritten count tests plus the unchanged determinism/FK/header tests).

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/benchmark_data.py tests/test_benchmark_data.py
git commit -m "feat(benchmark-data): iter_source_rows uses total-rows split semantics"
```

---

## Task 3: Benchmark scripts speak total rows

**Files:**
- Modify: `scripts/run_benchmarks.py:59-60` (`--sizes` arg)
- Modify: `scripts/run_benchmarks_100k.py` (`--size` arg, estimate rebase)
- Modify: `scripts/generate_benchmark_data.py` (`--rows` help)
- Test: `tests/test_run_benchmarks_100k.py` (create)

**Interfaces:**
- Consumes: total-rows generator (Task 2).
- Produces: `--sizes` help/default in total rows; `run_benchmarks_100k.estimate_seconds` scaled from an 8000-total-row reference.

- [ ] **Step 1: Write the failing test**

Create `tests/test_run_benchmarks_100k.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_benchmarks_100k as r100  # noqa: E402


def test_estimate_scales_with_total_rows():
    # Reference point is 8000 total rows; 80000 rows must be ~10x the effort.
    est_8k = r100.estimate_seconds(["postgres"], size=8_000, runs=1)["postgres"]
    est_80k = r100.estimate_seconds(["postgres"], size=80_000, runs=1)["postgres"]
    assert abs(est_80k / est_8k - 10.0) < 0.01


def test_reference_total_rows_is_8000():
    assert r100._REFERENCE_TOTAL_ROWS == 8_000
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_run_benchmarks_100k.py -v`
Expected: FAIL — `_REFERENCE_TOTAL_ROWS` does not exist and `estimate_seconds` still scales by `size/1000`.

- [ ] **Step 3: Implement**

In `scripts/run_benchmarks.py`, change the `--sizes` argument help:

```python
    parser.add_argument("--sizes", default="10000,100000",
                        help="Comma-separated TOTAL row counts across all sources "
                             "(default: 10000,100000). Split ~1:3:2:2 per source.")
```

In `scripts/run_benchmarks_100k.py`:
- Add a module constant `_REFERENCE_TOTAL_ROWS = 8000` next to `ROWS_AT_1K`, and update `ROWS_AT_1K`'s comment to say the rows are measured at **8000 total rows** (= the old 1000-product point).
- In `estimate_seconds`, change `scale = size / 1000.0` to `scale = size / _REFERENCE_TOTAL_ROWS`.
- Change the `--size` argument help to `"Total dataset size in rows (default: 100000)."` (keep default `100000`).
- Update the module docstring examples to describe sizes as total rows.

In `scripts/generate_benchmark_data.py`, change the `--rows` argument help from
"Number of products (N)." to `"Total number of rows across all sources (split ~1:3:2:2)."`.

- [ ] **Step 4: Run the test + a smoke estimate**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_run_benchmarks_100k.py -v`
Expected: PASS.
Run: `./.venv/Scripts/python.exe scripts/run_benchmarks_100k.py --estimate-only --only postgres,mongodb --size 100000`
Expected: prints an estimate; exits 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_benchmarks.py scripts/run_benchmarks_100k.py scripts/generate_benchmark_data.py tests/test_run_benchmarks_100k.py
git commit -m "feat(benchmarks): --sizes/--size are total rows; estimate rebased to 8000"
```

---

## Task 4: Regenerate committed reference dataset + docs

**Files:**
- Regenerate: `data/benchmark/ecommerce_stock.csv`, `ecommerce_purchase.csv`, `ecommerce_select_product.csv`, `ecommerce_add_to_cart.csv`, `ecommerce_join.csv`
- Modify: `data/benchmark/README.md`
- Modify: `README.md` (EN + PT Benchmarks sections)

**Interfaces:** none new. (No test file — verification is the byte-count check in Step 2.)

- [ ] **Step 1: Regenerate the reference dataset at 1000 total rows**

Run:
```bash
./.venv/Scripts/python.exe scripts/generate_benchmark_data.py --rows 1000 --seed 42 \
  --out data/benchmark --mode both
```
(`generate_benchmark_data.py`'s `--rows` now means total rows; 1000 keeps the reference at ~1000 rows, matching the README label.)

- [ ] **Step 2: Verify the new split**

Run:
```bash
./.venv/Scripts/python.exe -c "from polyglotimportcsv import benchmark_data as b; print(b._split_rows(1000,42))"
```
Then confirm each `data/benchmark/ecommerce_*.csv` has (rows − header) equal to the printed split, and `ecommerce_join.csv` has 1000 data rows. Expected: the four source files sum to 1000; join = 1000.

- [ ] **Step 3: Update the docs**

In `data/benchmark/README.md`, update any generation command to `--rows 1000` and note the number is **total rows** (split ~1:3:2:2 across the four sources).

In `README.md`, in BOTH Benchmarks sections (EN + PT), update:
- The generator example: `--rows 100000` now means **100000 total rows** (state it).
- Add one line: `--sizes` / `--rows` is the **total row count** across sources (split ~1:3:2:2 with slight seeded jitter), not the product count. EN wording e.g.: "`--sizes`/`--rows` is the total number of rows across all sources (split ~1:3:2:2 with slight seeded jitter)." PT equivalent.

- [ ] **Step 4: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: PASS (174 + new split tests; 0 failures).

- [ ] **Step 5: Commit**

```bash
git add data/benchmark/ README.md
git commit -m "docs(benchmarks): regenerate 1000-row reference; document --sizes as total rows"
```

---
```

## Self-Review

**Spec coverage (§12):** `--sizes`=total rows → Tasks 1-3; jitter ±10% summing to T → Task 1; stock=key space, FKs in [1,n_stock] → Task 2; scripts help/defaults → Task 3; estimate reindex → Task 3; reference dataset regen + `size`-means-rows docs → Task 4. Covered.

**Placeholders:** none — all steps carry real code/commands.

**Type consistency:** `_split_rows` keys/returns match across Tasks 1-2; `_REFERENCE_TOTAL_ROWS` defined and used in Task 3; `rows` param semantics consistent (total) across generator and callers.

