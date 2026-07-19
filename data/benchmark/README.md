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
