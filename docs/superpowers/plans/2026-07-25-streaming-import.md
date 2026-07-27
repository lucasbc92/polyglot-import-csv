# Streaming Import (Bounded Memory) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a streaming import path whose peak memory is ≈ one read chunk (constant in file size), as the default for real imports, while keeping the existing full-materialization path as the TCC phase-measured baseline.

**Architecture:** Ports & adapters. A `StreamReader` yields `(entity, chunk)` pairs (multi: per-file; combined: routed by origin). A backend-agnostic orchestrator (`stream_runner`) binds each entity from its first chunk (inferring `kinds`, with declared `db_type` winning), then per chunk applies row-local filters, casts (vectorized), routes rows to partition buffers, and flushes `BATCH`-sized batches to a `DbmsSink`. Each DBMS implements `DbmsSink` by reusing the row-shaping/batched-write helpers already in its importer. A new `execution` axis (`materialize|stream`) selects the path.

**Tech Stack:** Python 3.12, pandas (`read_csv(chunksize=...)`), pytest.

## Global Constraints

- No new third-party dependencies. Streaming uses pandas `chunksize`; writes reuse existing APIs.
- `READ_CHUNK = 8192` (read + inference-sample granularity); `BATCH = 1000` (DBMS flush granularity, same constant as redis/neo4j); Cassandra keeps concurrency 64 within a batch.
- **Type inference:** `kinds` inferred once from each entity's **first chunk** and reused for all its chunks; a **declared `db_type` in config always wins** over inference.
- Streaming always uses vectorized cast + batched writes (there is no "naive streaming"). `cast_frame(chunk, kinds, strategy="optimized")`; `format="mixed"` already guaranteed inside it.
- The naming for the write port is **`DbmsSink`** (never "Backend"); adapters keep product names (`PostgresSink`, `MongoSink`, `CassandraSink`, `RedisSink`, `Neo4jSink`).
- `execution` default = `stream` in the CLI; `materialize` reproduces the existing baseline verbatim and stays byte-for-byte unchanged.
- All new tests run without live databases (injected `DbmsSink` fakes / dry-run).
- Code/identifiers/comments English; specs/plans Portuguese.
- Commit after each task; push after each commit. Test command: `./.venv/Scripts/python.exe -m pytest tests -q` (baseline before this plan: 178 passed, 1 skipped).

---

## File Structure

**Created:**
- `src/polyglotimportcsv/stream_source.py` — `StreamReader.iter_entity_chunks` (chunked CSV read; multi + combined origin routing).
- `src/polyglotimportcsv/dbms_sink.py` — `DbmsSink` Protocol + `SinkFactory` type + a `_FakeSink` is NOT here (tests define fakes).
- `src/polyglotimportcsv/stream_binding.py` — `bind_entity_from_chunk(ename, ecfg, first_chunk) -> EntityBinding(cfg, kinds)` (reuses existing binding/inference, db_type wins).
- `src/polyglotimportcsv/stream_runner.py` — `run_stream_import(...)` orchestrator.
- `src/polyglotimportcsv/sinks/__init__.py`, `sinks/postgres_sink.py`, `sinks/mongo_sink.py`, `sinks/cassandra_sink.py`, `sinks/redis_sink.py`, `sinks/neo4j_sink.py`.
- Tests: `tests/test_stream_source.py`, `tests/test_stream_runner.py`, `tests/test_stream_memory.py`, `tests/test_sinks.py`.

**Modified:**
- Importer modules (`importers/*.py`) — extract shared row-shaping/batched-write helpers so sinks and the materialize importers share them (no duplication).
- `src/polyglotimportcsv/runner.py` — `execution` param; dispatch stream vs materialize.
- `src/polyglotimportcsv/cli.py` — `--execution {stream,materialize}` (default stream).
- `src/polyglotimportcsv/benchmark_runner.py`, `benchmark_results.py`, `benchmark_io.py` — `execution` axis + `peak_memory_mb`.
- `README.md` (EN/PT) — streaming section.

---

## Task 1: `StreamReader.iter_entity_chunks`

**Files:**
- Create: `src/polyglotimportcsv/stream_source.py`
- Test: `tests/test_stream_source.py`

