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
