<a id="english-architecture"></a>

# PolyglotImportCSV — Software Architecture

**Language:** [English](#english-architecture) · [Português](#arquitetura-em-português)

This document reflects the **Software Architecture** skill: separate parsing from persistence, depend on narrow contracts, and keep drivers at the outer edge.

## Layering (Clean Architecture–style)

| Layer | Responsibility | Modules |
|-------|------------------|---------|
| **Drivers / Frameworks** | DB clients, CLI | `cli.py`, `importers/*.py` |
| **Application / use case** | Orchestration, validation before I/O | `runner.py`, `validation.py` |
| **Domain helpers** | Filters, row materialisation, column naming | `filter_engine.py`, `materialize.py`, `entity_utils.py` |
| **Parsing / ports** | CSV + JSON config | `csv_reader.py`, `config_parser.py`, `schemas/` |

- **Parsing is independent** of any database: `csv_reader` and `config_parser` do not import drivers.
- **Importers** implement the same callable shape (`BackendImporterFn` in `importers/base.py`). `runner.run_import(..., importers=...)` accepts a registry so tests can inject fakes (**Dependency Inversion**).

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

**Idioma:** [English](#english-architecture) · [Português](#arquitetura-em-português)

Este documento segue a skill de **arquitetura de software**: separar *parsing* de persistência, contratos estreitos e *drivers* na borda.

### Camadas

| Camada | Papel | Módulos |
|--------|--------|---------|
| **Drivers** | Clientes de SGBD, CLI | `cli.py`, `importers/*.py` |
| **Caso de uso** | Orquestração, validação antes de I/O | `runner.py`, `validation.py` |
| **Domínio** | Filtros, materialização de linhas | `filter_engine.py`, `materialize.py`, `entity_utils.py` |
| **Parsing** | CSV + JSON | `csv_reader.py`, `config_parser.py`, `schemas/` |

### Testes (skill TDD)

Testes unitários evitam I/O real; o *registry* injetável em `run_import` permite *stubs* para novos cenários sem Docker.
