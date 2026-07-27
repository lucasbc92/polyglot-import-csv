# Streaming Neo4j Relationships Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `--execution stream` write Neo4j relationships (not just nodes) in bounded memory, matching the materialize graph, via a second streaming pass over the relationship source files.

**Architecture:** Pass 1 (unchanged) streams every source and writes nodes. A new **pass 2**, run per DBMS after all nodes are committed and before `sink.close()`, re-streams only the sources the relationships need (one read per source, filtered), reruns pass-1's per-chunk pipeline (union-reindex → non-`each` filter → cast) via a shared `_process_chunk` helper, and hands each cast chunk to `Neo4jSink.write_relationships`, which MERGEs edges with the existing `UNWIND … MATCH … MERGE` batching. The pass is gated on `getattr(sink, "write_relationships", None)`, so only `Neo4jSink` participates; the other four sinks are untouched.

**Tech Stack:** Python 3.12, pandas, pytest, neo4j driver (fake-driver tests only; no live DB).

## Global Constraints

- No new third-party dependencies. Edges reuse `importers.neo4j_importer` helpers.
- `BATCH = 1000` (DBMS flush granularity); streaming is always vectorized cast + batched writes (no "naive streaming").
- The write port is **`DbmsSink`** (never "Backend"); `write_relationships` is a Neo4j-only capability method, NOT added to the `DbmsSink` Protocol.
- Missing-endpoint edges are **silently skipped** (Cypher `MATCH` matches nothing), exactly as materialize does — no warning, no count. Do not add divergent logging.
- `materialize` path stays byte-for-byte unchanged; this plan only touches the streaming path and `Neo4jSink`.
- All new tests run without live databases (injected fake driver / fake sink / dry-run).
- Code/identifiers/comments English; specs/plans Portuguese-friendly but code stays English.
- Commit after each task; push after each commit. Test command: `./.venv/Scripts/python.exe -m pytest tests -q` (baseline before this plan: **235 passed, 1 skipped**).

---

## File Structure

**Modified:**
- `src/polyglotimportcsv/stream_runner.py` — extract `_process_chunk(chunk, ecfg, binding)` (shared by node loop + rel pass); add per-DBMS relationship second pass (source filtering, single re-stream, dispatch, fold edge counts into the return).
- `src/polyglotimportcsv/sinks/neo4j_sink.py` — add `write_relationships(...)`; drop the nodes-only warning; import `_rel_rows_for_batch` + `_merge_rels_batched`.

**Test files touched:**
- `tests/test_stream_runner.py` — fake graph sink records `write_relationships`; asserts ordering (after nodes), shaping, batching.
- `tests/test_sinks.py` — `Neo4jSink.write_relationships` UNWIND payload; warning removed / no-warning tests updated.
- `tests/test_stream_memory.py` — equivalence oracle for the real `PURCHASED` edge, streamed vs. materialized.

---

## Task 1: Extract `_process_chunk` helper (pure refactor, no behavior change)

**Files:**
- Modify: `src/polyglotimportcsv/stream_runner.py`
- Test: whole suite (behavior-preserving; existing stream tests are the guard)

**Interfaces:**
- Produces: `_process_chunk(chunk: pd.DataFrame, ecfg: Dict[str, Any], binding: EntityBinding) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]` returning `(cast_frame, filters)` where `cast_frame` is the chunk after union-reindex + non-`each` filters + `cast_frame(..., strategy="optimized")`, and `filters` is `binding.cfg.get("filters") or []` (returned so the node loop can pass it to `expand_each`). Consumed by the node loop (Task 1) and the relationship pass (Task 3).

- [ ] **Step 1: Add the helper**

Insert above `run_stream_import` in `stream_runner.py`:

