<!-- Language selector: keep this block at the top for GitHub / editors -->
**Language / Idioma / Língua:** [English](#english) · [Português (BR)](#português-br)

---

## English

Python CLI that imports CSV data into **PostgreSQL, Redis, MongoDB, Apache Cassandra, and Neo4j** using **two JSON files** validated with **JSON Schema**:

- `import_config.json` — a required `sources` block declaring where to read CSV data from, plus the entity/relationship/column mapping from each source to each backend.
- `sgbd_config.json` — the connection settings for each backend (which SGBDs are available).

The import configuration may only target backends declared in the SGBD configuration; otherwise the run aborts before touching any CSV or database.

### Sources

The `sources` block supports two input modes, chosen per config:

- **Per-entity CSVs (default):** one CSV path per named source, e.g. `"sources": {"stock": "ecommerce_stock.csv", "purchase": "ecommerce_purchase.csv"}`. Each file IS the origin of its rows — no discriminator column needed.
- **Combined CSV:** a single CSV whose column 0 values become source names, e.g. `"sources": {"ecommerce": {"file": "ecommerce_join.csv", "origin_column": true}}`. The importer slices the file by that column's distinct values; each value is exposed to mappings as the `_source` pseudo-column.

Any source's path can be overridden at run time with `--source NAME=PATH` (repeatable), without editing the config.

### Requirements

- Python 3.9+ (official Cassandra driver C extensions are easiest on Python ≤3.11; `--dry-run` never opens sockets).

### Install

```bash
pip install -e ".[dev]"
```

### Usage

```bash
python -m polyglotimportcsv \
  --config data/ecommerce/import_config.json \
  --sgbd-config data/ecommerce/sgbd_config.json \
  --dry-run
```

`--sgbd-config` is optional; when omitted it defaults to `sgbd_config.json` next to `--config`. Add `--source NAME=PATH` (repeatable) to override individual source paths without editing the config.

**Running example** (single script; use [Git Bash](https://git-scm.com/) on Windows or any Unix shell):

```bash
./run_example.sh                  # Docker (if needed) + clean + dry-run + import + inspect
./run_example.sh --dry-run        # validate config/sources only (no Docker)
./run_example.sh --fresh-start      # first-time: wipe volumes/images, re-pull, full default flow
./run_example.sh --clean --dry-run --import --inspect   # explicit equivalent of default
./run_example.sh --config data/ecommerce/import_config_combined.json   # combined CSV mode
```

Requires Docker for import/clean/inspect. Use `--fresh-start` for a true first-time run (removes volumes and images, re-pulls, then default flow). Every command is printed as `$ ...` in the terminal and in `logs/`.

Options:

- `--only postgres,redis` — run only listed backends.
- `--log-level DEBUG|INFO|WARNING|ERROR` — terminal verbosity (default `INFO`); the session log file under `logs/` always records `DEBUG`.
- `--show-data` / `--no-data` — force or suppress the per-entity record dump (default: entities with up to 50 rows are dumped).
- `--benchmark` — write per-phase metrics to `benchmarks/benchmark_<timestamp>.json` and append `benchmarks/benchmark_history.csv` (implies `--no-data`).
- `--execution stream|materialize` — write path (default `stream`). `stream` imports in bounded memory (~one read chunk, roughly constant in file size); `materialize` loads each source fully (the phase-measured baseline). Streaming supports union (`"source": [...]`) entities: it samples one first chunk per source to build the shared superset, then widens each chunk to it. `--dry-run` and `--benchmark` always use `materialize`. Neo4j relationships are streamed too, in a bounded second pass over the relationship sources after all nodes are written.
- `--no-create-schema` — skip DDL where applicable.

### Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (English + PT) for layering, SOLID mapping, and how **injectable importer registries** keep tests free of real databases. The TCC report lives in [docs-tcc/](docs-tcc/).

### Layout

| Path | Purpose |
|------|---------|
| `src/polyglotimportcsv/` | CLI, validation, filters, runner |
| `src/polyglotimportcsv/importers/` | One module per backend + `base.py` protocol |
| `src/polyglotimportcsv/schemas/` | Bundled JSON Schemas (`import_config`, `sgbd_config`) |
| `data/ecommerce/` | Sample CSVs + `import_config.json` + `sgbd_config.json` |
| `logs/` | Session logs from `run_example.sh` and direct CLI runs (gitignored) |
| `tests/` | `pytest` (stubs for I/O per TDD skill) |
| `docs-tcc/` | TCC I report (Markdown, BibTeX); `docs-tcc/scripts/` for Pandoc PDF/ODT |

### Scripts

- `./run_example.sh` — orchestrates Docker, import, clean, and inspect (see `--help`).
- `scripts/inspect_persisted_data.py` — low-level `clean` / `inspect` helpers (usually invoked via `run_example.sh`).

**Tab completion (Git Bash / bash):** add to `~/.bashrc` (use the absolute path of *your* clone), then open a new terminal:

```bash
# Replace with the path where you cloned the repository, e.g.:
#   ~/Documentos/UFSC/TCC1/polyglot-import-csv
source "/path/to/polyglot-import-csv/scripts/run_example.completion.bash"
```

After that, `./run_example.sh --` + TAB suggests flags (`--fresh-start`, `--clean`, `--inspect`, …); `--config` / `--log-file` suggest paths under `data/ecommerce/` and `logs/`.

### Benchmarks

Generate a deterministic synthetic e-commerce dataset. `--rows` is the **total
number of rows across all sources** (split ~1:3:2:2 among stock/purchase/select/
cart with slight seeded jitter), not the product count; the same `--seed`
reproduces byte-identical files:

    python scripts/generate_benchmark_data.py --rows 100000 --seed 42 \
      --out data/benchmark/generated/100000 --mode both

A small 1 000-row reference dataset is committed under `data/benchmark/` (both
input modes) for quick tests and CI.

Run the benchmark matrix (sizes × modes × repetitions) over **live** databases —
bring them up first (`docker compose up --wait` or `./run_example.sh`). Each
import is preceded by a clean, so every measurement is a cold load:

    python scripts/run_benchmarks.py --sizes 1000,10000,100000 \
      --modes multi,combined --repetitions 3

A crash part-way through does not cost the runs already measured: they are written
to `benchmarks/benchmark_checkpoint.json` after every import. Re-run with the same
axis flags plus `--resume` to measure only the missing cells:

    python scripts/run_benchmarks.py --sizes 1000,10000,100000 \
      --modes multi,combined --repetitions 3 --resume

A repetition is a full sweep of the matrix, not a burst of runs of the same cell.
The databases stay up for the whole matrix, so the first measurements pay the
warm-up (JVM JIT on Cassandra/Neo4j, DB buffers, OS page cache); sweeping spreads
that cost over every cell's first pass, and the median across passes drops it.

The matrix defaults to the `optimized` strategy (vectorized casting and batched
writes). Pass `--strategies naive,optimized` to measure both baselines in a single
run for a before/after comparison; `naive` reproduces the original row-at-a-time
behavior. Cassandra, Redis and Neo4j are slow only under `naive` — `optimized`
batches their writes, so the earlier per-row round-trip cost disappears. The same
switch exists on a single import: `python -m polyglotimportcsv --strategy naive`.

Cassandra absorbs those batched writes at concurrency 64, and a node busy flushing
or compacting can stop answering for longer than the driver's 10s default request
timeout. The session therefore uses 30s (`cassandra.connection.request_timeout` in
`sgbd_config.json` overrides it), and rows a batch reports as failed are retried
with backoff — retrying is safe because a Cassandra `INSERT` is an upsert on the
primary key. Without that, one slow response ends the whole matrix.

The matrix also has an `execution` axis (default `stream`). Pass
`--executions materialize,stream` to compare the two write paths: `materialize`
loads each source fully, so peak memory grows with the dataset, while `stream`
holds ~one read chunk at a time, so peak stays roughly constant. Each run records
`peak_memory_mb` (whole-import peak measured with `tracemalloc`). The same switch
exists on a single import: `python -m polyglotimportcsv --execution materialize`.

`tracemalloc` instruments every allocation, so it inflates the recorded seconds by
an amount that depends on how many allocations a path makes — and `materialize`
(few large pandas allocations) and `stream` (many small per-chunk ones) do not
allocate alike, so the overhead does not simply cancel out between them. Measure it
before trusting a timing comparison:

    python scripts/benchmark_tracemalloc_ab.py --size 10000 \
      --executions materialize,stream --repetitions 3

It runs the same cell with and without tracing, interleaving the two arms pass by
pass so both share the warm-up, and prints the overhead per execution path.

Results land in `benchmarks/`: a `benchmark_run_<timestamp>.json` plus an
append-only `benchmark_results.csv` (`size,mode,strategy,execution,backend,entity,
phase,rows,median_seconds,rows_per_second,peak_memory_mb`) for the report graphs.
The `filter` phase is left out of both, and of the end-of-run terminal table
(`metrics.EXCLUDED_PHASES`).

### License

MIT — see [LICENSE](LICENSE).

---

## Português (BR)

Ferramenta em Python para importar dados de CSV para **vários SGBDs** ao mesmo tempo — PostgreSQL, Redis, MongoDB, Apache Cassandra e Neo4j — com base em **dois arquivos JSON** validados por *JSON Schema*:

- `import_config.json` — um bloco `sources` obrigatório que declara de onde ler os dados CSV, além do mapeamento de entidades, relacionamentos e colunas de cada origem para cada SGBD.
- `sgbd_config.json` — as configurações de conexão de cada SGBD (quais bancos estão disponíveis).

A configuração de importação só pode referenciar SGBDs declarados na configuração de conexão; caso contrário, a execução é abortada antes de ler qualquer CSV ou conectar a qualquer banco.

### Origens dos dados (`sources`)

O bloco `sources` admite dois modos de entrada, escolhidos por configuração:

- **Um CSV por entidade (padrão):** um caminho de CSV por origem nomeada, por exemplo `"sources": {"stock": "ecommerce_stock.csv", "purchase": "ecommerce_purchase.csv"}`. Cada arquivo já é a origem de suas linhas — não é preciso coluna discriminadora.
- **CSV combinado:** um único CSV cuja coluna 0 designa a origem de cada linha, por exemplo `"sources": {"ecommerce": {"file": "ecommerce_join.csv", "origin_column": true}}`. O importador particiona o arquivo pelos valores distintos dessa coluna; cada valor fica disponível aos mapeamentos como a pseudocoluna `_source`.

O caminho de qualquer origem pode ser sobrescrito em tempo de execução com `--source NOME=CAMINHO` (repetível), sem editar a configuração.

### Requisitos

- Python 3.9+ (para o *driver* oficial do Cassandra, versões LTS até 3.11 costumam ser mais simples por causa das extensões C; `--dry-run` não abre conexões).

### Instalação

```bash
pip install -e ".[dev]"
```

### Uso

```bash
python -m polyglotimportcsv \
  --config data/ecommerce/import_config.json \
  --sgbd-config data/ecommerce/sgbd_config.json \
  --dry-run
```

O `--sgbd-config` é opcional; quando omitido, usa-se `sgbd_config.json` ao lado do `--config`. Use `--source NOME=CAMINHO` (repetível) para sobrescrever caminhos de origens individuais sem editar a configuração.

**Exemplo de execução** (um único script; no Windows use [Git Bash](https://git-scm.com/) ou WSL):

```bash
./run_example.sh                  # Docker (se necessário) + clean + dry-run + importação + inspect
./run_example.sh --dry-run        # só validação (sem Docker)
./run_example.sh --fresh-start      # primeiro uso: apaga volumes/imagens, baixa de novo, fluxo padrão
./run_example.sh --clean --dry-run --import --inspect   # equivalente explícito ao padrão
./run_example.sh --config data/ecommerce/import_config_combined.json   # modo CSV combinado
```

Requer Docker para importar/limpar/inspecionar. Use `--fresh-start` para simular o primeiro uso (remove volumes e imagens, `pull`, fluxo padrão). Cada comando aparece como `$ ...` no terminal e em `logs/`.

Opções úteis:

- `--only postgres,redis` — executa só os backends listados.
- `--log-level DEBUG|INFO|WARNING|ERROR` — verbosidade do terminal (padrão `INFO`); o arquivo de log de sessão em `logs/` sempre grava `DEBUG`.
- `--show-data` / `--no-data` — força ou suprime a exibição dos registros por entidade (padrão: entidades com até 50 linhas são exibidas).
- `--benchmark` — grava métricas por fase em `benchmarks/benchmark_<timestamp>.json` e acrescenta `benchmarks/benchmark_history.csv` (implica `--no-data`).
- `--execution stream|materialize` — caminho de escrita (padrão `stream`). `stream` importa com memória limitada (~um bloco de leitura, praticamente constante no tamanho do arquivo); `materialize` carrega cada origem por completo (a linha de base medida por fase). O modo `stream` também aceita entidades de união (`"source": [...]`): amostra o primeiro bloco de cada origem para montar o superconjunto de colunas e então alarga cada bloco para ele. `--dry-run` e `--benchmark` usam sempre `materialize`. Os relacionamentos do Neo4j também são transmitidos, em uma segunda passagem de memória limitada sobre as origens dos relacionamentos, após a escrita de todos os nós.
- `--no-create-schema` — não emite DDL de criação (quando aplicável).

### Arquitetura

Consulte [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (inglês + PT) para camadas, princípios SOLID e *registry* de importadores injetável nos testes. O relatório do TCC está em [docs-tcc/](docs-tcc/).

### Layout

| Caminho | Descrição |
|--------|------------|
| `src/polyglotimportcsv/` | CLI, validação, filtros, *runner* |
| `src/polyglotimportcsv/importers/` | Um módulo por backend + `base.py` (contrato) |
| `src/polyglotimportcsv/schemas/` | JSON Schemas embutidos (`import_config`, `sgbd_config`) |
| `data/ecommerce/` | CSVs de exemplo + `import_config.json` + `sgbd_config.json` |
| `tests/` | `pytest` (stubs, sem I/O real) |
| `docs-tcc/` | Relatório TCC I (Markdown + BibTeX); `docs-tcc/scripts/` para PDF/ODT via Pandoc |

### Scripts

- `./run_example.sh` — orquestra Docker, importação, limpeza e inspeção (`--help`).
- `scripts/inspect_persisted_data.py` — comandos `clean` / `inspect` (chamados pelo `run_example.sh`).

**Autocompletar com TAB (Git Bash / bash):** inclua no `~/.bashrc` (use o caminho absoluto do *seu* clone) e abra um terminal novo:

```bash
# Troque pelo caminho onde você clonou o repositório, por exemplo:
#   ~/Documentos/UFSC/TCC1/polyglot-import-csv
source "/caminho/para/polyglot-import-csv/scripts/run_example.completion.bash"
```

Depois, `./run_example.sh --` + TAB sugere flags (`--fresh-start`, `--clean`, `--inspect`, …); `--config` / `--log-file` sugerem caminhos em `data/ecommerce/` e `logs/`.

### Benchmarks

Gere um dataset e-commerce sintético determinístico. `--rows` é o **total de
linhas somando todas as fontes** (dividido ~1:3:2:2 entre stock/purchase/select/
cart com leve jitter seedado), não o número de produtos; a mesma `--seed` reproduz
arquivos byte-idênticos:

    python scripts/generate_benchmark_data.py --rows 100000 --seed 42 \
      --out data/benchmark/generated/100000 --mode both

Um dataset de referência pequeno (1 000 linhas) está versionado em
`data/benchmark/` (ambos os modos) para testes rápidos e CI.

Rode a matriz de benchmark (tamanhos × modos × repetições) sobre bancos **vivos** —
suba-os antes (`docker compose up --wait` ou `./run_example.sh`). Cada importação é
precedida de uma limpeza, então cada medição é uma carga a frio:

    python scripts/run_benchmarks.py --sizes 1000,10000,100000 \
      --modes multi,combined --repetitions 3

Uma queda no meio da matriz não custa as execuções já medidas: elas são gravadas em
`benchmarks/benchmark_checkpoint.json` após cada importação. Rode de novo com os
mesmos flags de eixo mais `--resume` para medir só as células que faltam:

    python scripts/run_benchmarks.py --sizes 1000,10000,100000 \
      --modes multi,combined --repetitions 3 --resume

Uma repetição é uma varredura completa da matriz, não uma rajada de execuções da
mesma célula. Os bancos ficam de pé durante toda a matriz, então as primeiras
medições pagam o aquecimento (JIT da JVM em Cassandra/Neo4j, buffers dos bancos,
page cache do SO); a varredura distribui esse custo pela primeira passada de cada
célula, e a mediana entre as passadas o descarta.

A matriz usa por padrão a estratégia `optimized` (casting vetorizado e escritas em
lote). Use `--strategies naive,optimized` para medir as duas linhas de base numa só
execução (comparação antes/depois); `naive` reproduz o comportamento original linha
a linha. O Cassandra recebe essas escritas em lote com concorrência 64, e um nó
ocupado com *flush* ou *compaction* pode parar de responder por mais que os 10s de
timeout padrão do driver. A sessão usa 30s (`cassandra.connection.request_timeout`
no `sgbd_config.json` sobrescreve), e as linhas que um lote reporta como falhas são
reenviadas com backoff — reenviar é seguro porque um `INSERT` no Cassandra é um
upsert pela chave primária. Sem isso, uma resposta lenta derruba a matriz inteira.
Cassandra, Redis e Neo4j só são lentos sob `naive` — `optimized` agrupa
suas escritas, eliminando o custo de uma ida ao banco por linha. A mesma opção vale
para uma importação avulsa: `python -m polyglotimportcsv --strategy naive`.

A matriz também tem um eixo `execution` (padrão `stream`). Use
`--executions materialize,stream` para comparar os dois caminhos de escrita:
`materialize` carrega cada origem por completo, então o pico de memória cresce com
o dataset, enquanto `stream` mantém ~um bloco de leitura por vez, então o pico fica
praticamente constante. Cada execução registra `peak_memory_mb` (pico da importação
inteira medido com `tracemalloc`). A mesma opção vale para uma importação avulsa:
`python -m polyglotimportcsv --execution materialize`.

O `tracemalloc` instrumenta cada alocação, então infla os segundos registrados em
uma medida que depende de quantas alocações o caminho faz — e `materialize` (poucas
alocações grandes do pandas) e `stream` (muitas pequenas, por bloco) não alocam da
mesma forma, então o custo não se cancela entre os dois. Meça antes de confiar em
uma comparação de tempo:

    python scripts/benchmark_tracemalloc_ab.py --size 10000 \
      --executions materialize,stream --repetitions 3

O script roda a mesma célula com e sem rastreamento, intercalando os dois braços a
cada passada (para que ambos dividam o aquecimento), e imprime o custo por caminho
de escrita.

Os resultados vão para `benchmarks/`: um `benchmark_run_<timestamp>.json` e um
`benchmark_results.csv` append-only (`size,mode,strategy,execution,backend,entity,
phase,rows,median_seconds,rows_per_second,peak_memory_mb`) para os gráficos do relatório.
A fase `filter` fica de fora dos dois e também da tabela final no terminal
(`metrics.EXCLUDED_PHASES`).

### Licença

MIT — ver [LICENSE](LICENSE).
