# Design — Verificação dos SGBDs, troca de nome SGBD → DBMS e READMEs bilíngues

Data: 2026-09-27
Status: aprovado em brainstorming; aguardando revisão do autor.
Branch: `dbms-check`, a partir de `main` (v1.0.0 já publicada).

## 0. Motivação

O orientador não usa Docker: roda os SGBDs instalados na própria máquina e
usa as releases. Hoje, quando um SGBD está desligado, a importação só descobre
isso ao chegar a vez dele, depois de outros SGBDs já terem recebido dados, e a
mensagem é o erro cru do driver. Este trabalho faz a ferramenta **verificar**
os SGBDs de destino antes de gravar qualquer coisa e **explicar como subi-los**,
com o comando pronto para copiar e colar num terminal. A ferramenta nunca
executa esse comando.

Aproveitando a mudança no arquivo de conexão, o termo "SGBD" sai de tudo o que
não é texto em português: identificadores, nomes de arquivo, opções da CLI,
chaves de esquema e mensagens da CLI (em inglês) passam a usar "DBMS".

## 1. Resumo das decisões

| # | Tema | Decisão |
|---|---|---|
| 1 | Subir SGBDs | A ferramenta só **diagnostica e mostra o comando**; nunca executa. |
| 2 | Onde fica o comando | Bloco opcional `start` por SGBD no arquivo de conexão: `{"command": …}` (sem Docker) **ou** `{"compose": {"file", "service"}}` (com Docker). O `docker-compose.yml` **não** é lido como configuração. |
| 3 | Quando verifica | Em toda importação real (não em `--dry-run`), entre "Load config" e "Load sources"; aborta antes de gravar se algum SGBD estiver fora. |
| 4 | Só verificar | Nova opção `--check-dbms`: verifica, mostra o diagnóstico e sai (0 = todos no ar, 1 = algum fora). |
| 5 | GUI | Botão "Verificar SGBDs"; o diagnóstico aparece no console integrado. O console **não** passa a executar comandos arbitrários: o usuário copia o comando para um terminal. |
| 6 | Nomes | `sgbd_config.json` → `dbms_config.json`, `sgbd_config.schema.json` → `dbms_config.schema.json`, `--sgbd-config` → `--dbms-config`. **Troca limpa**, sem aliases para os nomes antigos. |
| 7 | Onde "SGBD" continua | Textos em português: GUI, seções pt dos READMEs e o texto do relatório. O relatório ganha "DBMS" na lista de siglas. |
| 8 | Exemplos | `dbms_config.json` (Docker), `dbms_config_windows.json` e `dbms_config_linux.json` (sem Docker). |
| 9 | READMEs | Todos bilíngues (EN e PT), com o seletor padrão no topo. O `LEIAME.txt` da release vira `README.md`. |
| 10 | Release | v1.1.0, com notas bilíngues que avisam da mudança incompatível. Tag e push só com confirmação do autor no momento. |

## 2. Fases

A execução segue três fases, cada uma deixando a suíte verde:

1. **Troca de nome SGBD → DBMS** (seção 3). Não muda nenhum comportamento.
2. **Verificação dos SGBDs** (seções 4 a 7). Os textos novos já nascem bilíngues.
3. **READMEs bilíngues** (seção 8).

O relatório (seção 9) e a release (seção 10) vêm depois das três fases, porque
descrevem e empacotam o resultado final.

## 3. Fase 1 — Troca de nome SGBD → DBMS

### 3.1 Regra

Usa **DBMS**: nomes de arquivo, identificadores Python, opções da CLI, chaves e
textos (em inglês) dos JSON Schemas, mensagens da CLI (em inglês), comentários e
docstrings em inglês e as seções EN dos READMEs.

Continua **SGBD**: textos em português visíveis ao usuário (rótulos, mensagens e
dicas da GUI; seções PT dos READMEs) e o texto corrido do relatório.

### 3.2 O que muda

