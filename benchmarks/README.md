# Benchmark datasets — index and provenance

**Language / Idioma / Língua:** [English](#english) · [Português (BR)](#português-br)

## English

Audited 2026-08-01. Four campaigns are current and mutually consistent; everything
in `archive-prefix/` is superseded and must not be used.

`write_consolidated` **appends** to `benchmark_results.csv`. A folder that has been
written twice therefore holds two runs' rows under one filename. Every current
campaign below was verified to hold exactly one run.

### Current data

| Folder | Axes | tracemalloc | Use it for |
|---|---|---|---|
| `.` (root) | 1k/10k/100k × multi/combined × optimized × materialize/stream × 3 | **on** | `peak_memory_mb` only |
| `timings/` | same axes | **off** | `median_seconds` only |
| `naive/` | 10k × multi/combined × naive+optimized × materialize × 3 | **on** | peak, naive vs optimized |
| `timings-naive/` | same axes | **off** | time, naive vs optimized |

Timings and peaks cannot come from the same run: `tracemalloc` inflates the read
phase ~8.6× and map ~6.5×, against roughly nothing on the database writes, so a
traced run distorts the phases *against each other*. Hence the paired campaigns.

#### Verification performed

- Each `benchmark_results.csv` carries a single `timestamp` — no appended runs.
- Row count matches its `benchmark_run_*.json` exactly (108 / 108 / 68 / 68).
- Zero duplicate `(size, mode, strategy, execution, backend, entity, phase)` keys.
- `peak_memory_mb` populated in all traced rows, empty in all untraced rows.
- **Row counts identical across all four campaigns** for every shared cell — the
  workload is the same; only time and memory differ.
- `peak_memory_mb` reproduces to within **0.1%** across two independent campaigns
  (10k optimized materialize, measured 03:14 and 11:04). Same-cell *timings*
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
5. **Naive was measured only at 10k, materialize only.** Streaming ignores
   `--strategy naive` by design (`runner.py:136`). State the scope.
6. **Naive shows a *lower* peak than optimized** (14.4 vs 95.4 MB at 10k). This is
   real and reproducible: the optimized Neo4j path builds the whole relationship
   parameter list in memory (`neo4j_importer.py:287`) while naive iterates row by
   row (`:283`). Batching trades memory for throughput. Explain it or omit it —
   do not present it as an anomaly.

## Português (BR)

Auditado em 2026-08-01. Quatro campanhas estão atuais e mutuamente consistentes;
tudo em `archive-prefix/` está superado e não deve ser usado.

`write_consolidated` **acrescenta** ao `benchmark_results.csv`. Uma pasta gravada
duas vezes, portanto, guarda as linhas de duas execuções sob um único nome de
arquivo. Cada campanha atual abaixo foi verificada e contém exatamente uma
execução.

### Dados atuais

| Pasta | Eixos | tracemalloc | Use para |
|---|---|---|---|
| `.` (raiz) | 1k/10k/100k × multi/combined × optimized × materialize/stream × 3 | **ligado** | só `peak_memory_mb` |
| `timings/` | mesmos eixos | **desligado** | só `median_seconds` |
| `naive/` | 10k × multi/combined × naive+optimized × materialize × 3 | **ligado** | pico, naive vs optimized |
| `timings-naive/` | mesmos eixos | **desligado** | tempo, naive vs optimized |

Tempos e picos não podem vir da mesma execução: o `tracemalloc` infla a fase de
leitura ~8.6× e o mapeamento ~6.5×, contra praticamente nada nas escritas no
banco, então uma execução rastreada distorce as fases *umas contra as outras*.
Daí as campanhas pareadas.

#### Verificação realizada

- Cada `benchmark_results.csv` traz um único `timestamp` — sem execuções
  acrescentadas.
- A contagem de linhas bate exatamente com seu `benchmark_run_*.json`
  (108 / 108 / 68 / 68).
- Zero chaves `(size, mode, strategy, execution, backend, entity, phase)`
  duplicadas.
- `peak_memory_mb` preenchido em todas as linhas rastreadas, vazio em todas as
  não rastreadas.
- **Contagens de linhas idênticas nas quatro campanhas** para toda célula
  compartilhada — a carga de trabalho é a mesma; só tempo e memória diferem.
- `peak_memory_mb` reproduz dentro de **0.1%** entre duas campanhas
  independentes (10k optimized materialize, medidas às 03:14 e 11:04). Os
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

**Memória — materialize vs stream (rastreado, pico em MB, multi):**

| Tamanho | materialize | stream | razão |
|---|---|---|---|
| 1 000 | 10.5 | 10.7 | 0.98× |
| 10 000 | 95.3 | 47.8 | 2.0× |
| 100 000 | 950.7 | 75.9 | **12.5×** |

O materialize cresce linearmente com o dataset (10.5 → 95.3 → 950.7). O stream
se estabiliza (10.7 → 47.8 → 75.9). O modo `combined` se comporta da mesma
forma (12.6× em 100k).

**Tempo — materialize vs stream (não rastreado, segundos totais, multi):**

| Tamanho | materialize | stream | penalidade do stream |
|---|---|---|---|
| 1 000 | 2.87 | 4.63 | +61% |
| 10 000 | 16.20 | 20.94 | +29% |
| 100 000 | 149.93 | 165.03 | **+10%** |

A penalidade do streaming *diminui* conforme a vantagem de memória cresce.

**Naive vs optimized (não rastreado, 10k, materialize):**

| Modo | naive | optimized | ganho |
|---|---|---|---|
| multi | 135.74 s | 14.54 s | 9.3× |
| combined | 138.44 s | 16.30 s | 8.5× |

Concentrado no mapeamento (38.54 → 0.91 s, 42×) e na escrita (95.36 → 12.44 s,
7.7×). As duas escrevem as mesmas 27 494 linhas.

**Vazão de escrita por SGBD (não rastreado, 100k multi materialize):**

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
5. **O naive só foi medido em 10k, só em materialize.** O streaming ignora
   `--strategy naive` por design (`runner.py:136`). Deixe esse escopo claro.
6. **O naive mostra pico *menor* que o optimized** (14.4 vs 95.4 MB em 10k).
   Isso é real e reproduzível: o caminho otimizado do Neo4j monta a lista
   inteira de parâmetros do relacionamento em memória
   (`neo4j_importer.py:287`), enquanto o naive itera linha a linha (`:283`). O
   agrupamento em lotes troca memória por vazão. Explique isso ou omita — não
   apresente como uma anomalia.
