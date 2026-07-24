# Import Performance (naive vs optimized) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the three defects that made the first benchmark matrix measure the Python client loop instead of the databases (per-cell casting, row-at-a-time writes, inconsistent phase boundaries), while keeping the naive path selectable as a TCC2 experimental baseline.

**Architecture:** A single `strategy` string (`"naive"` | `"optimized"`, default `"optimized"`) threads from `run_import` through each importer and into `cast_frame`. Each row-at-a-time importer (redis, cassandra, neo4j) splits its write loop into `_write_naive` / `_write_batched`, selected by strategy, and gains an injectable client factory so the write path is testable without live databases. MongoDB's payload build moves inside its write timer. The benchmark runner gains a `strategies` axis; the consolidated CSV gains a `strategy` column with a header-mismatch guard.

**Tech Stack:** Python 3.12, pandas, pytest, psycopg2, pymongo, redis-py 8, cassandra-driver, neo4j 6, click.

## Global Constraints

- No new third-party dependencies. Batching uses APIs already present: `cassandra.concurrent.execute_concurrent_with_args`, `redis.Redis.pipeline`, `neo4j.Session.execute_write`.
- `strategy="naive"` must reproduce today's behavior verbatim — same casting, same per-row writes — so `benchmark.log` stays reproducible end to end.
- `strategy` default is `"optimized"` everywhere it appears.
- Casting contracts already pinned by `tests/test_casting.py` must keep holding: empty cell → `None`; integer → native `int` (never `float`); datetime → `datetime.datetime` (never `pandas.Timestamp`); string columns untouched including `""`.
- All new tests run without live databases (dry-run or injected fakes), consistent with the existing suite.
- Specs and plans are Portuguese; code, identifiers, and comments stay English to match the codebase.
- Commit after each task. Local commits only — do not push (user preference).
- Batch size constant: **1000** for redis/neo4j; cassandra concurrency **64**.
- Vectorized `pd.to_datetime` MUST pass `format="mixed"`. Without it pandas infers a single format from the first element and coerces all other formats to `NaT`, diverging from the per-cell path on real data (the e-commerce CSVs contain both `"...T..."` and `"... ..."` separators).

---

## File Structure

**Modified:**
- `src/polyglotimportcsv/casting.py` — vectorized `cast_frame` under `strategy`, per-cell path preserved.
- `src/polyglotimportcsv/mapping_resolver.py` — thread `strategy` into `cast_frame` calls.
- `src/polyglotimportcsv/runner.py` — accept `strategy`, pass to `resolve_backend_entities` and each importer.
- `src/polyglotimportcsv/importers/base.py` — Protocol gains `strategy` (keyword, default).
- `src/polyglotimportcsv/importers/redis_importer.py` — `_write_naive`/`_write_batched`, `client_factory`, hoist per-row lookups.
- `src/polyglotimportcsv/importers/cassandra_importer.py` — concurrent batched write, `session_factory`.
- `src/polyglotimportcsv/importers/neo4j_importer.py` — uniqueness constraint, UNWIND node/rel batches, `driver_factory`, pre-batch dedupe.
- `src/polyglotimportcsv/importers/mongodb_importer.py` — move payload build inside write timer.
- `src/polyglotimportcsv/benchmark_runner.py` — `strategies` axis.
- `src/polyglotimportcsv/benchmark_results.py` — `strategy` in key and `_RESULT_FIELDS`.
- `src/polyglotimportcsv/benchmark_io.py` — header-mismatch guard.
- `src/polyglotimportcsv/cli.py` — `--strategy` flag.
- `scripts/run_benchmarks.py` — `--strategies` flag.
- `scripts/run_benchmarks_100k.py` — conditional slow-warning; measured-rate note.

**Created:**
- `tests/test_casting_vectorized.py`
- `tests/test_importer_write_batching.py`
- `tests/test_phase_boundaries.py`

**Renamed (git mv):**
- `benchmarks/benchmark_results.csv` → `benchmarks/benchmark_results_naive_baseline.csv`

---

## Task 1: Vectorized `cast_frame` with strategy switch

**Files:**
- Modify: `src/polyglotimportcsv/casting.py`
- Test: `tests/test_casting_vectorized.py` (create), `tests/test_casting.py` (unchanged, acts as regression net)

**Interfaces:**
- Consumes: nothing new.
- Produces: `cast_frame(df, kinds, *, strategy="optimized")`. New keyword; existing positional calls keep working. Also `_cast_column_vectorized(series, kind) -> pd.Series` (module-private, object dtype, None for empties).

- [ ] **Step 1: Write the failing equivalence test**

Create `tests/test_casting_vectorized.py`:

```python
"""The optimized (vectorized) cast_frame must equal the naive (per-cell) one."""

import logging

import pandas as pd

from polyglotimportcsv.casting import cast_frame


def _frame():
    # One column per kind, plus an integer column with an unparseable value
    # that must survive as text (the fallback path), and empties everywhere.
    return pd.DataFrame(
        {
            "i": ["1", "", "3", "10000"],
            "f": ["1.5", "", "3.0", "2"],
            "b": ["true", "FALSE", "", "true"],
            # Deliberately mixes "space" and "T" separators: without
            # format="mixed" the vectorized path silently NaTs the second form.
            "d": ["2023-11-02 03:30:00Z", "", "2024-01-01T00:00:00Z", "notadate"],
            "s": ["a", "", "c", "d"],
            "bad": ["1", "", "notanumber", "4"],
        }
    )


_KINDS = {"i": "integer", "f": "float", "b": "boolean",
          "d": "datetime", "s": "string", "bad": "integer"}


def test_optimized_equals_naive_cell_by_cell():
    df = _frame()
    naive = cast_frame(df, _KINDS, strategy="naive")
    opt = cast_frame(df, _KINDS, strategy="optimized")
    assert list(naive.columns) == list(opt.columns)
    for col in naive.columns:
        n, o = list(naive[col]), list(opt[col])
        assert n == o, f"column {col!r}: naive={n} optimized={o}"
        for a, b in zip(n, o):
            assert type(a) is type(b), f"{col!r}: {type(a)} vs {type(b)}"


def test_optimized_preserves_unparseable_as_text_and_warns(caplog):
    df = _frame()
    with caplog.at_level(logging.WARNING):
        opt = cast_frame(df, _KINDS, strategy="optimized")
    # 'notanumber' stays as the original string, not None
    assert list(opt["bad"]) == [1, None, "notanumber", 4]
    assert any("could not be cast" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_casting_vectorized.py -v`
