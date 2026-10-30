<a id="english-architecture"></a>

# PolyglotImportCSV — Software Architecture

**Language / Idioma / Língua:** [English](#english-architecture) · [Português (BR)](#arquitetura-em-português)

This document reflects the **Software Architecture** skill: separate parsing from persistence, depend on narrow contracts, and keep drivers at the outer edge.

## Layering (Clean Architecture–style)

| Layer | Responsibility | Modules |
|-------|------------------|---------|
| **Drivers / Frameworks** | DB clients, CLI, terminal/log output | `cli.py`, `sinks/*.py`, `importers/*.py`, `reporting.py` |
| **Application / use case** | Orchestration, validation before I/O, metrics | `runner.py`, `import_plan.py`, `stream_runner.py`, `validation.py`, `data_validation.py`, `metrics.py`, `dbms_check.py` |
| **Domain helpers** | Source reading/profiling/binding, mapping resolution, casting, filters, row shaping, column naming | `sources.py`, `stream_source.py`, `source_profile.py`, `stream_binding.py`, `mapping_resolver.py`, `casting.py`, `column_selector.py`, `filter_engine.py`, `row_shaping.py`, `entity_utils.py` |
| **Parsing / ports** | CSV + JSON config, the write port | `csv_reader.py`, `config_parser.py`, `schemas/`, `dbms_sink.py` |

- **Parsing is independent** of any database: `csv_reader` and `config_parser` do not import drivers.
- **Source pipeline**: `stream_source.py` reads every CSV in chunks (`chunk_rows` turns `--chunk-size` into rows per chunk, from the width of each file's rows) and slices a combined CSV by its origin column, appending the `_source` pseudo-column. `source_profile.py` folds every chunk into per-column `ColumnStats`, so a column's type is inferred over the whole file (the inference read). `mapping_resolver.py` resolves auto/hybrid/manual column maps and `stream_binding.py` binds each entity to those types as an `EntityBinding`. `import_plan.plan_import` runs all of it once and returns an `ImportPlan`, which validation and write share. `casting.py` converts each chunk to native Python values by the inferred kind. Sinks receive ready batches and never read CSV themselves.
- **One engine, two kinds of sink (`DbmsStream` / `CheckingSink`)**: `stream_runner.DbmsStream` is one DBMS's share of the work. It takes each chunk through the entity's filters, casting and `each` split, buffers the rows per partition and hands batches (up to `--batch-size` rows) to a `DbmsSink`; for Neo4j it then feeds the relationships, in a second pass. `run_stream_import` runs it once per DBMS with the real sinks: the write read. The validation read runs the **same** engine, through `run_single_pass`, with `CheckingSink` (`Neo4jCheckingSink` for Neo4j) from `data_validation.py`: a `DbmsSink` that connects to nothing and, through the engine's `inspect_*` hooks, checks the rows its DBMS would receive and adds each problem to a `ValidationReport` (a count plus up to 5 examples, with file, line, column and value). Because both reads run the same code, each rule has one implementation, and the row counts of the validation are those of the write by construction.
- **Run order** (`runner.run_import`): configuration (JSON Schema, then cross-file consistency) → headers of every source (`validation.validate_headers`, which the GUI preflight calls too) → DBMS check (skipped by `--dry-run`) → inference read → validation read → write read. Any error up to the validation read exits with code 1 before anything is written; `--dry-run` stops after the validation read.
- **Reporting (rich)**: `reporting.py` drives two destinations — a terminal `RichHandler` filtered by `--log-level` and an always-DEBUG plain-text session file under `logs/`. `metrics.py` collects per-phase row counts and durations (`infer`, `validate`, and `write` per DBMS); `--benchmark` persists them under `benchmarks/`.
- **Sinks** implement `DbmsSink` (`dbms_sink.py`: `create_schema`, `ensure_partition`, `write_batch`, `close`), one per DBMS in `sinks/`, on top of the DBMS-specific helpers in `importers/`. `runner.run_import(..., sink_factories=...)` accepts a dict of factories (`default_sink_factories()` wires the real ones) so tests can inject fakes (**Dependency Inversion**).
- **DBMS check**: `dbms_check.py` probes every target DBMS over TCP before any data row is read, with addresses taken from the drivers' own parsing; `runner` prints the states and the `start` hints of the DBMS configuration and aborts with `DbmsUnavailableError` when one is not ready. It never runs a start command.

## SOLID mapping

- **SRP**: `schema_generator` only emits SQL DDL; each `*_sink` module handles one DBMS.
- **OCP**: A new DBMS is added with a key in `validation.BACKENDS`, a sink in `sinks/` and its entry in `default_sink_factories()` (plus a schema branch if needed); the engine does not change.
- **DIP**: The runner and the engine depend on the `DbmsSink` protocol and on sink factories, not on `psycopg2` or `redis` types.

## Testing (TDD skill)

- **Unit tests** mock or avoid I/O: filter tests, config schema tests, **fake sinks** in `test_stream_runner.py` and injected `sink_factories` in `test_runner.py`.
- **Integration tests** (optional) hit real databases via `docker-compose.yml`; not required for CI in the default `pytest` run.

---

<a id="arquitetura-em-português"></a>

## Arquitetura em português

**Language / Idioma / Língua:** [English](#english-architecture) · [Português (BR)](#arquitetura-em-português)

Este documento segue a skill de **arquitetura de software**: separar *parsing* de persistência, contratos estreitos e *drivers* na borda.

### Camadas

| Camada | Papel | Módulos |
|--------|--------|---------|
| **Drivers** | Clientes de SGBD, CLI, saída de terminal/log | `cli.py`, `sinks/*.py`, `importers/*.py`, `reporting.py` |
| **Caso de uso** | Orquestração, validação antes de I/O, métricas | `runner.py`, `import_plan.py`, `stream_runner.py`, `validation.py`, `data_validation.py`, `metrics.py`, `dbms_check.py` |
| **Domínio** | Leitura, perfil e vínculo das fontes, resolução de mapeamento, conversão de tipos, filtros, montagem de linhas | `sources.py`, `stream_source.py`, `source_profile.py`, `stream_binding.py`, `mapping_resolver.py`, `casting.py`, `column_selector.py`, `filter_engine.py`, `row_shaping.py`, `entity_utils.py` |
| **Parsing e portas** | CSV + JSON, a porta de escrita | `csv_reader.py`, `config_parser.py`, `schemas/`, `dbms_sink.py` |

`stream_source.py` lê cada CSV em blocos (`chunk_rows` converte `--chunk-size` em linhas por bloco, pela largura das linhas de cada arquivo) e fatia um CSV combinado pela coluna de origem, acrescentando a pseudocoluna `_source`. `source_profile.py` acumula cada bloco em `ColumnStats` por coluna, de modo que o tipo de uma coluna é inferido sobre o arquivo inteiro (a leitura de inferência). `mapping_resolver.py` resolve os mapeamentos de colunas e `stream_binding.py` vincula cada entidade a esses tipos (`EntityBinding`). `import_plan.plan_import` faz tudo isso uma vez e devolve um `ImportPlan`, que a validação e a gravação compartilham. `casting.py` converte cada bloco para valores nativos conforme o tipo inferido. Os *sinks* recebem lotes prontos e não leem CSV diretamente.
`stream_runner.DbmsStream` é a parte de cada SGBD no trabalho: leva cada bloco pelos filtros, pela conversão e pela divisão `each` da entidade, acumula as linhas por partição e entrega lotes (de até `--batch-size` linhas) a um `DbmsSink`; no Neo4j, alimenta depois os relacionamentos, em uma segunda passagem. `run_stream_import` o executa uma vez por SGBD, com os *sinks* reais: a leitura de gravação. A leitura de validação executa o **mesmo** motor, por `run_single_pass`, com `CheckingSink` (`Neo4jCheckingSink` no Neo4j), de `data_validation.py`: um `DbmsSink` que não conecta a nada e, pelos ganchos `inspect_*` do motor, confere as linhas que o seu SGBD receberia e acrescenta cada problema a um `ValidationReport` (a contagem e até 5 exemplos, com arquivo, linha, coluna e valor). Como as duas leituras executam o mesmo código, cada regra tem uma só implementação, e as contagens da validação são as da gravação por construção.
A ordem de `runner.run_import` é: configuração (JSON Schema, depois consistência entre os arquivos) → cabeçalhos de todas as fontes (`validation.validate_headers`, que a pré-verificação da GUI também chama) → verificação dos SGBDs (o `--dry-run` pula) → leitura de inferência → leitura de validação → leitura de gravação. Qualquer erro até a leitura de validação termina com código 1 antes de gravar; o `--dry-run` para depois da leitura de validação.
Antes de ler qualquer linha de dados, `dbms_check.py` sonda por TCP cada SGBD de destino, com os endereços obtidos pelo código dos próprios *drivers*; o `runner` mostra os estados e as dicas do bloco `start` e interrompe com `DbmsUnavailableError` quando algum não está pronto. O comando de `start` nunca é executado.
A camada de saída usa a biblioteca `rich`: o terminal respeita `--log-level` (padrão INFO) e o arquivo de sessão em `logs/` sempre grava DEBUG em texto puro; `metrics.py` mede linhas e duração por fase (inferência, validação e escrita por SGBD) e o flag `--benchmark` persiste os resultados em `benchmarks/`.

### Testes (skill TDD)

Testes unitários evitam I/O real; as fábricas de *sinks* injetáveis em `run_import` (`sink_factories`) permitem *stubs* para novos cenários sem Docker.