**Interfaces:**
- Consumes: `sources_cfg` (the config `sources` block), `base_dir: Path`, `overrides: Dict[str,str]`.
- Produces: `iter_entity_chunks(sources_cfg, base_dir, overrides=None, chunksize=READ_CHUNK) -> Iterator[Tuple[str, pandas.DataFrame]]`. Each yielded chunk has the source's data columns plus a trailing `_source` column (source name for multi; origin value for combined). Module constant `READ_CHUNK = 8192`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_stream_source.py`:

```python
import pandas as pd
from polyglotimportcsv import stream_source as ss
from polyglotimportcsv.sources import SOURCE_COLUMN


def _write_csv(path, header, rows):
    path.write_text(",".join(header) + "\n" +
                    "\n".join(",".join(str(c) for c in r) for r in rows) + "\n",
                    encoding="utf-8")


def test_multi_yields_chunks_with_source_column(tmp_path):
    _write_csv(tmp_path / "a.csv", ["id", "v"], [(i, f"x{i}") for i in range(2500)])
    cfg = {"alpha": "a.csv"}
    chunks = list(ss.iter_entity_chunks(cfg, tmp_path, chunksize=1000))
    assert [name for name, _ in chunks] == ["alpha", "alpha", "alpha"]  # ceil(2500/1000)
    total = sum(len(df) for _, df in chunks)
    assert total == 2500
    first = chunks[0][1]
    assert SOURCE_COLUMN in first.columns
    assert (first[SOURCE_COLUMN] == "alpha").all()
    assert list(first.columns)[:2] == ["id", "v"]


def test_combined_routes_by_origin(tmp_path):
    rows = [("stock", i, f"s{i}") for i in range(10)] + [("cart", i, f"c{i}") for i in range(5)]
    _write_csv(tmp_path / "j.csv", ["action", "id", "v"], rows)
    cfg = {"ecom": {"file": "j.csv"}}
    chunks = list(ss.iter_entity_chunks(cfg, tmp_path, chunksize=1000))
    by_name = {}
    for name, df in chunks:
        by_name.setdefault(name, 0)
        by_name[name] += len(df)
    assert by_name == {"stock": 10, "cart": 5}
    # origin column dropped; data columns + _source present
    a_chunk = next(df for name, df in chunks if name == "stock")
    assert "action" not in a_chunk.columns
    assert list(a_chunk.columns)[:2] == ["id", "v"]
    assert (a_chunk[SOURCE_COLUMN] == "stock").all()
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_stream_source.py -v`
Expected: FAIL — `No module named 'polyglotimportcsv.stream_source'`.

- [ ] **Step 3: Implement**

Create `src/polyglotimportcsv/stream_source.py`. Reuse the read options from `csv_reader.read_csv` (`dtype=str, keep_default_na=False, encoding="utf-8-sig"`) with `chunksize`. Resolve paths exactly like `sources._resolve_path` (import and reuse it). For multi (str decl), append `SOURCE_COLUMN = source name` to each chunk. For combined (dict decl with `"file"`), origin is column 0: per chunk, raise `SourceError` if any origin value is blank, drop the origin column, and yield one sub-frame per distinct origin value in that chunk with `SOURCE_COLUMN = origin`.

```python
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple
import pandas as pd
from polyglotimportcsv.business_exception import SourceError
from polyglotimportcsv.sources import SOURCE_COLUMN, _resolve_path

READ_CHUNK = 8192


def _read_chunks(path, chunksize):
    return pd.read_csv(path, dtype=str, keep_default_na=False,
                       encoding="utf-8-sig", chunksize=chunksize)


def iter_entity_chunks(
    sources_cfg: Dict[str, Any],
    base_dir: "str | Path",
    overrides: Optional[Dict[str, str]] = None,
    chunksize: int = READ_CHUNK,
) -> Iterator[Tuple[str, pd.DataFrame]]:
    base_dir = Path(base_dir)
    overrides = overrides or {}
    for name, decl in (sources_cfg or {}).items():
        if isinstance(decl, str):
            path = _resolve_path(name, decl, base_dir, overrides)
            for chunk in _read_chunks(path, chunksize):
                chunk = chunk.copy()
                chunk[SOURCE_COLUMN] = name
                yield name, chunk
            continue
        path = _resolve_path(name, decl["file"], base_dir, overrides)
        for chunk in _read_chunks(path, chunksize):
            if len(chunk.columns) < 2:
                raise SourceError(f"Source '{name}': combined CSV needs origin + data columns: {path}")
            origin_col = chunk.columns[0]
            origins = chunk[origin_col].astype(str)
            if (origins.str.strip() == "").any():
                raise SourceError(f"Source '{name}': combined CSV has empty origin value(s).")
            data = chunk.drop(columns=[origin_col])
            for value, idx in origins.groupby(origins).groups.items():
                sub = data.loc[idx].copy()
                sub[SOURCE_COLUMN] = str(value)
                yield str(value), sub
```

