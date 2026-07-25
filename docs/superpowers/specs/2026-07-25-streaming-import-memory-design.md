# Design: Importação em streaming com memória limitada

> Spec em português; código, identificadores e comentários em inglês (convenção do repositório).

## 1. Contexto e problema

O pipeline de importação atual **materializa tudo em memória**. `read_csv`
(`csv_reader.py:19`) faz `pd.read_csv(path, dtype=str, keep_default_na=False)` —
lê o arquivo inteiro como objetos `str` do Python (a representação mais cara que
existe). `load_sources` (`sources.py:65`) lê **todas** as fontes de uma vez num
`registry` que vive por toda a execução, e há cópias simultâneas: `df.copy()`
(`sources.py:89`), e no modo combinado o frame inteiro **mais** as fatias por
origem do `groupby` (`sources.py:112`). O `cast_cache` (`runner.py:139` →
`mapping_resolver.py:151`) retém os frames **convertidos** de **todos os DBMSs**
ao mesmo tempo — nada é liberado entre DBMSs.

### Medição (probe `tracemalloc`, fase load → cast, sem banco)

| Total de linhas | Produtos (÷8) | Pico load | Pico cast (vivo)   |
|-----------------|---------------|-----------|--------------------|
| 8.000           | 1.000         | 3,9 MB    | 12,3 MB (9,6)      |
| 80.000          | 10.000        | 36,3 MB   | 122,5 MB (96,2)    |
| 800.000         | 100.000       | 454,5 MB  | 1350,6 MB (1089,0) |

Escala ~linear com o total de linhas (levemente superlinear no load). O RSS real
costuma ser 1,5–2× o valor do `tracemalloc`, então 800k linhas sobre os 5 DBMSs
deve **estourar ~2–2,7 GB de pico** — a "explosão" observada no notebook do autor.
O cast custa ~3× o load porque o `cast_cache` mantém os frames convertidos dos 5
DBMSs vivos ao mesmo tempo. (Medições `tracemalloc` na fase load → cast, sem banco.)

Sob a nova semântica de `--sizes` (total de linhas, §12), esses casos são
`--sizes 8000/80000/800000`; o alvo do autor (`--sizes 10000,100000`) fica entre a
1ª e a 2ª linha (~1.250 / ~12.500 produtos).

## 2. Objetivo e não-objetivos

**Objetivo:** importar CSVs de qualquer tamanho com **pico de memória constante**
(≈ um pedaço de leitura, não o arquivo inteiro), como capacidade real do produto — o benchmark herda isso. Padrão
Magazine Luiza: ler em lotes, converter, gravar e descartar.

**Não-objetivos (YAGNI):** concorrência/threads (GIL; eixo à parte; Cassandra já
é concorrente dentro do lote), COPY/bulk-load, paralelismo entre DBMSs, alterar o
baseline de materialização, renomear os identificadores "backend" legados.

## 3. Decisões

- **Dois eixos ortogonais.** Além de `strategy` (`naive | optimized`, técnica de
  cast/escrita, medida em fases), entra `execution` (`materialize | stream`).
  - `materialize` = caminho atual. **Baseline do TCC intacto** (fases
    read→map→write, `strategy` naive/optimized). Não muda.
  - `stream` = novo pipeline. Pico ≈ um lote. Sempre cast vetorizado + escrita em
    lote (não existe "naive streaming"). **Padrão do import real (CLI).**
- **CLI:** `execution=stream` por padrão; `--execution materialize` reproduz o
  baseline manualmente.
- **Inferência de tipos:** o streaming não vê o arquivo inteiro. Infere `kinds`
  do **primeiro pedaço** de cada fonte (uma vez, reusado em todos os pedaços) e
  **`db_type` declarado no config sempre vence**. Documentar: para arquivos
  gigantes/heterogêneos, declare `db_type` para garantir o tipo.
- **Nomenclatura:** o protocolo de escrita chama-se **`DbmsSink`** (não
  "Backend"); adaptadores mantêm nomes de produto (`PostgresSink`, `MongoSink`,
  `CassandraSink`, `RedisSink`, `Neo4jSink`).

## 4. Arquitetura (portas e adaptadores)

Três unidades com responsabilidade única e interfaces bem definidas:

**4.1 `StreamReader`** (`stream_source.py`) — só conhece CSV.
```
iter_entity_chunks(source_cfg, base_dir, overrides, chunksize)
    -> Iterator[(entity_name, chunk_df)]
```
Usa `pd.read_csv(..., dtype=str, keep_default_na=False, encoding="utf-8-sig",
chunksize=READ_CHUNK)`. Multi: emite `(nome, pedaço)` com a pseudo-coluna `_source`.
Combinado: lê em pedaços e roteia cada linha pela coluna 0, emitindo
`(valor_origem, subframe)` (validando origem vazia por pedaço).

