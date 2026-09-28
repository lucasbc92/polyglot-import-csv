# Verificação dos SGBDs, troca de nome SGBD → DBMS e READMEs bilíngues — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Antes de gravar qualquer dado, a ferramenta verifica se os SGBDs de destino respondem e, para os que não respondem, mostra o comando que os inicia (tirado de um bloco `start` opcional do arquivo de conexão), sem nunca executá-lo; `--check-dbms` e o botão "Verificar SGBDs" fazem só a verificação. Junto, `sgbd_config` passa a se chamar `dbms_config`, todos os READMEs ficam bilíngues e sai a release v1.1.0.

**Architecture:** Um módulo novo, `dbms_check.py`, obtém os endereços de cada SGBD com o próprio código dos drivers (`MongoClient(connect=False)`, `GraphDatabase.driver`, `neo4j.Address.parse`, regras do libpq), sonda cada um por TCP em paralelo e devolve um `DbmsCheckReport` sem imprimir nada. O `runner` apresenta o relatório e aborta a importação com `DbmsUnavailableError` antes de ler os CSVs; `run_check` atende `--check-dbms`. Na GUI, o núcleo puro ganha `build_check_argv` e `Preflight.checkable`; a camada Qt ganha o botão e o estado "verificando".

**Tech Stack:** Python 3.9+, click, rich, jsonschema, pymongo 4.17, neo4j 6.2, PySide6, pytest, pytest-qt, LaTeX (latexmk/pdflatex, MiKTeX), Mermaid CLI.

**Spec:** `docs/superpowers/specs/2026-09-27-dbms-check-design.md`

## Global Constraints

- **Interpretador e suíte:** `PY=./.venv/Scripts/python.exe`, a partir da raiz do repositório. Suíte: `$PY -m pytest tests -q -p no:cacheprovider`. Referência antes deste plano: **634 passed, 1 skipped**. Cada tarefa termina com a suíte verde e com a contagem lida por inteiro: o `python` do sistema não tem `pytest-qt`, e o filtro do `rtk` esconde testes com erro.
- **Python mínimo:** 3.9. Sem `X | Y` em anotações de tempo de execução, sem `match`. Todo módulo novo começa com `from __future__ import annotations`.
- **Núcleo da GUI sem Qt:** `gui/state.py`, `gui/command.py`, `gui/launcher.py`, `gui/ansi.py` e `gui/preflight.py` não importam PySide6. `reporting.py` não importa `dbms_check` (a GUI importa `reporting` e não deve carregar pymongo/neo4j por isso).
- **Regra SGBD/DBMS:** "DBMS" em nomes de arquivo, identificadores, opções da CLI, JSON Schemas, mensagens da CLI (inglês), docstrings/comentários e seções EN dos READMEs. "SGBD" só em texto em português visível ao usuário (GUI, seções PT dos READMEs) e no texto corrido do relatório. Nunca "backend" em código novo.
- **Troca de nome limpa:** nenhum alias para `--sgbd-config` ou `sgbd_config.json`.
- **A ferramenta nunca executa o comando de `start`.** Só o exibe.
- **Endereços:** nenhum analisador de URI próprio (spec §5.1). Uma configuração que o driver aceita nunca vira `invalid`; exceção única, já decidida: porta do Neo4j que nem é número em 1–65535 nem nome de serviço conhecido, que o driver aceita na construção mas com a qual nunca conecta.
- **Rótulos da GUI:** português do Brasil. **Mensagens da CLI:** inglês.
- **Commits:** um por tarefa, mensagem em português (`feat(cli): ...`, `docs(tcc): ...`), terminando com `Co-Authored-By: Claude <modelo> <noreply@anthropic.com>`. `git push` logo após cada commit (política do projeto: o disco D: já perdeu objetos git).
- **Branch:** `dbms-check`, criada a partir de `main` na Tarefa 1.
- **Nenhum teste toca banco de dados.** A sonda é substituída por um fixture `autouse` (Tarefa 4); os testes da sonda real usam um socket local.
- **Tarefas 11 e 12 precisam do Docker** com a pilha do exemplo no ar, exceto MongoDB e Neo4j (`docker compose up -d --wait` e depois `docker compose stop mongodb neo4j`). Ao final, `docker compose start mongodb neo4j`.
- **Desvios deliberados em relação ao spec, já decididos:**
  1. O relatório separa `fixes` (conexões inválidas) de `starts` (comandos) e traz `service_commands: bool` em vez de uma única lista `hints`.
  2. A mensagem de `DbmsUnavailableError` lista os SGBDs e seus estados, mas não repete as dicas, que já saem logo acima.
  3. Status da GUI para código ≠ 0 na verificação: "Verificação não passou — veja o console". Uma configuração inválida também sai com 1.
  4. A `+srv` é resolvida por `pymongo.uri_parser.parse_uri(uri, warn=True)`, porque o `MongoClient(connect=False)` adia a resolução SRV.
  5. A figura 16 e a listagem do cap. 4 mostram **dois** SGBDs fora do ar (MongoDB e Neo4j).
  6. No relatório, a saída da verificação vira uma tabela LaTeX mais uma listagem das dicas, como a Tabela `tab:dryrun`. O pdflatex não aceita os caracteres de borda do rich.
  7. O seletor de idioma do `ARCHITECTURE.md` mantém as âncoras que o arquivo já tem.

## Review Focus

- **Comando de start comprido no terminal:** o rich quebraria a linha na largura do console, e a cópia levaria uma quebra de linha para dentro do comando. As dicas saem com `no_wrap=True, overflow="ignore"`. Teste na Tarefa 5 (`test_start_commands_are_never_wrapped`).
- **Arquivo de conexão com outro nome (`dbms_config_windows.json`):** as dicas e as correções citam o arquivo realmente usado, e não `dbms_config.json`. Teste na Tarefa 4 (`test_hints_name_the_dbms_config_actually_used`).
- **URI válida porém incomum** (opções na query, IPv6, socket Unix, `+srv`, esquemas `+s`/`+ssc`): nunca vira `invalid`. Teste de consistência com os drivers na Tarefa 3.
- **`--only` com um SGBD que não está no import config:** a verificação não testa SGBDs que a importação não usaria. Teste na Tarefa 5 (`test_run_check_targets_follow_only`).
- **Verificação interrompida pelo usuário:** interromper não pede confirmação e a GUI volta ao estado ocioso com a mensagem de falha da verificação. Teste na Tarefa 8 (`test_stopping_a_check_does_not_ask_for_confirmation`).

---

### Task 1: Troca de nome SGBD → DBMS (sem mudança de comportamento)

**Files:**
- Rename: `data/ecommerce/sgbd_config.json` → `data/ecommerce/dbms_config.json`
- Rename: `src/polyglotimportcsv/schemas/sgbd_config.schema.json` → `src/polyglotimportcsv/schemas/dbms_config.schema.json`
- Modify (script): `src/polyglotimportcsv/{config_parser,runner,cli,benchmark_runner,business_exception}.py`, `src/polyglotimportcsv/schemas/{dbms_config,import_config}.schema.json`, `src/polyglotimportcsv/gui/{state,command,preflight}.py`, `src/polyglotimportcsv/gui/widgets/{config_panel,main_window}.py`, `run_example.sh`, `scripts/run_example.completion.bash`, `scripts/{inspect_persisted_data,run_benchmarks,benchmark_tracemalloc_ab,capture_gui_figures}.py`, `tests/test_{benchmark_runner,benchmark_resume,benchmark_tracemalloc_ab,config_parser,gui_command,gui_config_panel,gui_main_window,gui_preflight,gui_state,validation_dry_run}.py`, `README.md`, `docs/ARCHITECTURE.md`, `data/ecommerce/README.md`, `packaging/LEIAME.txt`

**Interfaces:**
- Consumes: nada.
- Produces (usado por todas as tarefas seguintes):
  - `config_parser.DEFAULT_DBMS_CONFIG_NAME = "dbms_config.json"`
  - `config_parser.load_dbms_config(path) -> Dict[str, Any]`, `config_parser.validate_dbms_config(data) -> None`
  - `config_parser.merge_configs(import_cfg, dbms_cfg)`, `config_parser.load_config(import_path, dbms_path=None)`
  - `run_import(..., dbms_config_path=...)`; CLI `--dbms-config`
  - `gui.state.RunOptions.dbms_config_path`; chave de erro `"dbms_config_path"`; `ConfigPanel.dbms_config_path()`

- [ ] **Step 1: Branch**

```bash
git checkout -b dbms-check
```

- [ ] **Step 2: Renomear os dois arquivos**

```bash
git mv data/ecommerce/sgbd_config.json data/ecommerce/dbms_config.json
git mv src/polyglotimportcsv/schemas/sgbd_config.schema.json src/polyglotimportcsv/schemas/dbms_config.schema.json
```

- [ ] **Step 3: Aplicar a troca de nome com um script**

Salve em `$SCRATCH/rename_dbms.py`, onde `$SCRATCH` é o diretório de rascunho da sessão, e rode da raiz com `$PY "$SCRATCH/rename_dbms.py"`:

```python
"""One-off: sgbd -> dbms outside Portuguese user-facing text (spec §3)."""
import re
from pathlib import Path

# Every lowercase "sgbd" is an identifier, file name or CLI option: all go.
ALL_LOWER = [
    "src/polyglotimportcsv/config_parser.py", "src/polyglotimportcsv/runner.py",
    "src/polyglotimportcsv/cli.py", "src/polyglotimportcsv/benchmark_runner.py",
    "src/polyglotimportcsv/business_exception.py",
    "src/polyglotimportcsv/schemas/dbms_config.schema.json",
    "src/polyglotimportcsv/schemas/import_config.schema.json",
    "src/polyglotimportcsv/gui/state.py", "src/polyglotimportcsv/gui/command.py",
    "src/polyglotimportcsv/gui/preflight.py",
    "src/polyglotimportcsv/gui/widgets/config_panel.py",
    "src/polyglotimportcsv/gui/widgets/main_window.py",
    "run_example.sh", "scripts/run_example.completion.bash",
    "scripts/inspect_persisted_data.py", "scripts/run_benchmarks.py",
    "scripts/benchmark_tracemalloc_ab.py", "scripts/capture_gui_figures.py",
    "tests/test_benchmark_runner.py", "tests/test_benchmark_resume.py",
    "tests/test_benchmark_tracemalloc_ab.py", "tests/test_config_parser.py",
    "tests/test_gui_command.py", "tests/test_gui_config_panel.py",
    "tests/test_gui_main_window.py", "tests/test_gui_preflight.py",
    "tests/test_gui_state.py", "tests/test_validation_dry_run.py",
    "README.md", "docs/ARCHITECTURE.md", "data/ecommerce/README.md",
    "packaging/LEIAME.txt",
]
# Files written entirely in English: uppercase SGBD also becomes DBMS.
ENGLISH = [
    "src/polyglotimportcsv/config_parser.py", "src/polyglotimportcsv/cli.py",
    "src/polyglotimportcsv/business_exception.py",
    "src/polyglotimportcsv/schemas/dbms_config.schema.json",
    "src/polyglotimportcsv/schemas/import_config.schema.json",
    "run_example.sh", "scripts/inspect_persisted_data.py",
    "scripts/capture_gui_figures.py", "tests/test_config_parser.py",
    "data/ecommerce/README.md",
]


def upper(text):
    return text.replace("SGBDs", "DBMSs").replace("SGBD", "DBMS")


for name in ALL_LOWER:
    path = Path(name)
    text = path.read_text(encoding="utf-8")
    new = text.replace("sgbd", "dbms")
    if name in ENGLISH:
        new = upper(new)
    if name == "README.md":
        # Only the English half; the Portuguese half keeps "SGBD" in prose.
        head, sep, tail = new.partition("## Português (BR)")
        new = upper(head) + sep + tail
    if new != text:
        path.write_text(new, encoding="utf-8", newline="")
        print("updated", name)
```

O `newline=""` preserva os finais de linha originais. O `run_example.sh` precisa continuar com LF.

- [ ] **Step 4: Revisar os pontos que o script não decide sozinho**

Rode `git grep -n -i "sgbd" -- src scripts tests run_example.sh README.md docs/ARCHITECTURE.md data packaging` e confira que **cada** ocorrência restante é texto em português visível ao usuário. Devem sobrar só estas:
- `src/polyglotimportcsv/__init__.py` ("múltiplos SGBDs")
- `gui/state.py` ("SGBD desconhecido")
- `gui/preflight.py` ("Configuração de SGBDs não informada…")
- `gui/widgets/config_panel.py` (rótulos e dicas em português)
- `gui/widgets/options_panel.py` ("nenhum SGBD")
- `tests/test_gui_state.py` ("SGBD desconhecido: oracle")
- `README.md`, só na seção PT
- `docs/ARCHITECTURE.md`, na seção PT

Três pontos pedem conferência manual:
- O rótulo em `config_panel.py` deve ter ficado `"Configuração de SGBDs (--dbms-config)"`.
- A chave `QSettings` `"last_sgbd"` virou `"last_dbms"`. Isso é intencional: o último caminho lembrado some uma vez.
- No `README.md`, a seção EN diz "DBMS" e a PT continua dizendo "SGBD", mas com `dbms_config.json` e `--dbms-config`.

- [ ] **Step 5: Rodar a suíte**

Run: `$PY -m pytest tests -q -p no:cacheprovider`
Expected: `634 passed, 1 skipped`. Se algo falhar, a causa é uma ocorrência que o script não trocou, ou que trocou dentro de texto em português. Corrija à mão.

- [ ] **Step 6: Conferir o dry-run com o arquivo padrão**

Run: `$PY -m polyglotimportcsv --config data/ecommerce/import_config.json --dry-run --no-data`
Expected: termina com `✓ Finished dry-run`, sem `--dbms-config`, porque encontra `dbms_config.json` ao lado.

- [ ] **Step 7: Commit e push**

```bash
git add -A
git commit -m "refactor: sgbd_config passa a se chamar dbms_config

Troca limpa, sem aliases: dbms_config.json, dbms_config.schema.json e
--dbms-config. SGBD fica so nos textos em portugues da GUI e dos READMEs.

Co-Authored-By: Claude <modelo> <noreply@anthropic.com>"
git push -u origin dbms-check
```

---

### Task 2: Bloco `start` no esquema e os três arquivos de exemplo

**Files:**
- Modify: `src/polyglotimportcsv/schemas/dbms_config.schema.json`
- Modify: `data/ecommerce/dbms_config.json`
- Create: `data/ecommerce/dbms_config_windows.json`, `data/ecommerce/dbms_config_linux.json`
- Test: `tests/test_config_parser.py`

**Interfaces:**
- Consumes: `load_dbms_config`, `validate_dbms_config`, `merge_configs` (Tarefa 1).
- Produces: cada bloco de SGBD aceita `"start": {"command": str}` ou `"start": {"compose": {"file": str, "service": str}}`; os três arquivos de exemplo (usados nas Tarefas 5, 6, 10, 11 e 12).

- [ ] **Step 1: Escrever os testes que falham**

Acrescente ao fim de `tests/test_config_parser.py`, completando os imports que faltarem no topo (`from pathlib import Path`, `load_dbms_config`):

```python
ECOMMERCE = Path(__file__).resolve().parents[1] / "data" / "ecommerce"
DBMS_NAMES = ("postgres", "mongodb", "cassandra", "redis", "neo4j")


def _postgres_with(start):
    return {"version": 1, "postgres": {"connection": {"host": "h"}, "start": start}}


@pytest.mark.parametrize("start", [
    {"command": "net start postgresql-x64-16"},
    {"compose": {"file": "../../docker-compose.yml", "service": "postgres"}},
])
def test_dbms_schema_accepts_each_start_form(start):
    validate_dbms_config(_postgres_with(start))


@pytest.mark.parametrize("start", [
    {"command": "x", "compose": {"file": "f", "service": "s"}},  # both forms
    {"command": ""},
    {"command": "x", "sudo": True},
    {"compose": {"file": "f"}},
    {"compose": {"file": "f", "service": "s", "profile": "p"}},
    {},
])
def test_dbms_schema_rejects_a_malformed_start(start):
    with pytest.raises(BusinessException):
        validate_dbms_config(_postgres_with(start))


@pytest.mark.parametrize("name", [
    "dbms_config.json", "dbms_config_windows.json", "dbms_config_linux.json",
])
def test_example_dbms_configs_are_valid_and_declare_start_everywhere(name):
    cfg = load_dbms_config(ECOMMERCE / name)
    for dbms in DBMS_NAMES:
        assert "start" in cfg[dbms], (name, dbms)


def test_example_dbms_configs_share_the_same_connections():
    base = load_dbms_config(ECOMMERCE / "dbms_config.json")
    for name in ("dbms_config_windows.json", "dbms_config_linux.json"):
        other = load_dbms_config(ECOMMERCE / name)
        for dbms in DBMS_NAMES:
            assert other[dbms]["connection"] == base[dbms]["connection"], (name, dbms)
        assert other["postgres"]["schema"] == base["postgres"]["schema"]


def test_example_compose_references_point_at_the_repository_compose_file():
    for name in ("dbms_config.json", "dbms_config_windows.json"):
        cfg = load_dbms_config(ECOMMERCE / name)
        for dbms in DBMS_NAMES:
            compose = cfg[dbms]["start"].get("compose")
            if compose:
                assert (ECOMMERCE / compose["file"]).resolve().is_file(), (name, dbms)


def test_merge_does_not_carry_start_into_the_import_structure():
    import_cfg = {"sources": {"s": "s.csv"}, "postgres": {"entities": {}}}
    dbms_cfg = {"version": 1, "postgres": {"connection": {"host": "h"},
                                           "start": {"command": "x"}}}
    merged = merge_configs(import_cfg, dbms_cfg)
    assert "start" not in merged["postgres"]
    assert merged["postgres"]["connection"] == {"host": "h"}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `$PY -m pytest tests/test_config_parser.py -q -p no:cacheprovider`
Expected: FAIL. `start` é rejeitado por `additionalProperties: false`, e os arquivos `_windows`/`_linux` não existem.

- [ ] **Step 3: Esquema**

Em `src/polyglotimportcsv/schemas/dbms_config.schema.json`:

(a) Em cada uma das cinco definições (`postgresConnection`, `mongoConnection`, `cassandraConnection`, `redisConnection`, `neo4jConnection`), acrescente a `properties`, ao lado de `"connection"`:

```json
        "start": { "$ref": "#/$defs/start" }
