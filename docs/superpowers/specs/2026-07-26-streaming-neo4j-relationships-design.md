# Design — Neo4j relationships in the streaming import path

**Status:** design defined 2026-07-26, awaiting user approval before implementation.
**Context:** Plan 2 (streaming import) shipped `Neo4jSink` as **nodes only**. A
config with `relationships` logs `[neo4j] streaming imports nodes only;
relationships require --execution materialize` and skips every edge, so
`--execution stream` (the default) never produces a full graph for the sample
config (`neo4j/PURCHASED`). User chose (2026-07-26) to support relationship
streaming.

## Ground truth: how materialize writes relationships

`importers/neo4j_importer.run_neo4j_import` writes edges in a **second pass,
after all nodes** (`neo4j_importer.py:251-293`):

1. Nodes for every entity are MERGE'd first (pass 1).
2. Then, per relationship: read the **`from` entity's frame** (`from_be.df`),
   which carries *both* foreign keys (`from_src` and `to_src` are both resolved
   against `from_be.df.columns`) plus the edge props. Apply the `from` entity's
   **non-`each`** filters, then `UNWIND $batch AS row MATCH (a),(b) MERGE
   (a)-[r]->(b)` in `BATCH`-sized groups (`_rel_rows_for_batch` +
   `_merge_rels_batched`).
3. `MATCH` silently matches nothing when an endpoint node is absent, so an edge
   whose key has no node is **silently skipped** (no warning, no count).

**Two facts drive the design:**
- **Ordering:** every node of both endpoint labels must exist before an edge's
  `MATCH`. Materialize gets this from its two-pass structure; streaming has no
  "all nodes done" moment until the pass ends.
- **Boundedness:** an edge's rows come from a *single* frame (the `from`
  source), written in `UNWIND` batches. So relationships are as bounded as
  nodes — the only missing piece is the ordering guarantee.

## Streaming design: a bounded second pass

Add a **second streaming pass per DBMS**, run after pass 1 (all nodes committed)
and before `sink.close()`. It re-streams each relationship's `from` source in
chunks and MERGEs edges. Peak memory = one chunk of edge rows; correctness comes
from nodes already existing. The only cost is re-reading the relationship
sources once (I/O, not memory).

### 1. Orchestrator owns iteration/binding/casting; sink owns Cypher
The split from Plan 2 is preserved. In `run_stream_import`, after the node loop
for a DBMS:

- Skip unless `backend_cfg` has `relationships` **and** the sink exposes the
  capability: `write_rels = getattr(sink, "write_relationships", None)`. The
  other four sinks don't define it and are untouched (no `DbmsSink` protocol
  bloat; Postgres FKs stay `close()`-time DDL).
- **Filter the sources to only those the relationships need** (scalable re-read
  — one read per needed source, regardless of relationship count). For each
  relationship's `from` entity, resolve the source key(s) it reads: a `str`
  `source` (or a `None` source defaulting to the entity name) that is a `str`
  declaration in `sources` → that key; a `list` (union) → each element. Build
  `needed_str_keys` = those that are `str`-declared source keys. If any needed
  element is **not** a `str` key (i.e. a combined-CSV origin value), also
  include every combined (`dict`) declaration. `filtered_sources` = the `str`
  decls in `needed_str_keys` (plus all combined decls when required).
- **Single re-stream** `iter_entity_chunks(filtered_sources, …)`. Per yielded
  `(source_name, chunk)`: for each `from` entity matching that yield
  (`_matches`), run the **same per-chunk pipeline as pass 1** — union-reindex
  (if the `from` entity is a union) → non-`each` filters → `cast_frame` — once
  per `(from_entity, chunk)` (cache within the chunk). Then for each
  relationship whose `from` is that entity, call
  `sink.write_relationships(rname, rspec, from_binding, to_binding, cast_chunk)`.
