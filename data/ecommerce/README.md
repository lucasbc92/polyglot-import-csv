# E-commerce example data

| File | Purpose |
|------|---------|
| `ecommerce_join.csv` | Wide operational CSV (all `action` types in one file). Default input for `./run_example.sh`. |
| `import_config.json` | JSON Schema–validated mapping to PostgreSQL, MongoDB, Cassandra, Redis, and Neo4j. Used by the CLI and `run_example.sh`. |

For a larger stress test, add another CSV (e.g. `ecommerce_join_large.csv`) and pass:

```bash
./run_example.sh --csv data/ecommerce/ecommerce_join_large.csv
```

The config must reference columns present in that CSV.