```

(b) Acrescente em `$defs`, depois de `neo4jConnection`:

```json
    "start": {
      "description": "How to start this DBMS when it does not answer. Shown to the user, never executed.",
      "oneOf": [
        {
          "type": "object",
          "properties": {
            "command": { "type": "string", "minLength": 1, "description": "Command line that starts a DBMS installed on this machine." }
          },
          "required": ["command"],
          "additionalProperties": false
        },
        {
          "type": "object",
          "properties": {
            "compose": {
              "type": "object",
              "properties": {
                "file": { "type": "string", "minLength": 1, "description": "Docker Compose file, relative to this configuration file's folder." },
                "service": { "type": "string", "minLength": 1, "description": "Service of that file that runs this DBMS." }
              },
              "required": ["file", "service"],
              "additionalProperties": false
            }
          },
          "required": ["compose"],
          "additionalProperties": false
        }
      ]
    }
```

O `merge_configs` já copia só `connection` e `schema`, então não muda.

- [ ] **Step 4: Arquivos de exemplo**

`data/ecommerce/dbms_config.json` (substitui o conteúdo inteiro):

```json
{
  "version": 1,

  "postgres": {
    "connection": {
      "host": "127.0.0.1",
      "port": 5432,
      "database": "ecommerce",
      "user": "postgres",
      "password": "postgres"
    },
    "schema": "public",
    "start": { "compose": { "file": "../../docker-compose.yml", "service": "postgres" } }
  },

  "mongodb": {
    "connection": {
      "uri": "mongodb://127.0.0.1:27017",
      "database": "ecommerce"
    },
    "start": { "compose": { "file": "../../docker-compose.yml", "service": "mongodb" } }
  },

  "cassandra": {
    "connection": {
      "hosts": ["127.0.0.1"],
      "port": 9042,
      "keyspace": "ecommerce"
    },
    "start": { "compose": { "file": "../../docker-compose.yml", "service": "cassandra" } }
  },

  "redis": {
    "connection": { "host": "127.0.0.1", "port": 6379, "db": 0 },
    "start": { "compose": { "file": "../../docker-compose.yml", "service": "redis" } }
  },

  "neo4j": {
    "connection": {
      "uri": "bolt://127.0.0.1:7687",
      "user": "neo4j",
      "password": "password",
      "database": "neo4j"
    },
    "start": { "compose": { "file": "../../docker-compose.yml", "service": "neo4j" } }
  }
}
```

`data/ecommerce/dbms_config_windows.json`: mesmas conexões, com estes `start`:

```json
{
  "version": 1,

  "postgres": {
    "connection": {
      "host": "127.0.0.1",
      "port": 5432,
      "database": "ecommerce",
      "user": "postgres",
      "password": "postgres"
    },
    "schema": "public",
    "start": { "command": "net start postgresql-x64-16" }
  },

  "mongodb": {
    "connection": {
      "uri": "mongodb://127.0.0.1:27017",
      "database": "ecommerce"
    },
    "start": { "command": "net start MongoDB" }
  },

  "cassandra": {
    "connection": {
      "hosts": ["127.0.0.1"],
      "port": 9042,
      "keyspace": "ecommerce"
    },
    "start": { "compose": { "file": "../../docker-compose.yml", "service": "cassandra" } }
  },

  "redis": {
    "connection": { "host": "127.0.0.1", "port": 6379, "db": 0 },
    "start": { "command": "net start Memurai" }
  },

  "neo4j": {
    "connection": {
      "uri": "bolt://127.0.0.1:7687",
      "user": "neo4j",
      "password": "password",
      "database": "neo4j"
    },
    "start": { "command": "net start neo4j" }
  }
}
```

`data/ecommerce/dbms_config_linux.json`: mesmas conexões, com estes `start`:

```json
{
  "version": 1,

  "postgres": {
    "connection": {
      "host": "127.0.0.1",
      "port": 5432,
      "database": "ecommerce",
      "user": "postgres",
      "password": "postgres"
    },
    "schema": "public",
    "start": { "command": "sudo systemctl start postgresql" }
  },

  "mongodb": {
    "connection": {
      "uri": "mongodb://127.0.0.1:27017",
      "database": "ecommerce"
    },
    "start": { "command": "sudo systemctl start mongod" }
  },

  "cassandra": {
    "connection": {
      "hosts": ["127.0.0.1"],
      "port": 9042,
      "keyspace": "ecommerce"
    },
    "start": { "command": "sudo systemctl start cassandra" }
  },

  "redis": {
    "connection": { "host": "127.0.0.1", "port": 6379, "db": 0 },
    "start": { "command": "sudo systemctl start redis-server" }
  },

  "neo4j": {
    "connection": {
      "uri": "bolt://127.0.0.1:7687",
      "user": "neo4j",
      "password": "password",
      "database": "neo4j"
    },
    "start": { "command": "sudo systemctl start neo4j" }
  }
}
```

- [ ] **Step 5: Rodar os testes**

Run: `$PY -m pytest tests/test_config_parser.py -q -p no:cacheprovider`, depois a suíte inteira.
Expected: tudo verde, com 14 testes a mais que na Tarefa 1.

- [ ] **Step 6: Commit e push**

```bash
git add -A
git commit -m "feat(config): bloco start opcional por SGBD e exemplos para Windows e Linux

start aceita command (SGBD instalado na maquina) ou compose (arquivo e
servico do Docker Compose), nunca os dois. O dbms_config.json do exemplo
aponta para o docker-compose.yml; dbms_config_windows.json e
dbms_config_linux.json trazem comandos de servico.

Co-Authored-By: Claude <modelo> <noreply@anthropic.com>"
git push
```

---

### Task 3: `dbms_check.endpoints`: endereços com o código dos próprios drivers

**Files:**
- Create: `src/polyglotimportcsv/dbms_check.py`
- Test: `tests/test_dbms_check.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `dbms_check.Endpoint = Union[Tuple[str, Union[int, str]], str]` (TCP `(host, port)` ou caminho de socket Unix)
  - `dbms_check.InvalidConnectionError(ValueError)`
  - `dbms_check.endpoints(dbms: str, entry: Dict[str, Any]) -> List[Endpoint]`
  - `dbms_check.format_endpoint(endpoint: Endpoint) -> str`
  - `dbms_check._resolve_srv(uri: str) -> List[Tuple[str, int]]` (privada; os testes a substituem)

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_dbms_check.py`:

```python
"""dbms_check: addresses from the drivers' own parsing, probes and hints."""

from __future__ import annotations

import pytest
from neo4j import GraphDatabase
from pymongo import MongoClient
from pymongo.errors import ConfigurationError

from polyglotimportcsv import dbms_check
from polyglotimportcsv.dbms_check import InvalidConnectionError, endpoints, format_endpoint


def _mongo(uri):
    return endpoints("mongodb", {"connection": {"uri": uri, "database": "d"}})


def _neo4j(uri):
    return endpoints("neo4j", {"connection": {"uri": uri, "user": "u", "password": "p"}})


# -- defaults: the same as each importer's ------------------------------------


def test_defaults_match_the_importers():
    assert endpoints("postgres", {"connection": {}}) == [("127.0.0.1", 5432)]
    assert endpoints("redis", {"connection": {}}) == [("127.0.0.1", 6379)]
    assert endpoints("cassandra", {"connection": {"keyspace": "k"}}) == [("127.0.0.1", 9042)]
    assert endpoints("mongodb", {"connection": {}}) == [("127.0.0.1", 27017)]
    assert endpoints("neo4j", {"connection": {}}) == [("127.0.0.1", 7687)]


def test_cassandra_probes_every_host_on_the_shared_port():
    entry = {"connection": {"hosts": ["a", "b"], "port": 9043, "keyspace": "k"}}
    assert endpoints("cassandra", entry) == [("a", 9043), ("b", 9043)]


# -- postgres: libpq's rules for "host" ---------------------------------------


def test_postgres_host_may_list_several_hosts():
    entry = {"connection": {"host": "a, b", "port": 5433}}
    assert endpoints("postgres", entry) == [("a", 5433), ("b", 5433)]


def test_postgres_host_starting_with_a_slash_is_a_socket_directory():
    entry = {"connection": {"host": "/var/run/postgresql"}}
    assert endpoints("postgres", entry) == ["/var/run/postgresql/.s.PGSQL.5432"]


def test_postgres_empty_host_is_libpqs_default(monkeypatch):
    monkeypatch.setattr(dbms_check, "_ON_WINDOWS", True)
    assert endpoints("postgres", {"connection": {"host": ""}}) == [("localhost", 5432)]
    monkeypatch.setattr(dbms_check, "_ON_WINDOWS", False)
    assert endpoints("postgres", {"connection": {"host": ""}}) == [
        "/var/run/postgresql/.s.PGSQL.5432",
        "/tmp/.s.PGSQL.5432",
    ]


# -- consistency with the drivers (spec §5.1, §6.4) ----------------------------

VALID_MONGODB = [
    ("mongodb://127.0.0.1:27017", [("127.0.0.1", 27017)]),
    ("mongodb://u:p@db.example:27018/shop?authSource=admin", [("db.example", 27018)]),
    ("mongodb://a:1,b:2/?replicaSet=rs", [("a", 1), ("b", 2)]),
    ("mongodb://[::1]:27017", [("::1", 27017)]),
    ("mongodb://%2Ftmp%2Fmongodb-27017.sock", ["/tmp/mongodb-27017.sock"]),
    ("mongodb://h/?tls=true&directConnection=true", [("h", 27017)]),
    ("mongodb+srv://cluster0.example.net/shop", [("shard-0.example.net", 27017)]),
]
INVALID_MONGODB = [
    "mongodb://",
    "http://h",
    "mongodb://h:notaport",
    "mongodb://h:99999",
    "mongodb+srv://h:27017/db",
    "mongodb+srv://a,b/db",
]
VALID_NEO4J = [
    ("bolt://127.0.0.1:7687", [("127.0.0.1", 7687)]),
    ("bolt+s://h", [("h", 7687)]),
    ("bolt+ssc://h:7688", [("h", 7688)]),
    ("neo4j://h?policy=eu", [("h", 7687)]),
    ("neo4j+s://h:7690", [("h", 7690)]),
    ("neo4j+ssc://[::1]", [("::1", 7687)]),
    ("bolt://", [("localhost", 7687)]),
    ("bolt://h:0", [("h", 7687)]),  # the driver's Address.parse turns port 0 into the default
    ("bolt://h:http", [("h", "http")]),  # a service name, resolved by getaddrinfo
]
INVALID_NEO4J = ["bolt+routing://h", "http://h", "bolt://u:p@h"]


def _mongodb_driver_accepts(uri):
    try:
        MongoClient(uri, connect=False).close()
    except Exception:
        return False
    return True


def _neo4j_driver_accepts(uri):
    try:
        GraphDatabase.driver(uri, auth=("u", "p")).close()
    except Exception:
        return False
    return True


@pytest.fixture()
def fake_srv(monkeypatch):
    """No DNS in tests: the SRV record of any +srv URI names one shard."""
    monkeypatch.setattr(dbms_check, "_resolve_srv", lambda uri: [("shard-0.example.net", 27017)])


@pytest.mark.parametrize("uri, expected", VALID_MONGODB)
def test_a_mongodb_uri_the_driver_accepts_is_never_invalid(uri, expected, fake_srv):
    assert _mongodb_driver_accepts(uri)
    assert sorted(_mongo(uri), key=str) == sorted(expected, key=str)


@pytest.mark.parametrize("uri", INVALID_MONGODB)
def test_a_mongodb_uri_the_driver_rejects_is_invalid(uri, fake_srv):
    assert not _mongodb_driver_accepts(uri)
    with pytest.raises(InvalidConnectionError):
        _mongo(uri)


@pytest.mark.parametrize("uri, expected", VALID_NEO4J)
def test_a_neo4j_uri_the_driver_accepts_is_never_invalid(uri, expected):
    assert _neo4j_driver_accepts(uri)
    assert _neo4j(uri) == expected


@pytest.mark.parametrize("uri", INVALID_NEO4J)
def test_a_neo4j_uri_the_driver_rejects_is_invalid(uri):
    assert not _neo4j_driver_accepts(uri)
    with pytest.raises(InvalidConnectionError):
        _neo4j(uri)


@pytest.mark.parametrize("uri", ["bolt://h:notaservice", "neo4j://h:99999"])
def test_a_neo4j_port_no_connection_could_use_is_invalid(uri):
    # The driver accepts these at construction and fails only when it
    # connects; such a port can never work, so no working URI is rejected.
    assert _neo4j_driver_accepts(uri)
    with pytest.raises(InvalidConnectionError):
        _neo4j(uri)


def test_a_srv_uri_that_does_not_resolve_is_invalid(monkeypatch):
    def no_such_name(uri):
        raise ConfigurationError("The DNS query name does not exist: _mongodb._tcp.nowhere.invalid.")

    monkeypatch.setattr(dbms_check, "_resolve_srv", no_such_name)
    with pytest.raises(InvalidConnectionError, match="DNS query name does not exist"):
        _mongo("mongodb+srv://nowhere.invalid/db")


# -- presentation -------------------------------------------------------------


def test_format_endpoint():
    assert format_endpoint(("127.0.0.1", 5432)) == "127.0.0.1:5432"
    assert format_endpoint(("::1", 27017)) == "[::1]:27017"
    assert format_endpoint("/tmp/mongodb-27017.sock") == "/tmp/mongodb-27017.sock"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `$PY -m pytest tests/test_dbms_check.py -q -p no:cacheprovider`
Expected: FAIL com `ModuleNotFoundError: No module named 'polyglotimportcsv.dbms_check'`.

- [ ] **Step 3: Implementar**

`src/polyglotimportcsv/dbms_check.py`:

```python
"""Check that the target DBMS answer before anything is read or written.

No connection URI is parsed by hand here. MongoDB and Neo4j addresses come
from the drivers' own parsing: ``MongoClient(uri, connect=False)`` and
``GraphDatabase.driver(uri, auth=...)`` interpret a URI without connecting,
``pymongo.uri_parser.parse_uri`` performs the SRV lookup the client defers,
and ``neo4j.Address.parse`` applies the Neo4j driver's own defaults. A setting
the driver accepts is therefore never rejected here, and one it rejects never
passes (spec §5.1). PostgreSQL follows libpq's rules for ``host``; Redis and
Cassandra read ``host``/``hosts`` and ``port`` as their importers do.

Nothing here prints: the runner presents the report.
"""

from __future__ import annotations

import socket
import sys
from typing import Any, Dict, List, Tuple, Union
from urllib.parse import urlparse

from neo4j import Address, GraphDatabase
from pymongo import MongoClient, uri_parser

#: A TCP address ``(host, port)`` or the path of a Unix-domain socket. A port
#: may be a service name ("http"): the driver hands it to getaddrinfo as is,
#: and so does the probe.
Endpoint = Union[Tuple[str, Union[int, str]], str]

_ON_WINDOWS = sys.platform == "win32"
#: libpq's compiled-in socket directory is one of these on Linux/macOS builds.
_PG_DEFAULT_SOCKET_DIRS = ("/var/run/postgresql", "/tmp")


class InvalidConnectionError(ValueError):
    """The connection setting can never connect: the driver rejects it."""


def endpoints(dbms: str, entry: Dict[str, Any]) -> List[Endpoint]:
    """Addresses the importer of ``dbms`` would connect to, with its defaults."""
    conn = (entry or {}).get("connection") or {}
    if dbms == "postgres":
        return _postgres_endpoints(conn)
    if dbms == "redis":
        return [(conn.get("host", "127.0.0.1"), int(conn.get("port", 6379)))]
    if dbms == "cassandra":
        port = int(conn.get("port", 9042))
        return [(host, port) for host in (conn.get("hosts") or ["127.0.0.1"])]
    if dbms == "mongodb":
        return _mongodb_endpoints(conn.get("uri", "mongodb://127.0.0.1:27017"))
    if dbms == "neo4j":
        return _neo4j_endpoints(
            conn.get("uri", "bolt://127.0.0.1:7687"), conn.get("user"), conn.get("password")
        )
    raise ValueError("unknown DBMS: {0}".format(dbms))


def format_endpoint(endpoint: Endpoint) -> str:
    if isinstance(endpoint, str):
        return endpoint
    host, port = endpoint
    if ":" in host:  # an IPv6 literal
        return "[{0}]:{1}".format(host, port)
    return "{0}:{1}".format(host, port)


def _postgres_endpoints(conn: Dict[str, Any]) -> List[Endpoint]:
    """libpq: comma-separated hosts; '/dir' is a socket directory; '' the default."""
    port = int(conn.get("port", 5432))
    socket_name = ".s.PGSQL.{0}".format(port)
    result: List[Endpoint] = []
    for host in str(conn.get("host", "127.0.0.1")).split(","):
        host = host.strip()
        if not host:
            if _ON_WINDOWS:
                result.append(("localhost", port))
            else:
                result.extend(d + "/" + socket_name for d in _PG_DEFAULT_SOCKET_DIRS)
        elif host.startswith("/"):
            result.append(host.rstrip("/") + "/" + socket_name)
        else:
            result.append((host, port))
    return result


def _resolve_srv(uri: str) -> List[Tuple[str, int]]:
    """The SRV lookup ``MongoClient(connect=False)`` defers, with its tolerance
    for unknown URI options (``warn=True``: a warning, as in the client)."""
    return list(uri_parser.parse_uri(uri, warn=True)["nodelist"])


def _mongodb_endpoints(uri: str) -> List[Endpoint]:
    try:
        # Constructing the client parses and validates the URI; it connects
        # only when used.
        client = MongoClient(uri, connect=False)
    except Exception as exc:  # whatever the driver raises is its rejection
        raise InvalidConnectionError(str(exc)) from exc
    try:
        seeds = list(client.topology_description.server_descriptions())
    finally:
        client.close()
    if uri.startswith("mongodb+srv://"):
        try:
            seeds = _resolve_srv(uri)
        except Exception as exc:
            raise InvalidConnectionError(str(exc)) from exc
    # A Unix socket seed has no port: ("/tmp/mongodb-27017.sock", None).
    return [host if port is None else (host, port) for host, port in seeds]


def _neo4j_endpoints(uri: str, user: Any, password: Any) -> List[Endpoint]:
    try:
        # Construction checks the scheme and the URI without connecting.
        GraphDatabase.driver(uri, auth=(user, password)).close()
    except Exception as exc:
        raise InvalidConnectionError(str(exc)) from exc
    address = Address.parse(urlparse(uri).netloc, default_host="localhost", default_port=7687)
    return [(address.host, _usable_port(address.port))]


def _usable_port(port: Union[int, str]) -> Union[int, str]:
    """The Neo4j driver accepts any port text and fails only when it connects."""
    if isinstance(port, str) and not port.isdigit():
        try:
            socket.getservbyname(port, "tcp")
        except OSError as exc:
            raise InvalidConnectionError(
                "port {0!r} is neither a number nor a known service name".format(port)
            ) from exc
        return port
    number = int(port)
    if not 0 < number < 65536:
        raise InvalidConnectionError("port {0} is outside 1-65535".format(number))
    return number
```

- [ ] **Step 4: Rodar os testes**

Run: `$PY -m pytest tests/test_dbms_check.py -q -p no:cacheprovider`
Expected: PASS. Se um caso de `VALID_*` ou `INVALID_*` falhar na primeira asserção (a do driver), a tabela está errada, não o código. Confira com o driver e corrija a tabela. A regra é o que o driver faz.

- [ ] **Step 5: Suíte, commit e push**

```bash
$PY -m pytest tests -q -p no:cacheprovider
git add src/polyglotimportcsv/dbms_check.py tests/test_dbms_check.py
git commit -m "feat(dbms_check): enderecos dos SGBDs com o codigo dos proprios drivers

MongoClient(connect=False), GraphDatabase.driver e neo4j.Address.parse
interpretam as URIs sem conectar; a +srv e resolvida por parse_uri. Um
teste de consistencia prende a garantia: URI que o driver aceita nunca e
invalida, e a que ele rejeita nunca passa.

Co-Authored-By: Claude <modelo> <noreply@anthropic.com>"
git push
```

---

### Task 4: Sonda, relatório e dicas de inicialização

**Files:**
- Modify: `src/polyglotimportcsv/dbms_check.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_dbms_check.py`

**Interfaces:**
- Consumes: `endpoints`, `Endpoint`, `InvalidConnectionError` (Tarefa 3).
- Produces:
  - constantes `UP = "up"`, `DOWN = "down"`, `INVALID = "invalid"`, `PROBE_TIMEOUT = 2.0`
  - `probe(endpoint: Endpoint, timeout: float = PROBE_TIMEOUT) -> bool`
  - `@dataclass(frozen=True) DbmsStatus(dbms: str, endpoints: Tuple[Endpoint, ...], state: str, error: str = "")`
  - `@dataclass(frozen=True) DbmsCheckReport(statuses: Tuple[DbmsStatus, ...], fixes: Tuple[str, ...], starts: Tuple[str, ...], service_commands: bool)`, com as propriedades `ok -> bool` e `not_ready -> List[DbmsStatus]`
  - `start_hints(down: Sequence[str], dbms_cfg: Dict[str, Any], dbms_config_path: Path) -> List[str]`
  - `check_dbms(targets: Sequence[str], dbms_cfg: Dict[str, Any], dbms_config_path: Path, probe_fn: Optional[Callable[[Endpoint], bool]] = None) -> DbmsCheckReport`
  - `not_ready_message(report: DbmsCheckReport) -> str`
  - fixture `autouse` `_dbms_always_up` em `tests/conftest.py`

- [ ] **Step 1: Escrever os testes que falham**

Acrescente a `tests/test_dbms_check.py`, com os imports no topo (`import socket`, `import time`) e `from polyglotimportcsv.dbms_check import DOWN, INVALID, UP, check_dbms, not_ready_message, probe`:

```python
@pytest.fixture(autouse=True)
def _dbms_always_up():
    """Overrides the conftest stub: this module tests the real probe."""
    yield


# -- probe --------------------------------------------------------------------


def test_probe_is_true_for_a_listening_socket():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    try:
        assert probe(server.getsockname(), timeout=1.0) is True
    finally:
        server.close()


def test_probe_is_false_for_a_closed_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    assert probe(("127.0.0.1", port), timeout=0.5) is False


def test_probe_is_false_for_an_out_of_range_port():
    assert probe(("127.0.0.1", 70000), timeout=0.5) is False


def test_probe_is_false_for_a_missing_unix_socket(tmp_path):
    assert probe(str(tmp_path / "none.sock"), timeout=0.5) is False


# -- check_dbms ---------------------------------------------------------------

ALL = ["postgres", "mongodb", "cassandra", "redis", "neo4j"]


def _cfg():
    return {
        "version": 1,
        "postgres": {"connection": {"host": "127.0.0.1", "port": 5432},
                     "start": {"command": "net start postgresql-x64-16"}},
        "mongodb": {"connection": {"uri": "mongodb://127.0.0.1:27017", "database": "d"},
                    "start": {"compose": {"file": "../docker-compose.yml", "service": "mongodb"}}},
        "cassandra": {"connection": {"hosts": ["10.0.0.1", "10.0.0.2"], "keyspace": "k"},
                      "start": {"compose": {"file": "../docker-compose.yml", "service": "cassandra"}}},
        "redis": {"connection": {}},
        "neo4j": {"connection": {"uri": "http://h", "user": "u", "password": "p"},
                  "start": {"command": "net start neo4j"}},
    }


def test_check_reports_each_state_and_what_to_do(tmp_path):
    path = tmp_path / "cfg" / "dbms_config.json"
    answering = {("127.0.0.1", 5432), ("10.0.0.2", 9042)}
    report = check_dbms(ALL, _cfg(), path, probe_fn=lambda ep: ep in answering)

    assert {s.dbms: s.state for s in report.statuses} == {
        "postgres": UP, "mongodb": DOWN, "cassandra": UP, "redis": DOWN, "neo4j": INVALID,
    }
    assert [s.dbms for s in report.statuses] == ALL
    assert not report.ok
    compose = (tmp_path / "docker-compose.yml").resolve()
    assert report.starts == (
        'docker compose -f "{0}" up -d --wait mongodb'.format(compose),
        'redis: start the DBMS service, or declare "start" for it in dbms_config.json',
    )
    assert len(report.fixes) == 1
    assert report.fixes[0].startswith("neo4j: invalid connection (")
    assert report.fixes[0].endswith('Fix "connection" for it in dbms_config.json')
    # The only command-type start (neo4j) belongs to an INVALID DBMS, not a DOWN one.
    assert report.service_commands is False


def test_compose_services_of_one_file_share_one_command(tmp_path):
    path = tmp_path / "cfg" / "dbms_config.json"
    report = check_dbms(["postgres", "mongodb", "cassandra"], _cfg(), path, probe_fn=lambda ep: False)
    compose = (tmp_path / "docker-compose.yml").resolve()
    assert report.starts == (
        "net start postgresql-x64-16",
        'docker compose -f "{0}" up -d --wait mongodb cassandra'.format(compose),
    )
    assert report.service_commands is True


def test_hints_name_the_dbms_config_actually_used(tmp_path):
    path = tmp_path / "dbms_config_windows.json"
    report = check_dbms(["redis", "neo4j"], _cfg(), path, probe_fn=lambda ep: False)
    assert report.starts[0].endswith("in dbms_config_windows.json")
    assert report.fixes[0].endswith("in dbms_config_windows.json")


def test_all_up_is_ok_and_has_nothing_to_say(tmp_path):
    report = check_dbms(["postgres", "redis"], _cfg(), tmp_path / "d.json", probe_fn=lambda ep: True)
    assert report.ok
    assert report.not_ready == []
    assert report.starts == () and report.fixes == ()


def test_an_invalid_connection_is_never_probed(tmp_path):
    seen = []
    report = check_dbms(["neo4j"], _cfg(), tmp_path / "d.json",
                        probe_fn=lambda ep: seen.append(ep) or True)
    assert seen == []
    assert report.statuses[0].state == INVALID
    assert report.statuses[0].endpoints == ()
    assert not report.ok


def test_probes_run_in_parallel(tmp_path):
    def slow(endpoint):
        time.sleep(0.5)
        return True

    start = time.monotonic()
    # postgres 1 + cassandra 2 + redis 1 = four endpoints of 0.5 s each
    check_dbms(["postgres", "cassandra", "redis"], _cfg(), tmp_path / "d.json", probe_fn=slow)
    assert time.monotonic() - start < 1.5


def test_not_ready_message_lists_each_dbms_and_state(tmp_path):
    report = check_dbms(ALL, _cfg(), tmp_path / "d.json", probe_fn=lambda ep: False)
    message = not_ready_message(report)
    assert message.startswith("DBMS not ready: postgres (down), mongodb (down), cassandra (down),")
    assert "neo4j (invalid)" in message
```

Em `tests/conftest.py`, acrescente:

```python
@pytest.fixture(autouse=True)
def _dbms_always_up(monkeypatch):
    """Runner and CLI tests use fake importers and sinks: the DBMS check that
    precedes every real import must not open sockets. test_dbms_check.py
    overrides this fixture to exercise the real probe."""
    from polyglotimportcsv import dbms_check

    monkeypatch.setattr(dbms_check, "probe", lambda endpoint, timeout=2.0: True)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `$PY -m pytest tests/test_dbms_check.py -q -p no:cacheprovider`
Expected: FAIL com `ImportError: cannot import name 'DOWN'`. O conftest também falha em todos os testes enquanto `dbms_check.probe` não existir. Isso é esperado neste passo.

- [ ] **Step 3: Implementar**

Em `src/polyglotimportcsv/dbms_check.py`:

(a) Complete os imports:

```python
import os
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlparse
```

(b) Depois de `_PG_DEFAULT_SOCKET_DIRS`, acrescente:

```python
UP = "up"
DOWN = "down"
INVALID = "invalid"

#: Seconds each probe waits. On Windows a refused connection to 127.0.0.1
#: takes about 2 s (TCP retries the SYN), which is why probes run in parallel.
PROBE_TIMEOUT = 2.0
```

(c) Depois de `InvalidConnectionError`, acrescente:

```python
@dataclass(frozen=True)
class DbmsStatus:
    dbms: str
    endpoints: Tuple[Endpoint, ...]
    state: str  # UP, DOWN or INVALID
    error: str = ""  # the driver's message when INVALID


@dataclass(frozen=True)
class DbmsCheckReport:
    statuses: Tuple[DbmsStatus, ...]
    #: One line per INVALID DBMS: what to fix, and in which file.
    fixes: Tuple[str, ...]
    #: How to start each DOWN DBMS; compose services grouped per file.
    starts: Tuple[str, ...]
    #: True when a start hint is a plain command (net start, systemctl...),
    #: which usually needs an administrator terminal or sudo.
    service_commands: bool

    @property
    def ok(self) -> bool:
        return all(status.state == UP for status in self.statuses)

    @property
    def not_ready(self) -> List[DbmsStatus]:
        return [status for status in self.statuses if status.state != UP]
```

(d) No fim do módulo, acrescente:

```python
def probe(endpoint: Endpoint, timeout: float = PROBE_TIMEOUT) -> bool:
    """True when something accepts a connection at ``endpoint``. Never logs in."""
    try:
        if isinstance(endpoint, str):
            if not hasattr(socket, "AF_UNIX"):
                # Python on Windows has no AF_UNIX; the socket file exists
                # while its server runs.
                return os.path.exists(endpoint)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                sock.connect(endpoint)
            return True
        with socket.create_connection(endpoint, timeout=timeout):
            return True
    except (OSError, OverflowError, ValueError):
        # OverflowError/ValueError: a host/port setting with a port outside
        # 0-65535, which the driver could not connect to either.
        return False


def start_hints(
    down: Sequence[str], dbms_cfg: Dict[str, Any], dbms_config_path: Path
) -> List[str]:
    """How to start each DBMS in ``down``, in order; one docker command per compose file."""
    entries: List[Union[str, Path]] = []
    services: Dict[Path, List[str]] = {}
    for dbms in down:
        start = (dbms_cfg.get(dbms) or {}).get("start")
        if not start:
            entries.append('{0}: start the DBMS service, or declare "start" for it in {1}'.format(
                dbms, dbms_config_path.name))
        elif "command" in start:
            entries.append(start["command"])
        else:
            compose_file = (dbms_config_path.parent / start["compose"]["file"]).resolve()
            if compose_file not in services:
                services[compose_file] = []
                entries.append(compose_file)
            services[compose_file].append(start["compose"]["service"])
    return [
        'docker compose -f "{0}" up -d --wait {1}'.format(entry, " ".join(services[entry]))
        if isinstance(entry, Path) else entry
        for entry in entries
    ]


def check_dbms(
    targets: Sequence[str],
    dbms_cfg: Dict[str, Any],
    dbms_config_path: Path,
    probe_fn: Optional[Callable[[Endpoint], bool]] = None,
) -> DbmsCheckReport:
    """Probe every endpoint of ``targets`` in parallel and say what to do next."""
    probe_fn = probe_fn or probe  # looked up per call, so tests can patch probe
    resolved: Dict[str, Tuple[Endpoint, ...]] = {}
    errors: Dict[str, str] = {}
    for dbms in targets:
        try:
            resolved[dbms] = tuple(endpoints(dbms, dbms_cfg.get(dbms) or {}))
        except InvalidConnectionError as exc:
            errors[dbms] = str(exc)

    pairs = [(dbms, endpoint) for dbms, found in resolved.items() for endpoint in found]
    with ThreadPoolExecutor(max_workers=max(1, len(pairs))) as pool:
        answers = list(pool.map(lambda pair: probe_fn(pair[1]), pairs))
    answering = {dbms for (dbms, _), answered in zip(pairs, answers) if answered}

    statuses = tuple(
        DbmsStatus(dbms, (), INVALID, errors[dbms]) if dbms in errors
        else DbmsStatus(dbms, resolved[dbms], UP if dbms in answering else DOWN)
        for dbms in targets
    )
    down = [status.dbms for status in statuses if status.state == DOWN]
    fixes = tuple(
        '{0}: invalid connection ({1}). Fix "connection" for it in {2}'.format(
            status.dbms, status.error, dbms_config_path.name)
        for status in statuses if status.state == INVALID
    )
    service_commands = any(
        "command" in ((dbms_cfg.get(dbms) or {}).get("start") or {}) for dbms in down
    )
    return DbmsCheckReport(
        statuses, fixes, tuple(start_hints(down, dbms_cfg, dbms_config_path)), service_commands
    )


def not_ready_message(report: DbmsCheckReport) -> str:
    names = ", ".join("{0} ({1})".format(s.dbms, s.state) for s in report.not_ready)
    return "DBMS not ready: {0}. Fix or start them as shown above, then run again.".format(names)
