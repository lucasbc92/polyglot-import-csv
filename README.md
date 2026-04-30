<!-- Language selector: keep this block at the top for GitHub / editors -->
**Language / Idioma / Língua:** [English](#english) · [Português (BR)](#português-br)

---

## English

Python CLI that imports one **wide CSV** (joined relational view) into **PostgreSQL, Redis, MongoDB, Apache Cassandra, and Neo4j** using a **JSON** file validated with **JSON Schema**.

### Requirements

- Python 3.9+ (official Cassandra driver C extensions are easiest on Python ≤3.11; `--dry-run` never opens sockets).

### Install

```bash
pip install -e ".[dev]"
```

### Usage

```bash
python -m polyglotimportcsv data/ecommerce/ecommerce_join.csv --config data/ecommerce/import_config.json --dry-run
```

Remove `--dry-run` after `docker compose up -d` (see repo root `docker-compose.yml`).

Options:

- `--only postgres,redis` — run only listed backends.
- `--no-create-schema` — skip DDL where applicable.

### Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (English + PT) for layering, SOLID mapping, and how **injectable importer registries** keep tests free of real databases.

### Layout

| Path | Purpose |
|------|---------|
| `src/polyglotimportcsv/` | CLI, validation, filters, runner |
| `src/polyglotimportcsv/importers/` | One module per backend + `base.py` protocol |
| `src/polyglotimportcsv/schemas/` | Bundled JSON Schema |
| `data/ecommerce/` | Sample CSV + `import_config.json` |
| `tests/` | `pytest` (stubs for I/O per TDD skill) |
| `_docs/` | Thesis (Markdown, BibTeX); `_docs/scripts/` has `.ps1` (Windows) and `.sh` (Unix) for Pandoc |

### Scripts

- **Windows:** `scripts/run_example_windows.ps1` (or `run_example_windows.bat`, which calls PowerShell).
- **macOS / Linux:** `scripts/run_example_macos.sh`.

### License

MIT — see [LICENSE](LICENSE).

---

## Português (BR)

Ferramenta em Python para importar um **único CSV** (visão larga / *join* de várias tabelas) para **vários SGBDs** ao mesmo tempo — PostgreSQL, Redis, MongoDB, Apache Cassandra e Neo4j — com base em um arquivo **JSON** validado por *JSON Schema*.

### Requisitos

- Python 3.9+ (para o *driver* oficial do Cassandra, versões LTS até 3.11 costumam ser mais simples por causa das extensões C; `--dry-run` não abre conexões).

### Instalação

```bash
pip install -e ".[dev]"
```

### Uso

```bash
python -m polyglotimportcsv data/ecommerce/ecommerce_join.csv --config data/ecommerce/import_config.json --dry-run
```

Remova `--dry-run` após subir os bancos (por exemplo com `docker compose up -d` na raiz do repositório).

Opções úteis:

- `--only postgres,redis` — executa só os backends listados.
- `--no-create-schema` — não emite DDL de criação (quando aplicável).

### Arquitetura

Consulte [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (inglês + PT) para camadas, princípios SOLID e *registry* de importadores injetável nos testes.

### Layout

| Caminho | Descrição |
|--------|------------|
| `src/polyglotimportcsv/` | CLI, validação, filtros, *runner* |
| `src/polyglotimportcsv/importers/` | Um módulo por backend + `base.py` (contrato) |
| `src/polyglotimportcsv/schemas/` | JSON Schema embutido |
| `data/ecommerce/` | CSV de exemplo + `import_config.json` |
| `tests/` | `pytest` (stubs, sem I/O real) |
| `_docs/` | TCC (Markdown + BibTeX); em `_docs/scripts/` existem `.ps1` (Windows) e `.sh` (Unix) para Pandoc |

### Scripts

- **Windows:** `scripts/run_example_windows.ps1` (ou `run_example_windows.bat`, que chama o PowerShell).
- **macOS / Linux:** `scripts/run_example_macos.sh`.

### Licença

MIT — ver [LICENSE](LICENSE).
