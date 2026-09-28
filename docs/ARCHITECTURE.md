<a id="english-architecture"></a>

# PolyglotImportCSV — Software Architecture

**Language / Idioma / Língua:** [English](#english-architecture) · [Português (BR)](#arquitetura-em-português)

This document reflects the **Software Architecture** skill: separate parsing from persistence, depend on narrow contracts, and keep drivers at the outer edge.

## Layering (Clean Architecture–style)

| Layer | Responsibility | Modules |
|-------|------------------|---------|
| **Drivers / Frameworks** | DB clients, CLI, terminal/log output | `cli.py`, `importers/*.py`, `reporting.py` |
| **Application / use case** | Orchestration, validation before I/O, metrics | `runner.py`, `validation.py`, `metrics.py`, `dbms_check.py` |
| **Domain helpers** | Source loading/binding, mapping resolution, casting, filters, row materialisation, column naming | `sources.py`, `mapping_resolver.py`, `casting.py`, `column_selector.py`, `filter_engine.py`, `materialize.py`, `entity_utils.py` |
| **Parsing / ports** | CSV + JSON config | `csv_reader.py`, `config_parser.py`, `schemas/` |

- **Parsing is independent** of any database: `csv_reader` and `config_parser` do not import drivers.
- **Source pipeline (config v2)**: `sources.py` loads the `sources` block (one CSV per source, or a combined CSV sliced by its origin column) and appends the `_source` pseudo-column; `mapping_resolver.py` binds each entity to its source(s) and resolves auto/hybrid/manual column maps into `BoundEntity` frames; `casting.py` converts columns to native Python values by inferred kind. Importers receive ready `BoundEntity` frames and never read CSV themselves.
- **Reporting (rich)**: `reporting.py` drives two destinations — a terminal `RichHandler` filtered by `--log-level` and an always-DEBUG plain-text session file under `logs/`. `metrics.py` collects per-phase (read/filter/map/write) row counts and durations; `--benchmark` persists them under `benchmarks/`.
- **Importers** implement the same callable shape (`BackendImporterFn` in `importers/base.py`). `runner.run_import(..., importers=...)` accepts a registry so tests can inject fakes (**Dependency Inversion**).
- **DBMS check**: `dbms_check.py` probes every target DBMS over TCP before any CSV is read, with addresses taken from the drivers' own parsing; `runner` prints the states and the `start` hints of the DBMS configuration and aborts with `DbmsUnavailableError` when one is not ready. It never runs a start command.

## SOLID mapping

- **SRP**: `schema_generator` only emits SQL DDL; each `*_importer` module handles one backend.
- **OCP**: New backends register in `default_importer_registry()` without changing `validation.BACKENDS` ordering logic (add key + importer + schema branch if needed).
- **DIP**: Runner depends on `ImporterRegistry` (callables), not on `psycopg2` or `redis` types.

## Testing (TDD skill)

- **Unit tests** mock or avoid I/O: filter tests, config schema tests, **stub importer registry** in `test_runner_registry.py`.
- **Integration tests** (optional) hit real databases via `docker-compose.yml`; not required for CI in the default `pytest` run.

---

<a id="arquitetura-em-português"></a>

## Arquitetura em português

**Language / Idioma / Língua:** [English](#english-architecture) · [Português (BR)](#arquitetura-em-português)

Este documento segue a skill de **arquitetura de software**: separar *parsing* de persistência, contratos estreitos e *drivers* na borda.

### Camadas

| Camada | Papel | Módulos |
|--------|--------|---------|
| **Drivers** | Clientes de SGBD, CLI, saída de terminal/log | `cli.py`, `importers/*.py`, `reporting.py` |
| **Caso de uso** | Orquestração, validação antes de I/O, métricas | `runner.py`, `validation.py`, `metrics.py`, `dbms_check.py` |
| **Domínio** | Fontes, resolução de mapeamento, conversão de tipos, filtros, materialização de linhas | `sources.py`, `mapping_resolver.py`, `casting.py`, `column_selector.py`, `filter_engine.py`, `materialize.py`, `entity_utils.py` |
| **Parsing** | CSV + JSON | `csv_reader.py`, `config_parser.py`, `schemas/` |

No formato v2 da configuração, `sources.py` carrega o bloco `sources` (um CSV por fonte ou um CSV combinado fatiado pela coluna de origem) e acrescenta a pseudocoluna `_source`; `mapping_resolver.py` vincula cada entidade à(s) sua(s) fonte(s) e resolve os mapeamentos de colunas em quadros `BoundEntity`; `casting.py` converte as colunas para valores nativos conforme o tipo inferido. Os importadores recebem os quadros prontos e não leem CSV diretamente.
Antes de ler qualquer CSV, `dbms_check.py` sonda por TCP cada SGBD de destino, com os endereços obtidos pelo código dos próprios *drivers*; o `runner` mostra os estados e as dicas do bloco `start` e interrompe com `DbmsUnavailableError` quando algum não está pronto. O comando de `start` nunca é executado.
A camada de saída usa a biblioteca `rich`: o terminal respeita `--log-level` (padrão INFO) e o arquivo de sessão em `logs/` sempre grava DEBUG em texto puro; `metrics.py` mede linhas e duração por fase (leitura, filtro, mapeamento, escrita) e o flag `--benchmark` persiste os resultados em `benchmarks/`.

### Testes (skill TDD)

Testes unitários evitam I/O real; o *registry* injetável em `run_import` permite *stubs* para novos cenários sem Docker.