- `from_binding` / `to_binding` come from the pass-1 `bindings` cache. If the
  `to` entity is unbound (its source produced zero rows → zero target nodes),
  skip the relationship: no node can match, so materialize would MERGE zero
  edges too.

**Refactor:** extract pass 1's "chunk → filtered + cast frame" steps into a
small `_process_chunk(chunk, ecfg, binding)` helper reused by the node loop and
the relationship pass (no duplicated reindex/filter/cast logic).

### 2. `Neo4jSink.write_relationships`
New method (present only on `Neo4jSink`):

```
write_relationships(rname, rspec, from_binding, to_binding, batch) -> int
```

- `from_label/to_label` = sanitize(`rspec["from"]` / `rspec["to"]`); `rel_type`
  = sanitize(`rspec.get("type") or rname`).
- `from_key/to_key` = the single `is_key` column of `from_binding.cfg` /
  `to_binding.cfg` (via `flat_leaf_columns` + `target_field_name`, as the
  importer does).
- `from_src/to_src` resolved against `batch.columns` (both live in the `from`
  frame).
- `mk_names` = the `is_key` entries of `rspec.get("columns")` mapped through
  `target_field_name` (the edge's own key props, as in the importer).
- `rows = _rel_rows_for_batch(batch, from_src, to_src, rspec.get("columns") or
  {}, mk_names)`; `_merge_rels_batched(self._session, from_label, from_key,
  to_label, to_key, rel_type, mk_names, rows, advance=noop)`.
- Reuses the importer's existing helpers verbatim; edges need no dedupe (MERGE
  is idempotent). Returns the edge count.

The nodes-only warning in `Neo4jSink.__init__` is **removed** (streaming now
writes edges via the second pass). Edge counts are folded into
`run_stream_import`'s returned `{partition: rows}` under a `f":{rel_type}"` key
so the stream summary reflects them.

## Bounded-memory argument (must survive the T6-style proof)
- Pass 2 reads one chunk of the `from` source at a time and MERGEs it; nothing
  accumulates across chunks. Peak ≈ one chunk of edge rows — constant in total
  rows, same as the node pass.
- Node MERGEs already made every endpoint exist, so no buffering/join across
  passes is needed.

## Files
- `src/polyglotimportcsv/stream_runner.py` — `_process_chunk` helper; per-DBMS
  relationship second pass (source filtering, single re-stream, dispatch);
  fold edge counts into the return.
- `src/polyglotimportcsv/sinks/neo4j_sink.py` — `write_relationships`; drop the
  nodes-only warning; imports `_rel_rows_for_batch` + `_merge_rels_batched`.

## Tests (all DB-free)
- `test_stream_runner.py`: a fake graph sink recording `write_relationships`
  calls over a 2-entity + 1-relationship config → edge rows shaped correctly
  (a_id/b_id/props), batched ≤ `BATCH`, and only **after** all node writes.
- `test_sinks.py`: `Neo4jSink.write_relationships` against a fake driver →
  correct `MATCH…MERGE` UNWIND payload (endpoints, mk keys, rest props); no
  more nodes-only warning when relationships are declared.
- `test_stream_memory.py` (equivalence oracle): the **real** `neo4j/PURCHASED`
  relationship over the committed `data/benchmark/` reference — streamed edge
  tuples `(from_key, to_key, sorted props)` identical to what the materialize
  importer's relationship pass produces.
- Missing-endpoint edges are **silently skipped** (matches materialize) — the
  equivalence test exercises this implicitly (any FK with no node yields no edge
  in both paths).

## Out of scope
- Non-Neo4j "relationships" (Postgres FKs stay `close()`-time DDL; the other
  sinks have none).
- `naive` streaming (streaming is always vectorized + batched, per Plan 2).
- Grouping edges from *different* `from` entities that share one source into a
  single cast per chunk beyond the per-`(from_entity, chunk)` cache (YAGNI;
  distinct entities need distinct filter/cast anyway).