- [ ] **Step 4: Run tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_stream_source.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/stream_source.py tests/test_stream_source.py
git commit -m "feat(stream): chunked StreamReader with multi + combined origin routing"
```

---

## Task 2: `EntityBinding` from first chunk

**Files:**
- Create: `src/polyglotimportcsv/stream_binding.py`
- Test: `tests/test_stream_binding.py`

**Interfaces:**
- Consumes: `SourceData` (from `sources.py`), `resolve_backend_entities`-style binding pieces (`bind_entity_source`, `expand_entity_columns` in `mapping_resolver.py`), `infer_column_kinds` (`csv_reader.py`).
- Produces: `EntityBinding` dataclass `(cfg: dict, kinds: dict, source_name: str)` and `bind_entity_from_sample(ename, ecfg, sample_df, source_name) -> EntityBinding`. `kinds` come from `infer_column_kinds(sample_df[data_cols])` with `SOURCE_COLUMN -> "string"`; a declared `db_type` in `ecfg["columns"]` must survive into `cfg` unchanged (declared wins). `cfg` is the expanded per-entity column config exactly as `resolve_backend_entities` produces (minus the frame).

- [ ] **Step 1: Write the failing test**

Create `tests/test_stream_binding.py`:

```python
import pandas as pd
from polyglotimportcsv import stream_binding as sb
from polyglotimportcsv.sources import SOURCE_COLUMN


