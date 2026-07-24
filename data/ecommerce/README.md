# E-commerce example data

| File | Purpose |
|------|---------|
| `ecommerce_stock.csv`, `ecommerce_purchase.csv`, `ecommerce_select_product.csv`, `ecommerce_add_to_cart.csv` | One CSV per entity (default input mode). Each file IS the origin of its rows — no discriminator column needed. |
| `ecommerce_join.csv` | Combined CSV (alternative input mode): column 0 (`action`) is the origin column; each distinct value becomes a source. |
| `import_config.json` | v2 mapping config (multi-CSV `sources`). Default for `./run_example.sh`. |
| `import_config_combined.json` | Same SGBD blocks, `sources` pointing at the combined CSV — demonstrates that switching input modes changes nothing in the per-SGBD mapping. |
| `sgbd_config.json` | Connection settings per SGBD. |

## Knowing each row's origin

Knowing the **source (entity) of every row** is an essential requirement of the
import process. In the per-entity files the file itself designates the origin.
In the combined `ecommerce_join.csv`, column 0 plays that role: the importer
slices the file by its distinct values and each value becomes a named source
(also exposed to mappings as the `_source` pseudo-column).

For a larger stress test, add another CSV (e.g. `ecommerce_stock_large.csv`) and
override just that source's path:

```bash
python -m polyglotimportcsv --config data/ecommerce/import_config.json \
  --source stock=data/ecommerce/ecommerce_stock_large.csv \
  --dry-run
```

The config must reference columns present in that CSV.