```python
def _process_chunk(
    chunk: pd.DataFrame,
    ecfg: Dict[str, Any],
    binding: EntityBinding,
) -> "tuple[pd.DataFrame, List[Dict[str, Any]]]":
    """Run one chunk through the shared per-entity pipeline.

    Union entities are widened to the binding's superset (data_cols + _source,
    missing filled ""); then non-`each` filters and the vectorized cast are
    applied. Returns (cast_frame, filters) so the node loop can `expand_each`
    on the same filters. Reused by the node loop and the relationship pass so
    both shape rows identically.
    """
    working = chunk
    if isinstance(ecfg.get("source"), list):
        working = chunk.reindex(columns=list(binding.kinds.keys()), fill_value="")
    filters = binding.cfg.get("filters") or []
    non_each = [f for f in filters if f.get("operator") != "each"]
    filtered = apply_filters(working, non_each, binding.kinds)
    casted = cast_frame(filtered, binding.kinds, strategy="optimized")
    return casted, filters
```

- [ ] **Step 2: Replace the inline pipeline in the node loop**

In `run_stream_import`, replace the block from `binding = bindings[ename]` through the `casted = cast_frame(...)` line (the `working`/`filters`/`non_each`/`filtered`/`casted` lines, currently `stream_runner.py:188-200`) with:

```python
                binding = bindings[ename]
                casted, filters = _process_chunk(chunk, ecfg, binding)
```

Leave the following `for partition_name, part_df in expand_each(casted, filters, ename):` loop unchanged.

- [ ] **Step 3: Run the stream tests to confirm no behavior change**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_stream_runner.py tests/test_stream_memory.py tests/test_stream_source.py tests/test_stream_binding.py -q`
Expected: PASS (same counts as before — this is a pure extraction).

- [ ] **Step 4: Commit**

```bash
git add src/polyglotimportcsv/stream_runner.py
git commit -m "refactor(stream): extract _process_chunk shared by node + rel passes"
```

---

## Task 2: `Neo4jSink.write_relationships` (fake-driver TDD)

**Files:**
- Modify: `src/polyglotimportcsv/sinks/neo4j_sink.py`
- Test: `tests/test_sinks.py`

**Interfaces:**
- Consumes: `_rel_rows_for_batch`, `_merge_rels_batched` from `importers.neo4j_importer`; `flat_leaf_columns`, `target_field_name`, `resolve_csv_column` from `entity_utils`; `EntityBinding` (has `.cfg`).
- Produces: `Neo4jSink.write_relationships(rname: str, rspec: Dict[str, Any], from_binding: EntityBinding, to_binding: EntityBinding, batch: pd.DataFrame) -> int`. Shapes edge rows from `batch` (the `from` entity's cast chunk, which carries both foreign keys) and MERGEs them via one `UNWIND … MATCH … MERGE` payload; returns the edge count. Missing endpoints are skipped by `_rel_rows_for_batch` (it drops rows where `a_id`/`b_id` is `None`) and by Cypher `MATCH` — no warning.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_sinks.py` (near the other Neo4j tests). It reuses `_FakeNeoDriver`/`_user_sample` already in the file and the real `PURCHASED` rel spec + `Product` entity from the loaded config:

```python
NEO4J_PRODUCT_CFG = NEO4J_CFG["entities"]["Product"]
PURCHASED_RSPEC = NEO4J_CFG["relationships"]["PURCHASED"]


def _purchase_rel_chunk():
    # The 'from' (User) source is 'purchase', which carries user_id, product_id
    # (the two endpoint FKs) plus the edge props order_number/quantity/price/rating.
    return pd.DataFrame(
        {
            "user_id": ["u1", "u2"],
            "product_id": ["p1", "p2"],
            "order_number": ["o1", "o2"],
            "quantity": ["1", "2"],
            "price": ["10", "20"],
            "rating": ["5", "4"],
            SOURCE_COLUMN: ["purchase", "purchase"],
        }
    )


def test_neo4j_write_relationships_unwind_merges_edges():
    rec = {"run": [], "tx_run": []}
    driver = _FakeNeoDriver(rec)
    sink = Neo4jSink({"connection": {}}, driver_factory=lambda c: driver)

    from_binding = bind_entity_from_sample("User", NEO4J_USER_CFG, _user_sample(["u1", "u2"]), "purchase")
    to_binding = bind_entity_from_sample(
        "Product", NEO4J_PRODUCT_CFG,
        pd.DataFrame({"product_id": ["p1", "p2"], "product_name": ["a", "b"],
                      "product_brand": ["x", "y"], SOURCE_COLUMN: ["stock", "stock"]}),
        "stock",
    )

    count = sink.write_relationships("PURCHASED", PURCHASED_RSPEC, from_binding, to_binding, _purchase_rel_chunk())

    assert count == 2
    rel_batches = [p for q, p in rec["tx_run"] if "UNWIND" in q and "MERGE (a)" in q]
    assert len(rel_batches) == 1
    payload = rel_batches[0]["batch"]
    assert {r["a_id"] for r in payload} == {"u1", "u2"}
    assert {r["b_id"] for r in payload} == {"p1", "p2"}
    # order_number is the edge's is_key -> travels in the mk block, not rprops
    assert all("order_number" in r["mk"] for r in payload)


def test_neo4j_write_relationships_skips_null_endpoints():
    rec = {"run": [], "tx_run": []}
    driver = _FakeNeoDriver(rec)
    sink = Neo4jSink({"connection": {}}, driver_factory=lambda c: driver)

    from_binding = bind_entity_from_sample("User", NEO4J_USER_CFG, _user_sample(["u1"]), "purchase")
    to_binding = bind_entity_from_sample(
        "Product", NEO4J_PRODUCT_CFG,
        pd.DataFrame({"product_id": ["p1"], "product_name": ["a"],
                      "product_brand": ["x"], SOURCE_COLUMN: ["stock"]}),
        "stock",
    )
    # A genuinely null endpoint key (None, as an all-NaN cast column would yield)
    # is dropped by _rel_rows_for_batch. An empty string, by contrast, survives
    # here and is skipped later by Cypher MATCH (not exercised by the fake
    # driver) -- both match the materialize path, which uses the same helper.
    chunk = pd.DataFrame(
        {"user_id": ["u1", None], "product_id": ["p1", "p2"], "order_number": ["o1", "o2"],
         "quantity": ["1", "2"], "price": ["10", "20"], "rating": ["5", "4"],
         SOURCE_COLUMN: ["purchase", "purchase"]}
    )

    count = sink.write_relationships("PURCHASED", PURCHASED_RSPEC, from_binding, to_binding, chunk)

    # The row with a null user_id (a_id None) is dropped; only 1 edge shaped.
    assert count == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_sinks.py::test_neo4j_write_relationships_unwind_merges_edges -v`
Expected: FAIL — `AttributeError: 'Neo4jSink' object has no attribute 'write_relationships'`.

- [ ] **Step 3: Implement**

In `sinks/neo4j_sink.py`, extend the imports from `importers.neo4j_importer` to include the rel helpers:

```python
from polyglotimportcsv.importers.neo4j_importer import (
    _default_neo4j_driver,
    _dedupe_props,
    _merge_nodes_batched,
    _merge_rels_batched,
    _rel_rows_for_batch,
    _sanitize_label,
    props_from_row,
)
```

Also import `resolve_csv_column` alongside the existing `entity_utils` imports:

```python
from polyglotimportcsv.entity_utils import flat_leaf_columns, resolve_csv_column, target_field_name
```

Add the method to `Neo4jSink` (after `write_batch`):

```python
    def write_relationships(
        self,
        rname: str,
        rspec: Dict[str, Any],
        from_binding: EntityBinding,
        to_binding: EntityBinding,
        batch: pd.DataFrame,
    ) -> int:
        """MERGE one chunk of edges; endpoints must already exist (pass 2).

        ``batch`` is the ``from`` entity's cast chunk, which carries both
        foreign keys plus edge props. Rows with a missing endpoint key are
        dropped (by ``_rel_rows_for_batch``) and, if a node is nonetheless
        absent, Cypher ``MATCH`` silently creates no edge -- matching the
        materialize path.
        """
        from_label = _sanitize_label(rspec["from"])
        to_label = _sanitize_label(rspec["to"])
        rel_type = _sanitize_label(rspec.get("type") or rname)
        from_key_col = [(fk, sp) for fk, _, sp in flat_leaf_columns(from_binding.cfg) if sp.get("is_key")][0]
        to_key_col = [(fk, sp) for fk, _, sp in flat_leaf_columns(to_binding.cfg) if sp.get("is_key")][0]
        from_key = target_field_name(*from_key_col)
        to_key = target_field_name(*to_key_col)
        cols = list(batch.columns)
        from_src = resolve_csv_column(from_key_col[0], from_key_col[1], cols)
        to_src = resolve_csv_column(to_key_col[0], to_key_col[1], cols)
        rel_cols = rspec.get("columns") or {}
        mk_names = [target_field_name(fk, spec) for fk, spec in rel_cols.items() if spec.get("is_key")]
        rows = _rel_rows_for_batch(batch, from_src, to_src, rel_cols, mk_names)
        if not rows:
            return 0
        return _merge_rels_batched(
            self._session, from_label, from_key, to_label, to_key,
            rel_type, mk_names, rows, advance=lambda n: None,
        )
```