| Antes | Depois |
|---|---|
| `data/ecommerce/sgbd_config.json` | `data/ecommerce/dbms_config.json` |
| `schemas/sgbd_config.schema.json` (`$id`, `title`, `description`) | `schemas/dbms_config.schema.json`, com `title` "PolyglotImportCSV DBMS connection configuration" e descrição em termos de DBMS |
| `--sgbd-config` | `--dbms-config` (padrão: `dbms_config.json` ao lado de `--config`) |
| `DEFAULT_SGBD_CONFIG_NAME` | `DEFAULT_DBMS_CONFIG_NAME` |
| `load_sgbd_config`, `validate_sgbd_config` | `load_dbms_config`, `validate_dbms_config` |
| parâmetros `sgbd_config_path`, `sgbd_cfg`, `sgbd_path` | `dbms_config_path`, `dbms_cfg`, `dbms_path` |
| `RunOptions.sgbd_config_path`, chave de erro `"sgbd_config_path"`, `ConfigPanel.sgbd_config_path()` | `dbms_config_path` em todos |
| `preflight._check_sgbd` | `preflight._check_dbms` |
| mensagens em inglês "SGBD config…" | "DBMS config…" |
| menções em `import_config.schema.json`, `business_exception.py`, `__init__.py` | termos em DBMS |

Arquivos atingidos: `config_parser`, `runner`, `cli`, `benchmark_runner`,
`gui/{state,command,preflight}`, `gui/widgets/{config_panel,main_window,options_panel}`,
os testes correspondentes, `run_example.sh` e `scripts/run_example.completion.bash`,
`scripts/{inspect_persisted_data,run_benchmarks,benchmark_tracemalloc_ab,capture_gui_figures}.py`,
`README.md`, `docs/ARCHITECTURE.md`, `data/ecommerce/README.md` e `packaging/LEIAME.txt`
(este depois vira `README.md`; ver seção 8).

**Não mudam**, por serem registros históricos: `docs/superpowers/` (specs e
planos anteriores), `benchmarks/` (resultados gravados), `docs/releases/v1.0.0.md`,
`docs-tcc/revisao-gaps-tcc-codigo-2026-07-01.md` e os PDFs antigos do relatório.

### 3.3 Critério de aceite

- Suíte completa verde com o Python do venv (`./.venv/Scripts/python.exe -m pytest tests -q`).
- `git grep -i sgbd`, fora dos registros históricos da seção 3.2 e de `docs-tcc/`,
  só encontra textos em português (strings da GUI e seções PT dos READMEs).
- `polyglotimportcsv --config data/ecommerce/import_config.json --dry-run` funciona
  sem `--dbms-config` (encontra `dbms_config.json` ao lado).

## 4. Fase 2 — Esquema: bloco `start`

Em `dbms_config.schema.json`:

```json
"$defs": {
  "start": {
    "description": "How to start this DBMS when it is not responding. Shown to the user, never executed.",
    "oneOf": [
      {
        "type": "object",
        "properties": { "command": { "type": "string", "minLength": 1 } },
        "required": ["command"],
        "additionalProperties": false
      },
      {
        "type": "object",
        "properties": {
          "compose": {
            "type": "object",
            "properties": {
              "file": { "type": "string", "minLength": 1 },
              "service": { "type": "string", "minLength": 1 }
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
}
```

Cada uma das cinco definições de conexão (`postgresConnection` … `neo4jConnection`)
ganha `"start": { "$ref": "#/$defs/start" }` em `properties`. `version` continua
`1`, porque o campo é opcional e os arquivos atuais continuam válidos.

`compose.file` relativo é resolvido a partir da pasta do arquivo de conexão.
O `merge_configs` não copia `start` para a configuração mesclada: os importadores
não o usam.

## 5. Fase 2 — Módulo `dbms_check.py`

Módulo novo, sem dependência de drivers além do `pymongo.uri_parser` (o pymongo
já é dependência). Não imprime nada: devolve dados, e quem chama apresenta.

### 5.1 Endereços

`endpoints(dbms, entry) -> List[Tuple[str, int]]` lê `entry["connection"]` com os
**mesmos padrões dos importadores**:

| DBMS | Origem | Padrões |
|---|---|---|
| postgres | `host`, `port` | `127.0.0.1`, `5432` |
| redis | `host`, `port` | `127.0.0.1`, `6379` |
| cassandra | `hosts` × `port` | `["127.0.0.1"]`, `9042` |
| neo4j | `uri` via `urllib.parse` | `bolt://127.0.0.1:7687`; porta ausente → `7687` |
| mongodb | `uri` via `pymongo.uri_parser.parse_uri` (`nodelist`) | `mongodb://127.0.0.1:27017` |

Uma URI `mongodb+srv://` é resolvida pelo próprio `parse_uri`, que consulta o
registro SRV por DNS (o `dnspython` já vem com o pymongo) e devolve os nós reais,
que são sondados como os demais.

