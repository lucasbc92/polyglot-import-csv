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
