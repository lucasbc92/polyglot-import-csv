# Design — Union (list) sources in the streaming import path

**Status:** IMPLEMENTED 2026-07-26 (streaming plan Task 10). User approved both
open decisions: implement multi + combined union together ("os dois de uma vez"),
packaged as one appended Task 10 ("task 10 anexada").
**Context:** Plan 2 (streaming import) shipped with union sources *scoped out*
(`run_stream_import` fail-fast: `streaming does not support union (list) sources`).
Task 7 made `--execution stream` the default, so the flagship sample config —
which has a Cassandra `user_activity_log` entity with
`source: ["stock","purchase","select_product","add_to_cart"]` — now fails
out-of-the-box. User chose (2026-07-26) to **support union streaming** rather
than fall back / document a workaround / revert the default.

## Ground truth: how materialize unions sources

`mapping_resolver._union_source(entity_name, names, sources)` (the behaviour the
stream path must reproduce, row-for-row):

1. **Superset columns** `data_cols` = first-seen union of every named source's
   `file_header`, iterated in **union-list order** (stock's cols, then
   purchase's new cols, then select's, then cart's).
2. Reindex each source frame to `data_cols + [_source]`, **missing cells filled
   with `""`** (empty string, not NaN).
3. `pd.concat` the reindexed frames (rows stacked in union-list order).
4. `kinds = infer_column_kinds(concat[data_cols])`; `kinds[_source] = "string"`.
5. `_source` per row = the originating source name (each part already carries
   its own `_source`, preserved by the reindex).

The entity then maps columns via `expand_entity_columns` (for
`user_activity_log`: **manual** columns selecting a subset of the superset, incl.
`_source → event_type`, `order_number` (purchase-only), `selected_product_id`
(select-only), etc.).

**Two facts drive the design:**
- **Multi mode** unions *heterogeneous* schemas (separate files: 20/33/6/7 data
  cols) → the superset and `kinds` genuinely need all sources' columns.
- **Combined mode** unions *homogeneous* schemas: one CSV routed by origin, so
  every origin shares identical columns → superset = the combined file's data
  cols; no heterogeneity problem.

## Streaming design

Two globals need all-source knowledge — the **superset column order** and the
**kinds**. Everything downstream (filter → cast → expand → buffer → flush) is
already per-chunk and unchanged. So:

### 1. Eager per-source sample bind for union entities
On first encounter of a union entity (source is a `list`), build its
`EntityBinding` from a **one-chunk sample of each named source**, mirroring
`_union_source` on samples instead of full frames:
- For each source name in union-list order: resolve its path
  (`stream_source._resolve_path`) and read just its **first chunk**
  (`stream_source._read_chunks`, `next(...)`). Combined mode: read the first
  chunk of the combined file and route by origin (homogeneous cols, so any
  origin's sample gives the full column set).
- Build `data_cols` = first-seen union across those samples' columns (same order
  rule as `_union_source`).
- Reindex each sample to `data_cols + [_source]` (fill `""`), `pd.concat`,
  `infer_column_kinds(sample[data_cols])`, `kinds[_source]="string"`.
- Produce `cfg` via `expand_entity_columns` exactly as `resolve_backend_entities`
  does; return `EntityBinding(cfg, kinds, source_name="+".join(names))`.

Reading only the first chunk of each source keeps this **bounded** (one chunk ×
number-of-union-sources, constant in total rows). A shared column-union helper
is extracted so `_union_source` and the stream binding compute `data_cols`
identically (single source of truth for the ordering rule).

### 2. Per-chunk reindex to the superset
When a chunk arrives from a source that feeds a union entity, **reindex it to the
binding's superset** (`data_cols + [_source]`, fill `""`) before
`apply_filters → cast_frame → expand_each`. A `stock` chunk thus gains empty
`order_number`/`selected_product_id`/… columns, so cast/expand/write see exactly
what materialize's concatenated frame carried. Peak stays ≈ one chunk × superset
width (still constant in total rows).

### 3. `_matches` handles list sources
`stream_runner._matches`: a chunk feeds a union entity when
`yielded_name in ecfg["source"]` (list case), alongside the existing str / name
cases.

### 4. Remove the fail-fast
Delete `_validate_no_union_sources` (and its call). Empty-list `source: []` stays
an error (reuse the `bind_entity_source` empty-list message / `ImportExecutionError`).

## Bounded-memory argument (must survive the T6 proof)
- Sample bind reads 1 chunk per union source, once, at bind time — O(sources),
  not O(rows).
- Per-chunk reindex widens a chunk to the superset but never accumulates across
  chunks; buffers still flush at `BATCH`.
- **Rejected alternative:** "defer bind until a chunk from every union source is
  seen." In multi mode sources are read one-file-at-a-time, so this would buffer
  all of stock+purchase+select before binding on cart — O(rows), breaks the
  bound. Eager sampling avoids it.

## Files
- `src/polyglotimportcsv/mapping_resolver.py` — extract shared `data_cols`
  ordering helper (used by `_union_source` + stream binding).
- `src/polyglotimportcsv/stream_binding.py` — `bind_union_entity_from_samples(...)`
  (or extend `bind_entity_from_sample`) building the superset binding.
- `src/polyglotimportcsv/stream_source.py` — small helper to read one source's
  first chunk given `sources_cfg` + name (multi + combined origin routing).
- `src/polyglotimportcsv/stream_runner.py` — `_matches` list case; lazy union
  bind on first encounter; per-chunk reindex; drop `_validate_no_union_sources`.

## Tests (all DB-free)
- `test_stream_runner.py`: union entity over 2 fake multi sources with disjoint
  columns → fake sink receives rows with the superset columns, missing filled
  `""`, `_source` correct; batch boundaries intact.
- `test_stream_memory.py` (extend equivalence): the **real** `user_activity_log`
  union over the committed `data/benchmark/` reference — streamed vs materialized
  rows identical (same partition, count, key/data values incl. `_source`-derived
  `event_type`). This is the correctness oracle.
- Bounded-memory: confirm union path doesn't scale peak with rows (reuse the
  T6 probe with a union config).
- Empty `source: []` → `ImportExecutionError`.

## Open decisions to confirm on resume
1. **Combined-mode union**: design covers it (homogeneous cols), but the failing
   case is multi mode. Confirm whether to implement+test combined-union now or
   land multi first and follow up. (Recommendation: land both — combined is the
   easy sub-case and the equivalence test already exercises combined elsewhere.)
2. **Packaging**: implement as one new task appended to the streaming plan
   (`Task 10: union-source streaming`) via the same per-task commit+push+ledger
   flow, or as a standalone mini-plan. (Recommendation: one appended task.)