Quando não é possível obter endereços — URI que não se deixa analisar (porta não
numérica, esquema desconhecido no Neo4j, host ausente) ou falha de DNS numa
`+srv` —, `endpoints` lança `InvalidConnectionError` com a mensagem original. Uma
conexão que não se consegue nem interpretar também não vai conectar na
importação, então isso é um erro de configuração e **bloqueia** a execução
(estado `invalid`, seção 5.3).

### 5.2 Sonda

`probe(host, port, timeout=2.0) -> bool`: `socket.create_connection` seguido de
fechamento; qualquer `OSError` é `False`. Todas as sondas de uma verificação
rodam em paralelo (`ThreadPoolExecutor`): no Windows, conectar a uma porta
fechada de `127.0.0.1` demora cerca de 2 s por causa das retentativas do TCP, o
que em série daria cerca de 10 s com cinco SGBDs fora.

### 5.3 Estado por DBMS

- `up`: pelo menos um endereço responde. No Cassandra, basta um nó, como no driver.
- `down`: nenhum responde. Bloqueia; a dica é o comando de `start`.
- `invalid`: `endpoints` lançou `InvalidConnectionError`. Bloqueia; a dica é
  `<dbms>: invalid connection (<mensagem original>). Fix "connection" for it in dbms_config.json`.
  Não há sonda nem dica de `start` para esse DBMS.

### 5.4 Dicas de inicialização

`start_hints(down, dbms_cfg, dbms_config_dir) -> List[str]`, na ordem de `BACKENDS`:

- `command`: o texto literal.
- `compose`: SGBDs com o **mesmo arquivo** (caminho absoluto resolvido) viram um
  único comando, `docker compose -f "<caminho absoluto>" up -d --wait <serviço> [<serviço> …]`.
- sem `start`: `<dbms>: start the DBMS service, or declare "start" for it in dbms_config.json`.

### 5.5 Entrada

```python
@dataclass(frozen=True)
class DbmsStatus:
    dbms: str
    endpoints: List[Tuple[str, int]]
    state: str  # "up" | "down" | "invalid"
    error: str = ""  # mensagem original quando "invalid"

@dataclass(frozen=True)
class DbmsCheckReport:
    statuses: List[DbmsStatus]
    hints: List[str]  # correções de "invalid" primeiro, depois os comandos de start
    @property
    def ok(self) -> bool: ...  # todos "up"

def check_dbms(targets, dbms_cfg, dbms_config_dir, probe=probe) -> DbmsCheckReport
```

`targets` são os DBMS que a importação usaria: os presentes no import config,
filtrados por `--only`, na ordem de `BACKENDS`.

## 6. Fase 2 — CLI e runner

### 6.1 `--check-dbms`

- Não combina com `--dry-run` nem com `--benchmark` (`click.UsageError`). As
  outras opções, exceto `--only`, são aceitas e não afetam a verificação.
- `--config` continua obrigatório: ele define os alvos.
- Fluxo: banner `mode: check` → `step("Load config")` (valida os dois arquivos e
  o cruzamento, como hoje) → `step("Check DBMS")` → tabela e dicas.
- Saída do processo: `0` se `report.ok` (todos `up`); `1` caso contrário.
- Entrada no runner: `run_check(config_path, *, dbms_config_path, only, probe=...)`,
  chamada pela CLI no lugar de `run_import`.

### 6.2 Importação real

Em `_run_stream` e em `_run` (este apenas quando não é `dry_run`), logo depois de
"Load config" e antes de "Load sources":

- `step("Check DBMS")` e mostra a tabela.
- Se `report.ok` for falso, lança `DbmsUnavailableError` (subclasse de
  `BusinessException`, em `business_exception.py`), cuja mensagem lista os DBMS
  fora do ar ou com conexão inválida e as dicas. A CLI já converte `BusinessException` em mensagem e
  saída `1`. Nenhum CSV é lido e nada é gravado.

Para localizar o arquivo de conexão (pasta usada em `compose.file`), o runner usa
o mesmo caminho padrão do `load_config`.

### 6.3 Apresentação

Em inglês, como o resto da CLI, com `box.SQUARE` (a fonte da GUI não tem os
caracteres de borda pesada; mesmo motivo do `metrics_table`):

```
Check DBMS
  ┌───────────┬─────────────────┬────────┐
  │ DBMS      │ Endpoint        │ Status │
  │ postgres  │ 127.0.0.1:5432  │ up     │
  │ mongodb   │ 127.0.0.1:27017 │ down   │
  │ cassandra │ 127.0.0.1:9042  │ down   │
  └───────────┴─────────────────┴────────┘
To start the DBMS that are down, run in a terminal:
  docker compose -f "D:\…\docker-compose.yml" up -d --wait mongodb cassandra
Service commands (net start, systemctl) may need an administrator terminal or sudo.
```