def test_binding_infers_kinds_and_respects_declared_db_type():
    sample = pd.DataFrame({"id": ["1", "2"], "when": ["2023-01-01", "2023-01-02"],
                           SOURCE_COLUMN: ["e", "e"]})
    ecfg = {"source": "e", "columns": {"id": {"db_type": "TEXT"}}}  # declared TEXT wins
    b = sb.bind_entity_from_sample("e", ecfg, sample, "e")
    assert b.kinds["when"] == "datetime"        # inferred
    assert b.cfg["columns"]["id"]["db_type"] == "TEXT"   # declared preserved
    assert b.kinds[SOURCE_COLUMN] == "string"
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_stream_binding.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `stream_binding.py`. Build a `SourceData` from the sample (`name=source_name`, `df=sample_df`, `kinds=infer_column_kinds(sample_df[data_cols]) + {SOURCE_COLUMN: "string"}`, `file_header=data_cols`) where `data_cols = [c for c in sample_df.columns if c != SOURCE_COLUMN]`, then reuse `mapping_resolver.bind_entity_source` + `expand_entity_columns` to produce `cfg` exactly as `resolve_backend_entities` does (copy that function's cfg-building lines: `cfg = dict(ecfg); cfg["columns"] = expand_entity_columns(...); cfg.pop("source"/"csv_columns"/"auto_map")`). Return `EntityBinding(cfg=cfg, kinds=source.kinds, source_name=source_name)`.

- [ ] **Step 4: Run tests + Step 5: Commit**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_stream_binding.py -v` → PASS.
```bash
git add src/polyglotimportcsv/stream_binding.py tests/test_stream_binding.py
git commit -m "feat(stream): bind entity + infer kinds from first chunk (db_type wins)"
```

---

## Task 3: `DbmsSink` protocol + orchestrator with fake sink

**Files:**
- Create: `src/polyglotimportcsv/dbms_sink.py`
- Create: `src/polyglotimportcsv/stream_runner.py`
- Test: `tests/test_stream_runner.py`

**Interfaces:**
- Produces:
  - `DbmsSink` Protocol: `create_schema() -> None` (data-INDEPENDENT DBMS-level setup only — e.g. keyspace/database; may be a no-op); `ensure_partition(partition_name: str, binding: EntityBinding) -> None` (lazy per-partition/entity DDL, create-if-not-exists, called once per partition on first write); `write_batch(partition_name: str, binding: EntityBinding, batch: pandas.DataFrame) -> int`; `close() -> None`.
  - `SinkFactory = Callable[[dict], DbmsSink]` (receives the DBMS's `backend_cfg`).
  - `run_stream_import(config, base_dir, *, sink_factories: Dict[str, SinkFactory], only=None, create_schema=True, source_overrides=None, chunksize=READ_CHUNK, batch=BATCH) -> Dict[str, int]` returning `{partition_name: rows_written}` per DBMS aggregated. `BATCH = 1000`.

**Binding/schema ordering (refines the spec):** entities are bound **lazily** — the first time a chunk for an entity is seen, `bind_entity_from_sample` runs (cache the binding per entity). Per-entity/partition DDL is created **lazily** via `ensure_partition` on the first flush to each partition (tracked in a `seen_partitions` set), NOT via a create_schema-with-all-bindings up front — that up-front call is impossible in a streaming pass (combined mode interleaves entities; auto_map needs a data sample). `create_schema()` (when `create_schema=True`) is only for data-independent DBMS-level setup and may be a no-op for sinks that need none.

- [ ] **Step 1: Write the failing test** (fake sink records batches)

Create `tests/test_stream_runner.py` with a `_FakeSink` recording `create_schema()` calls, `ensure_partition(partition)` calls, and `write_batch(partition, len(batch))` calls, and a helper building a tiny 2-source multi config over CSVs in `tmp_path`. Assert: (a) rows written per partition equal the CSV row counts after filters; (b) each recorded batch length ≤ `batch`; (c) with `batch=1000` and a 2500-row source, exactly 3 write_batch flushes for that partition (1000,1000,500); (d) `create_schema()` called once (no args); (e) `ensure_partition` called exactly once per distinct partition; (f) `close()` called; (g) a `list`-typed `source:` raises `ImportExecutionError`. (Mirror the `test_importer_write_batching` fake-recorder style; the reviewer will check batch-boundary correctness.)

- [ ] **Step 2: Run to verify it fails** — module missing.

- [ ] **Step 3: Implement**

`dbms_sink.py`: the `Protocol` (runtime-checkable not required) + `SinkFactory` type alias.

`stream_runner.py`: `BATCH = 1000`. The config maps each DBMS to `{"entities": {ename: ecfg, ...}}`; each `ecfg["source"]` names the source that entity streams from (a `str`; if it is a `list`, raise `ImportExecutionError("streaming does not support union (list) sources: <ename>")` — union-source streaming is out of scope). Build `source_to_entities: Dict[dbms] -> Dict[source_name, List[(ename, ecfg)]]`.

For each DBMS in config (respecting `only`):
1. `sink = sink_factories[dbms](config[dbms])`; if `create_schema`, `sink.create_schema()`.
2. Iterate `iter_entity_chunks(config["sources"], base_dir, overrides, chunksize)`. Each yielded `(source_name, chunk)` maps to the entities that read that source (for combined mode `source_name` is the origin value = the entity name).
3. For each `(ename, ecfg)` fed by that chunk: **lazily bind** — if `ename` not in a `bindings` cache, `bindings[ename] = bind_entity_from_sample(ename, ecfg, chunk, source_name)`. Then `apply_filters(chunk, non_each_filters, binding.kinds)` → `cast_frame(filtered, binding.kinds)` → route rows into partitions via `expand_each(cast, filters, ename)` (each partition = `(partition_name, part_df)`) → append `part_df` to `buffers[partition_name]`.
4. Whenever `len(buffers[partition]) >= batch`: if `partition not in seen_partitions`, `sink.ensure_partition(partition, binding)` and add to `seen_partitions`; then `sink.write_batch(partition, binding, first `batch` rows)`, keep the remainder in the buffer, `written[partition] += batch`.
5. After all chunks: flush every non-empty buffer (ensure_partition if unseen, then write_batch) and `sink.close()`.

Return `written`. **Row-shaping happens inside the sink (write_batch), not here.** Keep the orchestrator DBMS-agnostic: no SQL/Cypher, no dedupe (sinks own that).

Note: buffering per partition means peak memory ≈ one read chunk + open partition buffers (< 1 chunk each until flushed) — constant in file size. Concatenate buffered `part_df`s with `pd.concat` at flush time.

- [ ] **Step 4: Run tests + Step 5: Commit**

```bash
git add src/polyglotimportcsv/dbms_sink.py src/polyglotimportcsv/stream_runner.py tests/test_stream_runner.py
git commit -m "feat(stream): DbmsSink protocol + bounded-memory orchestrator (fake-tested)"
```

---

## Task 4: Extract shared write helpers + `PostgresSink` + `MongoSink`

**Files:**
- Modify: `importers/postgres_importer.py`, `importers/mongodb_importer.py` (extract row-shaping/batched-write helpers to module-level, reused by sinks).
- Create: `src/polyglotimportcsv/sinks/__init__.py`, `sinks/postgres_sink.py`, `sinks/mongo_sink.py`.
- Test: `tests/test_sinks.py` (fake DB client per sink).

**Interfaces:**
- Produces: `PostgresSink(backend_cfg, *, connection_factory=...)`, `MongoSink(backend_cfg, *, client_factory=...)` implementing `DbmsSink`. Each `write_batch` shapes the cast batch into the DBMS payload (reusing the importer's existing row-shaping) and writes it via the batched API (`execute_values`/`insert_many`). `create_schema` runs the same DDL the materialize importer runs. `ensure_partition` creates the per-`each`-partition table/collection if absent.

- [ ] Steps: For each sink, write a fake-client test (no live DB) asserting `write_batch` issues one batched write per call with the right row count and shaped payload; `create_schema` issues DDL; injected factory. Extract the importer's row-shaping into a shared function both the importer and the sink call. TDD RED→GREEN. Commit:
```bash
git add src/polyglotimportcsv/sinks/ src/polyglotimportcsv/importers/postgres_importer.py src/polyglotimportcsv/importers/mongodb_importer.py tests/test_sinks.py
git commit -m "feat(stream): PostgresSink + MongoSink reusing shared write helpers"
```

*(The implementer reads the two importers to extract helpers; the reviewer verifies the materialize importers still behave identically — their tests must stay green.)*

---

## Task 5: `CassandraSink` + `RedisSink` + `Neo4jSink`

**Files:**
- Create: `sinks/cassandra_sink.py`, `sinks/redis_sink.py`, `sinks/neo4j_sink.py`.
- Modify: the three importers to share their batched-write/row-shaping helpers.
- Test: extend `tests/test_sinks.py`.

**Interfaces:**
- Produces: `CassandraSink` (concurrency 64 within `write_batch`), `RedisSink` (pipeline per `write_batch`), `Neo4jSink` (UNWIND per `write_batch`, and it **owns first-wins dedupe** via a per-entity seen-key set kept across `write_batch` calls). All reuse the importer helpers from Tasks 3–5 of the previous plan.

- [ ] Steps: per sink, fake-client TDD test (batch write shape, dedupe for Neo4j across two `write_batch` calls). Commit:
```bash
git add src/polyglotimportcsv/sinks/ src/polyglotimportcsv/importers/ tests/test_sinks.py
git commit -m "feat(stream): Cassandra/Redis/Neo4j sinks reusing batched-write helpers"
```

---

## Task 6: Memory-bound + equivalence tests

**Files:**
- Test: `tests/test_stream_memory.py`

**Interfaces:** none new.

- [ ] **Memory-bound test:** stream 10k vs 50k rows (generated to `tmp_path` via `benchmark_data.generate_dataset`) through a `_FakeSink` under `tracemalloc.reset_peak()`; assert the 50k peak is within a small factor of the 10k peak (e.g. `peak_50k < 2.0 * peak_10k`), proving memory does not scale with total rows.
- [ ] **Equivalence test:** collect all rows a `_FakeSink` receives from `run_stream_import` and compare (partition, sorted key values) to what the materialize path (`run_import` dry-run + resolver cast) produces for the same input — same partitions, same row counts, same casts.
- [ ] Commit:
```bash
git add tests/test_stream_memory.py
git commit -m "test(stream): bounded-memory proof + stream/materialize equivalence"
```

---

## Task 7: `execution` axis in runner + CLI

**Files:**
- Modify: `src/polyglotimportcsv/runner.py`, `src/polyglotimportcsv/cli.py`
- Test: `tests/test_cli.py`, `tests/test_runner_registry.py`

**Interfaces:**
- Produces: `run_import(..., execution: str = "stream")`; when `stream`, dispatch to `run_stream_import` with the real sink factories (a `default_sink_factories()` registry mapping DBMS→sink); when `materialize`, the existing path unchanged. CLI `--execution {stream,materialize}` default `stream` → threaded into `run_import`.

- [ ] TDD: CLI passes `execution` (monkeypatch `run_import`); runner dispatches to a fake stream function when `execution="stream"`. Commit:
```bash
git add src/polyglotimportcsv/runner.py src/polyglotimportcsv/cli.py tests/test_cli.py tests/test_runner_registry.py
git commit -m "feat(cli): --execution {stream,materialize} (default stream)"
```

---

## Task 8: `execution` axis + `peak_memory_mb` in benchmark

**Files:**
- Modify: `benchmark_runner.py`, `benchmark_results.py`, `benchmark_io.py`, `scripts/run_benchmarks.py`
- Test: `tests/test_benchmark_runner.py`, `tests/test_benchmark_results.py`

**Interfaces:**
- Produces: `run_matrix(..., executions=("stream",))` iterating execution modes (validated like modes/strategies); labeled runs gain `"execution"`; `median_results` keys on it; `_RESULT_FIELDS` gains `"execution"` after `"strategy"` and `"peak_memory_mb"` at the end. `run_matrix` measures peak via `tracemalloc` around each import and records `peak_memory_mb` per labeled run. `run_benchmarks.py` gains `--executions`.

- [ ] TDD mirroring the Task 7 strategy-axis change from the previous plan (validate unknown execution; update fake importers/`_run` helper to accept/emit `execution`). Commit:
```bash
git add src/polyglotimportcsv/benchmark_runner.py src/polyglotimportcsv/benchmark_results.py src/polyglotimportcsv/benchmark_io.py scripts/run_benchmarks.py tests/test_benchmark_runner.py tests/test_benchmark_results.py
git commit -m "feat(benchmarks): execution axis + peak_memory_mb (materialize vs stream)"
```

---

## Task 9: Full suite green + README streaming docs

**Files:**
- Modify: `README.md` (EN/PT)
- Test: whole suite

- [ ] Run `./.venv/Scripts/python.exe -m pytest tests -q` → all green.
- [ ] README EN+PT: document `--execution stream` (default; bounded memory) vs `--execution materialize` (phase baseline); note `--executions` in the benchmark and the `peak_memory_mb` column.
- [ ] Commit:
```bash
git add README.md
git commit -m "docs(readme): document streaming (bounded-memory) execution"
```

- [ ] **Manual validation (user, live DBs):** with the container up, `python -m polyglotimportcsv --config data/ecommerce/import_config.json` (stream by default) and a benchmark `--executions materialize,stream` to compare `peak_memory_mb`.

---

## Self-Review

**Spec coverage:** StreamReader §4.1→T1; binding/inference §6→T2; DbmsSink+orchestrator §4.2-4.3,§5→T3; sinks §10 seq 3-4→T4-T5; memory/equivalence tests §9→T6; execution axis+CLI §3→T7; benchmark peak-memory §8→T8; docs+green §10 seq 6→T9. Covered.

**Placeholder note:** Tasks 4/5/8 give interfaces + step outlines rather than full code because they mechanically reuse existing importer helpers and mirror the previous plan's axis-threading pattern; the SDD implementer reads the named source files and the reviewer verifies. Tasks 1-3, 6-7 carry concrete code/tests.

**Type consistency:** `EntityBinding(cfg,kinds,source_name)` defined T2, used T3-T5; `DbmsSink` method signatures fixed T3, implemented T4-T5; `SinkFactory` T3; `execution` default `"stream"` T7-T8; `READ_CHUNK=8192`/`BATCH=1000` constants consistent.