```

- [ ] **Step 4: Rodar os testes**

Run: `$PY -m pytest tests/test_dbms_check.py -q -p no:cacheprovider`, depois a suíte inteira.
Expected: tudo verde.

- [ ] **Step 5: Commit e push**

```bash
git add -A
git commit -m "feat(dbms_check): sonda TCP em paralelo, relatorio e dicas de inicializacao

check_dbms sonda todos os enderecos ao mesmo tempo (timeout de 2 s) e devolve,
por SGBD, up, down ou invalid; os comandos de start de um mesmo compose viram
um so docker compose up. Um fixture autouse impede os demais testes de abrir
sockets.

Co-Authored-By: Claude <modelo> <noreply@anthropic.com>"
git push
```

---

### Task 5: Runner: passo "Check DBMS", `run_check` e `DbmsUnavailableError`

**Files:**
- Modify: `src/polyglotimportcsv/business_exception.py`
- Modify: `src/polyglotimportcsv/config_parser.py` (`load_config`)
- Modify: `src/polyglotimportcsv/runner.py`
- Test: `tests/test_runner_registry.py`, `tests/test_config_parser.py`

**Interfaces:**
- Consumes: `check_dbms`, `not_ready_message`, `format_endpoint`, `DbmsCheckReport`, `UP`, `DOWN`, `INVALID` (Tarefas 3 e 4).
- Produces:
  - `business_exception.DbmsUnavailableError(BusinessException)`
  - `config_parser.resolve_dbms_config_path(import_path, dbms_path=None) -> Path`
  - `runner.run_check(config_path, *, dbms_config_path=None, only=None) -> DbmsCheckReport`
  - toda importação real verifica os SGBDs antes de "Load sources"

- [ ] **Step 1: Escrever os testes que falham**

Em `tests/test_config_parser.py`:

```python
from polyglotimportcsv.config_parser import resolve_dbms_config_path


def test_resolve_dbms_config_path_defaults_next_to_the_import_config(tmp_path):
    cfg = tmp_path / "import_config.json"
    assert resolve_dbms_config_path(cfg) == tmp_path / "dbms_config.json"
    assert resolve_dbms_config_path(cfg, "other.json") == Path("other.json")
```

Em `tests/test_runner_registry.py`, acrescente os imports `from polyglotimportcsv.business_exception import DbmsUnavailableError` e `from polyglotimportcsv.runner import run_check`, e ao fim:

```python
def _probe_answers(value, seen=None):
    def fake(endpoint, timeout=2.0):
        if seen is not None:
            seen.append(endpoint)
        return value
    return fake


def test_a_real_import_stops_before_reading_sources_when_a_dbms_is_down(monkeypatch):
    monkeypatch.setattr("polyglotimportcsv.dbms_check.probe", _probe_answers(False))

    def must_not_run(*a, **k):
        raise AssertionError("nothing may be read or written when a DBMS is down")

    monkeypatch.setattr("polyglotimportcsv.runner.load_sources", must_not_run)
    monkeypatch.setattr("polyglotimportcsv.runner.run_stream_import", must_not_run)
    with pytest.raises(DbmsUnavailableError, match=r"postgres \(down\)"):
        run_import(CFG, execution="stream", only=["postgres"])
    with pytest.raises(DbmsUnavailableError, match=r"postgres \(down\)"):
        run_import(CFG, execution="materialize", only=["postgres"],
                   importers={"postgres": must_not_run})


def test_dry_run_never_checks_the_dbms(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("dry-run must not probe")

    monkeypatch.setattr("polyglotimportcsv.dbms_check.probe", boom)
    run_import(CFG, dry_run=True, only=["postgres"],
               importers={"postgres": lambda cfg, entities, **kw: []})


def test_run_check_targets_follow_only(monkeypatch):
    seen = []
    monkeypatch.setattr("polyglotimportcsv.dbms_check.probe", _probe_answers(True, seen))
    report = run_check(CFG, only=["redis"])
    assert [s.dbms for s in report.statuses] == ["redis"]
    assert seen == [("127.0.0.1", 6379)]
    assert report.ok


def test_run_check_prints_the_table_and_the_start_command(monkeypatch, capsys):
    monkeypatch.setattr("polyglotimportcsv.dbms_check.probe", _probe_answers(False))
    linux = CFG.with_name("dbms_config_linux.json")
    report = run_check(CFG, dbms_config_path=linux, only=["redis", "neo4j"])
    out = capsys.readouterr().out
    assert not report.ok
    assert "Check DBMS" in out
    assert "127.0.0.1:6379" in out
    assert "To start the DBMS that are down, run in a terminal:" in out
    assert "sudo systemctl start redis-server" in out
    assert "sudo systemctl start neo4j" in out
    assert "administrator terminal or sudo" in out


def test_start_commands_are_never_wrapped(monkeypatch, capsys):
    """A wrapped command would carry a line break into the terminal it is pasted in."""
    monkeypatch.setattr("polyglotimportcsv.dbms_check.probe", _probe_answers(False))
    run_check(CFG, only=["redis"])  # dbms_config.json: a long docker compose line
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if "docker compose -f" in l)
    assert line.rstrip().endswith("up -d --wait redis")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `$PY -m pytest tests/test_runner_registry.py tests/test_config_parser.py -q -p no:cacheprovider`
Expected: FAIL com `ImportError` (`DbmsUnavailableError`, `run_check`, `resolve_dbms_config_path`).

- [ ] **Step 3: Exceção**

Em `src/polyglotimportcsv/business_exception.py`, ao fim:

```python
class DbmsUnavailableError(BusinessException):
    """A target DBMS does not answer, or its connection setting is invalid.

    Raised by the check that precedes every real import, before any CSV is
    read or anything is written.
    """
```

- [ ] **Step 4: `resolve_dbms_config_path`**

Em `src/polyglotimportcsv/config_parser.py`, antes de `load_config`:

```python
def resolve_dbms_config_path(
    import_path: Union[str, Path], dbms_path: Optional[Union[str, Path]] = None
) -> Path:
    """``dbms_path``, or ``dbms_config.json`` next to the import configuration."""
    if dbms_path is None:
        return Path(import_path).with_name(DEFAULT_DBMS_CONFIG_NAME)
    return Path(dbms_path)
```

Em `load_config`, troque

```python
    if dbms_path is None:
        dbms_path = import_path.with_name(DEFAULT_DBMS_CONFIG_NAME)
```

por

```python
    dbms_path = resolve_dbms_config_path(import_path, dbms_path)
```

- [ ] **Step 5: Runner**

Em `src/polyglotimportcsv/runner.py`:

(a) Imports: acrescente `from rich import box` e `from rich.table import Table` junto a `from rich.text import Text`. Troque `from polyglotimportcsv.config_parser import load_config` por:

```python
from polyglotimportcsv.business_exception import DbmsUnavailableError
from polyglotimportcsv.config_parser import load_config, load_dbms_config, resolve_dbms_config_path
from polyglotimportcsv.dbms_check import (
    DOWN,
    INVALID,
    UP,
    DbmsCheckReport,
    check_dbms,
    format_endpoint,
    not_ready_message,
)
```

(b) Depois de `_print_backend_line`, acrescente:

```python
_STATE_STYLE = {UP: "green", DOWN: "red", INVALID: "red"}


def _dbms_targets(config: Dict, only: Optional[Iterable[str]]) -> List[str]:
    """The DBMS the import would write to: those configured, narrowed by --only."""
    only_set = {x.strip().lower() for x in only if x and str(x).strip()} if only else set()
    return [b for b in BACKENDS if b in config and (not only_set or b in only_set)]


def _print_command(line: str) -> None:
    # Never wrapped: a line break inside a command would be pasted along with it.
    print_rich(Text("      " + line, style="bold", no_wrap=True, overflow="ignore"))


def _print_dbms_check(report: DbmsCheckReport, dbms_config_path: Path) -> None:
    # box.SQUARE for the same reason as metrics_table: the GUI font lacks the
    # heavy box glyphs.
    table = Table(header_style="bold", box=box.SQUARE)
    table.add_column("DBMS")
    table.add_column("Endpoint")
    table.add_column("Status")
    for status in report.statuses:
        where = ", ".join(format_endpoint(e) for e in status.endpoints) or "—"
        table.add_row(status.dbms, where, Text(status.state, style=_STATE_STYLE[status.state]))
    print_rich(table)
    if report.fixes:
        note(f"Fix the connection settings in {dbms_config_path.name}:")
        for line in report.fixes:
            _print_command(line)
    if report.starts:
        note("To start the DBMS that are down, run in a terminal:")
        for line in report.starts:
            _print_command(line)
        if report.service_commands:
            note("Service commands (net start, systemctl) may need an administrator terminal or sudo.")


def _check_dbms_step(
    config_path: Path,
    dbms_config_path: Optional[str | Path],
    config: Dict,
    only: Optional[Iterable[str]],
) -> DbmsCheckReport:
    step("Check DBMS")
    path = resolve_dbms_config_path(config_path, dbms_config_path)
    report = check_dbms(_dbms_targets(config, only), load_dbms_config(path), path)
    _print_dbms_check(report, path)
    return report


def _require_dbms(
    config_path: Path,
    dbms_config_path: Optional[str | Path],
    config: Dict,
    only: Optional[Iterable[str]],
) -> None:
    """Stop before any CSV is read when a target DBMS is not ready."""
    report = _check_dbms_step(config_path, dbms_config_path, config, only)
    if not report.ok:
        raise DbmsUnavailableError(not_ready_message(report))


def run_check(
    config_path: str | Path,
    *,
    dbms_config_path: Optional[str | Path] = None,
    only: Optional[Iterable[str]] = None,
) -> DbmsCheckReport:
    """Check the DBMS the import would use and return the report (CLI --check-dbms)."""
    config_path = Path(config_path)
    banner("Polyglot Import CSV", subtitle="mode: check")
    step("Load config", str(config_path))
    config = load_config(config_path, dbms_config_path)
    report = _check_dbms_step(config_path, dbms_config_path, config, only)
    if report.ok:
        success("All target DBMS are up")
    return report
```

O arquivo já tem `from __future__ import annotations`, então `Optional[str | Path]` é válido em 3.9, como no resto do runner.

(c) Em `_run_stream`, logo depois de `note(f"{len(backends_in_cfg)} backend(s) configured: ...")`:

```python
    _require_dbms(config_path, dbms_config_path, config, only)
```

(d) Em `_run`, logo depois da mesma linha `note(...)`:

```python
    if not dry_run:
        _require_dbms(config_path, dbms_config_path, config, only)
```

- [ ] **Step 6: Rodar os testes**

Run: `$PY -m pytest tests/test_runner_registry.py tests/test_config_parser.py -q -p no:cacheprovider`, depois a suíte inteira.
Expected: tudo verde. Se `test_start_commands_are_never_wrapped` falhar por quebra de linha, confira se o `Text` tem `no_wrap=True, overflow="ignore"`.

- [ ] **Step 7: Commit e push**

```bash
git add -A
git commit -m "feat(runner): verifica os SGBDs antes de ler as fontes

Toda importacao real mostra a tabela de estados e, se algum SGBD estiver fora
do ar ou com conexao invalida, para com DbmsUnavailableError antes de ler
qualquer CSV. run_check faz so a verificacao. Os comandos de start saem sem
quebra de linha, para serem copiados inteiros.

Co-Authored-By: Claude <modelo> <noreply@anthropic.com>"
git push
```

---

### Task 6: CLI `--check-dbms`

**Files:**
- Modify: `src/polyglotimportcsv/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `runner.run_check`, `dbms_check.not_ready_message` (Tarefas 4 e 5).
- Produces: `polyglotimportcsv --config … [--dbms-config …] [--only …] --check-dbms` sai com 0 (todos `up`), 1 (algum fora ou configuração inválida) ou 2 (uso inválido).

- [ ] **Step 1: Escrever os testes que falham**

Em `tests/test_cli.py` (imports no topo: `from pathlib import Path`, `import pytest`):

```python
ECOMMERCE = Path(__file__).resolve().parents[1] / "data" / "ecommerce"


def _report(ok):
    from polyglotimportcsv.dbms_check import DOWN, UP, DbmsCheckReport, DbmsStatus

    status = DbmsStatus("redis", (("127.0.0.1", 6379),), UP if ok else DOWN)
    return DbmsCheckReport((status,), (), (), False)


def _no_import(*a, **k):
    raise AssertionError("--check-dbms must not import")


def test_cli_check_dbms_exits_zero_when_all_are_up(tmp_path, monkeypatch):
    captured = {}

    def fake_run_check(config_path, **kwargs):
        captured.update(kwargs)
        return _report(True)

    monkeypatch.setattr("polyglotimportcsv.cli.run_check", fake_run_check)
    monkeypatch.setattr("polyglotimportcsv.cli.run_import", _no_import)
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")
    result = CliRunner().invoke(main, ["--config", str(cfg), "--check-dbms", "--only", "redis"])
    assert result.exit_code == 0, result.output
    assert captured == {"dbms_config_path": None, "only": ["redis"]}


def test_cli_check_dbms_exits_one_when_a_dbms_is_down(tmp_path, monkeypatch):
    monkeypatch.setattr("polyglotimportcsv.cli.run_check", lambda config_path, **kw: _report(False))
    monkeypatch.setattr("polyglotimportcsv.cli.run_import", _no_import)
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")
    result = CliRunner().invoke(main, ["--config", str(cfg), "--check-dbms"])
    assert result.exit_code == 1
    assert "DBMS not ready: redis (down)" in result.output


@pytest.mark.parametrize("flag", ["--dry-run", "--benchmark"])
def test_cli_check_dbms_rejects_dry_run_and_benchmark(tmp_path, flag):
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")
    result = CliRunner().invoke(main, ["--config", str(cfg), "--check-dbms", flag])
    assert result.exit_code == 2
    assert "--check-dbms cannot be combined" in result.output


def test_cli_check_dbms_end_to_end_shows_the_start_command(monkeypatch):
    monkeypatch.setattr("polyglotimportcsv.dbms_check.probe", lambda ep, timeout=2.0: False)
    result = CliRunner().invoke(main, [
        "--config", str(ECOMMERCE / "import_config.json"),
        "--dbms-config", str(ECOMMERCE / "dbms_config_linux.json"),
        "--check-dbms", "--only", "redis",
    ])
    assert result.exit_code == 1
    assert "sudo systemctl start redis-server" in result.output
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `$PY -m pytest tests/test_cli.py -q -p no:cacheprovider`
Expected: FAIL (`no such option: --check-dbms`).

- [ ] **Step 3: Implementar**

Em `src/polyglotimportcsv/cli.py`:

(a) Imports: `from polyglotimportcsv.dbms_check import not_ready_message` e `from polyglotimportcsv.runner import run_check, run_import`.

(b) Uma opção nova, logo depois de `--dry-run`:

```python
@click.option(
    "--check-dbms",
    "check_dbms_only",
    is_flag=True,
    help="Only check that the target DBMS answer, show how to start the ones "
    "that do not, and exit (0 when all are up). Imports nothing.",
)
```

(c) O parâmetro `check_dbms_only: bool` em `main`, logo depois de `dry_run: bool`.

(d) No corpo, antes de `log_path = setup_reporting(...)`:

```python
    if check_dbms_only and (dry_run or benchmark):
        raise click.UsageError("--check-dbms cannot be combined with --dry-run or --benchmark.")
```

(e) Dentro do `try`, antes de `run_import(`:

```python
        if check_dbms_only:
            report = run_check(config_path, dbms_config_path=dbms_config_path, only=only_list)
            if not report.ok:
                error(not_ready_message(report))
                sys.exit(1)
            return
```

- [ ] **Step 4: Rodar os testes**

Run: `$PY -m pytest tests/test_cli.py -q -p no:cacheprovider`, depois a suíte inteira.
Expected: tudo verde.

- [ ] **Step 5: Conferência manual**

Run: `$PY -m polyglotimportcsv --config data/ecommerce/import_config.json --dbms-config data/ecommerce/dbms_config_windows.json --check-dbms`
Expected: a tabela com os cinco SGBDs. Sem Docker, todos aparecem `down`, seguidos de `net start …`, da linha `docker compose -f "…docker-compose.yml" up -d --wait cassandra` e da nota sobre administrador. O código de saída é 1 (`echo $?`).

- [ ] **Step 6: Commit e push**

```bash
git add -A
git commit -m "feat(cli): --check-dbms verifica os SGBDs e sai sem importar

Sai com 0 quando todos respondem e 1 quando algum esta fora do ar ou com
conexao invalida; nao combina com --dry-run nem com --benchmark.

Co-Authored-By: Claude <modelo> <noreply@anthropic.com>"
git push
```

---

### Task 7: GUI, núcleo puro: `build_check_argv` e `Preflight.checkable`

**Files:**
- Modify: `src/polyglotimportcsv/gui/command.py`
- Modify: `src/polyglotimportcsv/gui/preflight.py`
- Test: `tests/test_gui_command.py`, `tests/test_gui_preflight.py`

**Interfaces:**
- Consumes: `RunOptions.dbms_config_path`, `preflight._check_dbms` (Tarefa 1).
- Produces:
  - `command.build_check_argv(options: RunOptions) -> List[str]`
  - `Preflight.checkable: bool = False`