A última linha só aparece quando alguma dica é um `command`. No Cassandra com
vários nós, a coluna Endpoint lista todos, separados por vírgula. Um DBMS
`invalid` aparece com Endpoint `—` e Status `invalid`, e sua correção vem antes
dos comandos de start, sob "Fix the connection settings in dbms_config.json:".

### 6.4 Testes

- Um fixture `autouse` em `tests/conftest.py` troca `dbms_check.probe` por
  "sempre no ar", para que os testes existentes do runner, com importadores e
  sinks falsos, não abram sockets. Os testes da verificação sobrescrevem esse fixture.
- `test_dbms_check.py`: padrões e URIs de `endpoints` (incluindo Mongo com vários
  hosts, `+srv` com a resolução DNS simulada, Neo4j sem porta); `invalid` para
  porta não numérica, esquema Neo4j desconhecido e falha de DNS numa `+srv`,
  bloqueando o `ok` e sem sonda; agrupamento das dicas `compose` por arquivo; caminho relativo resolvido; SGBD sem `start`; sonda real contra um
  `socket` local aberto e contra uma porta fechada.
- Esquema: `command` válido; `compose` válido; os dois juntos são inválidos;
  campo extra é inválido; `command` vazio é inválido.
- CLI e runner: `--check-dbms` sai com 0 e 1; é incompatível com `--dry-run` e
  `--benchmark`; respeita `--only`; a importação aborta com `DbmsUnavailableError`
  antes de ler as fontes (o registro de importadores falso não é chamado);
  `--dry-run` não verifica.

## 7. Fase 2 — GUI

### 7.1 Núcleo puro (sem PySide6)

`command.build_check_argv(options)` devolve
`--config … [--dbms-config …] [--only …] --check-dbms --log-level …`.

`Preflight` ganha `checkable: bool`, verdadeiro quando o import config passou no
seu esquema e o arquivo de conexão foi lido, validado e cruzado com ele sem erro.
Não dá para usar as chaves de erro para isso: sem fontes sobrescritas, erros de
cabeçalho de CSV também caem em `config_path` (`preflight._check_headers`).

### 7.2 `ConsolePanel`

- Botão "Verificar SGBDs" entre "Copiar" e "▶ Executar", com o sinal `check_requested`.
- Desabilitado durante qualquer execução, no modo de edição (ali o texto digitado
  manda; quem quiser verificar digita `--check-dbms`) e quando `set_check_enabled(False)`.

### 7.3 `MainWindow`

- `refresh_command` habilita o botão quando `checked.checkable` e `validate()` não
  acusa erro em `config_path`, `dbms_config_path` nem `only`. Erros de fontes ou
  de CSV **não** bloqueiam.
- `on_check` reaproveita o caminho do `on_run`: limpa o console, entra no estado
  em execução e inicia o processo com `launcher.resolve() + build_check_argv(...)`.
  A primeira linha do console mostra o comando completo da verificação.
- Interromper uma verificação não pede confirmação: não há dados para ficarem pela metade.
- Mensagem de status ao terminar: código 0 → "Todos os SGBDs estão respondendo";
  código 1 → "Há SGBDs fora do ar — veja o console". A importação mantém suas
  mensagens atuais.

### 7.4 Testes

`build_check_argv`; `checkable` (erro de CSV → verdadeiro; esquema inválido ou
arquivo de conexão ausente → falso); habilitação do botão (ocioso, em execução,
edição, só erro de fontes, erro de configuração); `on_check` iniciando o processo
certo com `tests/gui_fake_cli.py`; mensagens de status para 0 e 1; stop sem
confirmação durante a verificação.

## 8. Fase 3 — READMEs bilíngues

Todo README tem, no topo, o seletor que o `README.md` já usa:

```markdown
**Language / Idioma / Língua:** [English](#english) · [Português (BR)](#português-br)
```

seguido de uma seção `## English` e uma `## Português (BR)` com o mesmo conteúdo.

