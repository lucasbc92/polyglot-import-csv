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