Expected: FAIL — `cast_frame()` got an unexpected keyword argument `strategy`.

- [ ] **Step 3: Implement the vectorized path**

In `src/polyglotimportcsv/casting.py`, replace the `cast_frame` function (lines 61-89) and add the helper. Keep `cast_value` and the existing per-cell loop as the naive branch:

```python
def _cast_column_vectorized(series: pd.Series, kind: str) -> "tuple[pd.Series, int]":
    """Vectorized cast of one column to native values; return (result, fallbacks).

    Empty cells ('' and None) become None in every kind (masked before the
    converter runs, so NaT/NaN/eq('true') never leak through). Values the
    converter can't parse are returned unchanged as their original text and
    counted as fallbacks, matching the per-cell contract.
    """
    empty = series.isna() | (series == "")
    original = series.astype(object)
    fallbacks = 0

    if kind == "boolean":
        parsed = series.astype(str).str.strip().str.lower().eq("true")
        out = parsed.astype(object).where(~empty, None)
        return pd.Series(list(out), index=series.index, dtype=object), 0

    if kind in ("integer", "float"):
        num = pd.to_numeric(series.where(~empty), errors="coerce")
        bad = num.isna() & ~empty
        fallbacks = int(bad.sum())
        if kind == "integer":
            vals = [
                None if e else (o if b else int(v))
                for e, b, v, o in zip(empty, bad, num, original)
            ]
        else:
            vals = [
                None if e else (o if b else float(v))
                for e, b, v, o in zip(empty, bad, num, original)
            ]
        return pd.Series(vals, index=series.index, dtype=object), fallbacks

    if kind == "datetime":
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            # format="mixed" is REQUIRED for equivalence with the per-cell path.
            # Without it pandas infers ONE format from the first element and
            # coerces every value in another format to NaT: a column holding
            # "2023-11-02 03:30:00Z" and "2024-01-01T00:00:00Z" (space vs T)
            # loses the second format entirely, while per-cell to_datetime
            # parses both. Verified against pandas in this environment.
            ts = pd.to_datetime(series.where(~empty), errors="coerce",
                                utc=True, format="mixed")
        bad = ts.isna() & ~empty
        fallbacks = int(bad.sum())
        py = ts.dt.to_pydatetime()
        vals = [
            None if e else (o if b else d)
            for e, b, d, o in zip(empty, bad, py, original)
        ]
        return pd.Series(vals, index=series.index, dtype=object), fallbacks

    return original, 0


def cast_frame(df: pd.DataFrame, kinds: Dict[str, str], *, strategy: str = "optimized") -> pd.DataFrame:
    """Return a copy with typed columns converted to native values.

    ``strategy='naive'`` casts cell by cell (the original path);
    ``strategy='optimized'`` casts per column with pandas. Both yield identical
    values and element types. Only integer/float/boolean/datetime columns are
    converted (empty cells become None); string columns keep raw values.
    """
    out = df.copy()
    for col in out.columns:
        kind = kinds.get(col, "string")
        if kind not in ("integer", "float", "boolean", "datetime"):
            continue
        if strategy == "optimized":
            result, fallbacks = _cast_column_vectorized(out[col], kind)
            out[col] = result
        else:
            values = [cast_value(v, kind) for v in out[col]]
            fallbacks = sum(
                1
                for orig, v in zip(out[col], values)
                if v is orig and orig is not None and orig != ""
            )
            out[col] = pd.Series(values, index=out.index, dtype=object)
        if fallbacks:
            logger.warning(
                "column %r: %d value(s) could not be cast to %s and stayed text",
                col, fallbacks, kind,
            )
        logger.debug("column %r cast to %s (%d value(s))", col, kind, len(out[col]))
    return out
```

- [ ] **Step 4: Run both casting test files**

Run: `python -m pytest tests/test_casting_vectorized.py tests/test_casting.py -v`
Expected: PASS (all). `test_casting.py` still calls `cast_frame(df, kinds)` positionally and now exercises the optimized default, pinning int/datetime element types.

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/casting.py tests/test_casting_vectorized.py
git commit -m "perf(casting): vectorized cast_frame with naive fallback path"
```

---

## Task 2: Thread `strategy` through mapping_resolver and runner

**Files:**
- Modify: `src/polyglotimportcsv/mapping_resolver.py:125-153`
- Modify: `src/polyglotimportcsv/runner.py:42-84, 87-160`
- Modify: `src/polyglotimportcsv/importers/base.py:15-26`
- Test: `tests/test_mapping_resolver.py` (add one), reuse `tests/test_importer_metrics.py`

**Interfaces:**
- Consumes: `cast_frame(df, kinds, *, strategy=...)` from Task 1.
- Produces:
  - `resolve_backend_entities(backend_cfg, sources, cast_cache=None, *, strategy="optimized")`
  - `run_import(..., strategy: str = "optimized")` — new keyword after `benchmark`.
  - `BackendImporterFn.__call__(..., *, dry_run, create_schema, strategy="optimized")`.
  - Cast cache key gains strategy so naive and optimized frames never collide.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_mapping_resolver.py`:

```python
def test_resolve_uses_strategy_for_casting():
    import pandas as pd
    from polyglotimportcsv.sources import SOURCE_COLUMN, SourceData
    from polyglotimportcsv.mapping_resolver import resolve_backend_entities

    df = pd.DataFrame({"n": ["1", "2"], SOURCE_COLUMN: ["s", "s"]})
    sd = SourceData(name="s", df=df,
                    kinds={"n": "integer", SOURCE_COLUMN: "string"},
                    file_header=["n"])
    bcfg = {"entities": {"E": {"source": "s", "columns": {"n": {}}}}}
    cache: dict = {}
    resolve_backend_entities(bcfg, {"s": sd}, cache, strategy="naive")
    resolve_backend_entities(bcfg, {"s": sd}, cache, strategy="optimized")
    # Distinct strategies must not share a cached frame.
    assert len({k for k in cache}) == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_mapping_resolver.py::test_resolve_uses_strategy_for_casting -v`
