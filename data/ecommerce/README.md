# E-commerce example data

| File | Purpose |
|------|---------|
| `ecommerce_join.csv` | Wide operational CSV (all `action` types in one file). Default input for `./run_example.sh`. |
| `ecommerce_stock.csv`, `ecommerce_purchase.csv`, `ecommerce_select_product.csv`, `ecommerce_add_to_cart.csv` | `ecommerce_join.csv` split by the `action` column, one file per entity. Not consumed by the current importer; kept as a data basis for a possible future one-CSV-per-entity import mode (no `action`/`filters` discriminator needed). |
| `import_config.json` | JSON Schema–validated mapping to PostgreSQL, MongoDB, Cassandra, Redis, and Neo4j. Used by the CLI and `run_example.sh`. |

## Why the `action` column exists

Knowing the **source (entity) of every row** is an essential requirement of the import
process. In the combined `ecommerce_join.csv`, that role is played by the `action`
discriminator column: it is the only thing that tells the importer which entity each
row belongs to, and it is what the `filters` in `import_config.json` match against
(`action == stock`, `action == purchase`, …). Without such a column (`action`,
`table`, `collection`, or similar), a combined CSV cannot be partitioned into entities
at all.

The per-entity CSVs above illustrate the alternative that removes this requirement:
when each file holds exactly one entity, the file itself designates the data's origin,
so no discriminator column and no `filters` are needed. This one-CSV-per-entity mode
is planned as future work (TCC II).

For a larger stress test, add another CSV (e.g. `ecommerce_join_large.csv`) and pass:

```bash
./run_example.sh --csv data/ecommerce/ecommerce_join_large.csv
```

The config must reference columns present in that CSV.