- [ ] **Step 1: Escrever os testes que falham**

Em `tests/test_gui_command.py` (importe `build_check_argv` junto de `build_argv`):

```python
def test_build_check_argv_keeps_only_what_the_check_uses():
    dbms = Path("/proj/dbms.json")
    options = RunOptions(
        config_path=CFG, dbms_config_path=dbms, only=("redis", "neo4j"),
        dry_run=True, execution="materialize", log_level="DEBUG", show_data=True,
        sources=(("stock", Path("/x.csv")),),
    )
    assert build_check_argv(options) == [
        "--config", str(CFG), "--dbms-config", str(dbms),
        "--only", "redis,neo4j", "--check-dbms", "--log-level", "DEBUG",
    ]


def test_build_check_argv_with_defaults():
    assert build_check_argv(RunOptions(config_path=CFG)) == [
        "--config", str(CFG), "--check-dbms", "--log-level", "INFO",
    ]
```

Em `tests/test_gui_preflight.py`:

```python
def test_a_valid_pair_of_configs_is_checkable(ecommerce):
    assert _check(ecommerce).checkable


def test_a_csv_problem_does_not_block_the_check(ecommerce):
    (ecommerce / "ecommerce_stock.csv").unlink()
    result = _check(ecommerce)
    assert result.errors  # the header check still reports the missing CSV
    assert result.checkable


def test_an_import_config_that_fails_its_schema_is_not_checkable(ecommerce):
    (ecommerce / "import_config.json").write_text('{"postgres": {}}', encoding="utf-8")
    assert not _check(ecommerce).checkable


def test_a_dbms_config_that_misses_a_target_is_not_checkable(ecommerce):
    path = ecommerce / "dbms_config.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["neo4j"]
    path.write_text(json.dumps(data), encoding="utf-8")
    assert not _check(ecommerce).checkable


def test_a_missing_explicit_dbms_config_is_not_checkable(ecommerce):
    result = preflight.check(RunOptions(
        config_path=ecommerce / "import_config.json",
        dbms_config_path=ecommerce / "nao_existe.json",
    ))
    assert not result.checkable
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `$PY -m pytest tests/test_gui_command.py tests/test_gui_preflight.py -q -p no:cacheprovider`
Expected: FAIL (`ImportError: build_check_argv`; `AttributeError: checkable`).

- [ ] **Step 3: Implementar**

Em `src/polyglotimportcsv/gui/command.py`, depois de `build_argv`:

```python
def build_check_argv(options: RunOptions) -> List[str]:
    """Arguments of "Verificar SGBDs": what ``--check-dbms`` reads, nothing else."""
    argv = []  # type: List[str]
    if options.config_path is not None:
        argv += ["--config", str(options.config_path)]
    if options.dbms_config_path is not None:
        argv += ["--dbms-config", str(options.dbms_config_path)]
    if options.only:
        argv += ["--only", ",".join(options.only)]
    argv.append("--check-dbms")
    argv += ["--log-level", options.log_level]
    return argv
```

Em `src/polyglotimportcsv/gui/preflight.py`:

(a) Em `Preflight`, depois de `errors`:

```python
    #: True when both configuration files are valid and agree with each other,
    #: which is all ``--check-dbms`` needs: the check reads no CSV. The error
    #: keys cannot say this, because a CSV header problem is filed under
    #: "config_path" when no source is overridden.
    checkable: bool = False
```

(b) Em `check`, logo depois do bloco `dbms_error = _check_dbms(...)` / `if dbms_error: ...`:

```python
    checkable = not dbms_error and (
        options.dbms_config_path is None or options.dbms_config_path.is_file()
    )
```

(c) Troque o `return` final de `check` por:

```python
    return Preflight(kind=kind, declared=declared, errors=errors, checkable=checkable)
```

- [ ] **Step 4: Rodar os testes**

Run: `$PY -m pytest tests/test_gui_command.py tests/test_gui_preflight.py -q -p no:cacheprovider`, depois a suíte inteira. O teste que garante o núcleo sem Qt precisa continuar passando.
Expected: tudo verde.

- [ ] **Step 5: Commit e push**

```bash
git add -A
git commit -m "feat(gui): argumentos da verificacao e Preflight.checkable

build_check_argv monta so o que --check-dbms le. checkable diz se os dois
arquivos de configuracao sao validos e coerentes; problemas nos CSVs nao
contam, porque a verificacao nao le dados.