Expected: FAIL — unexpected keyword `strategy`.

- [ ] **Step 3: Implement threading**

In `mapping_resolver.py`, change `resolve_backend_entities` signature and body:

```python
def resolve_backend_entities(
    backend_cfg: Dict[str, Any],
    sources: Dict[str, SourceData],
    cast_cache: Optional[Dict[tuple, pd.DataFrame]] = None,
    *,
    strategy: str = "optimized",
) -> Dict[str, BoundEntity]:
```

Change the cache key line (was `cache_key = _binding_cache_key(ecfg, ename)`):

```python
        cache_key = (strategy,) + _binding_cache_key(ecfg, ename)
        if cache_key not in cast_cache:
            cast_cache[cache_key] = cast_frame(src.df, src.kinds, strategy=strategy)
```

In `runner.py`, add `strategy: str = "optimized"` to `run_import` (after `benchmark: bool = False`) and to `_run`'s keyword params, forward it in the `_run(...)` call, then use it:

```python
        with collector.timed(backend, "*", "map") as t:
            bound = resolve_backend_entities(bcfg, sources, cast_cache, strategy=strategy)
            t.rows = sum(len(be.df) for be in bound.values())
        validate_backend_entities(backend, bcfg, bound)
        for ename, be in bound.items():
            if len(be.df) == 0:
                logger.warning("entity %s/%s bound to 0 row(s)", backend, ename)
            dump_entity_frame(backend, ename, be.df, force=show_data)
        backend_lines = fn(bcfg, bound, dry_run=dry_run,
                           create_schema=create_schema, strategy=strategy)
```

In `importers/base.py`, add the keyword to the Protocol:

```python
    def __call__(
        self,
        backend_cfg: Dict[str, Any],
        entities: Dict[str, BoundEntity],
        *,
        dry_run: bool,
        create_schema: bool,
        strategy: str = "optimized",
    ) -> List[str]:
        ...
```

Also add `strategy="optimized"` (accept-and-ignore for now) to each of the five `run_*_import` signatures so the runner call in this task doesn't break them. Tasks 3-6 give it meaning; mongodb/postgres keep ignoring it for writes.

For `postgres_importer.py` and `mongodb_importer.py`, add `strategy: str = "optimized"` to the signature and a `_ = strategy` line near the top (they batch already; strategy only affected their map phase, which is handled in the resolver).

- [ ] **Step 4: Run resolver + runner + metrics tests**

Run: `python -m pytest tests/test_mapping_resolver.py tests/test_importer_metrics.py tests/test_runner_registry.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/mapping_resolver.py src/polyglotimportcsv/runner.py src/polyglotimportcsv/importers/
git commit -m "feat: thread strategy from run_import through resolver and importers"
```

---

## Task 3: Redis batched writes via pipeline

**Files:**
- Modify: `src/polyglotimportcsv/importers/redis_importer.py`
- Test: `tests/test_importer_write_batching.py` (create)

**Interfaces:**
- Consumes: `strategy` keyword (Task 2).
- Produces: `run_redis_import(..., *, dry_run, create_schema, strategy="optimized", client_factory=_default_redis_client)`. `client_factory(conn: dict) -> client`. `_write_naive(client, kv_pairs)` and `_write_batched(client, kv_pairs, batch=1000)` returning count written.

- [ ] **Step 1: Write the failing test**

Create `tests/test_importer_write_batching.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_importer_write_batching.py -k redis -v`
Expected: FAIL — `run_redis_import()` got an unexpected keyword argument `client_factory`.

- [ ] **Step 3: Implement**

Rewrite `src/polyglotimportcsv/importers/redis_importer.py`. Add a default factory, split the write loop, hoist the per-entity lookups out of the row loop:

```python
"""Import key-value rows into Redis."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Tuple

import redis

from polyglotimportcsv import metrics
from polyglotimportcsv.business_exception import ImportExecutionError
from polyglotimportcsv.mapping_resolver import BoundEntity
from polyglotimportcsv.filter_engine import apply_filters, expand_each
from polyglotimportcsv.materialize import redis_payload_from_row
from polyglotimportcsv.reporting import entity_progress

logger = logging.getLogger(__name__)


def _default_redis_client(conn: Dict[str, Any]):
    return redis.Redis(
        host=conn.get("host", "127.0.0.1"),
        port=int(conn.get("port", 6379)),
        db=int(conn.get("db", 0)),
        password=conn.get("password") or None,
        decode_responses=True,
    )


def _kv_pairs(part_df, entity_cfg) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for _, row in part_df.iterrows():
        try:
            pairs.append(redis_payload_from_row(row, entity_cfg))
        except ValueError:
            continue
    return pairs


def _write_naive(client, pairs: List[Tuple[str, str]], advance) -> int:
    count = 0
    for k, v in pairs:
        client.set(k, v)
        count += 1
        advance(1)
    return count


def _write_batched(client, pairs: List[Tuple[str, str]], advance, batch: int = 1000) -> int:
    count = 0
    for i in range(0, len(pairs), batch):
        chunk = pairs[i : i + batch]
        pipe = client.pipeline(transaction=False)
        for k, v in chunk:
            pipe.set(k, v)
        pipe.execute()
        count += len(chunk)
        advance(len(chunk))
    return count


def run_redis_import(
    backend_cfg: Dict[str, Any],
    entities: Dict[str, "BoundEntity"],
    *,
    dry_run: bool,
    create_schema: bool,
    strategy: str = "optimized",
    client_factory: Callable[[Dict[str, Any]], Any] = _default_redis_client,
) -> List[str]:
    lines: List[str] = []
    conn = backend_cfg.get("connection") or {}
    _ = create_schema  # Redis has no DDL

    if dry_run:
        lines.append("[redis] dry-run: would SET keys for entities.")
        for ename, be in entities.items():
            non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
            with metrics.timed_phase("redis", ename, "filter") as t:
                dff = apply_filters(be.df, non_each, be.kinds)
                t.rows = len(dff)
            for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
                lines.append(f"  entity {part_name}: {len(part_df)} row(s)")
        return lines

    client = client_factory(conn)
    try:
        client.ping()
    except Exception as e:
        raise ImportExecutionError(f"Redis connection failed: {e}") from e

    writer = _write_naive if strategy == "naive" else _write_batched
    for ename, be in entities.items():
        non_each = [f for f in (be.cfg.get("filters") or []) if f.get("operator") != "each"]
        with metrics.timed_phase("redis", ename, "filter") as t:
            dff = apply_filters(be.df, non_each, be.kinds)
            t.rows = len(dff)
        for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
            if part_df.empty:
                logger.warning("[redis] entity %s has 0 row(s) after filters", part_name)
            with metrics.timed_phase("redis", part_name, "write") as tw:
                pairs = _kv_pairs(part_df, be.cfg)
                with entity_progress(f"redis · {part_name}", len(pairs)) as advance:
                    count = writer(client, pairs, advance)
                tw.rows = count
            logger.debug("[redis] SET %d key(s) for %s", count, part_name)
            lines.append(f"[redis] SET {count} key(s) for {part_name}")
    return lines
```

