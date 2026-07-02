---
name: software-architecture
description: >-
  Applies layered architecture, clear module boundaries, SOLID, and dependency
  inversion for data pipelines and multi-backend tools. Use when designing or
  refactoring imports, CLI orchestration, persistence adapters, configuration
  formats, or when the user mentions architecture, coupling, Clean Architecture,
  ports and adapters, or maintainability.
---

# Software architecture (project skill)

## When to read this skill

Use it for **new features**, **refactors**, or **reviews** that touch how code is split across modules—especially CSV/config parsing, validation, filtering, and database-specific importers.

## Principles (apply in this order)

1. **Separate concerns**
   - **Parsing / config**: no database drivers (e.g. JSON Schema + CSV reading only).
   - **Use case / orchestration**: validate inputs, choose backends, call importers through narrow contracts—not concrete driver types everywhere.
   - **Infrastructure**: driver code and SQL/Cypher/CQL live at the edge (importer modules, CLI wiring).

2. **Stable direction of dependencies**
   - Inner layers must not import outer layers.
   - Prefer **protocols / callables** (e.g. importer registry) so tests and future backends can substitute behavior without editing core orchestration.

3. **SOLID (practical checklist)**
   - **SRP**: one module per backend; schema DDL generation separate from row insert paths where it helps clarity.
   - **OCP**: add a backend by registering an importer + config keys, not by scattering `if backend ==` across unrelated files.
   - **LSP**: importers honor the same contract (same inputs/outputs, same error semantics for “skip vs fail” as documented).
   - **ISP**: small interfaces for what the runner actually needs (import function + config slice), not “god” types.
   - **DIP**: `runner` depends on abstractions (registry of callables / protocol), not on `psycopg2` / `redis` types directly.

4. **Configuration as data**
   - Treat the import JSON as **declarative** contract: validate with schema; keep “business rules” in code, not hidden magic in config.

5. **Documentation stays honest**
   - When architecture changes, update `docs/ARCHITECTURE.md` and keep the README “layout” table accurate.

## Anti-patterns to avoid

- Importing drivers from `config_parser`, `csv_reader`, or `filter_engine`.
- Duplicating the same column→entity mapping logic in every importer without shared helpers.
- Growing `cli.py` into orchestration + business rules + DB details—push orchestration to `runner` and keep CLI thin.

## Project anchors (read before large edits)

- `src/polyglotimportcsv/runner.py` — orchestration and importer injection.
- `src/polyglotimportcsv/importers/base.py` — importer contract.
- `docs/ARCHITECTURE.md` — layering map for contributors.