Co-Authored-By: Claude <modelo> <noreply@anthropic.com>"
git push
```

---

### Task 8: GUI: botão "Verificar SGBDs"

**Files:**
- Modify: `src/polyglotimportcsv/gui/widgets/console_panel.py`
- Modify: `src/polyglotimportcsv/gui/widgets/main_window.py`
- Test: `tests/test_gui_console_panel.py`, `tests/test_gui_main_window.py`

**Interfaces:**
- Consumes: `command.build_check_argv`, `command.to_display`, `Preflight.checkable` (Tarefa 7).
- Produces:
  - `ConsolePanel.check_button`, sinal `ConsolePanel.check_requested`, `ConsolePanel.set_check_enabled(enabled: bool)`
  - `MainWindow.argv_for_check() -> List[str]`, `MainWindow.on_check()`
  - constantes `CHECK_OK_STATUS`, `CHECK_FAILED_STATUS`, `CHECK_FIELDS` em `main_window.py`

- [ ] **Step 1: Escrever os testes que falham**

Em `tests/test_gui_console_panel.py`:

```python
def test_check_button_emits_check_requested(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.set_check_enabled(True)
    with qtbot.waitSignal(panel.check_requested, timeout=1000):
        panel.check_button.click()


def test_check_button_follows_running_editing_and_the_form(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.set_check_enabled(True)
    assert panel.check_button.isEnabled()
    panel.set_running(True)
    assert not panel.check_button.isEnabled()
    panel.set_running(False)
    assert panel.check_button.isEnabled()
    panel.set_editing(True)
    assert not panel.check_button.isEnabled()
    panel.set_editing(False)
    assert panel.check_button.isEnabled()
    panel.set_check_enabled(False)
    assert not panel.check_button.isEnabled()
```

Em `tests/test_gui_main_window.py`:

```python
def test_check_is_available_with_valid_configs_even_when_a_csv_is_missing(
    window, config_files, tmp_path
):
    cfg, dbms = config_files
    (tmp_path / "items.csv").unlink()
    window.config_panel.set_paths(cfg, dbms)
    assert not window.console_panel.run_button.isEnabled()
    assert window.console_panel.check_button.isEnabled()


def test_check_is_unavailable_without_a_valid_import_config(window, tmp_path):
    assert not window.console_panel.check_button.isEnabled()
    window.config_panel.set_paths(tmp_path / "ausente.json", None)
    assert not window.console_panel.check_button.isEnabled()


def test_argv_for_check_uses_the_launcher_prefix(window, config_files):
    cfg, dbms = config_files
    window.config_panel.set_paths(cfg, dbms)
    argv = window.argv_for_check()
    prefix = launcher.resolve()
    assert argv[:len(prefix)] == prefix
    assert argv[len(prefix):len(prefix) + 2] == ["--config", str(cfg)]
    assert argv[-3:] == ["--check-dbms", "--log-level", "INFO"]


def _run_fake_check(qtbot, window, monkeypatch, exit_code):
    import sys

    fake_cli = Path(__file__).parent / "gui_fake_cli.py"
    monkeypatch.setattr(
        window, "argv_for_check", lambda: [sys.executable, str(fake_cli), str(exit_code)]
    )
    with qtbot.waitSignal(window.process.finished, timeout=15000):
        window.on_check()


def test_a_passing_check_says_so_in_the_status_bar(qtbot, window, config_files, monkeypatch):
    cfg, dbms = config_files
    window.config_panel.set_paths(cfg, dbms)
    _run_fake_check(qtbot, window, monkeypatch, 0)
    qtbot.waitUntil(lambda: "Todos os SGBDs estão respondendo" in window.status_label.text(),
                    timeout=5000)
    text = window.console_panel.log_view.toPlainText()
    assert text.startswith("Verificando: polyglotimportcsv")
    assert "--check-dbms" in text.splitlines()[0]
    assert "primeira linha" in text  # the child's own output follows


def test_a_failing_check_says_so_in_the_status_bar(qtbot, window, config_files, monkeypatch):
    cfg, dbms = config_files
    window.config_panel.set_paths(cfg, dbms)
    _run_fake_check(qtbot, window, monkeypatch, 1)
    qtbot.waitUntil(lambda: "Verificação não passou" in window.status_label.text(), timeout=5000)
    assert window.config_panel.isEnabled()
    assert "Executar" in window.console_panel.run_button.text()


def test_a_run_after_a_check_reports_like_a_run(window, config_files):
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window._checking = True
    window._on_finished(1)
    assert "Verificação não passou" in window.status_label.text()
    window._on_finished(0)
    assert "Concluído" in window.status_label.text()


def test_stopping_a_check_does_not_ask_for_confirmation(window, monkeypatch):
    window._checking = True
    monkeypatch.setattr(
        "polyglotimportcsv.gui.widgets.main_window.QMessageBox.question",
        lambda *a, **k: pytest.fail("a check writes nothing: no confirmation"),
    )
    stopped = []
    monkeypatch.setattr(window.process, "stop", lambda: stopped.append(1))
    window.on_stop()
    assert stopped == [1]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `$PY -m pytest tests/test_gui_console_panel.py tests/test_gui_main_window.py -q -p no:cacheprovider`
Expected: FAIL (`AttributeError: 'ConsolePanel' object has no attribute 'set_check_enabled'`).

- [ ] **Step 3: `ConsolePanel`**

Em `src/polyglotimportcsv/gui/widgets/console_panel.py`:

(a) Sinal novo, junto dos outros: `check_requested = Signal()`.

(b) Em `__init__`, junto de `self._run_enabled = True`: `self._check_enabled = True`.

(c) Depois da criação de `self.run_button` (e antes de `save_log_button`):

```python
        self.check_button = QPushButton("Verificar SGBDs", self)
        self.check_button.setObjectName("checkButton")
        self.check_button.setToolTip(
            "Testa se os SGBDs de destino respondem, sem importar nada (--check-dbms). "
            "Para os que não respondem, o console mostra o comando que os inicia, "
            "para ser copiado para um terminal."
        )
        self.check_button.clicked.connect(self.check_requested)
```

(d) No layout de ações, entre `copy_button` e `run_button`:

```python
        actions.addWidget(self.copy_button)
        actions.addWidget(self.check_button)
        actions.addWidget(self.run_button)
```

(e) Chame `self._update_check_enabled()` logo depois de `self._update_run_enabled()`, tanto em `set_editing` quanto em `set_running`.

(f) Depois de `set_run_enabled`:

```python
    def set_check_enabled(self, enabled: bool) -> None:
        """Offer "Verificar SGBDs" when the configuration files allow a check."""
        self._check_enabled = enabled
        self._update_check_enabled()
```

(g) Depois de `_update_run_enabled`:

```python
    def _update_check_enabled(self) -> None:
        # In edit mode the typed text is the source of truth; a check built
        # from the locked form would silently ignore it.
        self.check_button.setEnabled(
            self._check_enabled and not self._running and not self._editing
        )
```

- [ ] **Step 4: `MainWindow`**

Em `src/polyglotimportcsv/gui/widgets/main_window.py`:

(a) Constantes, depois de `INVALID_EDIT_STATUS`:

```python
CHECK_OK_STATUS = "Todos os SGBDs estão respondendo"
CHECK_FAILED_STATUS = "Verificação não passou — veja o console"
#: Form fields whose errors block "Verificar SGBDs"; the other fields concern
#: the CSV sources, which the check does not read.
CHECK_FIELDS = ("config_path", "dbms_config_path", "only")
```

(b) Em `__init__`: `self._checking = False` junto de `self._log_path = None`, e a conexão `self.console_panel.check_requested.connect(self.on_check)` junto de `run_requested`.

(c) Em `refresh_command`, troque

```python
        errors = dict(checked.errors)
        errors.update(validate(options))
```

por

```python
        local = validate(options)
        errors = dict(checked.errors)
        errors.update(local)
```

e, depois de `self.console_panel.set_run_enabled(not errors)`:

```python
        self.console_panel.set_check_enabled(
            checked.checkable and not any(field in local for field in CHECK_FIELDS)
        )
```

(d) Depois de `argv_for_run`:

```python
    def argv_for_check(self) -> List[str]:
        """Full argv of "Verificar SGBDs": launcher prefix plus the check arguments."""
        return launcher.resolve() + command_module.build_check_argv(self.options())
```

(e) Troque o corpo de `on_run` depois do `try/except` por uma chamada a um método comum, e acrescente `on_check`:

```python
    def on_run(self) -> None:
        # I3: resolve argv before touching anything else. shlex.split raises
        # ValueError on an edited command with an unbalanced quote (e.g. a
        # pasted Windows path), and the previous run's log must survive that
        # rejection instead of being wiped by an early clear_output().
        try:
            argv = self.argv_for_run()
        except ValueError:
            self.status_label.setText(INVALID_EDIT_STATUS)
            return
        self._checking = False
        self._start(argv, "Executando: {0} …\n".format(" ".join(launcher.resolve())))

    def on_check(self) -> None:
        argv = self.argv_for_check()
        shown = command_module.to_display(command_module.build_check_argv(self.options()))
        self._checking = True
        self._start(argv, "Verificando: {0}\n".format(shown))

    def _start(self, argv: List[str], header: str) -> None:
        self.console_panel.clear_output()
        self.console_panel.append_output(header)
        self._set_form_enabled(False)
        self.console_panel.set_running(True)
        self.log_path_label.setText("")
        self._log_search_buffer = ""
        self._log_path_found = False
        self._log_path = None
        self.console_panel.set_log_available(False)
        self._started_at = time.monotonic()
        self._elapsed_timer.start()
        self._tick()
        self.process.start(argv, self.console_panel.console_columns(), True)
```

(f) Em `on_stop`, no início:

```python
        if self._checking:
            # A check writes nothing: there is nothing to leave half-done.
            self.process.stop()
            return
```

(g) Em `_on_finished`, troque o `if code == 0: … else: …` final por:

```python
        if self._checking:
            self._checking = False
            self.status_label.setText(CHECK_OK_STATUS if code == 0 else CHECK_FAILED_STATUS)
        elif code == 0:
            self.status_label.setText("Concluído — {0:.2f} s".format(elapsed))
        else:
            self.status_label.setText("Falhou — código de saída {0}".format(code))
```

(h) Em `_on_failed`, na primeira linha: `self._checking = False`.

(i) Em `_tick`:

```python
    def _tick(self) -> None:
        elapsed = int(time.monotonic() - self._started_at)
        verb = "Verificando" if self._checking else "Executando"
        self.status_label.setText(
            "{0} — {1:02d}:{2:02d} decorridos".format(verb, elapsed // 60, elapsed % 60)
        )
```

- [ ] **Step 5: Rodar os testes**

Run: `$PY -m pytest tests/test_gui_console_panel.py tests/test_gui_main_window.py -q -p no:cacheprovider`, depois a suíte inteira.
Expected: tudo verde, inclusive os testes antigos de `on_run` ("Executando: …" continua sendo a primeira linha de uma importação).

- [ ] **Step 6: Conferência visual**

Run: `$PY -m polyglotimportcsv.gui` (ou o entry point `polyglotimportcsv-gui`). Escolha `data/ecommerce/import_config.json` e `data/ecommerce/dbms_config_windows.json` e clique em "Verificar SGBDs".
Expected: o console mostra "Verificando: …", a tabela e os comandos. A barra de estado diz "Verificação não passou" sem Docker, ou "Todos os SGBDs…" com Docker. A linha de ações cabe na largura mínima da janela (960 px).

- [ ] **Step 7: Commit e push**

```bash
git add -A
git commit -m "feat(gui): botao Verificar SGBDs

Roda --check-dbms com os arquivos e a selecao de SGBDs do formulario; fica
disponivel com as duas configuracoes validas, mesmo com pendencias nos CSVs.
Interromper uma verificacao nao pede confirmacao.

Co-Authored-By: Claude <modelo> <noreply@anthropic.com>"
git push
```

---

### Task 9: READMEs bilíngues e README da release

**Files:**
- Modify: `README.md`, `docs/ARCHITECTURE.md`, `data/ecommerce/README.md`, `data/benchmark/README.md`, `benchmarks/README.md`
- Rename + rewrite: `packaging/LEIAME.txt` → `packaging/README.md`
- Modify: `scripts/package_release.py`
- Test: `tests/test_package_release.py`

**Interfaces:**
- Consumes: nomes e opções das Tarefas 1 a 8.
- Produces: `packaging/README.md`, empacotado como `README.md` na raiz de cada zip.

Seletor padrão, que vai na primeira linha de todo README (depois do título H1, quando houver):

```markdown
**Language / Idioma / Língua:** [English](#english) · [Português (BR)](#português-br)
```

Cada README tem uma seção `## English` e uma `## Português (BR)` com o mesmo conteúdo. As subseções usam `###`.

- [ ] **Step 1: Teste do empacotador que falha**

Em `tests/test_package_release.py`:
- No fixture `repo`, a linha `(root / "packaging" / "LEIAME.txt").write_text("leia-me\n", encoding="utf-8")` vira `(root / "packaging" / "README.md").write_text("readme\n", encoding="utf-8")`.
- Em `test_a_zip_holds_the_executable_and_the_example`, `prefix + "LEIAME.txt",` vira `prefix + "README.md",`.
- Acrescente o teste abaixo. É uma proteção: o empacotador já leva tudo de `data/ecommerce/`, então este teste passa desde o início.

```python
def test_the_three_dbms_configs_are_shipped(repo, tmp_path):
    names = ("dbms_config.json", "dbms_config_windows.json", "dbms_config_linux.json")
    for name in names:
        (repo / "data" / "ecommerce" / name).write_text("{}", encoding="utf-8")
    exe = tmp_path / "polyglotimportcsv.exe"
    exe.write_bytes(b"MZ")
    out = package_release.build_zip(repo, exe, tmp_path / "release", "pkg")
    for name in names:
        assert "pkg/data/ecommerce/" + name in _names(out)
```

Run: `$PY -m pytest tests/test_package_release.py -q -p no:cacheprovider`
Expected: FAIL em `test_a_zip_holds_the_executable_and_the_example` (o empacotador ainda procura `packaging/LEIAME.txt`, que o fixture não cria mais).

- [ ] **Step 2: Empacotador**

```bash
git mv packaging/LEIAME.txt packaging/README.md
```

Em `scripts/package_release.py`, troque `yield repo / "packaging" / "LEIAME.txt", "LEIAME.txt"` por `yield repo / "packaging" / "README.md", "README.md"`, e no docstring troque "a short LEIAME" por "a bilingual README".

- [ ] **Step 3: `packaging/README.md`**

Conteúdo inteiro:

````markdown
# PolyglotImportCSV

**Language / Idioma / Língua:** [English](#english) · [Português (BR)](#português-br)

## English

Imports CSV files into PostgreSQL, MongoDB, Cassandra, Redis and Neo4j in a
single run, driven by two JSON configuration files.

Project: https://github.com/lucasbc92/polyglot-import-csv

### Package contents

| Path | What it is |
|---|---|
| `polyglotimportcsv-gui(.exe)` | graphical interface (GUI package only) |
| `polyglotimportcsv(.exe)` | command line (CLI package only) |
| `data/ecommerce/` | example scenario: CSVs and configurations (`import_config_invalido.json` has a deliberate error, to see validation at work) |
| `data/ecommerce/dbms_config*.json` | the same DBMS connections, three ways to start them: `dbms_config.json` (Docker), `dbms_config_windows.json`, `dbms_config_linux.json` |
| `docker-compose.yml` | containers for the five DBMS of the example |
| `LICENSE` | MIT licence |

Mentions of `run_example.sh` and `python -m polyglotimportcsv` in
`docker-compose.yml` and `data/ecommerce/README.md` refer to the source
repository; with the executables, use the commands below.

### Graphical interface

- Windows: double-click `polyglotimportcsv-gui.exe`.
- Linux: run `./polyglotimportcsv-gui` in a terminal, in this folder. If the
  window does not open, install `sudo apt install libxcb-cursor0`.

Choose `data/ecommerce/import_config.json` and `data/ecommerce/dbms_config.json`,
tick "Simulação (--dry-run)" and click Executar.

### Command line

The dry run validates the configurations and shows how many records would go to
each destination, without connecting to any DBMS. In this folder:

```
Windows (PowerShell):  .\polyglotimportcsv.exe --config data/ecommerce/import_config.json --dry-run
Windows (cmd):         polyglotimportcsv.exe --config data/ecommerce/import_config.json --dry-run
Linux:                 ./polyglotimportcsv --config data/ecommerce/import_config.json --dry-run
```

Use `--help` for every option. On Windows, use the CLI package to work in a
terminal: the GUI executable prints no text to an interactive terminal.

### Real import

The DBMS of the example can run in Docker or be installed on this machine.

- **With Docker:** in this folder, `docker compose up -d --wait` (Cassandra
  takes about a minute), then use `data/ecommerce/dbms_config.json`, the default.
- **Without Docker:** install and start the DBMS, then pass the connection file
  of your system: `--dbms-config data/ecommerce/dbms_config_windows.json` (or
  `dbms_config_linux.json`); in the GUI, choose it as the DBMS configuration.
  Service names vary between installations: adjust the `start` blocks to yours.
  Cassandra does not run natively on Windows; there it needs Docker or WSL.

Before importing, check that the DBMS answer: add `--check-dbms` to the command,
or click "Verificar SGBDs" in the GUI. For each DBMS that does not answer, the
output shows the command that starts it. The tool never runs it: copy it into a
terminal (service commands usually need an administrator terminal or `sudo`).
A real import runs the same check first and stops before writing anything if a
DBMS is down.

Then run the same command without `--dry-run` (or untick the dry run in the GUI).

### Run log

Each run writes a complete log under `logs/`, in the folder the program was
started from. In the GUI, the path appears in the status bar (a click opens the
folder) and "Salvar log…" copies the file.

### Windows

The executables are not digitally signed. On the first run, SmartScreen may
warn about an unrecognised app: click "More info" and then "Run anyway".

### Linux

Requires Linux x64 with glibc 2.35 or later (e.g. Ubuntu 22.04+ or Debian 12+).
If needed, make the files executable: `chmod +x polyglotimportcsv*`.

## Português (BR)

Importa arquivos CSV para PostgreSQL, MongoDB, Cassandra, Redis e Neo4j em uma
única execução, conforme dois arquivos de configuração em JSON.

Projeto: https://github.com/lucasbc92/polyglot-import-csv

### Conteúdo do pacote

| Caminho | O que é |
|---|---|
| `polyglotimportcsv-gui(.exe)` | interface gráfica (só no pacote da GUI) |
| `polyglotimportcsv(.exe)` | linha de comando (só no pacote da CLI) |
| `data/ecommerce/` | cenário de exemplo: CSVs e configurações (`import_config_invalido.json` tem um erro proposital, para ver a validação em ação) |
| `data/ecommerce/dbms_config*.json` | as mesmas conexões com os SGBDs e três formas de subi-los: `dbms_config.json` (Docker), `dbms_config_windows.json`, `dbms_config_linux.json` |
| `docker-compose.yml` | contêineres dos cinco SGBDs do exemplo |
| `LICENSE` | licença MIT |

As menções a `run_example.sh` e a `python -m polyglotimportcsv` em
`docker-compose.yml` e em `data/ecommerce/README.md` referem-se ao repositório
do código-fonte; com os executáveis, use os comandos abaixo.

### Interface gráfica

- Windows: dê dois cliques em `polyglotimportcsv-gui.exe`.
- Linux: execute `./polyglotimportcsv-gui` em um terminal, nesta pasta. Se a
  janela não abrir, instale `sudo apt install libxcb-cursor0`.

Escolha `data/ecommerce/import_config.json` e `data/ecommerce/dbms_config.json`,
marque "Simulação (--dry-run)" e clique em Executar.

### Linha de comando

O modo de simulação valida as configurações e mostra quantos registros iriam
para cada destino, sem conectar a nenhum SGBD. Nesta pasta:

```
Windows (PowerShell):  .\polyglotimportcsv.exe --config data/ecommerce/import_config.json --dry-run
Windows (cmd):         polyglotimportcsv.exe --config data/ecommerce/import_config.json --dry-run
Linux:                 ./polyglotimportcsv --config data/ecommerce/import_config.json --dry-run
```

Para ver todas as opções, use `--help`. No Windows, use o pacote da CLI para
trabalhar no terminal: o executável da interface gráfica não exibe texto em um
terminal interativo.

### Importação real

Os SGBDs do exemplo podem rodar no Docker ou estar instalados nesta máquina.

- **Com Docker:** nesta pasta, `docker compose up -d --wait` (o Cassandra leva
  cerca de um minuto) e use `data/ecommerce/dbms_config.json`, o padrão.
- **Sem Docker:** instale e inicie os SGBDs e informe o arquivo de conexão do
  seu sistema: `--dbms-config data/ecommerce/dbms_config_windows.json` (ou
  `dbms_config_linux.json`); na interface gráfica, escolha-o como configuração
  de SGBDs. Os nomes de serviço variam de uma instalação para outra: ajuste os
  blocos `start` à sua. O Cassandra não roda nativamente no Windows; lá, ele
  precisa do Docker ou do WSL.

Antes de importar, confira se os SGBDs respondem: acrescente `--check-dbms` ao
comando, ou clique em "Verificar SGBDs" na interface gráfica. Para cada SGBD
que não responder, a saída mostra o comando que o inicia. A ferramenta nunca o
executa: copie-o para um terminal (comandos de serviço costumam exigir um
terminal de administrador ou `sudo`). Uma importação real faz a mesma
verificação antes e para sem gravar nada se algum SGBD estiver fora do ar.

Depois, execute o mesmo comando sem `--dry-run` (ou desmarque a simulação na
interface gráfica).

### Log da execução

Cada execução grava um log completo em `logs/`, a partir da pasta em que o
programa foi executado. Na interface gráfica, o caminho aparece na barra de
estado (um clique abre a pasta) e o botão "Salvar log…" copia o arquivo.

### Windows

Os executáveis não são assinados digitalmente. Na primeira execução, o
SmartScreen pode avisar sobre um aplicativo não reconhecido: clique em "Mais
informações" e depois em "Executar assim mesmo".

### Linux

Requer Linux x64 com glibc 2.35 ou superior (por exemplo, Ubuntu 22.04+ ou
Debian 12+). Se necessário, dê permissão de execução: `chmod +x polyglotimportcsv*`.
````

- [ ] **Step 4: `README.md`**

Na seção EN, depois da lista "Options:" (que termina em `- --no-create-schema — skip DDL where applicable.`), insira:

````markdown
### Checking the DBMS

Before reading any CSV, a real import checks that every target DBMS (those in
the import configuration, narrowed by `--only`) answers on its address, and
stops before writing anything if one does not. `--check-dbms` runs only that
check and exits, with code 0 when all are up:

```bash
python -m polyglotimportcsv --config data/ecommerce/import_config.json \
  --dbms-config data/ecommerce/dbms_config_windows.json --check-dbms
```

For each DBMS that is down, the output shows how to start it, taken from the
optional `start` block of that DBMS in the connection file: a command for a
DBMS installed on the machine, or a Docker Compose service (the file path is
relative to the connection file).

```json
"postgres":  { "connection": { "...": "..." }, "start": { "command": "net start postgresql-x64-16" } },
"cassandra": { "connection": { "...": "..." }, "start": { "compose": { "file": "../../docker-compose.yml", "service": "cassandra" } } }
```

The tool never runs these commands: copy them into a terminal (service commands
usually need an administrator terminal or `sudo`). `data/ecommerce/` ships three
connection files with the same connections and different `start` blocks:
`dbms_config.json` (Docker Compose, the default), `dbms_config_windows.json` and
`dbms_config_linux.json`. Service names vary between installations; adjust them
to yours. In the GUI, the "Verificar SGBDs" button runs the same check.
````

Na seção PT, no ponto equivalente (depois da lista de opções da seção "Uso"), insira:

````markdown
### Verificação dos SGBDs

Antes de ler qualquer CSV, uma importação real verifica se cada SGBD de destino
(os presentes na configuração de importação, filtrados por `--only`) responde
no seu endereço, e para sem gravar nada se algum não responder. `--check-dbms`
faz só essa verificação e sai, com código 0 quando todos respondem:

```bash
python -m polyglotimportcsv --config data/ecommerce/import_config.json \
  --dbms-config data/ecommerce/dbms_config_windows.json --check-dbms
```

Para cada SGBD fora do ar, a saída mostra como subi-lo, a partir do bloco
opcional `start` daquele SGBD no arquivo de conexão: um comando, para um SGBD
instalado na máquina, ou um serviço do Docker Compose (o caminho do arquivo é
relativo ao arquivo de conexão).

```json
"postgres":  { "connection": { "...": "..." }, "start": { "command": "net start postgresql-x64-16" } },
"cassandra": { "connection": { "...": "..." }, "start": { "compose": { "file": "../../docker-compose.yml", "service": "cassandra" } } }
```

A ferramenta nunca executa esses comandos: copie-os para um terminal (comandos
de serviço costumam exigir um terminal de administrador ou `sudo`). A pasta
`data/ecommerce/` traz três arquivos de conexão com as mesmas conexões e blocos
`start` diferentes: `dbms_config.json` (Docker Compose, o padrão),
`dbms_config_windows.json` e `dbms_config_linux.json`. Os nomes de serviço
variam de uma instalação para outra; ajuste-os à sua. Na interface gráfica, o
botão "Verificar SGBDs" faz a mesma verificação.
````

Nas duas seções, na lista de opções, acrescente depois de `--dry-run`, ou no fim da lista se `--dry-run` não estiver nela:
- EN: `- `--check-dbms` — only check that the target DBMS answer and exit (see "Checking the DBMS").`
- PT: `- `--check-dbms` — só verifica se os SGBDs de destino respondem e sai (veja "Verificação dos SGBDs").`

Na tabela "Layout" das duas seções, `data/ecommerce/` passa a citar `dbms_config*.json`.

- [ ] **Step 5: `docs/ARCHITECTURE.md`**

- As duas linhas de seletor (a EN, `**Language:** …`, e a PT, `**Idioma:** …`) viram:
  `**Language / Idioma / Língua:** [English](#english-architecture) · [Português (BR)](#arquitetura-em-português)`
- Na tabela de camadas EN, linha "Application / use case", acrescente `dbms_check.py` aos módulos. Na tabela PT, linha "Caso de uso", idem.
- Na lista EN, depois do item "Reporting (rich)", acrescente:
  `- **DBMS check**: `dbms_check.py` probes every target DBMS over TCP before any CSV is read, with addresses taken from the drivers' own parsing; `runner` prints the states and the `start` hints of the DBMS configuration and aborts with `DbmsUnavailableError` when one is not ready. It never runs a start command.`
- Na parte PT, depois do parágrafo que começa "No formato v2 da configuração", acrescente:
  `Antes de ler qualquer CSV, `dbms_check.py` sonda por TCP cada SGBD de destino, com os endereços obtidos pelo código dos próprios *drivers*; o `runner` mostra os estados e as dicas do bloco `start` e interrompe com `DbmsUnavailableError` quando algum não está pronto. O comando de `start` nunca é executado.`

- [ ] **Step 6: `data/ecommerce/README.md`**

Conteúdo inteiro:

````markdown
# E-commerce example data

**Language / Idioma / Língua:** [English](#english) · [Português (BR)](#português-br)

## English

| File | Purpose |
|------|---------|
| `ecommerce_stock.csv`, `ecommerce_purchase.csv`, `ecommerce_select_product.csv`, `ecommerce_add_to_cart.csv` | One CSV per entity (default input mode). Each file IS the origin of its rows — no discriminator column needed. |
| `ecommerce_join.csv` | Combined CSV (alternative input mode): column 0 (`action`) is the origin column; each distinct value becomes a source. |
| `import_config.json` | v2 mapping config (multi-CSV `sources`). Default for `./run_example.sh`. |
| `import_config_combined.json` | Same DBMS blocks, `sources` pointing at the combined CSV — demonstrates that switching input modes changes nothing in the per-DBMS mapping. |
| `import_config_invalido.json` | A deliberately invalid config (its `stock` source is a number), to see the validation at work. |
| `dbms_config.json` | Connection settings per DBMS; its `start` blocks point at the Docker Compose services of `../../docker-compose.yml`. Default when `--dbms-config` is omitted. |
| `dbms_config_windows.json` | Same connections; `start` holds Windows service commands (`net start …`). Cassandra, which does not run natively on Windows, keeps the Docker Compose service. |
| `dbms_config_linux.json` | Same connections; `start` holds `sudo systemctl start …` commands. |

The `start` blocks are only shown, never run, when `--check-dbms` (or the check
that precedes every real import) finds a DBMS down. Service names vary between
installations: adjust them to yours.

### Knowing each row's origin

Knowing the **source (entity) of every row** is an essential requirement of the
import process. In the per-entity files the file itself designates the origin.
In the combined `ecommerce_join.csv`, column 0 plays that role: the importer
slices the file by its distinct values and each value becomes a named source
(also exposed to mappings as the `_source` pseudo-column).

For a larger stress test, add another CSV (e.g. `ecommerce_stock_large.csv`) and
override just that source's path:

```bash
python -m polyglotimportcsv --config data/ecommerce/import_config.json \
  --source stock=data/ecommerce/ecommerce_stock_large.csv \
  --dry-run
```

The config must reference columns present in that CSV.

## Português (BR)

| Arquivo | Finalidade |
|---------|------------|
| `ecommerce_stock.csv`, `ecommerce_purchase.csv`, `ecommerce_select_product.csv`, `ecommerce_add_to_cart.csv` | Um CSV por entidade (modo de entrada padrão). Cada arquivo É a origem das suas linhas — não há coluna discriminadora. |
| `ecommerce_join.csv` | CSV combinado (modo alternativo): a coluna 0 (`action`) é a coluna de origem; cada valor distinto vira uma fonte. |
| `import_config.json` | Configuração de mapeamento v2 (`sources` com vários CSVs). Padrão do `./run_example.sh`. |
| `import_config_combined.json` | Os mesmos blocos por SGBD, com `sources` apontando o CSV combinado — mostra que trocar o modo de entrada não muda nada no mapeamento de cada SGBD. |
| `import_config_invalido.json` | Uma configuração inválida de propósito (a fonte `stock` é um número), para ver a validação em ação. |
| `dbms_config.json` | Conexão com cada SGBD; os blocos `start` apontam os serviços do Docker Compose de `../../docker-compose.yml`. É o padrão quando `--dbms-config` é omitido. |
| `dbms_config_windows.json` | As mesmas conexões; `start` traz comandos de serviço do Windows (`net start …`). O Cassandra, que não roda nativamente no Windows, mantém o serviço do Docker Compose. |
| `dbms_config_linux.json` | As mesmas conexões; `start` traz comandos `sudo systemctl start …`. |

Os blocos `start` são só exibidos, nunca executados, quando o `--check-dbms` (ou
a verificação que antecede toda importação real) encontra um SGBD fora do ar.
Os nomes de serviço variam de uma instalação para outra: ajuste-os à sua.

### A origem de cada linha

Saber a **fonte (entidade) de cada linha** é um requisito essencial da
importação. Nos arquivos por entidade, o próprio arquivo designa a origem. No
`ecommerce_join.csv` combinado, a coluna 0 faz esse papel: o importador fatia o
arquivo pelos seus valores distintos e cada valor vira uma fonte nomeada
(também exposta aos mapeamentos como a pseudocoluna `_source`).

Para um teste maior, acrescente outro CSV (por exemplo,
`ecommerce_stock_large.csv`) e sobrescreva só o caminho daquela fonte:

```bash
python -m polyglotimportcsv --config data/ecommerce/import_config.json \
  --source stock=data/ecommerce/ecommerce_stock_large.csv \
  --dry-run
```

A configuração precisa referenciar colunas presentes nesse CSV.
````

- [ ] **Step 7: `data/benchmark/README.md` e `benchmarks/README.md`**

Em cada um:
1. Mantenha o título H1.
2. Logo abaixo dele, ponha o seletor padrão e `## English`.
3. Rebaixe cada `##` existente para `###` (e cada `###` para `####`).
4. Ao fim, acrescente `## Português (BR)` com a tradução integral do conteúdo EN: mesmas subseções (rebaixadas), tabelas, blocos de código e números. Não traduza código, caminhos e nomes de colunas.
5. No `benchmarks/README.md`, "SGBD" nunca aparece na seção EN. Na PT, use "SGBD".

Confira que os links relativos continuam válidos.

- [ ] **Step 8: Rodar a suíte**

Run: `$PY -m pytest tests -q -p no:cacheprovider`
Expected: tudo verde.

Confira também os seletores: `grep -rn "Language / Idioma / Língua" --include=README.md . docs/ARCHITECTURE.md` deve listar `README.md`, `packaging/README.md`, `data/ecommerce/README.md`, `data/benchmark/README.md`, `benchmarks/README.md` e `docs/ARCHITECTURE.md`.

- [ ] **Step 9: Commit e push**

```bash
git add -A
git commit -m "docs: READMEs bilingues e README.md no lugar do LEIAME da release

Todos os READMEs ganham secoes EN e PT com o seletor de idioma; o README
principal e o do pacote explicam o --check-dbms, o bloco start e os tres
arquivos de conexao do exemplo.

Co-Authored-By: Claude <modelo> <noreply@anthropic.com>"
git push
```

---

### Task 10: Relatório: nomes, siglas, esquema, apêndices, figuras 7, 9, 10 e 11 e o bloco `start`

**Files:**
- Modify: `docs-tcc/main.tex` (siglas)
- Modify: `docs-tcc/chapters/ch4proposta.tex`, `docs-tcc/chapters/apendiceconfig.tex`, `docs-tcc/chapters/apendiceschemas.tex`
- Modify: `docs-tcc/images/figure7-overview.mmd`, `docs-tcc/images/figure10-config-pipeline.mmd`, `docs-tcc/images/figure11-import-algorithm.mmd`
- Rename + modify: `docs-tcc/images/figure9-sgbd-schema.{mmd,png}` → `figure9-dbms-schema.{mmd,png}`
- Regenerate: `docs-tcc/images/figure{7,9,10,11}-*.png`

**Interfaces:**
- Consumes: esquema e `dbms_config*.json` (Tarefa 2); comportamento das Tarefas 5 e 6.
- Produces: rótulos `sec:inicializacao-sgbds` e `lst:start-windows`, que a Tarefa 11 referencia. A Tarefa 11 cria `sec:verificacao-sgbds` e, até lá, o `\ref` sai como "??" no PDF intermediário.

- [ ] **Step 1: Troca de nome no relatório**

A partir de `docs-tcc/`, nos arquivos `chapters/ch4proposta.tex`, `chapters/apendiceconfig.tex` e `chapters/apendiceschemas.tex`:
- `sgbd\_config` → `dbms\_config` (nomes de arquivo, em `\texttt{}`)
- `-{}-sgbd-config` → `-{}-dbms-config`
- `--sgbd-config` e `sgbd_config` dentro de `lstlisting` → `--dbms-config` e `dbms_config`
- rótulos `lst:sgbd-config-full` → `lst:dbms-config-full` e `fig:sgbd-schema` → `fig:dbms-schema`, em todas as referências
- `images/figure9-sgbd-schema` → `images/figure9-dbms-schema`

O texto corrido continua dizendo "SGBD". Os rótulos `tab:escrita-sgbd` e `fig:throughput-sgbd` do cap. 6 falam do conceito, não de arquivo, e ficam como estão.

Depois: `git grep -n -i "sgbd.config\|sgbd-config\|sgbd\\\\_config" -- docs-tcc/chapters docs-tcc/images/*.mmd` não deve retornar nada.

- [ ] **Step 2: Sigla**

Em `docs-tcc/main.tex`, na lista `siglas`, entre `\item[DDL]` e `\item[GUI]`:

```latex
  \item[DBMS] \textit{Database Management System} (Sistema de Gerenciamento de Banco de Dados)
```

- [ ] **Step 3: Apêndices**

- `apendiceconfig.tex`, seção "Arquivo de Conexão (`dbms\_config.json`)": substitua o corpo da listagem pelo conteúdo atual de `data/ecommerce/dbms_config.json`, copiado byte a byte.
- `apendiceschemas.tex`: substitua os corpos das duas listagens de esquema pelo conteúdo atual de `src/polyglotimportcsv/schemas/import_config.schema.json` (a `description` mudou na Tarefa 1) e de `src/polyglotimportcsv/schemas/dbms_config.schema.json` (agora com `$defs/start`), também byte a byte.

Confira com `diff` entre o trecho extraído do `.tex` e o arquivo.

- [ ] **Step 4: Texto do cap. 4, uso da CLI**

Em `chapters/ch4proposta.tex`:

(a) Na listagem do comando principal (seção Visão Geral), depois da linha `  [--dry-run] \`, acrescente `  [--check-dbms] \`.

(b) Troque `mapeamento antes da carga real; \texttt{-{}-create-schema} e` por:

```latex
mapeamento antes da carga real; \texttt{-{}-check-dbms} apenas verifica se os SGBDs de
destino respondem e encerra sem importar, como detalha a
Seção~\ref{sec:verificacao-sgbds}; \texttt{-{}-create-schema} e
```

(c) No parágrafo "**O arquivo de conexão.**", troque

```latex
SGBD de \texttt{dbms\_config} carrega apenas um descritor
\texttt{connection} com os parâmetros de acesso pertinentes àquela tecnologia (por
```

por

```latex
SGBD de \texttt{dbms\_config} carrega um descritor
\texttt{connection} com os parâmetros de acesso pertinentes àquela tecnologia e,
opcionalmente, um descritor \texttt{start}, que diz como iniciá-lo
(Seção~\ref{sec:inicializacao-sgbds}) (por
```

(d) Seção de validação (`sec:validacao`): troque `A validação ocorre em \textbf{três camadas} antes de qualquer conexão com os SGBDs.` por `A validação ocorre em \textbf{três camadas} antes de qualquer gravação nos SGBDs.`

(e) Seção do algoritmo: troque `uma mensagem de erro antes que qualquer conexão com os SGBDs seja aberta.` por `uma mensagem de erro antes que qualquer dado seja gravado nos SGBDs.`

(f) Seção do algoritmo, logo depois do parágrafo que começa "Na etapa de \textbf{carregamento da configuração}", insira este parágrafo:

```latex
Em uma importação real, segue-se a \textbf{verificação dos SGBDs} de destino,
detalhada na Seção~\ref{sec:verificacao-sgbds}: se algum deles não responder, a
execução termina antes da leitura de qualquer CSV, com a indicação de como iniciá-lo.
```

- [ ] **Step 5: Subseção "Inicialização dos SGBDs"**

Em `chapters/ch4proposta.tex`, imediatamente antes de `\subsection{Validação, Consistência entre Arquivos e Fluxo de Carregamento}`, insira:

```latex
\subsection{Inicialização dos SGBDs}
\label{sec:inicializacao-sgbds}

O arquivo de conexão diz \textit{onde} alcançar cada SGBD, mas não o que fazer quando
ele não responde. Para esse caso, cada bloco de SGBD aceita um descritor opcional
\texttt{start}, que registra \textit{como} iniciá-lo, em uma de duas formas mutuamente
exclusivas: \texttt{command}, uma linha de comando para um SGBD instalado na própria
máquina, ou \texttt{compose}, que indica um arquivo do Docker Compose e o serviço
correspondente. A ferramenta \textbf{nunca executa} esse comando: ela o exibe, pronto
para ser copiado para um terminal, quando a verificação descrita na
Seção~\ref{sec:verificacao-sgbds} encontra o SGBD fora do ar. A escolha é deliberada:
iniciar um serviço do sistema operacional costuma exigir privilégios de administrador,
que a ferramenta não tem nem deve pedir. A Listagem~\ref{lst:start-windows} mostra dois
blocos do arquivo de conexão de exemplo para Windows, um em cada forma.

\begin{lstlisting}[style=jsonstyle,caption={Descritores \texttt{start} nas duas formas (\texttt{dbms\_config\_windows.json}).},label={lst:start-windows}]
"postgres": {
  "connection": { ... },
  "schema": "public",
  "start": { "command": "net start postgresql-x64-16" }
},
"cassandra": {
  "connection": { ... },
  "start": {
    "compose": {
      "file":    "../../docker-compose.yml",
      "service": "cassandra"
    }
  }
}
\end{lstlisting}

O PostgreSQL, instalado como serviço do Windows, é iniciado por \texttt{net start}; o
Apache Cassandra, que não roda nativamente no Windows, é descrito por um serviço do
Docker Compose, cujo arquivo tem caminho relativo à pasta do próprio arquivo de
conexão. O cenário de exemplo traz três arquivos de conexão com as mesmas conexões e
descritores \texttt{start} distintos: \texttt{dbms\_config.json}, todo em Docker
Compose; \texttt{dbms\_config\_windows.json}, com serviços do Windows; e
\texttt{dbms\_config\_linux.json}, com o \texttt{systemctl}. Como os nomes de serviço
dependem de cada instalação, os comandos desses arquivos são exemplos a ajustar.
```

- [ ] **Step 6: Diagramas Mermaid**

`git mv docs-tcc/images/figure9-sgbd-schema.mmd docs-tcc/images/figure9-dbms-schema.mmd` e `git mv docs-tcc/images/figure9-sgbd-schema.png docs-tcc/images/figure9-dbms-schema.png`.

`figure9-dbms-schema.mmd`, conteúdo inteiro:

```
flowchart LR
    ROOT["dbms_config (raiz)\nversion*, additionalProperties: false"]
    ROOT --> PG[postgres]
    ROOT --> MG[mongodb]
    ROOT --> CS[cassandra]
    ROOT --> RD[redis]
    ROOT --> NJ[neo4j]

    PG --> PGC["connection(host, port, database,\nuser, password), schema"]
    MG --> MGC["connection(uri*, database*)"]
    CS --> CSC["connection(hosts*, port,\nkeyspace*, protocol_version)"]
    RD --> RDC["connection(host, port, db, password)"]
    NJ --> NJC["connection(uri*, user*,\npassword*, database)"]

    PG -.-> ST
    MG -.-> ST
    CS -.-> ST
    RD -.-> ST
    NJ -.-> ST
    ST["start (opcional), um de:\ncommand*\nou compose(file*, service*)"]

    style ROOT fill:#dbeafe,stroke:#2563eb,color:#1e293b
    style PGC fill:#fef3c7,stroke:#d97706,color:#1e293b
    style MGC fill:#fef3c7,stroke:#d97706,color:#1e293b
    style CSC fill:#fef3c7,stroke:#d97706,color:#1e293b
    style RDC fill:#fef3c7,stroke:#d97706,color:#1e293b
    style NJC fill:#fef3c7,stroke:#d97706,color:#1e293b
    style ST fill:#dcfce7,stroke:#16a34a,color:#1e293b
```

`figure11-import-algorithm.mmd`: troque a linha `    LC --> LS["load_sources()…` pelas linhas abaixo e acrescente o estilo ao fim:

```
    LC --> CHK{"verifica os SGBDs\n(sonda TCP;\nomitida em --dry-run)"}
    CHK -->|"algum fora do ar\nou inválido"| STOP(["Fim: estados e\ncomandos para subi-los"])
    CHK -->|todos no ar| LS["load_sources()\nlê CSV(s), infere tipos\n(fatia origem no modo combinado)"]
```

```
    style STOP fill:#fee2e2,stroke:#dc2626,color:#1e293b
```

`figure7-overview.mmd` e `figure10-config-pipeline.mmd`: só a troca de nome do Step 1 (`dbms_config.json`, `dbms_config.schema.json`, `dbms_map`). Confira que a troca ocorreu.

- [ ] **Step 7: Renderizar**

```bash
SCRATCH="<diretório de rascunho da sessão>"
printf '{"executablePath": "C:/Program Files/Google/Chrome/Application/chrome.exe"}' > "$SCRATCH/puppeteer.json"
printf '{"theme": "default"}' > "$SCRATCH/mermaid.json"
cd docs-tcc/images
for spec in "figure7-overview 1072" "figure9-dbms-schema 766" "figure10-config-pipeline 1176" "figure11-import-algorithm 1176"; do
  set -- $spec
  npx -y @mermaid-js/mermaid-cli@11.4.0 -p "$SCRATCH/puppeteer.json" -c "$SCRATCH/mermaid.json" \
    -b white -s 2 -w "$2" -i "$1.mmd" -o "$1.png"
done
cd ../..
```

Abra cada PNG (ferramenta Read) e compare com a versão anterior (`git show HEAD:docs-tcc/images/figure11-import-algorithm.png > "$SCRATCH/old11.png"`). O tema, as cores e a fonte devem ser os mesmos. Se o tema diferir, ajuste `mermaid.json` (a nota do projeto diz "classic-theme config") até coincidir e renderize de novo. Uma figura densa demais pede divisão, pela preferência do orientador.

- [ ] **Step 8: Compilar**

```bash
cd docs-tcc && latexmk -pdf -interaction=nonstopmode main.tex; cd ..
```

Expected: compila. As únicas referências indefinidas permitidas são a `sec:verificacao-sgbds` (três ocorrências, criadas na Tarefa 11). Confira com `grep -n "undefined" docs-tcc/main.log`. Abra as páginas das figuras 9 e 11 e da subseção nova no PDF para conferir o layout.

- [ ] **Step 9: Commit e push**

```bash
git add -A docs-tcc
git commit -m "docs(tcc): dbms_config, sigla DBMS, bloco start e figuras 7, 9, 10 e 11

Os nomes de arquivo e a opcao passam a dbms_config e --dbms-config, com DBMS
na lista de siglas; os apendices trazem o esquema e o arquivo de conexao
atuais; a secao 4.2 ganha a subsecao sobre o bloco start e a figura 11 o
passo de verificacao dos SGBDs.

Co-Authored-By: Claude <modelo> <noreply@anthropic.com>"
git push
```

---

### Task 11: Relatório: verificação dos SGBDs, figuras da GUI 12 a 16 e PDF v2.2 (precisa do Docker)

**Files:**
- Modify: `scripts/capture_gui_figures.py`
- Modify: `docs-tcc/chapters/ch4proposta.tex`
- Regenerate: `docs-tcc/images/figure1{2,3,4,5}-gui-*.png`; Create: `docs-tcc/images/figure16-gui-verificacao.png`
- Create: `docs-tcc/TCC2-PolyglotImportCSV-Report-v2.2.pdf`

**Interfaces:**
- Consumes: `dbms_check.check_dbms`, `config_parser.load_dbms_config`, `MainWindow.on_check`, `ConsolePanel.check_button`; rótulos da Tarefa 10.
- Produces: rótulos `sec:verificacao-sgbds`, `tab:check-dbms`, `lst:check-dbms`, `fig:gui-verificacao`.

- [ ] **Step 1: Preparar os SGBDs**

```bash
docker compose up -d --wait
docker compose stop mongodb neo4j
```

- [ ] **Step 2: Saída real para o texto**

```bash
NO_COLOR=1 COLUMNS=110 $PY -m polyglotimportcsv --config data/ecommerce/import_config.json \
  --dbms-config data/ecommerce/dbms_config_windows.json --check-dbms > "$SCRATCH/check.txt" 2>&1; echo "exit $?"
```

Expected: `exit 1`. A tabela deve mostrar `postgres`, `cassandra` e `redis` `up`, e `mongodb` e `neo4j` `down`. As dicas devem ser `net start MongoDB` e `net start neo4j`, seguidas da nota sobre administrador. Guarde o arquivo: os Steps 4 e 5 copiam dele.

- [ ] **Step 3: Script das figuras**

Em `scripts/capture_gui_figures.py` (após a Tarefa 1 a constante se chama `DBMS`):

(a) Imports: `from polyglotimportcsv.config_parser import load_dbms_config` e `from polyglotimportcsv.dbms_check import check_dbms`.

(b) Constantes, depois de `DBMS`:

```python
DBMS_WINDOWS = DATA / "dbms_config_windows.json"
#: Stopped on purpose for figure 16: docker compose stop mongodb neo4j.
STOPPED = {"mongodb", "neo4j"}
TARGETS = ("postgres", "mongodb", "cassandra", "redis", "neo4j")
```

(c) `new_window` ganha o parâmetro `dbms: Path = DBMS` e usa `window.config_panel.set_paths(config, dbms)`.

(d) Função nova, antes de `main`:

```python
def ready_for_figure_16() -> bool:
    """Figure 16 needs the example stack up with exactly STOPPED down."""
    report = check_dbms(TARGETS, load_dbms_config(DBMS_WINDOWS), DBMS_WINDOWS)
    down = {status.dbms for status in report.statuses if status.state != "up"}
    return down == STOPPED
```

(e) Em `main`, logo depois da conferência de arquivos ausentes (e acrescente `DBMS_WINDOWS` a essa tupla):

```python
    if not ready_for_figure_16():
        print(
            "figure 16 needs the example stack up with only MongoDB and Neo4j stopped:\n"
            "  docker compose up -d --wait\n"
            "  docker compose stop mongodb neo4j",
            file=sys.stderr,
        )
        return 1
```

(f) Em `main`, depois de `failing.hide()`:

```python
        # Figure 16: "Verificar SGBDs" with the Windows connection file while
        # MongoDB and Neo4j are stopped: the states, the net start commands and
        # the status bar saying the check did not pass.
        checking = new_window(app, settings_path, CONFIG, DBMS_WINDOWS)
        checking.options_panel.dry_run_box.setChecked(False)
        app.processEvents()
        assert checking.console_panel.check_button.isEnabled(), "the check must be offered"
        checking.on_check()
        pump_until_idle(app, checking)
        assert "Verificação não passou" in checking.status_label.text()
        grab(checking, "figure16-gui-verificacao.png")
        checking.hide()
```

(g) Docstring do módulo: "four GUI figures" vira "five GUI figures". Acrescente um parágrafo:

"Figure 16 is a real `--check-dbms` run from the "Verificar SGBDs" button, with the example stack up except MongoDB and Neo4j (`docker compose stop mongodb neo4j`); the script refuses to run otherwise."

- [ ] **Step 4: Capturar as figuras**

Run: `$PY scripts/capture_gui_figures.py`
Expected: imprime as cinco figuras com os status. A 16 deve dizer "Verificação não passou — veja o console". Abra cada PNG e confira:
- o botão "Verificar SGBDs" aparece nas cinco;
- na 16, a tabela e as duas linhas `net start` estão legíveis;
- as bordas da tabela estão alinhadas (`box.SQUARE`).

- [ ] **Step 5: Subseção "Verificação dos SGBDs"**

Em `chapters/ch4proposta.tex`, imediatamente antes de `\subsection{O Cenário de Exemplo e os Arquivos de Dados}`, insira o texto abaixo. Preencha a Tabela e a Listagem **com o conteúdo de `$SCRATCH/check.txt`**: os endereços, os estados e as linhas de dica, na ordem em que aparecem.

```latex
\subsection{Verificação dos SGBDs}
\label{sec:verificacao-sgbds}

Antes de ler as fontes, toda importação real verifica se os SGBDs de destino --- os
presentes no arquivo de importação, filtrados por \texttt{-{}-only} --- respondem. A
verificação abre uma conexão TCP com cada endereço declarado no arquivo de conexão e a
fecha em seguida, sem autenticar. As sondas correm em paralelo, com limite de dois
segundos cada, de modo que o tempo total não cresce com o número de SGBDs. Cada SGBD
termina em um de três estados: \textbf{no ar}, quando algum de seus endereços responde
(no Cassandra, basta um nó); \textbf{fora do ar}, quando nenhum responde; e
\textbf{conexão inválida}, quando o próprio \textit{driver} rejeita a configuração, como
em uma URI com esquema desconhecido. Um único SGBD fora do ar ou com conexão inválida
\textbf{interrompe} a execução antes da leitura dos CSVs, o que evita uma carga parcial:
sem a verificação, os SGBDs anteriores na ordem de importação receberiam dados antes que
a falha do seguinte fosse descoberta.

Os endereços não são extraídos por um analisador próprio. Para o MongoDB e o Neo4j,
cuja conexão é descrita por uma URI, a ferramenta constrói o cliente do próprio
\textit{driver} sem conectar e obtém dele os endereços; assim, uma URI aceita pelo
\textit{driver} nunca é recusada pela verificação, e uma recusada nunca passa. Para o
PostgreSQL, seguem-se as regras da biblioteca cliente \texttt{libpq}, inclusive listas
de hosts e \textit{sockets} Unix.

Quando algum SGBD não responde, a ferramenta mostra, abaixo da tabela de estados, o
que fazer: para cada descritor \texttt{command}, o próprio comando; para os descritores
\texttt{compose} de um mesmo arquivo, um único \texttt{docker compose up}; e, para um
SGBD sem \texttt{start}, uma orientação genérica. A opção \texttt{-{}-check-dbms}
executa apenas essa etapa e encerra, com código de saída zero quando todos os SGBDs
respondem. A Tabela~\ref{tab:check-dbms} e a Listagem~\ref{lst:check-dbms} reproduzem
uma verificação feita com o arquivo de conexão de exemplo para Windows, com o MongoDB e
o Neo4j fora do ar.

\begin{table}[H]
  \caption{Estados reportados por \texttt{-{}-check-dbms} com dois SGBDs fora do ar.}
  \label{tab:check-dbms}
  \centering
  \begin{tabular}{l l l}
    \toprule
    SGBD & Endereço & Estado \\
    \midrule
    postgres  & 127.0.0.1:5432  & up   \\
    mongodb   & 127.0.0.1:27017 & down \\
    cassandra & 127.0.0.1:9042  & up   \\
    redis     & 127.0.0.1:6379  & up   \\
    neo4j     & 127.0.0.1:7687  & down \\
    \bottomrule
  \end{tabular}
  \par\vspace{4pt}
  {\footnotesize Fonte: Elaborado pelo autor (2026).}
\end{table}

Abaixo da tabela, a ferramenta lista os comandos que iniciam os dois SGBDs fora do ar,
retirados dos descritores \texttt{start} do arquivo de conexão:

\begin{lstlisting}[style=textstyle,caption={Comandos de inicialização mostrados por \texttt{-{}-check-dbms}.},label={lst:check-dbms}]
To start the DBMS that are down, run in a terminal:
  net start MongoDB
  net start neo4j
Service commands (net start, systemctl) may need an administrator terminal or sudo.
\end{lstlisting}
```

A tabela e a listagem acima trazem o conteúdo **esperado**. Se `$SCRATCH/check.txt` divergir, vale o arquivo.

- [ ] **Step 6: Seção da interface gráfica**

Em `chapters/ch4proposta.tex`, seção `sec:interface-grafica`:

(a) Troque `governada por doze opções` por `governada por treze opções`.

(b) Troque `falha de conexão com um SGBD, aparecem no console exatamente como apareceriam no terminal` por `falha de gravação em um SGBD, aparecem no console exatamente como apareceriam no terminal`.

(c) Depois do bloco `\begin{figure}…\label{fig:gui-erro}…\end{figure}` e antes do parágrafo "Uma limitação de escopo", insira:

```latex
A disponibilidade dos SGBDs, que a validação prévia deliberadamente não examina, tem um
botão próprio: \textbf{Verificar SGBDs}, ao lado do botão de execução. Ele executa a CLI
com \texttt{-{}-check-dbms}, com os arquivos de configuração e a seleção de SGBDs do
formulário, e depende apenas de que esses dois arquivos sejam válidos --- pendências nas
fontes CSV não o bloqueiam, porque a verificação não lê dados. A saída é a mesma do
terminal, inclusive os comandos que iniciam cada SGBD fora do ar, que o usuário copia
para um terminal: o console integrado executa somente a própria ferramenta. A
Figura~\ref{fig:gui-verificacao} mostra uma verificação com dois SGBDs fora do ar.

\begin{figure}[H]
  \centering
  \includegraphics[width=0.95\textwidth]{images/figure16-gui-verificacao}
  \caption{Verificação dos SGBDs pela interface gráfica: MongoDB e Neo4j fora do ar e,
  abaixo da tabela de estados, os comandos que os iniciam.}
  \label{fig:gui-verificacao}
  \par\vspace{4pt}
  {\footnotesize Fonte: Elaborado pelo autor (2026).}
\end{figure}
```

- [ ] **Step 7: Compilar e gerar a v2.2**

```bash
cd docs-tcc && latexmk -pdf -interaction=nonstopmode main.tex && cp main.pdf TCC2-PolyglotImportCSV-Report-v2.2.pdf; cd ..
```

Expected: nenhuma referência indefinida (`grep -n "undefined" docs-tcc/main.log` vazio). Abra no PDF:
- a lista de siglas, com DBMS;
- as subseções novas;
- a Tabela `tab:check-dbms`;
- as figuras 9, 11 e 16;
- a seção da GUI.

Anote o número de páginas. **Não apague a v2.1**: o destino dela é decisão do autor.

- [ ] **Step 8: Religar os SGBDs**

```bash
docker compose start mongodb neo4j
```

- [ ] **Step 9: Suíte, commit e push**

```bash
$PY -m pytest tests -q -p no:cacheprovider
git add -A scripts/capture_gui_figures.py docs-tcc
git commit -m "docs(tcc): verificacao dos SGBDs, figura 16 e relatorio v2.2

A secao 4.3 ganha a subsecao sobre a verificacao, com estados e comandos de
uma execucao real com MongoDB e Neo4j fora do ar; a secao 4.6 apresenta o
botao Verificar SGBDs (figura 16). Figuras 12 a 15 recapturadas com o botao
novo.

Co-Authored-By: Claude <modelo> <noreply@anthropic.com>"
git push
```

---

### Task 12: Versão 1.1.0 e notas da release (sem tag)

**Files:**
- Modify: `pyproject.toml`, `src/polyglotimportcsv/__init__.py`
- Test: `tests/test_version.py`
- Create: `docs/releases/v1.1.0.md`

**Interfaces:**
- Consumes: tudo o que veio antes.
- Produces: pacote em 1.1.0 e `docs/releases/v1.1.0.md`, que o workflow publica como corpo da release (`body_path: docs/releases/${{ github.ref_name }}.md`).

- [ ] **Step 1: Teste que falha**

Em `tests/test_version.py`, troque o último teste por:

```python
def test_the_delivered_version_is_1_1_0():
    assert polyglotimportcsv.__version__ == "1.1.0"
```

Run: `$PY -m pytest tests/test_version.py -q -p no:cacheprovider`
Expected: FAIL (`'1.0.0' == '1.1.0'`).

- [ ] **Step 2: Versão**

`pyproject.toml`: `version = "1.1.0"`. `src/polyglotimportcsv/__init__.py`: `__version__ = "1.1.0"`.

Run: `$PY -m pytest tests/test_version.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 3: `docs/releases/v1.1.0.md`**

Os tamanhos dos zips ficam como na v1.0.0, com "≈". O autor confere depois do build.

````markdown
**Language / Idioma / Língua:** [English](#english) · [Português (BR)](#português-br)

## English

**PolyglotImportCSV 1.1.0** checks the target DBMS before importing and tells
you how to start the ones that are down.

### Highlights

- **DBMS check before every real import:** each target DBMS is probed over TCP
  before any CSV is read; if one is down or its connection setting is invalid,
  the run stops without writing anything.
- **`--check-dbms`** runs only the check and exits (0 when all are up). In the
  GUI, the **Verificar SGBDs** button does the same.
- **How to start them:** an optional `start` block per DBMS in the connection
  file — a command for a DBMS installed on the machine, or a Docker Compose
  service. The tool shows it, ready to copy into a terminal; it never runs it.
- **Examples without Docker:** `data/ecommerce/dbms_config_windows.json` and
  `dbms_config_linux.json`, next to the Docker one.
- **Bilingual READMEs**, including the one inside each package (`README.md`,
  which replaces `LEIAME.txt`).

### Breaking change

The connection file and its option were renamed, with no aliases:

| 1.0.0 | 1.1.0 |
|---|---|
| `sgbd_config.json` | `dbms_config.json` |
| `--sgbd-config` | `--dbms-config` |

Rename your file (or pass `--dbms-config`), and update scripts that use the old option.

### Downloads

| File | Contents |
|---|---|
| `polyglotimportcsv-gui-v1.1.0-windows-x64.zip` | GUI for Windows |
| `polyglotimportcsv-v1.1.0-windows-x64.zip` | CLI for Windows |
| `polyglotimportcsv-gui-v1.1.0-linux-x64.zip` | GUI for Linux |
| `polyglotimportcsv-v1.1.0-linux-x64.zip` | CLI for Linux |

Every package carries the e-commerce example, `docker-compose.yml` and a
`README.md` with the first steps. No Python installation is needed.

## Português (BR)

O **PolyglotImportCSV 1.1.0** verifica os SGBDs de destino antes de importar e
diz como subir os que estiverem fora do ar.

### Destaques

- **Verificação dos SGBDs antes de toda importação real:** cada SGBD de destino
  é sondado por TCP antes da leitura de qualquer CSV; se algum estiver fora do
  ar ou com a conexão inválida, a execução para sem gravar nada.
- **`--check-dbms`** faz só a verificação e sai (código 0 quando todos
  respondem). Na interface gráfica, o botão **Verificar SGBDs** faz o mesmo.
- **Como subi-los:** um bloco `start` opcional por SGBD no arquivo de conexão —
  um comando, para um SGBD instalado na máquina, ou um serviço do Docker
  Compose. A ferramenta o mostra, pronto para copiar para um terminal; nunca o
  executa.
- **Exemplos sem Docker:** `data/ecommerce/dbms_config_windows.json` e
  `dbms_config_linux.json`, ao lado do arquivo para Docker.
- **READMEs bilíngues**, inclusive o que vai em cada pacote (`README.md`, no
  lugar do `LEIAME.txt`).

### Mudança incompatível

O arquivo de conexão e a sua opção mudaram de nome, sem aliases:

| 1.0.0 | 1.1.0 |
|---|---|
| `sgbd_config.json` | `dbms_config.json` |
| `--sgbd-config` | `--dbms-config` |

Renomeie o seu arquivo (ou use `--dbms-config`) e atualize os scripts que usam a opção antiga.

### Downloads

| Arquivo | Conteúdo |
|---|---|
| `polyglotimportcsv-gui-v1.1.0-windows-x64.zip` | Interface gráfica para Windows |
| `polyglotimportcsv-v1.1.0-windows-x64.zip` | Linha de comando para Windows |
| `polyglotimportcsv-gui-v1.1.0-linux-x64.zip` | Interface gráfica para Linux |
| `polyglotimportcsv-v1.1.0-linux-x64.zip` | Linha de comando para Linux |

Todos os pacotes trazem o cenário de exemplo de e-commerce, o
`docker-compose.yml` e um `README.md` com os primeiros passos. Não é preciso
instalar Python.
````

- [ ] **Step 4: Suíte completa, commit e push**

```bash
$PY -m pytest tests -q -p no:cacheprovider
git add -A
git commit -m "chore(release): versao 1.1.0 e notas bilingues

Co-Authored-By: Claude <modelo> <noreply@anthropic.com>"
git push
```

Expected da suíte: verde, com a contagem somando todos os testes novos das Tarefas 2 a 9.

- [ ] **Step 5: Parar e perguntar**

**Não** faça merge em `main`, **não** crie o tag `v1.1.0` e **não** apague a v2.1 do relatório. Relate ao autor:
- a contagem da suíte;
- o número de páginas do relatório v2.2;
- as cinco figuras regeneradas.

Depois pergunte:
1. se pode fazer o merge `--no-ff` de `dbms-check` em `main`;
2. se pode criar e enviar o tag `v1.1.0`, o que dispara a publicação da release;
3. o que fazer com `TCC2-PolyglotImportCSV-Report-v2.1.pdf`.
````