| Arquivo | Ação |
|---|---|
| `README.md` | já segue o padrão; recebe `--dbms-config`, `--check-dbms` e o bloco `start` nas duas seções |
| `docs/ARCHITECTURE.md` | troca o seletor atual pelo padrão; ganha `dbms_check.py` na tabela de camadas |
| `data/ecommerce/README.md` | ganha a seção PT; explica os três `dbms_config*.json` e avisa que os nomes de serviço variam por instalação |
| `data/benchmark/README.md`, `benchmarks/README.md` | ganham a seção PT |
| `packaging/LEIAME.txt` | vira `packaging/README.md` bilíngue (texto puro não tem hyperlink); `scripts/package_release.py` e seu teste passam a empacotar `README.md` |
| `docs/releases/v1.1.0.md` | nasce bilíngue |

## 9. Relatório (`docs-tcc/`)

Preferências do orientador valem: legenda abaixo da figura, frase de introdução
antes de cada listagem, nenhuma prosa de histórico de versões ("antes era…").

- **Siglas** (`main.tex`): `\item[DBMS] \textit{Database Management System} (Sistema de Gerenciamento de Banco de Dados)`.
- **Troca de nome**: `sgbd\_config*` e `--sgbd-config` viram `dbms\_config*` e
  `--dbms-config` nos caps. 4 e 6 e nos dois apêndices. O texto corrido continua
  dizendo "SGBD". O apêndice de configuração mostra o `dbms_config.json` com os
  blocos `start`; o de esquemas mostra o esquema novo.
- **Figuras (Mermaid, `scripts/gerar-diagramas.sh`)**: 7 e 10 com o nome novo;
  9 com o bloco `start`, renomeada `figure9-dbms-schema`; 11 com o passo
  "Verificar SGBDs" entre carregar a configuração e carregar as fontes.
- **Texto novo no cap. 4**:
  - §4.2, subseção "Inicialização dos SGBDs": o bloco `start`, com trecho do
    `dbms_config_windows.json`.
  - §4.3, subseção "Verificação dos SGBDs": sonda TCP antes de qualquer escrita,
    aborto antes da carga, `--check-dbms` e um exemplo de saída.
  - §4.6: parágrafo sobre o botão "Verificar SGBDs" e a **figura 16**.
- **Figuras da GUI**: 12 a 15 recapturadas (o botão novo aparece); a 16 mostra a
  GUI depois de uma verificação real com um SGBD propositalmente fora do ar.
  `scripts/capture_gui_figures.py` ganha esse cenário.
- **PDF**: `TCC2-PolyglotImportCSV-Report-v2.2.pdf`. O destino da v2.1 é decidido
  pelo autor no momento.

## 10. Exemplos e release

### 10.1 `data/ecommerce/`

Os três arquivos têm as mesmas conexões de hoje; muda só o `start`:

| SGBD | `dbms_config.json` | `dbms_config_windows.json` | `dbms_config_linux.json` |
|---|---|---|---|
| postgres | compose `postgres` | `net start postgresql-x64-16` | `sudo systemctl start postgresql` |
| mongodb | compose `mongodb` | `net start MongoDB` | `sudo systemctl start mongod` |
| cassandra | compose `cassandra` | compose `cassandra` (não roda nativamente no Windows) | `sudo systemctl start cassandra` |
| redis | compose `redis` | `net start Memurai` (substituto compatível; o Redis não tem versão oficial para Windows) | `sudo systemctl start redis-server` |
| neo4j | compose `neo4j` | `net start neo4j` (serviço criado por `neo4j windows-service install`) | `sudo systemctl start neo4j` |

O `file` do compose é `../../docker-compose.yml`. O `run_example.sh` continua
com a própria espera pelo Docker; só troca o nome do arquivo e da opção.

### 10.2 Release v1.1.0

- Versão 1.1.0 no pacote (`test_version` cobre).
- `package_release.py` empacota os três `dbms_config*.json` e o `README.md` bilíngue.
- `docs/releases/v1.1.0.md` bilíngue, com a mudança incompatível em destaque:
  `--sgbd-config` → `--dbms-config`, `sgbd_config.json` → `dbms_config.json`.
- Tag e push do tag **somente com confirmação do autor no momento**.

## 11. Fora do escopo

- Subir SGBDs automaticamente ou executar o comando de `start`.
- A GUI executar comandos que não sejam da própria ferramenta.
- Detectar serviços instalados ou gerenciadores de serviço.
- Ler o `docker-compose.yml` como configuração de conexão.
- Aliases para `--sgbd-config` e `sgbd_config.json`.
- Verificar credenciais: a sonda é TCP; erro de senha continua vindo do importador.
- i18n da GUI (trabalho futuro: GUI bilíngue, PT para o meio acadêmico e EN para portfólio).
