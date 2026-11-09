# Benchmark datasets — index and provenance

**Language / Idioma / Língua:** [English](#english) · [Português (BR)](#português-br)

## English

Audited 2026-08-01. The four campaigns in the root, `timings/`, `naive/` and
`timings-naive/` were measured with the 2.x releases and are mutually consistent;
they stay valid as history (whole-file load × stream, naive × optimized writes).
Everything in `archive-prefix/` is superseded and must not be used. The campaigns of
the current version, 3.0.0, are in `v3/` (see "Campaigns of the current version").

`write_consolidated` **appends** to `benchmark_results.csv`. A folder that has been
written twice therefore holds two runs' rows under one filename. Every current
campaign below was verified to hold exactly one run.

The four campaigns below were measured when the tool could still import in two
ways: loading each source whole in memory (the *whole-file load*, `execution=materialize`
in the old CSVs) or streaming it in chunks (`stream`). The `execution` column of their
CSVs tells them apart: `stream` for the second and the other value for the first. The
tool now imports one way only: every import streams, in three reads (inference,
validation and write). New campaigns therefore vary the read chunk size instead (see
"Campaigns of the current version"), and their phases are `infer`, `validate` and
`write`.

### Current data

| Folder | Axes | tracemalloc | Use it for |
|---|---|---|---|
| `.` (root) | 1k/10k/100k × multi/combined × optimized × whole-file load/stream × 3 | **on** | `peak_memory_mb` only |
| `timings/` | same axes | **off** | `median_seconds` only |
| `naive/` | 10k × multi/combined × naive+optimized × whole-file load × 3 | **on** | peak, naive vs optimized |
| `timings-naive/` | same axes | **off** | time, naive vs optimized |

The `naive` strategy was removed from the tool in 2.0.0. `naive/` and
`timings-naive/` were measured on 2026-08-01, before the removal; version 1.1.0
(tag `v1.1.0`) is the last release that has the strategy — check out that tag
to run it again. Their CSVs keep the
`strategy` column, which the current results no longer have.

Timings and peaks cannot come from the same run: `tracemalloc` inflates the read
phase ~8.6× and map ~6.5×, against roughly nothing on the database writes, so a
traced run distorts the phases *against each other*. Hence the paired campaigns.

#### Verification performed

- Each `benchmark_results.csv` carries a single `timestamp` — no appended runs.
- Row count matches its `benchmark_run_*.json` exactly (108 / 108 / 68 / 68).
- Zero duplicate `(size, mode, strategy, execution, dbms, entity, phase)` keys.
- `peak_memory_mb` populated in all traced rows, empty in all untraced rows.
- **Row counts identical across all four campaigns** for every shared cell — the
  workload is the same; only time and memory differ.
- `peak_memory_mb` reproduces to within **0.1%** across two independent campaigns
  (10k optimized whole-file load, measured 03:14 and 11:04). Same-cell *timings*
  differ by **15–38%** between campaigns.

### Interruptions (both recovered correctly)

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

### `archive-prefix/` — superseded, do not cite

All three CSVs are multiple runs appended into one file, on code predating
`8d1bacb` (the inference optimization):

- `benchmark_results.csv` — 216 rows, every key duplicated (2 runs).
- `benchmark_results_optimized.csv` — identical to the above.
- `benchmark_results_naive.csv` — **misnamed**: 250 rows = two full *optimized*
  matrices (07-31 18:50 and 23:32) plus one naive 10k run (08-01 01:43).

Superseded by `naive/` + `timings-naive/`, which cover both strategies in one
consistent pass.

### Headline results

**Memory — whole-file load vs stream (traced, peak MB, multi):**

| Size | whole-file load | stream | ratio |
|---|---|---|---|
| 1 000 | 10.5 | 10.7 | 0.98× |
| 10 000 | 95.3 | 47.8 | 2.0× |
| 100 000 | 950.7 | 75.9 | **12.5×** |

The whole-file load grows linearly with the dataset (10.5 → 95.3 → 950.7). Stream
flattens (10.7 → 47.8 → 75.9). `combined` mode behaves the same (12.6× at 100k).

**Time — whole-file load vs stream (untraced, total seconds, multi):**

| Size | whole-file load | stream | stream penalty |
|---|---|---|---|
| 1 000 | 2.87 | 4.63 | +61% |
| 10 000 | 16.20 | 20.94 | +29% |
| 100 000 | 149.93 | 165.03 | **+10%** |

The streaming penalty *shrinks* as the memory advantage grows.

**Naive vs optimized (untraced, 10k, whole-file load):**

| Mode | naive | optimized | speedup |
|---|---|---|---|
| multi | 135.74 s | 14.54 s | 9.3× |
| combined | 138.44 s | 16.30 s | 8.5× |

Concentrated in map (38.54 → 0.91 s, 42×) and write (95.36 → 12.44 s, 7.7×).
Both write the same 27 494 rows.

**Per-DBMS write throughput (untraced, 100k multi, whole-file load):**

| DBMS | rows | seconds | rows/s |
|---|---|---|---|
| cassandra | 100 000 | 109.61 | 912 |
| neo4j | 51 602 | 13.23 | 3 901 |
| postgres | 62 167 | 8.13 | 7 644 |
| redis | 49 558 | 4.56 | 10 865 |
| mongodb | 11 609 | 0.80 | 14 431 |

### Caveats for the evaluation chapter

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
5. **Naive was measured only at 10k, with the whole-file load only.** In 1.1.0, streaming ignores
   `--strategy naive` by design (`v1.1.0:src/polyglotimportcsv/runner.py:251`).
   State the scope.
6. **Naive shows a *lower* peak than optimized** (14.4 vs 95.4 MB at 10k). This is
   real and reproducible: in 1.1.0, the optimized Neo4j path builds the whole
   relationship parameter list in memory
   (`v1.1.0:src/polyglotimportcsv/importers/neo4j_importer.py:287`) while naive
   iterates row by row (`:283`). Batching trades memory for throughput. Explain it or omit it —
   do not present it as an anomaly.

### Campaigns of the current version

`scripts/run_benchmarks.py` has a chunk-size axis, `--chunk-sizes`, in place of the
removed write-path axis. It takes read chunk sizes in MB, separated by commas
(default `8`; each from 8 to 256), and every size is another cell of the matrix. The
consolidated `benchmark_results.csv` has these columns:

    timestamp,size,mode,chunk_mb,dbms,entity,phase,rows,median_seconds,rows_per_second,peak_memory_mb

The `phase` column holds `infer` and `validate`, once per import, and `write`, once
per DBMS. A results file with the old header (an `execution` column and no
`chunk_mb`) is refused with exit code 2 before anything is measured, so a campaign
of this version goes into another folder:

    python scripts/run_benchmarks.py --sizes 100000 --modes multi \
      --chunk-sizes 8,64,256 --repetitions 3 --out benchmarks/v3/chunks-memory

As in the campaigns above, memory and time come from separate runs: a traced run
(the default) for `peak_memory_mb` and an untraced one (`--no-trace-memory`) for
`median_seconds`. `--resume` continues an interrupted matrix only when
`--chunk-sizes` and the other axis flags match.

#### The 3.0.0 campaigns

| Folder | Axes | tracemalloc | Use it for |
|---|---|---|---|
| `v3/memory/` | 1k/10k/100k × multi/combined × 8 MB × 3 | **on** | `peak_memory_mb` only |
| `v3/timings/` | same axes | **off** | `median_seconds` only |
| `v3/chunks-memory/` | 100k × multi × 8/64/256 MB × 3 | **on** | peak per chunk size |
| `v3/chunks-timings/` | same axes | **off** | time per chunk size |

Measured on 2026-11-01 and 02, at commit `eeac219` (branch `fluxo-unico`, before the
3.0.0 tag), with Python 3.14.5 on Windows 11. The five DBMSs ran in Docker Desktop
with 3.88 GiB of memory and 8 CPUs; Cassandra has a 1 GB heap
(`MAX_HEAP_SIZE` in `docker-compose.yml`). The host has 8 GB of memory, with 650 to
800 MB free whenever it was checked during the campaigns, and its system drive was
found full after them. The memory campaign was stopped after 8 of its 18 runs, when
the host ran low on memory, and was resumed with `--resume`; its CSV carries the
timestamp of the resumed run.

**Verification performed**, on every folder:

- Each `benchmark_results.csv` carries a single `timestamp`, and its row count
  matches its `benchmark_run_*.json` (42 / 42 / 21 / 21).
- No duplicate `(size, mode, chunk_mb, dbms, entity, phase)` keys.
- `peak_memory_mb` filled in every traced row and empty in every untraced row.
- `infer` and `validate` read exactly `size` rows in every cell.
- The MongoDB write holds the `stock` plus the `purchase` rows of the generated
  dataset (`product_catalog` plus `orders`): 11 609 + 38 833 = 50 442 at 100 000.
- Row counts identical between the paired folders for every shared key (42 keys
  between `memory` and `timings`, 21 between `chunks-memory` and `chunks-timings`).

Below, every number is a median of 3 repetitions, and a total is the sum of the
phase medians.

**Time per phase, 100 000 rows, 8 MB chunks (`v3/timings`, seconds):**

| Phase | multi | combined |
|---|---|---|
| `infer` | 16.98 | 21.23 |
| `validate` | 27.69 | 34.98 |
| `write` PostgreSQL | 12.72 | 14.26 |
| `write` MongoDB | 8.63 | 9.00 |
| `write` Cassandra | 110.96 | 116.25 |
| `write` Redis | 5.44 | 12.61 |
| `write` Neo4j | 27.10 | 29.06 |
| **total** | **209.51** | **237.39** |
| `infer` + `validate`, share of the total | 21.3% | 23.7% |

**Growth, 8 MB chunks (total seconds from `v3/timings`, peak MB from `v3/memory`):**

| Size | multi, s | multi, peak MB | combined, s | combined, peak MB |
|---|---|---|---|---|
| 1 000 | 6.51 | 10.4 | 5.81 | 10.2 |
| 10 000 | 22.67 | 40.1 | 27.18 | 44.2 |
| 100 000 | 209.51 | 66.1 | 237.39 | 54.6 |

From 1 000 to 100 000 rows (100×), the total grows 32× in multi and 41× in
combined, and the peak grows 6.4× and 5.3×. From 10 000 to 100 000 (10×), the total
grows 9.2× and 8.7×, and the peak 1.65× and 1.24×.

**Chunk size, 100 000 rows, multi (peak from `v3/chunks-memory`, seconds from
`v3/chunks-timings`):**

| Chunk | `purchase` blocks | peak MB | total, s | `infer`, s | `validate`, s |
|---|---|---|---|---|---|
| 8 MB | 10 | 66.2 | 204.00 | 15.69 | 27.53 |
| 64 MB | 2 | 131.9 | 192.91 | 10.95 | 22.71 |
| 256 MB | 1 | 149.9 | 190.88 | 9.74 | 23.57 |

At 100 000 rows the largest source, `purchase` (38 833 rows, 14.4 MB on disk),
takes 10 blocks at 8 MB, 2 at 64 MB and 1 at 256 MB; the other three take 2 blocks
at 8 MB and 1 from 64 MB on. At 256 MB, then, every source is read whole in one
block. Against 8 MB, 64 MB doubles the peak (2.0×) and cuts the total by 5.4%, and
256 MB raises the peak 2.3× and cuts the total by 6.4%. `infer` falls 30% and 38%;
`validate` falls 17% and 14%.

**Write throughput per DBMS, 100 000 rows, multi, 8 MB chunks (`v3/timings`):**

| DBMS | rows | seconds | rows/s |
|---|---|---|---|
| PostgreSQL | 73 660 | 12.72 | 5 793 |
| MongoDB | 50 442 | 8.63 | 5 845 |
| Cassandra | 100 000 | 110.96 | 901 |
| Redis | 49 558 | 5.44 | 9 118 |
| Neo4j | 89 275 | 27.10 | 3 294 |

#### Caveats for these numbers

- **Never mix traced and untraced folders.** tracemalloc slows the phases unevenly:
  with it, the 100 000-row multi import takes 3.3× as long, `infer` 6.2× and the
  Cassandra write 2.1×. Peaks come from `memory` and `chunks-memory`; times from
  `timings` and `chunks-timings`.
- **Variation between campaigns.** The same cell, 100 000 multi with 8 MB chunks,
  was measured in two campaigns: 209.51 s in `timings` and 204.00 s in
  `chunks-timings` (2.7% apart), and 66.1 MB in `memory` and 66.2 MB in
  `chunks-memory`. A time difference of a few percent is within that noise: the
  5–6% that 64 and 256 MB chunks save in total is about twice it.
- **The load is not the 2.x load.** The example now writes the `orders`
  collection to MongoDB, split by state: at 100 000 rows, 38 833 more documents
  than in the 2.x campaigns. Do not compare the totals with the 2.x ones as if the
  load were the same.
- **Cassandra dominates the write.** At 100 000 multi it takes 67% of the write
  time (64% in combined) and 53% of the whole import.

### Preliminary campaign (`v4-preview/`)

Measured on 2026-11-08/09 for the report preview, on commit `641e8a8` with its
defaults: 128 MB chunks and 2048-row batches. Volumes 1 024, 16 384, 32 768,
65 536, 131 072 and 262 144 rows, multi and combined. `timings/` has 3 repetitions
without tracemalloc. `memory/` has **1** repetition with tracemalloc. Both folders
passed the checks (one timestamp, no duplicate keys, all 12 cells, `infer`/`validate`
rows equal to the size), and their row counts are identical in every cell. The
timing campaign was interrupted twice, by an out-of-memory error in pandas and by
an unresponsive Docker engine, and was resumed with `--resume` without losing
measured runs. The final campaign of 3.2.0 will replace these numbers.

| Rows | multi time (s) | ms/row | multi peak (MB) | combined time (s) | ms/row | combined peak (MB) |
|---:|---:|---:|---:|---:|---:|---:|
| 1 024 | 9.35 | 9.13 | 11.2 | 8.87 | 8.66 | 10.7 |
| 16 384 | 45.36 | 2.77 | 55.2 | 43.08 | 2.63 | 74.3 |
| 32 768 | 75.17 | 2.29 | 72.4 | 80.53 | 2.46 | 99.0 |
| 65 536 | 135.34 | 2.07 | 97.8 | 162.20 | 2.47 | 143.8 |
| 131 072 | 294.19 | 2.24 | 195.5 | 353.14 | 2.69 | 225.1 |
| 262 144 | 555.10 | 2.12 | 300.0 | 593.92 | 2.27 | 370.7 |

Exponent `b` of `log t = a + b log N`, fitted from 16 384 rows on: time 0.92 (multi)
and 0.97 (combined), which is linear growth; peak 0.63 and 0.58. At 262 144 multi,
the write takes 82.4% of the time, Cassandra alone 58.0%, and `infer` plus
`validate` take 17.6%.

### Exploratory campaign (`v4-explore/`)

Measured on 2026-11-09 on commit `491a64f` to choose the automatic block and batch
sizes: 131 072 rows, multi. One axis at a time: blocks of 16, 32, 64, 128 and 256 MB
with 2048-row batches (`chunks-*`), and batches of 512 to 8192 rows with 128 MB
blocks (`batches-*`). Time is the median of 3 repetitions; memory comes from 1.
Every folder passed the checks, and the paired folders have identical row counts.
`chunks-memory` was interrupted once (Cassandra refused the connection with a CRC
mismatch) and resumed with `--resume` after a Docker restart.

| Block (MB) | 16 | 32 | 64 | 128 | 256 |
|---|---:|---:|---:|---:|---:|
| total (s) | 275.08 | 304.36 | 282.19 | 248.00 | 251.00 |
| peak (MB) | 103.6 | 127.9 | 144.9 | 195.5 | 195.5 |

| Batch (rows) | 512 | 1024 | 2048 | 4096 | 8192 |
|---|---:|---:|---:|---:|---:|
| total (s) | 211.97 | 206.57 | 195.34 | 208.00 | 202.80 |
| peak (MB) | 200.4 | 197.0 | 195.5 | 195.6 | 197.1 |

The shared cell (128 MB, 2048) took 248.00 s in one campaign and 195.34 s in the
other: compare only within a campaign. Blocks that read the largest source whole
(about 95.5 MB here) are the fastest; peak ≈ 87.0 + 1.078 × effective block (MB) at this volume; the base grows with the data (about 22.2 + 2.31 × MiB of sources on disk, fitted on `v4-preview/`).
The batch barely moves time or peak. The resulting rule is in
`docs/superpowers/specs/2026-11-08-revisao-ronaldo-v23-design.md`.

## Português (BR)

Auditado em 2026-08-01. As quatro campanhas da raiz, `timings/`, `naive/` e
`timings-naive/` foram medidas com as versões 2.x e são mutuamente consistentes;
continuam válidas como histórico (carga integral × transmissão em blocos, escrita
ingênua × otimizada). Tudo em `archive-prefix/` está superado e não deve ser usado.
As campanhas da versão atual, a 3.0.0, estão em `v3/` (veja "Campanhas da versão
atual").

`write_consolidated` **acrescenta** ao `benchmark_results.csv`. Uma pasta gravada
duas vezes, portanto, guarda as linhas de duas execuções sob um único nome de
arquivo. Cada campanha atual abaixo foi verificada e contém exatamente uma
execução.

As quatro campanhas abaixo foram medidas quando a ferramenta ainda importava de
duas formas: carregando cada origem inteira na memória (a *carga integral*,
`execution=materialize` nos CSVs antigos) ou transmitindo-a em blocos (`stream`). A
coluna `execution` dos CSVs distingue as duas: `stream` para a segunda e o outro valor
para a primeira. A ferramenta agora importa de uma só forma: toda importação
transmite, em três leituras (inferência, validação e gravação). As campanhas novas,
portanto, variam o tamanho do bloco de leitura (veja "Campanhas da versão atual"), e
suas fases são `infer`, `validate` e `write`.

### Dados atuais

| Pasta | Eixos | tracemalloc | Use para |
|---|---|---|---|
| `.` (raiz) | 1k/10k/100k × multi/combined × optimized × carga integral/stream × 3 | **ligado** | só `peak_memory_mb` |
| `timings/` | mesmos eixos | **desligado** | só `median_seconds` |
| `naive/` | 10k × multi/combined × naive+optimized × carga integral × 3 | **ligado** | pico, naive vs optimized |
| `timings-naive/` | mesmos eixos | **desligado** | tempo, naive vs optimized |

A estratégia `naive` foi removida da ferramenta na versão 2.0.0. `naive/` e
`timings-naive/` foram medidos em 01/08/2026, antes da remoção; a versão 1.1.0
(tag `v1.1.0`) é a última que contém a estratégia — faça checkout dessa tag
para executá-la de novo. Os CSVs dessas pastas
mantêm a coluna `strategy`, que os resultados atuais já não têm.

Tempos e picos não podem vir da mesma execução: o `tracemalloc` infla a fase de
leitura ~8.6× e o mapeamento ~6.5×, contra praticamente nada nas escritas no
banco, então uma execução rastreada distorce as fases *umas contra as outras*.
Daí as campanhas pareadas.

#### Verificação realizada

- Cada `benchmark_results.csv` traz um único `timestamp` — sem execuções
  acrescentadas.
- A contagem de linhas bate exatamente com seu `benchmark_run_*.json`
  (108 / 108 / 68 / 68).
- Zero chaves `(size, mode, strategy, execution, dbms, entity, phase)`
  duplicadas.
- `peak_memory_mb` preenchido em todas as linhas rastreadas, vazio em todas as
  não rastreadas.
- **Contagens de linhas idênticas nas quatro campanhas** para toda célula
  compartilhada — a carga de trabalho é a mesma; só tempo e memória diferem.
- `peak_memory_mb` reproduz dentro de **0.1%** entre duas campanhas
  independentes (10k optimized carga integral, medidas às 03:14 e 11:04). Os
  *tempos* da mesma célula diferem em **15–38%** entre campanhas.

### Interrupções (ambas recuperadas corretamente)

| Execução | Falha | Recuperação |
|---|---|---|
| Matriz raiz, 03:14 | Cassandra `TypeError: '<' not supported between NoHostAvailable and OperationTimedOut` | 20 execuções com checkpoint; retomada às 15:18, concluiu 36/36 |
| `timings-naive/`, 18:24 | Cassandra `ConnectionShutdown: CRC mismatch on header` | 5 execuções com checkpoint; retomada às 19:01, concluiu 12/12 |

Nenhuma das duas corrompe os dados. Ambas são falhas no momento da conexão, o
`--resume` reconfere os eixos da matriz antes de continuar, cada célula trunca
suas tabelas antes de importar, e nenhum commit aconteceu entre as metades
interrompida e retomada de nenhuma das duas execuções (`8d1bacb` às 02:40,
próximo commit `5dd1931` às 17:34). A concordância de 0.1% no pico de memória
acima confirma, de forma independente, que as duas metades rodaram o mesmo
código.

Não sobrou nenhum `benchmark_checkpoint.json` em lugar nenhum.

### `archive-prefix/` — superado, não citar

Os três CSVs são várias execuções acrescentadas em um único arquivo, em código
anterior ao `8d1bacb` (a otimização de inferência):

- `benchmark_results.csv` — 216 linhas, toda chave duplicada (2 execuções).
- `benchmark_results_optimized.csv` — idêntico ao anterior.
- `benchmark_results_naive.csv` — **mal nomeado**: 250 linhas = duas matrizes
  *optimized* completas (07-31 18:50 e 23:32) mais uma execução naive de 10k
  (08-01 01:43).

Superado por `naive/` + `timings-naive/`, que cobrem as duas estratégias em uma
única passada consistente.

### Resultados principais

**Memória — carga integral vs stream (rastreado, pico em MB, multi):**

| Tamanho | carga integral | stream | razão |
|---|---|---|---|
| 1 000 | 10.5 | 10.7 | 0.98× |
| 10 000 | 95.3 | 47.8 | 2.0× |
| 100 000 | 950.7 | 75.9 | **12.5×** |

A carga integral cresce linearmente com o dataset (10.5 → 95.3 → 950.7). O stream
se estabiliza (10.7 → 47.8 → 75.9). O modo `combined` se comporta da mesma
forma (12.6× em 100k).

**Tempo — carga integral vs stream (não rastreado, segundos totais, multi):**

| Tamanho | carga integral | stream | penalidade do stream |
|---|---|---|---|
| 1 000 | 2.87 | 4.63 | +61% |
| 10 000 | 16.20 | 20.94 | +29% |
| 100 000 | 149.93 | 165.03 | **+10%** |

A penalidade do streaming *diminui* conforme a vantagem de memória cresce.

**Naive vs optimized (não rastreado, 10k, carga integral):**

| Modo | naive | optimized | ganho |
|---|---|---|---|
| multi | 135.74 s | 14.54 s | 9.3× |
| combined | 138.44 s | 16.30 s | 8.5× |

Concentrado no mapeamento (38.54 → 0.91 s, 42×) e na escrita (95.36 → 12.44 s,
7.7×). As duas escrevem as mesmas 27 494 linhas.

**Vazão de escrita por SGBD (não rastreado, 100k multi, carga integral):**

| SGBD | linhas | segundos | linhas/s |
|---|---|---|---|
| cassandra | 100 000 | 109.61 | 912 |
| neo4j | 51 602 | 13.23 | 3 901 |
| postgres | 62 167 | 8.13 | 7 644 |
| redis | 49 558 | 4.56 | 10 865 |
| mongodb | 11 609 | 0.80 | 14 431 |

### Ressalvas para o capítulo de avaliação

1. **Nunca misture as campanhas rastreadas e não rastreadas em uma mesma
   tabela.** Memória vem das pastas rastreadas, tempo das pastas `timings*`,
   informado como tal.
2. **O Cassandra é 80% da fase de escrita** (109.6 s de 136.3 s em 100k). Ele
   roda com heap de 1 GB em uma VM Docker de ~3.8 GB em um host de 8 GB — um
   limite do ambiente, não uma propriedade do SGBD. Qualquer afirmação sobre a
   "fase de escrita" é uma afirmação sobre o Cassandra, a menos que seja
   detalhada por SGBD.
3. **A precisão do tempo é de ~20%.** Duas campanhas da mesma célula no mesmo
   código divergiram em 15–38%. Não tire conclusões de diferenças abaixo de
   ~20%. O pico de memória não tem esse problema (0.1%).
4. **O stream relata uma única linha agregada** — `(stream) * write`, com
   leitura+mapeamento+escrita fundidos. Não há detalhamento por SGBD ou por
   fase para o streaming; as colunas `read`/`map` leem 0.00 nas linhas de
   stream e não devem ser apresentadas como "o streaming não lê nada".
5. **O naive só foi medido em 10k, só com a carga integral.** Na versão 1.1.0, o
   streaming ignora `--strategy naive` por design
   (`v1.1.0:src/polyglotimportcsv/runner.py:251`). Deixe esse escopo claro.
6. **O naive mostra pico *menor* que o optimized** (14.4 vs 95.4 MB em 10k).
   Isso é real e reproduzível: na versão 1.1.0, o caminho otimizado do Neo4j
   monta a lista inteira de parâmetros do relacionamento em memória
   (`v1.1.0:src/polyglotimportcsv/importers/neo4j_importer.py:287`), enquanto o
   naive itera linha a linha (`:283`). O
   agrupamento em lotes troca memória por vazão. Explique isso ou omita — não
   apresente como uma anomalia.

### Campanhas da versão atual

O `scripts/run_benchmarks.py` tem um eixo de tamanho de bloco, `--chunk-sizes`, no
lugar do eixo do caminho de escrita, que foi removido. Ele recebe tamanhos de bloco
de leitura em MB, separados por vírgula (padrão `8`; cada um de 8 a 256), e cada
tamanho é mais uma célula da matriz. O `benchmark_results.csv` consolidado tem estas
colunas:

    timestamp,size,mode,chunk_mb,dbms,entity,phase,rows,median_seconds,rows_per_second,peak_memory_mb

A coluna `phase` traz `infer` e `validate`, uma vez por importação, e `write`, uma
vez por SGBD. Um arquivo de resultados com o cabeçalho antigo (uma coluna `execution`
e nenhuma `chunk_mb`) é recusado com código de saída 2 antes de medir qualquer coisa,
então uma campanha desta versão vai para outra pasta:

    python scripts/run_benchmarks.py --sizes 100000 --modes multi \
      --chunk-sizes 8,64,256 --repetitions 3 --out benchmarks/v3/chunks-memory

Como nas campanhas acima, memória e tempo vêm de execuções separadas: uma execução
rastreada (o padrão) para o `peak_memory_mb` e uma não rastreada
(`--no-trace-memory`) para o `median_seconds`. O `--resume` só continua uma matriz
interrompida quando `--chunk-sizes` e os demais flags de eixo coincidem.

#### As campanhas da 3.0.0

| Pasta | Eixos | tracemalloc | Use para |
|---|---|---|---|
| `v3/memory/` | 1k/10k/100k × multi/combined × 8 MB × 3 | **ligado** | só `peak_memory_mb` |
| `v3/timings/` | mesmos eixos | **desligado** | só `median_seconds` |
| `v3/chunks-memory/` | 100k × multi × 8/64/256 MB × 3 | **ligado** | pico por tamanho de bloco |
| `v3/chunks-timings/` | mesmos eixos | **desligado** | tempo por tamanho de bloco |

Medidas em 2026-11-01 e 02, no *commit* `eeac219` (ramo `fluxo-unico`, antes da tag
3.0.0), com Python 3.14.5 no Windows 11. Os cinco SGBDs rodaram no Docker Desktop
com 3,88 GiB de memória e 8 CPUs; o Cassandra tem *heap* de 1 GB (`MAX_HEAP_SIZE` no
`docker-compose.yml`). A máquina tem 8 GB de memória, com 650 a 800 MB livres em
todas as vezes em que isso foi conferido durante as campanhas, e o disco do sistema
foi encontrado cheio depois delas. A campanha de memória parou depois de 8 das suas
18 execuções, quando faltou memória na máquina, e foi retomada com `--resume`; o
CSV dela traz o *timestamp* da execução retomada.

**Verificação realizada**, em todas as pastas:

- Cada `benchmark_results.csv` traz um único `timestamp`, e o número de linhas bate
  com o do seu `benchmark_run_*.json` (42 / 42 / 21 / 21).
- Nenhuma chave `(size, mode, chunk_mb, dbms, entity, phase)` repetida.
- `peak_memory_mb` preenchido em todas as linhas rastreadas e vazio em todas as não
  rastreadas.
- `infer` e `validate` leram exatamente `size` linhas em todas as células.
- A escrita do MongoDB tem as linhas de `stock` mais as de `purchase` da base gerada
  (`product_catalog` mais `orders`): 11 609 + 38 833 = 50 442 em 100 000.
- Contagens de linhas idênticas entre as pastas pareadas em todas as chaves comuns
  (42 chaves entre `memory` e `timings`, 21 entre `chunks-memory` e
  `chunks-timings`).

Abaixo, todo número é a mediana de 3 repetições, e um total é a soma das medianas
das fases.

**Tempo por fase, 100 000 linhas, blocos de 8 MB (`v3/timings`, segundos):**

| Fase | multi | combined |
|---|---|---|
| `infer` | 16,98 | 21,23 |
| `validate` | 27,69 | 34,98 |
| `write` PostgreSQL | 12,72 | 14,26 |
| `write` MongoDB | 8,63 | 9,00 |
| `write` Cassandra | 110,96 | 116,25 |
| `write` Redis | 5,44 | 12,61 |
| `write` Neo4j | 27,10 | 29,06 |
| **total** | **209,51** | **237,39** |
| `infer` + `validate`, fração do total | 21,3% | 23,7% |

**Crescimento, blocos de 8 MB (total em segundos de `v3/timings`, pico em MB de
`v3/memory`):**

| Tamanho | multi, s | multi, pico MB | combined, s | combined, pico MB |
|---|---|---|---|---|
| 1 000 | 6,51 | 10,4 | 5,81 | 10,2 |
| 10 000 | 22,67 | 40,1 | 27,18 | 44,2 |
| 100 000 | 209,51 | 66,1 | 237,39 | 54,6 |

De 1 000 para 100 000 linhas (100×), o total cresce 32× no multifonte e 41× no
combinado, e o pico cresce 6,4× e 5,3×. De 10 000 para 100 000 (10×), o total cresce
9,2× e 8,7×, e o pico 1,65× e 1,24×.

**Tamanho do bloco, 100 000 linhas, multifonte (pico de `v3/chunks-memory`, segundos
de `v3/chunks-timings`):**

| Bloco | blocos de `purchase` | pico MB | total, s | `infer`, s | `validate`, s |
|---|---|---|---|---|---|
| 8 MB | 10 | 66,2 | 204,00 | 15,69 | 27,53 |
| 64 MB | 2 | 131,9 | 192,91 | 10,95 | 22,71 |
| 256 MB | 1 | 149,9 | 190,88 | 9,74 | 23,57 |

Em 100 000 linhas, a maior fonte, `purchase` (38 833 linhas, 14,4 MB em disco), ocupa
10 blocos com 8 MB, 2 com 64 MB e 1 com 256 MB; as outras três ocupam 2 blocos com
8 MB e 1 a partir de 64 MB. Com 256 MB, portanto, toda fonte é lida inteira em um só
bloco. Em relação a 8 MB, o bloco de 64 MB dobra o pico (2,0×) e reduz o total em
5,4%, e o de 256 MB eleva o pico 2,3× e reduz o total em 6,4%. O `infer` cai 30% e
38%; o `validate` cai 17% e 14%.

**Vazão de escrita por SGBD, 100 000 linhas, multifonte, blocos de 8 MB
(`v3/timings`):**

| SGBD | linhas | segundos | linhas/s |
|---|---|---|---|
| PostgreSQL | 73 660 | 12,72 | 5 793 |
| MongoDB | 50 442 | 8,63 | 5 845 |
| Cassandra | 100 000 | 110,96 | 901 |
| Redis | 49 558 | 5,44 | 9 118 |
| Neo4j | 89 275 | 27,10 | 3 294 |

#### Ressalvas sobre estes números

- **Nunca misture pastas rastreadas e não rastreadas.** O tracemalloc deixa as fases
  mais lentas de forma desigual: com ele, a importação multifonte de 100 000 linhas
  leva 3,3× mais tempo, o `infer` 6,2× e a escrita no Cassandra 2,1×. Os picos vêm de
  `memory` e `chunks-memory`; os tempos, de `timings` e `chunks-timings`.
- **Variação entre campanhas.** A mesma célula, 100 000 multifonte com blocos de
  8 MB, foi medida em duas campanhas: 209,51 s em `timings` e 204,00 s em
  `chunks-timings` (2,7% de diferença), e 66,1 MB em `memory` e 66,2 MB em
  `chunks-memory`. Uma diferença de tempo de poucos por cento está dentro desse
  ruído: os 5–6% que os blocos de 64 e 256 MB economizam no total são cerca do dobro
  dele.
- **A carga não é a da 2.x.** O cenário agora grava no MongoDB a coleção `orders`,
  dividida por estado: em 100 000 linhas, são 38 833 documentos a mais do que nas
  campanhas da 2.x. Não compare os totais com os da 2.x como se a carga fosse a
  mesma.
- **O Cassandra domina a escrita.** Em 100 000 multifonte, ele leva 67% do tempo de
  escrita (64% no combinado) e 53% da importação inteira.

### Campanha intermediária (`v4-preview/`)

Medida em 2026-11-08/09 para a prévia do relatório, sobre o *commit* `641e8a8` e os
seus padrões: blocos de 128 MB e lotes de 2048 linhas. Volumes de 1 024, 16 384,
32 768, 65 536, 131 072 e 262 144 linhas, multifonte e combinado. `timings/` tem 3
repetições sem tracemalloc. `memory/` tem **1** repetição com tracemalloc. As duas
pastas passaram na conferência (um só *timestamp*, nenhuma chave repetida, as 12
células, linhas de `infer`/`validate` iguais ao volume), e as contagens de linhas são
idênticas entre elas em todas as células. A campanha de tempo foi interrompida duas
vezes, por falta de memória no pandas e por um motor do Docker que parou de
responder, e foi retomada com `--resume` sem perder execuções já medidas. A campanha
final da 3.2.0 substituirá estes números.

| Linhas | tempo multi (s) | ms/linha | pico multi (MB) | tempo combinado (s) | ms/linha | pico combinado (MB) |
|---:|---:|---:|---:|---:|---:|---:|
| 1 024 | 9,35 | 9,13 | 11,2 | 8,87 | 8,66 | 10,7 |
| 16 384 | 45,36 | 2,77 | 55,2 | 43,08 | 2,63 | 74,3 |
| 32 768 | 75,17 | 2,29 | 72,4 | 80,53 | 2,46 | 99,0 |
| 65 536 | 135,34 | 2,07 | 97,8 | 162,20 | 2,47 | 143,8 |
| 131 072 | 294,19 | 2,24 | 195,5 | 353,14 | 2,69 | 225,1 |
| 262 144 | 555,10 | 2,12 | 300,0 | 593,92 | 2,27 | 370,7 |

Expoente `b` de `log t = a + b log N`, ajustado a partir de 16 384 linhas: tempo 0,92
(multifonte) e 0,97 (combinado), ou seja, crescimento linear; pico 0,63 e 0,58. Em
262 144 multifonte, a escrita leva 82,4% do tempo, o Cassandra sozinho 58,0%, e
`infer` mais `validate`, 17,6%.

### Campanha exploratória (`v4-explore/`)

Medida em 2026-11-09 sobre o *commit* `491a64f` para escolher os tamanhos automáticos
do bloco e do lote: 131 072 linhas, multifonte. Um eixo de cada vez: blocos de 16, 32,
64, 128 e 256 MB com lotes de 2048 linhas (`chunks-*`), e lotes de 512 a 8192 linhas
com blocos de 128 MB (`batches-*`). O tempo é a mediana de 3 repetições; a memória,
de 1. Todas as pastas passaram na conferência, e as pastas pares têm contagens de
linhas idênticas. `chunks-memory` foi interrompida uma vez (o Cassandra recusou a
conexão com CRC *mismatch*) e retomada com `--resume` depois de reiniciar o Docker.

| Bloco (MB) | 16 | 32 | 64 | 128 | 256 |
|---|---:|---:|---:|---:|---:|
| total (s) | 275,08 | 304,36 | 282,19 | 248,00 | 251,00 |
| pico (MB) | 103,6 | 127,9 | 144,9 | 195,5 | 195,5 |

| Lote (linhas) | 512 | 1024 | 2048 | 4096 | 8192 |
|---|---:|---:|---:|---:|---:|
| total (s) | 211,97 | 206,57 | 195,34 | 208,00 | 202,80 |
| pico (MB) | 200,4 | 197,0 | 195,5 | 195,6 | 197,1 |

A célula comum (128 MB, 2048) levou 248,00 s numa campanha e 195,34 s na outra:
compare só dentro de uma campanha. Os blocos que leem a maior fonte inteira (cerca de
95,5 MB aqui) são os mais rápidos; pico ≈ 87,0 + 1,078 × bloco efetivo (MB) nesse volume; a base cresce com os dados (cerca de 22,2 + 2,31 × MiB das fontes em disco, ajustada sobre `v4-preview/`). O lote
quase não mexe no tempo nem no pico. A regra resultante está em
`docs/superpowers/specs/2026-11-08-revisao-ronaldo-v23-design.md`.
