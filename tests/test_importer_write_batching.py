"""Write-path batching per backend, exercised with injected fake clients.

These are the first tests to run the importer write loop at all — the rest of
the suite is dry-run. Each fake records how the driver was called so we can
assert batched vs row-at-a-time behavior without a live database.
"""

import pandas as pd

from polyglotimportcsv.mapping_resolver import BoundEntity


def _be(name, cfg, data):
    df = pd.DataFrame(data)
    kinds = {c: "string" for c in df.columns}
    return BoundEntity(name=name, cfg=cfg, df=df, kinds=kinds)


# ---------- Redis ----------

class _FakePipeline:
    def __init__(self, parent):
        self.parent = parent
        self.queued = 0

    def set(self, k, v):
        self.queued += 1
        return self

    def execute(self):
        self.parent.pipeline_execs += 1
        self.parent.piped_sets += self.queued
        self.queued = 0
        return []


class _FakeRedis:
    def __init__(self):
        self.set_calls = 0
        self.pipeline_execs = 0
        self.piped_sets = 0

    def ping(self):
        return True

    def set(self, k, v):
        self.set_calls += 1

    def pipeline(self, transaction=False):
        return _FakePipeline(self)


def _redis_entity(n):
    return _be(
        "cart",
        {"columns": {"cart_id": {"is_key": True}, "qty": {}}},
        {"cart_id": [f"c{i}" for i in range(n)], "qty": [str(i) for i in range(n)]},
    )


def test_redis_optimized_uses_pipeline_no_per_row_set():
    from polyglotimportcsv.importers.redis_importer import run_redis_import
    fake = _FakeRedis()
    run_redis_import(
        {"entities": {}}, {"cart": _redis_entity(2500)},
        dry_run=False, create_schema=False, strategy="optimized",
        client_factory=lambda conn: fake,
    )
    assert fake.set_calls == 0
    assert fake.pipeline_execs == 3          # ceil(2500/1000)
    assert fake.piped_sets == 2500


def test_redis_naive_sets_one_per_row():
    from polyglotimportcsv.importers.redis_importer import run_redis_import
    fake = _FakeRedis()
    run_redis_import(
        {"entities": {}}, {"cart": _redis_entity(2500)},
        dry_run=False, create_schema=False, strategy="naive",
        client_factory=lambda conn: fake,
    )
    assert fake.set_calls == 2500
    assert fake.pipeline_execs == 0