Note: `_kv_pairs` (payload building) is inside the `write` timer, matching §4.5's boundary rule and the other row-shaping backends.

- [ ] **Step 4: Run redis tests + redis dry-run regression**

Run: `python -m pytest tests/test_importer_write_batching.py -k redis tests/test_importer_metrics.py -k redis -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/importers/redis_importer.py tests/test_importer_write_batching.py
git commit -m "perf(redis): pipeline batched writes with naive fallback + injectable client"
```

---

## Task 4: Cassandra concurrent batched writes

**Files:**
- Modify: `src/polyglotimportcsv/importers/cassandra_importer.py`
- Test: `tests/test_importer_write_batching.py` (extend)

**Interfaces:**
- Consumes: `strategy` (Task 2).
- Produces: `run_cassandra_import(..., *, dry_run, create_schema, strategy="optimized", session_factory=_default_cassandra_session)`. `session_factory(conn: dict) -> (cluster, session)`. `_write_naive(session, prepared, params_list)` and `_write_batched(session, prepared, params_list, concurrency=64)`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_importer_write_batching.py`:

```python
# ---------- Cassandra ----------

class _FakeSession:
    def __init__(self):
        self.executes = []          # each execute() call
        self.prepared = 0

    def execute(self, stmt, params=None):
        self.executes.append((stmt, params))
        return []

    def prepare(self, cql):
        self.prepared += 1
        return ("prep", cql)

    def set_keyspace(self, ks):
        pass


class _FakeCluster:
    def __init__(self, session):
        self._session = session

    def shutdown(self):
        pass


def _cass_entity(n):
    return _be(
        "user_activity_log",
        {"columns": {"user_id": {"is_key": True}, "action": {}},
         "cassandra_partition": ["user_id"]},
        {"user_id": [f"u{i}" for i in range(n)], "action": ["x"] * n},
    )


def test_cassandra_optimized_uses_concurrent_not_per_row(monkeypatch):
    import polyglotimportcsv.importers.cassandra_importer as ci
    calls = {"concurrent": 0, "rows": 0}

    def fake_concurrent(session, prepared, params, concurrency=64, **kw):
        calls["concurrent"] += 1
        calls["rows"] += len(list(params))
        return []

    monkeypatch.setattr(ci, "execute_concurrent_with_args", fake_concurrent)
    session = _FakeSession()
    ci.run_cassandra_import(
        {"connection": {}}, {"user_activity_log": _cass_entity(2500)},
        dry_run=False, create_schema=False, strategy="optimized",
        session_factory=lambda conn: (_FakeCluster(session), session),
    )
    assert calls["concurrent"] == 1
    assert calls["rows"] == 2500
    # No per-row execute for INSERTs (execute() only used for DDL, skipped here)
    assert all("INSERT" not in str(s) for s, _ in session.executes)


def test_cassandra_naive_executes_one_per_row():
    import polyglotimportcsv.importers.cassandra_importer as ci
    session = _FakeSession()
    ci.run_cassandra_import(
        {"connection": {}}, {"user_activity_log": _cass_entity(2500)},
        dry_run=False, create_schema=False, strategy="naive",
        session_factory=lambda conn: (_FakeCluster(session), session),
    )
    insert_execs = [e for e in session.executes if e[1] is not None]
    assert len(insert_execs) == 2500
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_importer_write_batching.py -k cassandra -v`
Expected: FAIL — unexpected keyword `session_factory`.

- [ ] **Step 3: Implement**

In `cassandra_importer.py`, add near the top-level imports:

```python
from typing import Any, Callable, Dict, List, Tuple
from cassandra.concurrent import execute_concurrent_with_args
```

(Keep the existing lazy driver import inside the factory — the module-level `execute_concurrent_with_args` import is safe because `cassandra.concurrent` doesn't need a reactor; if CI lacks the driver entirely, guard it — see note below.)

Add the default factory and split the write. Replace the connect block (lines 94-116) and the per-row write loop (lines 170-187):

```python
def _default_cassandra_session(conn: Dict[str, Any]):
    import os
    os.environ["CASS_DRIVER_NO_EXTENSIONS"] = "1"
    try:
        from cassandra.cluster import Cluster
        from cassandra.io.asyncioreactor import AsyncioConnection
    except Exception as e:  # pragma: no cover - environment specific
        raise ImportExecutionError(
            f"Cassandra driver could not be loaded: {e}. "
            "Install 'pyasyncore' on Python 3.12+; see DataStax docs."
        ) from e
    hosts = conn.get("hosts") or ["127.0.0.1"]
    port = int(conn.get("port", 9042))
    cluster = Cluster(hosts, port=port, connect_timeout=5)
    cluster.connection_class = AsyncioConnection
    return cluster, cluster.connect()


