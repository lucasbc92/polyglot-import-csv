# Benchmark datasets — index and provenance

Audited 2026-08-01. Four campaigns are current and mutually consistent; everything
in `archive-prefix/` is superseded and must not be used.

`write_consolidated` **appends** to `benchmark_results.csv`. A folder that has been
written twice therefore holds two runs' rows under one filename. Every current
campaign below was verified to hold exactly one run.

## Current data

| Folder | Axes | tracemalloc | Use it for |
|---|---|---|---|
| `.` (root) | 1k/10k/100k × multi/combined × optimized × materialize/stream × 3 | **on** | `peak_memory_mb` only |
| `timings/` | same axes | **off** | `median_seconds` only |
| `naive/` | 10k × multi/combined × naive+optimized × materialize × 3 | **on** | peak, naive vs optimized |
| `timings-naive/` | same axes | **off** | time, naive vs optimized |

Timings and peaks cannot come from the same run: `tracemalloc` inflates the read
phase ~8.6× and map ~6.5×, against roughly nothing on the database writes, so a
traced run distorts the phases *against each other*. Hence the paired campaigns.

### Verification performed

- Each `benchmark_results.csv` carries a single `timestamp` — no appended runs.
- Row count matches its `benchmark_run_*.json` exactly (108 / 108 / 68 / 68).
- Zero duplicate `(size, mode, strategy, execution, backend, entity, phase)` keys.
- `peak_memory_mb` populated in all traced rows, empty in all untraced rows.
- **Row counts identical across all four campaigns** for every shared cell — the
  workload is the same; only time and memory differ.
- `peak_memory_mb` reproduces to within **0.1%** across two independent campaigns
  (10k optimized materialize, measured 03:14 and 11:04). Same-cell *timings*
  differ by **15–38%** between campaigns.

## Interruptions (both recovered correctly)

| Run | Failure | Recovery |
|---|---|---|
| Root matrix, 03:14 | Cassandra `TypeError: '<' not supported between NoHostAvailable and OperationTimedOut` | 20 runs checkpointed; resumed 15:18, completed 36/36 |
| `timings-naive/`, 18:24 | Cassandra `ConnectionShutdown: CRC mismatch on header` | 5 runs checkpointed; resumed 19:01, completed 12/12 |

Neither corrupts the data. Both are connection-time failures, `--resume` re-checks
the matrix axes before continuing, every cell truncates its tables before importing,
and no commit landed between the interrupted and resumed halves of either run
(`8d1bacb` at 02:40, next commit `5dd1931` at 17:34). The 0.1% peak-memory
agreement above independently confirms both halves ran the same code.

No leftover `benchmark_checkpoint.json` remains anywhere.

## `archive-prefix/` — superseded, do not cite

All three CSVs are multiple runs appended into one file, on code predating
`8d1bacb` (the inference optimization):

- `benchmark_results.csv` — 216 rows, every key duplicated (2 runs).
- `benchmark_results_optimized.csv` — identical to the above.
- `benchmark_results_naive.csv` — **misnamed**: 250 rows = two full *optimized*
  matrices (07-31 18:50 and 23:32) plus one naive 10k run (08-01 01:43).

Superseded by `naive/` + `timings-naive/`, which cover both strategies in one
consistent pass.

## Headline results

**Memory — materialize vs stream (traced, peak MB, multi):**

| Size | materialize | stream | ratio |
|---|---|---|---|
| 1 000 | 10.5 | 10.7 | 0.98× |
| 10 000 | 95.3 | 47.8 | 2.0× |
| 100 000 | 950.7 | 75.9 | **12.5×** |

Materialize grows linearly with the dataset (10.5 → 95.3 → 950.7). Stream flattens
(10.7 → 47.8 → 75.9). `combined` mode behaves the same (12.6× at 100k).

**Time — materialize vs stream (untraced, total seconds, multi):**

| Size | materialize | stream | stream penalty |
|---|---|---|---|
| 1 000 | 2.87 | 4.63 | +61% |
| 10 000 | 16.20 | 20.94 | +29% |
| 100 000 | 149.93 | 165.03 | **+10%** |

The streaming penalty *shrinks* as the memory advantage grows.

**Naive vs optimized (untraced, 10k, materialize):**

| Mode | naive | optimized | speedup |
|---|---|---|---|
| multi | 135.74 s | 14.54 s | 9.3× |
| combined | 138.44 s | 16.30 s | 8.5× |

Concentrated in map (38.54 → 0.91 s, 42×) and write (95.36 → 12.44 s, 7.7×).
Both write the same 27 494 rows.

**Per-DBMS write throughput (untraced, 100k multi materialize):**

| DBMS | rows | seconds | rows/s |
|---|---|---|---|
| cassandra | 100 000 | 109.61 | 912 |
| neo4j | 51 602 | 13.23 | 3 901 |
| postgres | 62 167 | 8.13 | 7 644 |
| redis | 49 558 | 4.56 | 10 865 |
| mongodb | 11 609 | 0.80 | 14 431 |

## Caveats for the evaluation chapter

1. **Never mix the traced and untraced campaigns in one table.** Memory from the
   traced folders, time from the `timings*` folders, stated as such.
2. **Cassandra is 80% of the write phase** (109.6 s of 136.3 s at 100k). It runs on
   a 1 GB heap in a ~3.8 GB Docker VM on an 8 GB host — an environment limit, not a
   property of the DBMS. Any "write phase" claim is a claim about Cassandra unless
   it is broken out per DBMS.
3. **Timing precision is ~20%.** Two campaigns of the same cell on the same code
   differed by 15–38%. Do not draw conclusions from differences under ~20%. Peak
   memory has no such problem (0.1%).
4. **Stream reports one aggregate row** — `(stream) * write`, read+map+write fused.
   There is no per-DBMS or per-phase breakdown for streaming; the `read`/`map`
   columns read 0.00 for stream rows and must not be presented as "streaming does
   no reading".
5. **Naive was measured only at 10k, materialize only.** Streaming ignores
   `--strategy naive` by design (`runner.py:136`). State the scope.
6. **Naive shows a *lower* peak than optimized** (14.4 vs 95.4 MB at 10k). This is
   real and reproducible: the optimized Neo4j path builds the whole relationship
   parameter list in memory (`neo4j_importer.py:287`) while naive iterates row by
   row (`:283`). Batching trades memory for throughput. Explain it or omit it —
   do not present it as an anomaly.
