"""Deterministic synthetic dataset generator (spec §2)."""

import csv as _csv
from collections import Counter
from pathlib import Path

from polyglotimportcsv import benchmark_data as bd

REAL = Path(__file__).resolve().parents[1] / "data" / "ecommerce"


def _rows(seed, rows):
    return list(bd.iter_source_rows(seed, rows))


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


def test_cardinalities_follow_split():
    split = bd._split_rows(80_000, 42)
    counts = Counter(src for src, _ in _rows(42, 80_000))
    assert dict(counts) == split


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
