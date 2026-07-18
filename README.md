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

### Licença

MIT — ver [LICENSE](LICENSE).