**4.2 Orquestrador** (`stream_runner.py`) — conhece o fluxo, não conhece SQL/Cypher.
Por DBMS: abre o sink → `create_schema` → para cada entidade, lê em pedaços de
`READ_CHUNK` linhas → `apply_filters` (row-local, reusado) → `cast_frame` no pedaço
→ roteia linhas para partições (`each`/combinado) → acumula buffers por partição →
descarrega no sink a cada `BATCH` (1000) → no fim descarrega restos e `close()`. O
orquestrador é **agnóstico de DBMS**: estado específico (ex.: dedupe first-wins) fica
no sink (ver 4.3), não aqui.

**4.3 `DbmsSink`** (protocolo; um adaptador por DBMS) — só escreve.
```
create_schema(entities)                # DDL a partir do config
ensure_partition(partition_name)       # DDL tardio p/ partições de `each`
write_batch(partition_name, batch_df)  # molda linhas + grava via _write_batched
close()
```
Cada adaptador **reusa** a moldagem de linha + escrita em lote já existentes nos
importers (`_kv_pairs`, `_row_values`, doc-build, props/dedupe), extraídas para
módulos compartilhados. Fábrica injetável (padrão dos `client_factory` /
`session_factory` / `driver_factory` já entregues) → **testável sem banco**.

Um sink pode manter **estado por entidade** entre lotes quando o DBMS exige — ex.:
`Neo4jSink` guarda o *set de chaves vistas* para o dedupe first-wins (memória ∝ nº
de chaves distintas, só chaves). Os demais sinks não deduplicam (upsert/insert).

Fronteiras: o reader não conhece DBMS; o orquestrador não conhece SQL; o sink não
conhece CSV/filtro.

## 5. Fluxo de dados

- **Multi:** por DBMS → `create_schema` → por entidade: 1º pedaço → infere `kinds`
  (uma vez) → filtros → cast → roteia → bufferiza → descarrega a cada 1000 → demais
  pedaços reusando `kinds` → descarrega restos → `close()`. Arquivo lido 1×/DBMS.
- **Combinado:** o reader roteia por origem; daí idêntico ao multi. Lido 1×/DBMS.
- **Partições `each`:** nomes vêm dos dados. Schema não-`each` criado antes (do
  config); `each` via `ensure_partition(nome)` na 1ª aparição (create-if-not-exists).
- **Dedupe first-wins (Neo4j):** feito no `Neo4jSink` (set de chaves vistas
  atravessando pedaços), não no orquestrador.
- **Descarga:** buffer por partição; descarrega quando ≥ `BATCH` (1000); no fim, os
  parciais.
- **Granularidades:** `READ_CHUNK` (leitura + amostra de inferência) e `BATCH`
  (descarga no DBMS) são independentes. O pico ≈ um `READ_CHUNK` × nº de colunas —
  constante no tamanho do arquivo.

## 6. Inferência de tipos (ponto crítico)

O `materialize` infere `kinds` do arquivo inteiro; o streaming, do 1º pedaço.
`cast_frame` e os filtros usam `kinds`. Se o 1º pedaço disser "coluna X é integer"
mas um pedaço posterior trouxer `"N/A"`, o streaming casta diferente do
materialize (silenciosamente). Mitigação decidida: **`db_type` declarado sempre
vence** a inferência; inferência do 1º pedaço só vale para colunas não declaradas.
Documentado: declare `db_type` para arquivos gigantes/heterogêneos. (Segunda
passada de inferência global fica como escape futuro `--infer full`, não construída
agora.)

## 7. Tratamento de erros

- Falha ao abrir o sink → `ImportExecutionError` (igual hoje); um DBMS que falha
  interrompe a execução, como já é.
- **Não-atomicidade:** lotes já descarregados ficam gravados se algo falhar no
  meio — o import atual também não é atômico sobre o arquivo. Documentar.
- Schema idempotente (create-if-not-exists) → re-execução não quebra.
- Célula que não bate o tipo inferido: mesma semântica do `optimized` por pedaço
  (numérico coage; datetime avisa uma vez).
- Reader: CSV malformado / origem vazia no combinado → erro com contexto.

## 8. Métricas e integração com benchmark

- `execution=stream` medido por **pico de memória** (`tracemalloc`) + wall-clock
  total, **não** por fases (elas se intercalam).
- Novo eixo `execution` (materialize|stream) nos runs rotulados e coluna
  `execution` no CSV consolidado; campo novo `peak_memory_mb`. Reusa o guard de
  header (coluna nova → header muda → baseline antigo protegido).