- [ ] **Step 4: Run tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_sinks.py -k neo4j -v`
Expected: the two new tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/sinks/neo4j_sink.py tests/test_sinks.py
git commit -m "feat(stream): Neo4jSink.write_relationships (UNWIND MATCH MERGE, reuses importer helpers)"
```

---

## Task 3: Drop the nodes-only warning

**Files:**
- Modify: `src/polyglotimportcsv/sinks/neo4j_sink.py`
- Test: `tests/test_sinks.py`

**Interfaces:** none new.

- [ ] **Step 1: Update the warning tests**

In `tests/test_sinks.py`, `test_neo4j_logs_nodes_only_warning_when_relationships_declared` asserts the warning IS logged — that behavior is going away. Replace that test with one asserting NO nodes-only warning even when relationships are declared:

```python
def test_neo4j_no_nodes_only_warning_when_relationships_declared(caplog):
    rec = {"run": [], "tx_run": []}
    driver = _FakeNeoDriver(rec)

    with caplog.at_level(logging.WARNING, logger="polyglotimportcsv.sinks.neo4j_sink"):
        Neo4jSink(NEO4J_CFG, driver_factory=lambda c: driver)

    warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert not any("nodes only" in m for m in warnings)
```

Leave `test_neo4j_no_warning_when_no_relationships_declared` as-is (still valid).

- [ ] **Step 2: Run to verify the old assertion now fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_sinks.py::test_neo4j_no_nodes_only_warning_when_relationships_declared -v`
Expected: FAIL — the constructor still logs "streaming imports nodes only".

- [ ] **Step 3: Remove the warning**

In `sinks/neo4j_sink.py` `Neo4jSink.__init__`, delete:

```python
        if backend_cfg.get("relationships"):
            logger.warning(
                "[neo4j] streaming imports nodes only; relationships require --execution materialize"
            )
```

Update the module docstring's "NODES ONLY" paragraph (lines 4-8) to state that relationships are written via a second pass driven by `stream_runner` calling `write_relationships`.

- [ ] **Step 4: Run tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_sinks.py -k neo4j -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/sinks/neo4j_sink.py tests/test_sinks.py
git commit -m "feat(stream): drop Neo4jSink nodes-only warning (rels now streamed)"
```

---

## Task 4: Relationship second pass in `run_stream_import`

**Files:**
- Modify: `src/polyglotimportcsv/stream_runner.py`
- Test: `tests/test_stream_runner.py`

**Interfaces:**
- Consumes: `_process_chunk` (Task 1); `sink.write_relationships` (Task 2, capability-detected via `getattr`); `bindings` cache (already built in pass 1); `iter_entity_chunks`; `_matches`.
- Produces: after pass 1, `run_stream_import` runs a per-DBMS relationship pass and folds edge counts into the returned dict under key `f":{rel_type}"`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_stream_runner.py`. The `_FakeSink` there must gain relationship-recording. First extend `_FakeSink` with a `write_relationships` that records call order relative to node writes:

```python
    # add to _FakeSink.__init__:
        self.calls = []          # ordered log of ("node", partition) / ("rel", rname)
        self.rel_rows = {}       # rname -> total rows received

    # add to _FakeSink.write_batch (record ordering), at the top:
        self.calls.append(("node", partition_name))

    # add new method to _FakeSink:
    def write_relationships(self, rname, rspec, from_binding, to_binding, batch):
        self.calls.append(("rel", rname))
        self.rel_rows[rname] = self.rel_rows.get(rname, 0) + len(batch)
        return len(batch)