def _row_values(row, ordered_src, cql_by_src):
    values = []
    for src in ordered_src:
        val = row.get(src)
        if pd.isna(val):
            values.append(None)
        elif cql_by_src[src] == "text":
            values.append(str(val))
        else:
            values.append(val)
    return values


def _write_naive(session, prepared, params_list, advance) -> int:
    count = 0
    for values in params_list:
        session.execute(prepared, values)
        count += 1
        advance(1)
    return count


def _write_batched(session, prepared, params_list, advance, concurrency: int = 64) -> int:
    execute_concurrent_with_args(session, prepared, params_list, concurrency=concurrency)
    advance(len(params_list))
    return len(params_list)
```

Change `run_cassandra_import` signature to add `strategy="optimized"` and `session_factory=_default_cassandra_session`, replace the connect block with:

```python
    try:
        cluster, session = session_factory(conn)
    except ImportExecutionError:
        raise
    except Exception as e:
        raise ImportExecutionError(f"Cassandra connection failed: {e}") from e
```

Remove the now-duplicated keyspace-DDL lines only if the factory owns them — keep the `CREATE KEYSPACE` / `set_keyspace` in the caller (the fake session provides `set_keyspace`). Guard keyspace DDL so it's skipped when `create_schema` is False (matches the fake, which asserts no INSERT-shaped executes). Replace the inner write loop with:

```python
            params_list = [_row_values(row, ordered_src, cql_by_src)
                           for _, row in part_df.iterrows()]
            writer = _write_naive if strategy == "naive" else _write_batched
            with metrics.timed_phase("cassandra", table, "write") as tw:
                with entity_progress(f"cassandra · {table}", len(params_list)) as advance:
                    count = writer(session, prep, params_list, advance)
                tw.rows = count
            lines.append(f"[cassandra] inserted {count} row(s) into {keyspace}.{table}")
```

Row-value construction (`params_list`) sits inside the write timer, matching §4.5.

**CI guard note:** If `cassandra.concurrent` may be unimportable in CI, move `from cassandra.concurrent import execute_concurrent_with_args` to module level guarded by try/except that sets it to `None`, and `_write_batched` raises `ImportExecutionError` if it's `None`. The monkeypatch test replaces the module attribute regardless.

- [ ] **Step 4: Run cassandra tests + dry-run regression**

Run: `python -m pytest tests/test_importer_write_batching.py -k cassandra tests/test_graph_wide_importers_dry_run.py -k cassandra tests/test_cassandra_types.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/importers/cassandra_importer.py tests/test_importer_write_batching.py
git commit -m "perf(cassandra): concurrent batched writes with naive fallback + injectable session"
```

---

## Task 5: Neo4j uniqueness constraint + UNWIND batches

**Files:**
- Modify: `src/polyglotimportcsv/importers/neo4j_importer.py`
- Test: `tests/test_importer_write_batching.py` (extend)

**Interfaces:**
- Consumes: `strategy` (Task 2).
- Produces: `run_neo4j_import(..., *, dry_run, create_schema, strategy="optimized", driver_factory=_default_neo4j_driver)`. `driver_factory(conn: dict) -> driver`. Node writer batches via `UNWIND ... MERGE`; constraint emitted when `create_schema`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_importer_write_batching.py`:

```python
# ---------- Neo4j ----------

class _FakeNeoSession:
    def __init__(self, recorder):
        self.recorder = recorder

    def run(self, q, **params):
        self.recorder["run"].append((q, params))
        return []

    def execute_write(self, fn, *a, **k):
        return fn(_FakeTx(self.recorder), *a, **k)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeTx:
    def __init__(self, recorder):
        self.recorder = recorder

    def run(self, q, **params):
        self.recorder["tx_run"].append((q, params))
        return []


class _FakeDriver:
    def __init__(self, recorder):
        self.recorder = recorder

    def verify_connectivity(self):
        pass

    def session(self, database=None):
        return _FakeNeoSession(self.recorder)

    def close(self):
        pass


def _neo_entities(n):
    user = _be("User", {"columns": {"user_id": {"is_key": True}}},
               {"user_id": [f"u{i}" for i in range(n)]})
    return {"User": user}


def test_neo4j_optimized_batches_nodes_with_unwind():
    import polyglotimportcsv.importers.neo4j_importer as ni
    rec = {"run": [], "tx_run": []}
    ni.run_neo4j_import(
        {"connection": {}}, _neo_entities(2500),
        dry_run=False, create_schema=True, strategy="optimized",
        driver_factory=lambda conn: _FakeDriver(rec),
    )
    # Nodes written in UNWIND batches inside execute_write, not one run() per row.
    assert any("UNWIND" in q for q, _ in rec["tx_run"])
    node_batches = [p for q, p in rec["tx_run"] if "UNWIND" in q and "MERGE (n" in q]
    assert sum(len(p["batch"]) for p in node_batches) == 2500
    assert len(node_batches) == 3          # ceil(2500/1000)
    # A uniqueness constraint was created.
    assert any("CONSTRAINT" in q and "UNIQUE" in q for q, _ in rec["run"])


def test_neo4j_naive_runs_one_merge_per_row():
    import polyglotimportcsv.importers.neo4j_importer as ni
    rec = {"run": [], "tx_run": []}
    ni.run_neo4j_import(
        {"connection": {}}, _neo_entities(2500),
        dry_run=False, create_schema=False, strategy="naive",
        driver_factory=lambda conn: _FakeDriver(rec),
    )
    merges = [q for q, _ in rec["run"] if "MERGE (n" in q]
    assert len(merges) == 2500
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_importer_write_batching.py -k neo4j -v`
Expected: FAIL — unexpected keyword `driver_factory`.

- [ ] **Step 3: Implement**

In `neo4j_importer.py`, add:

```python
from typing import Any, Callable, Dict, List


def _default_neo4j_driver(conn: Dict[str, Any]):
    uri = conn.get("uri", "bolt://127.0.0.1:7687")
    user = conn.get("user", "neo4j")
    password = conn.get("password", "password")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    return driver
```

