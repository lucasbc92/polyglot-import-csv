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

**Full running example (Docker + dry-run + import):**

```powershell
.\run_example.ps1
```

Requires Docker Desktop. The script starts all five databases, runs `--dry-run`, then imports with `--create-schema`. You can also run manually after `docker compose up -d` (see `docker-compose.yml` at repo root).

Options:

- `--only postgres,redis` — run only listed backends.
- `--no-create-schema` — skip DDL where applicable.

### Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (English + PT) for layering, SOLID mapping, and how **injectable importer registries** keep tests free of real databases. The TCC report lives in [docs-tcc/](docs-tcc/).

### Layout

| Path | Purpose |
|------|---------|
| `src/polyglotimportcsv/` | CLI, validation, filters, runner |
| `src/polyglotimportcsv/importers/` | One module per backend + `base.py` protocol |
| `src/polyglotimportcsv/schemas/` | Bundled JSON Schema |
| `data/ecommerce/` | Sample CSV + `import_config.json` |
| `tests/` | `pytest` (stubs for I/O per TDD skill) |
| `docs-tcc/` | TCC I report (Markdown, BibTeX); `docs-tcc/scripts/` for Pandoc PDF/ODT |

### Scripts

- **Windows (recommended):** `run_example.ps1` at repo root — Docker stack + dry-run + import.
- **Windows (dry-run only):** `scripts/run_example_windows.ps1`
- **macOS / Linux:** `scripts/run_example_macos.sh` (dry-run); use `docker compose` + CLI for full import.

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

**Exemplo completo (Docker + dry-run + importação):**

```powershell
.\run_example.ps1
```

Requer Docker Desktop. O script sobe os cinco bancos, executa `--dry-run` e depois importa com `--create-schema`. Também é possível usar `docker compose up -d` na raiz e rodar o CLI manualmente.

Opções úteis:

- `--only postgres,redis` — executa só os backends listados.
- `--no-create-schema` — não emite DDL de criação (quando aplicável).

### Arquitetura

Consulte [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (inglês + PT) para camadas, princípios SOLID e *registry* de importadores injetável nos testes. O relatório do TCC está em [docs-tcc/](docs-tcc/).

### Layout

| Caminho | Descrição |
|--------|------------|
| `src/polyglotimportcsv/` | CLI, validação, filtros, *runner* |
| `src/polyglotimportcsv/importers/` | Um módulo por backend + `base.py` (contrato) |
| `src/polyglotimportcsv/schemas/` | JSON Schema embutido |
| `data/ecommerce/` | CSV de exemplo + `import_config.json` |
| `tests/` | `pytest` (stubs, sem I/O real) |
| `docs-tcc/` | Relatório TCC I (Markdown + BibTeX); `docs-tcc/scripts/` para PDF/ODT via Pandoc |

### Scripts

- **Windows (recomendado):** `run_example.ps1` na raiz — Docker + dry-run + importação.
- **Windows (só dry-run):** `scripts/run_example_windows.ps1`
- **macOS / Linux:** `scripts/run_example_macos.sh` (dry-run); use `docker compose` + CLI para importação completa.

### Licença

MIT — ver [LICENSE](LICENSE).
