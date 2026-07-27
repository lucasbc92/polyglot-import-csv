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

    if mode in ("combined", "both"):
        path = out / JOIN_FILE
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, lineterminator="\n")
            writer.writerow(JOIN_COLUMNS)
            for src, row in iter_source_rows(seed, rows):
                writer.writerow([src] + [row.get(c, "") for c in JOIN_COLUMNS[1:]])
        written["combined"] = path

    return written