- Permite comparar `materialize` vs `stream` em memória — o resultado que motiva
  este trabalho no TCC.

## 9. Testes (todos sem banco, via `DbmsSink` fake que registra `write_batch`)

- **Prova do fix (memória):** streamar 10k vs 50k linhas e asseverar que o pico
  (`tracemalloc`) fica ~estável — não escala com o total (memória constante).
- **Equivalência:** estado final streamado (linhas entregues ao fake) == estado
  final do materialize (mesmas conversões/partições) para a mesma entrada.
- **Fronteira de pedaço:** dedupe entre pedaços; roteamento `each`/combinado
  atravessando pedaços; flush inclui o resto (não-múltiplo de 1000);
  `ensure_partition` chamado 1× por partição nova.
- **Inferência:** `db_type` declarado vence o 1º-pedaço; inferência usada quando
  não declarado.
- **Reader:** unidade para chunking multi e combinado (roteamento por origem).

## 10. Escopo e sequência

Sequência (o plano ordena):
0. (independente do streaming, pode ir primeiro) Semântica de `--sizes` = total de
   linhas + split proporcional com jitter no gerador (§12).
1. `StreamReader` (multi + combinado) + testes.
2. Protocolo `DbmsSink` + fake + orquestrador (filtro→cast→roteia→bufferiza→flush).
3. `PostgresSink` + `MongoSink` (DBMSs padrão do benchmark e alvos reais prováveis).
4. `CassandraSink` + `RedisSink` + `Neo4jSink`.
5. Eixo `execution` + métrica `peak_memory_mb` no benchmark.
6. CLI `--execution` (stream por padrão) + docs (README EN/PT).

## 11. Constraints globais

- Sem novas dependências de terceiros. `chunksize` é do pandas; escrita reusa as
  APIs já presentes.
- `READ_CHUNK` (default 8192 linhas) = granularidade de leitura e amostra de
  inferência; `BATCH = 1000` (mesmo constante de redis/neo4j) = granularidade de
  descarga no DBMS. Cassandra mantém concorrência 64 dentro do lote.
- `cast_frame` no streaming usa `strategy="optimized"` (vetorizado, `format="mixed"`
  já garantido) — os contratos de casting pinados por `tests/test_casting.py` seguem
  valendo.
- `execution` default = `stream` no CLI; `materialize` preserva 100% o baseline.
- Código/identificadores/comentários em inglês; specs/planos em português.
- Commit por tarefa, push a cada commit (política vigente).

## 12. Semântica de `--sizes` = total de linhas (gerador)

Mudança independente do streaming, mas necessária para medir volumes realistas.

- `--sizes T` passa a significar **total de linhas** (soma das 4 fontes), não nº de
  produtos. `--sizes 10000,100000` ⇒ ~1.250 / ~12.500 produtos.
- O gerador deriva as contas por fonte de T: proporções-base **1:3:2:2**
  (stock:purchase:select:cart) com **jitter ±10% seedado**, renormalizado para
  **somar exatamente T** (o resto de arredondamento vai para a maior fonte).
- **Invariantes:** (a) determinismo — mesmo `(seed, T)` gera arquivos
  byte-idênticos (o jitter deriva do seed); seeds diferentes → splits diferentes.
  (b) FKs válidas — `stock` define o espaço de chaves: `n_stock` linhas = `n_stock`
  produtos únicos (ids 1..`n_stock`); purchase/select/cart referenciam produtos em
  [1, `n_stock`]. `num_users`/`num_categories` passam a escalar sobre `n_stock`.

**Impactos:**
- `benchmark_data`: `iter_source_rows`/`generate_dataset` recebem `total_rows`;
  helper resolve `(n_stock, n_purchase, n_select, n_cart)` de T com jitter seedado.
- `run_benchmarks.py`: help do `--sizes` = "total de linhas"; defaults revisados
  para linhas.
- `run_benchmarks_100k.py`: `--size` e as tabelas de estimativa (`ROWS_AT_1K`,
  `MEASURED_ROWS_PER_S`) reindexadas por total de linhas.
- Reference dataset committed em `data/benchmark/` (hoje 1.000 produtos = 8.000
  linhas): regenerar sob a nova semântica e atualizar o comando nos docs + testes
  que assertam contagens.
- Coluna `size` nos resultados = total de linhas (o baseline naive antigo tinha
  size=produtos — anotar nos docs).

**Testes:** soma exata = T; cada fonte dentro de ±10% da proporção-base;
determinismo (mesmo seed → idêntico; seeds diferentes → splits diferentes); FKs
válidas (ids referenciados ≤ `n_stock`).
