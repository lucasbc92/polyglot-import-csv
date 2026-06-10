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

**Running example** (single script; use [Git Bash](https://git-scm.com/) on Windows or any Unix shell):

```bash
./run_example.sh                  # Docker (if needed) + clean + dry-run + import + inspect
./run_example.sh --dry-run        # validate CSV/config only (no Docker)
./run_example.sh --fresh-start      # first-time: wipe volumes/images, re-pull, full default flow
./run_example.sh --clean --dry-run --import --inspect   # explicit equivalent of default
./run_example.sh --csv path/to/your.csv --config data/ecommerce/import_config.json
```

Requires Docker for import/clean/inspect. Use `--fresh-start` for a true first-time run (removes volumes and images, re-pulls, then default flow). Every command is printed as `$ ...` in the terminal and in `logs/`.

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
| `logs/` | Session logs from `run_example.sh` and direct CLI runs (gitignored) |
| `tests/` | `pytest` (stubs for I/O per TDD skill) |
| `docs-tcc/` | TCC I report (Markdown, BibTeX); `docs-tcc/scripts/` for Pandoc PDF/ODT |

### Scripts

- `./run_example.sh` — orchestrates Docker, import, clean, and inspect (see `--help`).
- `scripts/inspect_persisted_data.py` — low-level `clean` / `inspect` helpers (usually invoked via `run_example.sh`).

**Tab completion (Git Bash / bash):** add to `~/.bashrc`, then open a new terminal:

```bash
source "/c/Users/DELL/Documents/polyglot-import-csv/scripts/run_example.completion.bash"
```

After that, `./run_example.sh --` + TAB suggests flags (`--fresh-start`, `--clean`, `--inspect`, …); `--csv` / `--config` / `--log-file` suggest paths under `data/ecommerce/` and `logs/`.

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

**Exemplo de execução** (um único script; no Windows use [Git Bash](https://git-scm.com/) ou WSL):

```bash
./run_example.sh                  # Docker (se necessário) + clean + dry-run + importação + inspect
./run_example.sh --dry-run        # só validação (sem Docker)
./run_example.sh --fresh-start      # primeiro uso: apaga volumes/imagens, baixa de novo, fluxo padrão
./run_example.sh --clean --dry-run --import --inspect   # equivalente explícito ao padrão
```

Requer Docker para importar/limpar/inspecionar. Use `--fresh-start` para simular o primeiro uso (remove volumes e imagens, `pull`, fluxo padrão). Cada comando aparece como `$ ...` no terminal e em `logs/`.

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

- `./run_example.sh` — orquestra Docker, importação, limpeza e inspeção (`--help`).
- `scripts/inspect_persisted_data.py` — comandos `clean` / `inspect` (chamados pelo `run_example.sh`).

**Autocompletar com TAB (Git Bash / bash):** inclua no `~/.bashrc` e abra um terminal novo:

```bash
source "/c/Users/DELL/Documents/polyglot-import-csv/scripts/run_example.completion.bash"
```

Depois, `./run_example.sh --` + TAB sugere flags (`--fresh-start`, `--clean`, `--inspect`, …); `--csv` / `--config` / `--log-file` sugerem caminhos em `data/ecommerce/` e `logs/`.

### Licença

MIT — ver [LICENSE](LICENSE).