Change the signature to add `strategy="optimized"`, `driver_factory=_default_neo4j_driver`, stop discarding `create_schema`. Replace the connect block (lines 56-65) with `driver = driver_factory(conn)` wrapped in the existing `ImportExecutionError` translation. Keep `database` from conn.

For the node loop, after computing `plabel`, `key_name`, and the deduped rows, branch on strategy. Extract the existing per-row loop into `_merge_nodes_naive(session, q, part_df, be.cfg, key_name)` returning `(merged, skipped)`. Add the batched path:

```python
def _dedupe_props(part_df, ecfg, key_name, props_from_row):
    """First-wins dedupe by key; returns (list-of-props, skipped_count)."""
    seen = set()
    out, skipped = [], 0
    for _, row in part_df.iterrows():
        props = props_from_row(row, ecfg)
        kid = props.get(key_name)
        if kid is None:
            continue
        if kid in seen:
            skipped += 1
            continue
        seen.add(kid)
        out.append(props)
    return out, skipped


def _merge_nodes_batched(session, plabel, key_name, props_list, advance, batch=1000):
    q = (f"UNWIND $batch AS row "
         f"MERGE (n:{plabel} {{{key_name}: row.k}}) SET n += row.props")
    merged = 0
    for i in range(0, len(props_list), batch):
        chunk = props_list[i : i + batch]
        payload = [{"k": p[key_name],
                    "props": {k: v for k, v in p.items() if k != key_name}}
                   for p in chunk]
        session.execute_write(lambda tx: tx.run(q, batch=payload))
        merged += len(chunk)
        advance(len(chunk))
    return merged
```

Constraint creation, before the entity loop, when `create_schema`:

```python
        if create_schema:
            for ename, be in entities.items():
                key_cols = [(fk, sp) for fk, _, sp in flat_leaf_columns(be.cfg) if sp.get("is_key")]
                if len(key_cols) == 1:
                    kn = target_field_name(*key_cols[0])
                    lbl = _sanitize_label(ename)
                    session.run(
                        f"CREATE CONSTRAINT IF NOT EXISTS "
                        f"FOR (n:{lbl}) REQUIRE n.{kn} IS UNIQUE"
                    )
```

Wire the branch in the node loop:

```python
                props_list, skipped = _dedupe_props(part_df, be.cfg, key_name, props_from_row)
                with metrics.timed_phase("neo4j", part_name, "write") as tw:
                    with entity_progress(f"neo4j · {part_name}", len(props_list)) as advance:
                        if strategy == "naive":
                            merged = _merge_nodes_naive(session, plabel, key_name,
                                                        props_list, advance)
                        else:
                            merged = _merge_nodes_batched(session, plabel, key_name,
                                                          props_list, advance)
                    tw.rows = merged
```

`_merge_nodes_naive` issues `session.run(f"MERGE (n:{plabel} {{{key_name}: $k}}) SET n += $props", k=..., props=...)` per row over `props_list` (already deduped, so the `seen`/skip logic moves into `_dedupe_props`). Apply the same UNWIND-vs-per-row branch to the relationship loop, batching on the same key of 1000.

- [ ] **Step 4: Run neo4j tests + dry-run regression**

Run: `python -m pytest tests/test_importer_write_batching.py -k neo4j tests/test_graph_wide_importers_dry_run.py -k neo4j -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/importers/neo4j_importer.py tests/test_importer_write_batching.py
git commit -m "perf(neo4j): uniqueness constraint + UNWIND batched merges with naive fallback"
```

---

## Task 6: MongoDB phase boundary + phase-boundary test

**Files:**
- Modify: `src/polyglotimportcsv/importers/mongodb_importer.py:56-68`
- Test: `tests/test_phase_boundaries.py` (create)

**Interfaces:**
- Consumes: nothing new (mongodb already batches).
- Produces: MongoDB builds documents inside the `write` timer.

- [ ] **Step 1: Write the failing test**

Create `tests/test_phase_boundaries.py`:

```python
"""Every backend must shape rows inside its own 'write' timer (spec §4.5)."""

import inspect

from polyglotimportcsv.importers import mongodb_importer


def test_mongodb_builds_documents_inside_write_timer():
    src = inspect.getsource(mongodb_importer.run_mongodb_import)
    write_at = src.index('timed_phase("mongodb", part_name, "write")')
    docs_at = src.index("mongo_document_from_row")
    # The doc-building call must appear after the write timer opens, not before.
    assert docs_at > write_at, "MongoDB builds payloads before its write timer opens"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_phase_boundaries.py -v`
Expected: FAIL — `mongo_document_from_row` currently appears before the write timer.

- [ ] **Step 3: Implement**

In `mongodb_importer.py`, move the comprehension inside the timer. Replace lines 56-68:

```python
        for part_name, part_df in expand_each(dff, be.cfg.get("filters") or [], ename):
            with metrics.timed_phase("mongodb", part_name, "write") as tw:
                docs = [mongo_document_from_row(row, be.cfg) for _, row in part_df.iterrows()]
                if not docs:
                    logger.warning("[mongodb] collection %s has 0 document(s) after filters", part_name)
                    lines.append(f"[mongodb] inserted 0 document(s) into {part_name}")
                    tw.rows = 0
                    continue
                logger.debug("[mongodb] insert_many into %s: %d document(s)", part_name, len(docs))
                with entity_progress(f"mongodb · {part_name}", len(docs)) as advance:
                    db[part_name].insert_many(docs)
                    advance(len(docs))
                tw.rows = len(docs)
            lines.append(f"[mongodb] inserted {len(docs)} document(s) into {part_name}")
```

- [ ] **Step 4: Run boundary test + mongodb dry-run regression**

Run: `python -m pytest tests/test_phase_boundaries.py tests/test_importer_metrics.py -k mongodb -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/importers/mongodb_importer.py tests/test_phase_boundaries.py
git commit -m "fix(mongodb): build documents inside the write timer for phase parity"
```

---

## Task 7: Strategy axis in benchmark runner and consolidated output