```

Then the test:

```python
def test_stream_import_writes_relationships_after_all_nodes(tmp_path):
    # Two node entities from two sources + one relationship whose 'from' is User
    # (source 'people', carrying both FKs person_id and thing_id).
    _write_csv(tmp_path / "people.csv", ["person_id", "thing_id", "weight"],
               [(f"u{i}", f"t{i}", i) for i in range(3)])
    _write_csv(tmp_path / "things.csv", ["thing_id", "label"],
               [(f"t{i}", f"L{i}") for i in range(3)])
    config = {
        "sources": {"people": "people.csv", "things": "things.csv"},
        "neo4j": {
            "entities": {
                "User": {"source": "people", "columns": {"person_id": {"is_key": True}}},
                "Thing": {"source": "things", "columns": {"thing_id": {"is_key": True}}},
            },
            "relationships": {
                "LIKES": {"from": "User", "to": "Thing", "type": "LIKES",
                          "columns": {"weight": {}}},
            },
        },
    }
    fake = _FakeSink()

    written = sr.run_stream_import(
        config, tmp_path, sink_factories={"neo4j": lambda cfg: fake}, batch=1000
    )

    # (a) edges recorded and counted under the rel_type key
    assert fake.rel_rows == {"LIKES": 3}
    assert written[":LIKES"] == 3
    assert written["User"] == 3 and written["Thing"] == 3

    # (b) every node write happens before the first relationship write
    first_rel = next(i for i, c in enumerate(fake.calls) if c[0] == "rel")
    assert all(c[0] == "node" for c in fake.calls[:first_rel])

    # (c) the relationship pass drives from the User source, resolving both
    #     endpoints' FKs from that one frame
    assert fake.closed is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_stream_runner.py::test_stream_import_writes_relationships_after_all_nodes -v`
Expected: FAIL — no `write_relationships` is ever called (`fake.rel_rows == {}`), so the `written[":LIKES"]` assertion raises `KeyError`.

- [ ] **Step 3: Implement the pass**

In `stream_runner.py`, add a helper above `run_stream_import`:

```python
def _relationship_from_source_decls(
    relationships: Dict[str, Any],
    entities: Dict[str, Any],
    sources_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Sources feeding any relationship's `from` entity (scalable re-read: one
    read per needed source, not per relationship).

    A `from` entity's source is its `source` (str), its own name if `source` is
    absent, or every element of a `list` (union) source. If any needed element
    is a combined-CSV origin (not a str key in `sources_cfg`), include every
    combined (dict) declaration so its origins are produced.
    """
    needed_keys: set = set()
    needs_combined = False
    str_keys = {k for k, v in sources_cfg.items() if isinstance(v, str)}
    for rspec in (relationships or {}).values():
        from_e = rspec.get("from")
        ecfg = entities.get(from_e) or {}
        ref = ecfg.get("source")
        refs = ref if isinstance(ref, list) else [ref if ref is not None else from_e]
        for r in refs:
            if r in str_keys:
                needed_keys.add(r)
            else:
                needs_combined = True
    out = {k: v for k, v in sources_cfg.items() if k in needed_keys}
    if needs_combined:
        out.update({k: v for k, v in sources_cfg.items() if isinstance(v, dict)})
    return out
```

Then, in `run_stream_import`, between the remainder-flush loop and `sink.close()` (currently `stream_runner.py:209-215`), insert the pass:

```python
        for partition_name in list(buffers.keys()):
            _flush_remainder(
                partition_name, buffers, partition_binding,
                seen_partitions, written, sink,
            )

        write_rels = getattr(sink, "write_relationships", None)
        relationships = bcfg.get("relationships") or {}
        if write_rels is not None and relationships:
            rel_sources = _relationship_from_source_decls(
                relationships, entities, config.get("sources") or {}
            )
            # from-entity -> its relationships (drive each from source once)
            from_rels: Dict[str, List[tuple]] = {}
            for rname, rspec in relationships.items():
                from_rels.setdefault(rspec.get("from"), []).append((rname, rspec))
            for yielded_name, chunk in iter_entity_chunks(
                rel_sources, base_dir, source_overrides, chunksize
            ):
                for from_e, rlist in from_rels.items():
                    ecfg = entities.get(from_e)
                    if ecfg is None or not _matches(from_e, ecfg, yielded_name):
                        continue
                    from_binding = bindings.get(from_e)
                    if from_binding is None:
                        continue  # from source had zero rows -> zero nodes -> zero edges
                    casted, _ = _process_chunk(chunk, ecfg, from_binding)
                    for rname, rspec in rlist:
                        to_binding = bindings.get(rspec.get("to"))
                        if to_binding is None:
                            continue  # to entity unbound -> no target nodes -> no edges
                        rel_type = rspec.get("type") or rname
                        n = write_rels(rname, rspec, from_binding, to_binding, casted)
                        key = f":{rel_type}"
                        written[key] = written.get(key, 0) + n

        sink.close()
```

- [ ] **Step 4: Run tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_stream_runner.py -v`
Expected: the new test PASSES; the two existing tests still pass.

- [ ] **Step 5: Commit**

```bash
git add src/polyglotimportcsv/stream_runner.py tests/test_stream_runner.py
git commit -m "feat(stream): relationship second pass (bounded re-stream of rel sources)"
```

---

## Task 5: Equivalence oracle + full suite + docs

**Files:**
- Modify: `tests/test_stream_memory.py`, `README.md` (EN/PT)
- Test: whole suite

**Interfaces:** none new.

- [ ] **Step 1: Write the equivalence test**

Add to `tests/test_stream_memory.py` (it already imports `sr`, `apply_filters`, `resolve_backend_entities`, `load_sources`, `SOURCE_COLUMN`, and has `_ecommerce_config_and_overrides`, `_RecordingSink`, `_compare_columns`). The stream side needs a recording sink that captures `write_relationships` frames; add a small subclass inline, and reproduce the materialize edge shaping with the importer's own helper:

```python
def test_stream_union_and_rel_purchased_matches_materialize():
    """The real neo4j PURCHASED relationship (from 'purchase') streamed vs.
    materialized over data/benchmark/ must yield identical edges."""
    from polyglotimportcsv.importers.neo4j_importer import _rel_rows_for_batch
    from polyglotimportcsv.entity_utils import (
        flat_leaf_columns, resolve_csv_column, target_field_name,
    )

    config, base_dir, overrides = _ecommerce_config_and_overrides()
    dbms = "neo4j"

    class _RelSink(_RecordingSink):
        def __init__(self):
            super().__init__()
            self.rel_frames = {}

        def write_relationships(self, rname, rspec, from_binding, to_binding, batch):
            self.rel_frames.setdefault(rname, []).append(batch.copy())
            return len(batch)

    sink = _RelSink()
    sr.run_stream_import(
        config, base_dir,
        sink_factories={dbms: lambda cfg: sink},
        only=[dbms], source_overrides=overrides, chunksize=8192,
    )
    stream_edges = pd.concat(sink.rel_frames["PURCHASED"], ignore_index=True)

    # --- Materialize edge rows for PURCHASED ---
    sources = load_sources(config["sources"], base_dir, overrides)
    bound = resolve_backend_entities(config[dbms], sources, {}, strategy="optimized")
    rspec = config[dbms]["relationships"]["PURCHASED"]
    from_be = bound[rspec["from"]]
    f1 = [x for x in (from_be.cfg.get("filters") or []) if x.get("operator") != "each"]
    mat_dff = apply_filters(from_be.df, f1, from_be.kinds)

    def _edge_tuples(df):
        fk_from = [(fk, sp) for fk, _, sp in flat_leaf_columns(bound[rspec["from"]].cfg) if sp.get("is_key")][0]
        fk_to = [(fk, sp) for fk, _, sp in flat_leaf_columns(bound[rspec["to"]].cfg) if sp.get("is_key")][0]
        cols = list(df.columns)
        from_src = resolve_csv_column(fk_from[0], fk_from[1], cols)
        to_src = resolve_csv_column(fk_to[0], fk_to[1], cols)
        rel_cols = rspec.get("columns") or {}
        mk_names = [target_field_name(fk, sp) for fk, sp in rel_cols.items() if sp.get("is_key")]
        rows = _rel_rows_for_batch(df, from_src, to_src, rel_cols, mk_names)
        return sorted(
            (str(a), str(b), tuple(sorted((k, str(v)) for k, v in {**rest, **mk}.items())))
            for a, b, rest, mk in rows
        )

    assert _edge_tuples(stream_edges) == _edge_tuples(mat_dff)
    assert len(_edge_tuples(stream_edges)) > 0
```

- [ ] **Step 2: Run the equivalence test**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_stream_memory.py::test_stream_union_and_rel_purchased_matches_materialize -v`
Expected: PASS. If it fails, the streamed edge shaping diverges from materialize — fix in `Neo4jSink.write_relationships` or `_process_chunk`, not in the test.

- [ ] **Step 3: Run the whole suite**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: PASS, zero failures. Baseline was 235 passed / 1 skipped; this plan adds tests (Task 2: +2, Task 4: +1, Task 5: +1) and replaces one warning test (Task 3: net 0), so expect **≥239 passed, 1 skipped**.

- [ ] **Step 4: Update README (EN + PT)**

In `README.md`, the EN `--execution` bullet currently ends the streaming description without mentioning graph edges. Append to the EN bullet (the one at the `--execution stream|materialize` line in the English options list):

> Neo4j relationships are streamed too, in a bounded second pass over the relationship sources after all nodes are written.

Append the PT equivalent to the Portuguese `--execution` bullet:

> Os relacionamentos do Neo4j também são transmitidos, em uma segunda passagem de memória limitada sobre as origens dos relacionamentos, após a escrita de todos os nós.

- [ ] **Step 5: Commit**

```bash
git add tests/test_stream_memory.py README.md
git commit -m "test(stream): PURCHASED edge equivalence + README streaming-rels note"
```

- [ ] **Step 6: Manual validation (user, live DBs — not CI)**

With the stack up (`docker compose up --wait`):

```bash
python -m polyglotimportcsv --config data/ecommerce/import_config.json
```

Expected: the run streams by default and now reports merged `:PURCHASED` relationship(s) alongside the `User`/`Product` nodes — no "nodes only" warning. Cross-check the edge count against a materialize run (`--execution materialize`).

---

## Self-Review

**Spec coverage:** second pass §1 → Task 4 (`_relationship_from_source_decls` scalable re-read, `getattr` gate, `bindings` reuse, unbound-`to` skip); `_process_chunk` refactor → Task 1; `Neo4jSink.write_relationships` §2 (helpers, mk_names, silent skip) → Task 2; drop nodes-only warning → Task 3; folded edge counts under `:rel_type` → Task 4; bounded-memory (one chunk, nothing accumulates) — inherent in Task 4's per-chunk dispatch, no separate probe needed since the node memory test already proves the streaming loop is bounded and the rel pass reuses the same loop; equivalence oracle §Tests → Task 5; missing-endpoint silent skip → Task 2 test + Task 5 (implicit); out-of-scope (non-Neo4j rels, naive) honored.

**Placeholder scan:** none — every step has concrete code, exact run commands, and expected results.

**Type consistency:** `write_relationships(rname, rspec, from_binding, to_binding, batch) -> int` identical in Task 2 (def), Task 4 (call), Task 5 (fake). `_process_chunk(chunk, ecfg, binding) -> (frame, filters)` identical in Task 1 (def) and Task 4 (call, `casted, _ =`). Edge-count key `f":{rel_type}"` consistent Task 4 impl ↔ Task 4 test (`written[":LIKES"]`). `_relationship_from_source_decls(relationships, entities, sources_cfg)` defined and called once, both in Task 4.

**Ordering:** Task 1 (refactor, guarded by existing tests) → Task 2 (sink method, independent) → Task 3 (warning removal, independent of 2 but both touch the sink; sequential to avoid edit conflicts) → Task 4 (needs 1 + 2) → Task 5 (needs all). Strictly sequential; each ends green.