**Files:**
- Modify: `src/polyglotimportcsv/benchmark_runner.py:44-107`
- Modify: `src/polyglotimportcsv/benchmark_results.py:11-44`
- Test: `tests/test_benchmark_runner.py` (extend), `tests/test_benchmark_results.py` (extend if present)

**Interfaces:**
- Consumes: `run_import(..., strategy=...)` (Task 2).
- Produces: `run_matrix(..., strategies: Iterable[str] = ("optimized",))`. Labeled runs gain `"strategy"`. `median_results` keys on strategy; `_RESULT_FIELDS` includes `"strategy"` after `"mode"`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_benchmark_runner.py`:

```python
def test_run_matrix_iterates_strategies(tmp_path):
    seen = []

    def fake_importer(config_path, *, sgbd_config_path, collector, show_data,
                      only, create_schema, source_overrides, strategy):
        seen.append(strategy)
        collector.record("postgres", "products", "write", rows=100, seconds=0.1)
        return []

    labeled = brun.run_matrix(
        sizes=[1000], modes=["multi"], repetitions=1,
        strategies=["naive", "optimized"],
        sgbd_config_path=None, config_dir="data/ecommerce", data_dir=tmp_path,
        seed=1, only=["postgres"], cleaners={},
        importer=fake_importer, load_cfg=lambda c, s: {"postgres": {}},
        generate=lambda out_dir, rows, seed, mode: None,
    )
    assert sorted(seen) == ["naive", "optimized"]
    assert {r["strategy"] for r in labeled} == {"naive", "optimized"}
    from polyglotimportcsv.benchmark_results import median_results
    res = median_results(labeled)
    assert {r["strategy"] for r in res} == {"naive", "optimized"}
```

Note: the existing `fake_importer` signatures in this file must gain `strategy` — update the three older tests' inner functions to accept `strategy` (keyword) too, or they'll break once `run_matrix` passes it.

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_benchmark_runner.py::test_run_matrix_iterates_strategies -v`
Expected: FAIL — `run_matrix()` got an unexpected keyword `strategies`.

- [ ] **Step 3: Implement**

In `benchmark_runner.py`, add `strategies: Iterable[str] = ("optimized",)` to `run_matrix`, and nest the loop. Change the innermost block:

```python
    strategies = list(strategies)
    for size in sizes:
        for mode in modes:
            cfg_name, _ = _MODE_CONFIG[mode]
            config_path = config_dir / cfg_name
            dpath = _ensure_dataset(data_dir, size, seed, mode, generate)
            overrides = _overrides(mode, dpath)
            merged = load_cfg(config_path, sgbd_config_path)
            selected = requested or [b for b in _ALL_BACKENDS if b in merged]
            for strategy in strategies:
                for rep in range(repetitions):
                    for backend in selected:
                        block = merged.get(backend)
                        if block is not None and backend in cleaners:
                            cleaners[backend](block)
                    collector = MetricsCollector()
                    importer(
                        config_path,
                        sgbd_config_path=sgbd_config_path,
                        collector=collector,
                        show_data=False,
                        only=selected,
                        create_schema=True,
                        source_overrides=overrides,
                        strategy=strategy,
                    )
                    labeled.append({
                        "size": size, "mode": mode, "strategy": strategy,
                        "repetition": rep, "records": collector.to_records(),
                    })
                    if on_run is not None:
                        on_run(labeled)
    return labeled
```

In `benchmark_results.py`, add `"strategy"` to `_RESULT_FIELDS` after `"mode"`, and key the grouping on it:

```python
_RESULT_FIELDS = (
    "timestamp", "size", "mode", "strategy", "backend", "entity", "phase",
    "rows", "median_seconds", "rows_per_second",
)
```

```python
    for run in labeled_runs:
        for rec in run["records"]:
            key = (run["size"], run["mode"], run["strategy"],
                   rec["backend"], rec["entity"], rec["phase"])
            ...
    for key in order:
        size, mode, strategy, backend, entity, phase = key
        ...
        results.append({
            "size": size, "mode": mode, "strategy": strategy,
            "backend": backend, "entity": entity, "phase": phase,
            "rows": g["rows"], "median_seconds": med, "rows_per_second": rps,
        })
```

- [ ] **Step 4: Run benchmark runner + results tests**

Run: `python -m pytest tests/test_benchmark_runner.py tests/test_benchmark_results.py -v`
Expected: PASS (after updating the three older fake_importer signatures to accept `strategy`).

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/benchmark_runner.py src/polyglotimportcsv/benchmark_results.py tests/test_benchmark_runner.py
git commit -m "feat(benchmarks): strategy axis in run_matrix and consolidated results"
```

---

## Task 8: CSV header guard + baseline rename

**Files:**
- Modify: `src/polyglotimportcsv/benchmark_io.py:38-49`
- Rename: `benchmarks/benchmark_results.csv` → `benchmarks/benchmark_results_naive_baseline.csv`
- Test: `tests/test_benchmark_output.py` (extend) or new assertion in `tests/test_benchmark_results.py`

**Interfaces:**
- Consumes: `_RESULT_FIELDS` with `strategy` (Task 7).
- Produces: `write_json_and_csv` raises `ValueError` when appending to an existing CSV whose header differs from `csv_fields`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_benchmark_output.py`:

```python
import pytest

from polyglotimportcsv.benchmark_io import write_json_and_csv


def test_append_to_mismatched_header_raises(tmp_path):
    csv_path = tmp_path / "r.csv"
    csv_path.write_text("timestamp,size,mode\n", encoding="utf-8")
    with pytest.raises(ValueError, match="header"):
        write_json_and_csv(
            tmp_path, {"timestamp": "t"},
            [{"size": 1, "mode": "multi", "extra": "x"}],
            json_prefix="j", csv_name="r.csv",
            csv_fields=("timestamp", "size", "mode", "extra"),
            payload_key="results",
        )
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_benchmark_output.py::test_append_to_mismatched_header_raises -v`
Expected: FAIL — no error raised (row appended under wrong header).

- [ ] **Step 3: Implement the guard**

In `benchmark_io.py`, before opening for append, check the existing header:

```python
    csv_path = out / csv_name
    new_file = not csv_path.exists()
    if not new_file:
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            existing = fh.readline().rstrip("\n\r")
        if existing and existing != ",".join(csv_fields):
            raise ValueError(
                f"CSV header mismatch in {csv_path}: file has {existing!r} but "
                f"this run writes {','.join(csv_fields)!r}. Move or rename the old "
                "file (its columns changed)."
            )
    ts = metadata.get("timestamp", "")
```

- [ ] **Step 4: Run + rename baseline**

Run: `python -m pytest tests/test_benchmark_output.py -v`
Expected: PASS.

```bash
git mv benchmarks/benchmark_results.csv benchmarks/benchmark_results_naive_baseline.csv
```

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/benchmark_io.py tests/test_benchmark_output.py
git commit -m "feat(benchmarks): guard CSV append against header mismatch; keep naive baseline"
```

---

## Task 9: CLI flags for strategy

**Files:**
- Modify: `src/polyglotimportcsv/cli.py`
- Modify: `scripts/run_benchmarks.py`
- Modify: `scripts/run_benchmarks_100k.py`
- Test: `tests/test_cli.py` (extend)

**Interfaces:**
- Consumes: `run_import(..., strategy=...)` (Task 2), `run_matrix(..., strategies=...)` (Task 7).
- Produces: `polyglot-import --strategy {naive,optimized}`; `run_benchmarks.py --strategies a,b`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py` (follow the file's existing CliRunner pattern):

```python
def test_cli_passes_strategy(monkeypatch):
    from click.testing import CliRunner
    import polyglotimportcsv.cli as climod

    captured = {}

    def fake_run_import(config_path, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(climod, "run_import", fake_run_import)
    runner = CliRunner()
    # --dry-run so no DB; reuse a config that exists in the repo
    res = runner.invoke(climod.main, [
        "--config", "data/ecommerce/import_config.json",
        "--dry-run", "--strategy", "naive",
    ])
    assert res.exit_code == 0, res.output
    assert captured["strategy"] == "naive"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_cli.py::test_cli_passes_strategy -v`
Expected: FAIL — no such option `--strategy` (or `strategy` absent from captured kwargs).

- [ ] **Step 3: Implement**

In `cli.py`, add the option after `--only`:

```python
@click.option(
    "--strategy",
    default="optimized",
    show_default=True,
    type=click.Choice(["naive", "optimized"], case_sensitive=False),
    help="Write/cast strategy. 'naive' reproduces the row-at-a-time baseline.",
)
```

Add `strategy: str` to `main`'s params and pass `strategy=strategy` into `run_import(...)`.

In `scripts/run_benchmarks.py`, add the argument and forward it:

```python
    parser.add_argument("--strategies", default="optimized",
                        help="Comma-separated strategies: naive,optimized (default: optimized).")
```

Parse with `_parse_str_list(args.strategies)`, add to `meta`, and pass `strategies=...` to `run_matrix(...)`.

In `scripts/run_benchmarks_100k.py`, forward `--strategies` if the caller passes it (it already flows through `passthrough`), and make the slow-backend warning conditional:

```python
    if slow and "naive" in args.strategies:
        print(...)  # existing warning text
```

Add a top note that `MEASURED_ROWS_PER_S` is naive-path data and understates the optimized run.

- [ ] **Step 4: Run CLI tests**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/cli.py scripts/run_benchmarks.py scripts/run_benchmarks_100k.py tests/test_cli.py
git commit -m "feat(cli): --strategy for imports and --strategies for the benchmark matrix"
```

---

## Task 10: Full suite green + README note

**Files:**
- Modify: `README.md` (Benchmarks section, EN + PT)
- Test: whole suite

**Interfaces:** none new.

- [ ] **Step 1: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS. Known pre-existing failure to confirm is unrelated: `tests/test_duplicate_csv_column_example.py` (missing config file deleted before this work). If it still fails for that reason, leave it; if any *other* test fails, fix it in the owning task's file.

- [ ] **Step 2: Document the strategy switch**

In `README.md`, under the existing Benchmarks headings (EN and PT), add a short paragraph: the matrix defaults to `optimized`; `--strategies naive,optimized` runs both for the before/after comparison; `naive` reproduces the row-at-a-time baseline. Note that cassandra/redis/neo4j are slow only under `naive`.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): document naive/optimized benchmark strategies"
```

- [ ] **Step 4: Validation run (manual, requires live DBs — not CI)**

With databases up (`docker compose up --wait`):

```bash
python scripts/run_benchmarks.py --sizes 1000,10000 --strategies naive,optimized --repetitions 3
```

Expected: consolidated JSON + `benchmark_results.csv` with a `strategy` column; optimized rows show the map-phase and write-phase speedups. Then, only if satisfied:

```bash
python scripts/run_benchmarks_100k.py --strategies optimized
```

---

## Self-Review Notes

- **Spec §1.1 (casting)** → Task 1. **§1.2 (row writes)** → Tasks 3,4,5. **§1.3 (phase boundary)** → Task 6. **§3.1 strategy axis** → Task 2. **§3.2 injectable client** → Tasks 3-5. **§4.1-4.6** → Tasks 1,3,4,5,6,2. **§5 metrics/CSV** → Tasks 7,8. **§6 CLI** → Task 9. **§7 tests** → each task's tests + Task 10. **§8 validation** → Task 10 Step 4. **§9 out-of-scope** honored (no COPY, no cross-backend parallelism, clean_postgres untouched).
- **Type consistency:** `strategy` is the single param name everywhere; factory params named `client_factory` (redis), `session_factory` (cassandra), `driver_factory` (neo4j) — different because the driver connection shapes differ (client vs cluster+session vs driver). Batch constant 1000 for redis/neo4j, concurrency 64 for cassandra, stated in Global Constraints and reused verbatim.
- **Ordering risk:** Task 2 makes the five importers accept `strategy` (ignoring it) so Task 2's runner change doesn't break them before Tasks 3-6 give it meaning. Tasks 3-6 are independent of each other and can run in any order after Task 2.
