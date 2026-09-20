# Design — TCC2: interface gráfica do PolyglotImportCSV

Data: 2026-09-20
Status: aprovado em brainstorming; aguardando revisão final do autor.

Especifica a interface gráfica prevista no plano de trabalho ratificado de TCC2
(implementação em outubro). A GUI é um **invólucro fino sobre a CLI existente**:
não reimplementa nenhuma etapa da importação e não altera código de
`src/polyglotimportcsv/` fora do novo pacote `gui/`.

Protótipo de alta fidelidade que serviu de base:
<https://www.figma.com/design/TM69VaXUwySeeUDdOBMmL5> — página *GUI — Telas*,
quadros `01 · Ocioso`, `02 · Executando`, `03 · Sucesso`, `04 · Erro`.

## 1. Contexto e objetivo

A CLI atual (`src/polyglotimportcsv/cli.py`) expõe onze opções que precisam ser
digitadas corretamente a cada execução, e o erro de uma flag mal formada só
aparece depois que o comando roda. Para a demonstração do TCC2 e para o uso por
quem não conhece a sintaxe, a GUI oferece:

1. **Montagem assistida do comando** — cada flag vira um controle gráfico, e o
   comando resultante fica visível o tempo todo.
2. **Execução e acompanhamento** — o comando é executado e a saída da CLI
   (logs, tabelas e barras de progresso do `rich`) aparece em um console
   integrado, com estado final explícito.

O valor didático está justamente em manter o comando à vista: a GUI ensina a
CLI em vez de escondê-la.

## 2. Escopo

### 2.1 Dentro do escopo

- Seleção dos dois arquivos JSON de configuração por *file chooser*.
- Um controle para cada opção da CLI: `--config`, `--sgbd-config`, `--only`,
  `--strategy`, `--execution`, `--dry-run`, `--create-schema/--no-create-schema`,
  `--benchmark`, `--log-level`, `--show-data/--no-data` e `--source NOME=CAMINHO`
  (repetível).
- Painel de CLI integrado, **somente leitura por padrão**, exibindo o comando
  montado.
- **Modo de edição**: o comando vira editável e o formulário é bloqueado.
- Execução do comando, com log em tempo real, interrupção e estado final.
- Persistência de conveniências entre sessões (geometria, últimos caminhos).

### 2.2 Fora do escopo (decidido explicitamente)

- **Visualizar ou editar os arquivos JSON de configuração.** Continuam sendo
  editados em qualquer editor de texto externo. Isto restringe a formulação mais
  ampla que constava do plano de ratificação.
- Pré-visualização de CSV, editor de mapeamento coluna a coluna, assistente de
  criação de configuração.
- Visualização de métricas em gráficos dentro da GUI — os benchmarks continuam
  sendo conduzidos pelos scripts de `scripts/`.
- Qualquer interface web ou multiusuário.

Uma GUI mais ambiciosa permanece registrada como Atividade Futura.

## 3. Arquitetura

### 3.1 Separação entre núcleo puro e camada Qt

O pacote novo é `src/polyglotimportcsv/gui/`, organizado em duas camadas. A
regra de dependência é unidirecional: **os módulos do núcleo não importam
PySide6**, o que os torna testáveis sem instanciar `QApplication`.

```
src/polyglotimportcsv/gui/
    __init__.py
    app.py                # ponto de entrada: QApplication + MainWindow
    state.py              # RunOptions (dataclass) + validação
    command.py            # RunOptions -> argv; argv -> texto exibido
    launcher.py           # resolução do executável e do ambiente do filho
    ansi.py               # tradutor de sequências ANSI para HTML
    process.py            # ImportProcess: QObject sobre QProcess
    widgets/
        __init__.py
        main_window.py    # janela, divisor, barra de status
        config_panel.py   # cartão "Arquivos de configuração"
        options_panel.py  # cartão "Opções de execução"
        sources_panel.py  # cartão "Fontes CSV"
        console_panel.py  # comando montado + botões + área de log
```

`ansi.py`, `command.py`, `launcher.py` e `state.py` são Python puro. `process.py`
é a única fronteira: conhece Qt (para sinais) e o núcleo.

### 3.2 Fluxo de dados

```
widgets  --(sinal de alteração)-->  RunOptions  --command.build_argv-->  argv
                                                --command.to_display-->  texto do painel

[Executar] --> launcher.resolve() + argv --> ImportProcess (QProcess)
           --> readyRead --> ansi.AnsiRenderer --> ConsolePanel
           --> finished(code) --> estado final (barra de status + botões)
```

Qualquer alteração em um controle reconstrói `RunOptions` inteiro e remonta o
comando. Não há atualização incremental do texto — remontar é barato e elimina
uma classe inteira de bugs de sincronização.

## 4. Estado e montagem do comando

### 4.1 `RunOptions`

```python
@dataclass(frozen=True)
class RunOptions:
    config_path: Optional[Path]
    sgbd_config_path: Optional[Path]
    only: tuple[str, ...]              # vazio = todos os configurados
    strategy: str                      # "naive" | "optimized"
    execution: str                     # "stream" | "materialize"
    dry_run: bool
    create_schema: bool
    benchmark: bool
    log_level: str                     # DEBUG | INFO | WARNING | ERROR
    show_data: Optional[bool]          # None = padrão da CLI
    sources: tuple[tuple[str, Path], ...]
```

### 4.2 Regras de montagem (`command.build_argv`)

`build_argv` emite **apenas o que difere do padrão da CLI**, para que o comando
exibido seja o mais curto possível e legível:

| Condição | Emite |
|---|---|
| sempre | `--config <caminho>` |
| `sgbd_config_path` definido | `--sgbd-config <caminho>` |
| `only` não vazio | `--only a,b,c` |
| `strategy != "optimized"` | `--strategy naive` |
| `execution != "stream"` | `--execution materialize` |
| `dry_run` verdadeiro | `--dry-run` |
| `create_schema` falso | `--no-create-schema` |
| `benchmark` verdadeiro | `--benchmark` |
| `log_level != "INFO"` | `--log-level <nível>` |
| `show_data is True` | `--show-data` |
| `show_data is False` | `--no-data` |
| cada par em `sources` | `--source NOME=CAMINHO` |

`to_display(argv)` produz o texto do painel: `polyglotimportcsv` seguido dos
argumentos, com aspas apenas onde necessário (`shlex.quote` no POSIX; regra
equivalente com aspas duplas no Windows). O texto exibido é informativo e fiel —
a execução usa a lista `argv`, sem passar por shell.

## 5. Modo de edição

Estado do painel de CLI, com duas posições:

- **Somente leitura (padrão).** O texto é derivado de `RunOptions`. Selo
  `somente leitura` visível. Botões: `Editar comando`, `Copiar`, `▶ Executar`.
- **Edição.** O `QPlainTextEdit` fica editável e **todo o formulário é
  desabilitado** (`setEnabled(False)`), sinalizando que o texto passou a ser a
  fonte da verdade. Botões: `Voltar ao formulário`, `Copiar`, `▶ Executar`.

`Voltar ao formulário` **descarta** o texto editado e remonta a partir de
`RunOptions`; a ação pede confirmação quando o texto foi alterado. Não existe
caminho de volta do texto para os controles: não há analisador de comando, e
essa é a razão de o formulário ser bloqueado em vez de apenas ignorado.

Ao executar em modo de edição, o texto é dividido com `shlex.split(posix=False)`
no Windows e `posix=True` nos demais sistemas. O primeiro token é descartado e
substituído pelo lançador resolvido (§6.1); os demais tokens são passados como
estão. Um texto que a CLI rejeite produz o mesmo erro que produziria no
terminal — e é isso que se quer.

## 6. Execução

### 6.1 Resolução do lançador

O comando **exibido** começa por `polyglotimportcsv`, que é o que a pessoa
digitaria. O comando **executado** usa um prefixo resolvido em tempo de
execução, por `launcher.resolve()`:

1. Se `sys.frozen` (executável PyInstaller): `[sys.executable, "--cli"]`, com
   `app.py` desviando para `cli.main()` quando vê esse primeiro argumento.
2. Caso contrário: `[sys.executable, "-m", "polyglotimportcsv"]`.

Esta é a única divergência entre o texto mostrado e o processo iniciado, e ela é
documentada na própria interface: o prefixo resolvido aparece como *tooltip* do
painel e é registrado como primeira linha do log de cada execução
(`Executando: <prefixo> ...`). O restante do argv é idêntico ao exibido.

### 6.2 `ImportProcess`

`QObject` que encapsula um `QProcess` e expõe os sinais `started()`,
`output(html)`, `failed(mensagem)` e `finished(codigo)`.

- Canais unidos (`setProcessChannelMode(MergedChannels)`) — o `rich` escreve em
  `stdout` e as exceções em `stderr`; a ordem relativa importa para a leitura.
- Ambiente do filho, além do herdado: `FORCE_COLOR=1` (faz o `rich` emitir cor e
  animar as barras mesmo sem TTY), `PYTHONUNBUFFERED=1`,
  `PYTHONIOENCODING=utf-8` e `COLUMNS` igual à largura atual do console em
  caracteres, recalculado a cada execução.
- Diretório de trabalho: **o diretório de trabalho corrente** (`os.getcwd()`),
  não a raiz do projeto como esta seção afirmava antes de a implementação ser
  medida. Ao lançar a GUI de dentro do repositório — que é o caso da
  demonstração — o efeito é o mesmo: `logs/` e `benchmarks/` caem onde a CLI já
  os coloca. A partir de um executável congelado ou de um atalho, porém, esses
  diretórios seguem o diretório de trabalho do lançamento, e não o projeto.
- Interrupção: `terminate()`, espera de 3 s, depois `kill()`. Como `terminate()`
  não atinge processos de console no Windows, o caminho efetivo lá é o `kill()`.
  O botão pede confirmação, avisando que a importação pode parar pela metade e
  deixar dados parcialmente gravados.

## 7. Console: tradução de ANSI

`ansi.AnsiRenderer` converte o fluxo de bytes do filho em operações sobre as
linhas do console. É a parte mais delicada do trabalho e tem escopo fechado.

Subconjunto suportado:

| Sequência | Tratamento |
|---|---|
| `SGR` (`ESC[...m`) | cores 30–37, 90–97, fundo 40–47/100–107, `1` (negrito), `22`, `39`, `49`, `0`, e as formas estendidas `38;5;n` e `38;2;r;g;b` |
| `\r` | reinicia a linha corrente (substituição, não nova linha) |
| `ESC[<n>A` seguido de `ESC[2K` | apaga e reescreve as `n` últimas linhas — é o que o `rich.Progress` usa para animar |
| `ESC[?25l` / `ESC[?25h` | ignoradas (mostrar/ocultar cursor) |
| qualquer outra | removida do texto, sem quebrar o restante da linha |

A saída é um `QTextEdit` em modo HTML, com buffer de linhas limitado (padrão
5.000 linhas, as mais antigas descartadas). As cores ANSI são mapeadas para os
mesmos tokens do protótipo.

O terminador de linha do Windows é `\r\n`, e por isso o `\r` da tabela acima só
reinicia a linha corrente quando **não** é seguido de `\n`. Um `\r\n` é fim de
linha; tratá-lo como reinício apagaria cada linha logo depois de escrevê-la.

**Cor no Windows — medido, não previsto.** Com `FORCE_COLOR=1` e a saída em um
*pipe*, o console do `rich` usado por `reporting.py` relata
`legacy_windows=True` e `color_system='windows'`: nessa combinação o `rich` não
emite sequências ANSI, e sim chamadas Win32 de console, que não têm efeito
sobre um *pipe*. Numa execução real de 80 KB de saída, o filho não emitiu um
único byte ESC. **O console da GUI é, portanto, monocromático na plataforma do
autor**, e a semelhança com o quadro `02 · Executando` do protótipo não se
verifica ali. O tradutor de ANSI continua correto e exercitado por testes, e a
cor aparece em plataformas cujo `rich` escolhe `color_system='truecolor'`.

`FORCE_COLOR=1` continua sendo indispensável por outro motivo: `reporting.py`
desvia de `entity_progress` quando `not _console.is_terminal`, de modo que sem
essa variável **não há barra de progresso alguma**. Ela não deve ser removida a
pretexto de "simplificar", mesmo estando claro que não é ela que traz a cor no
Windows.

**Plano B documentado:** se a animação de progresso se mostrar instável em alguma
combinação de terminal/versão do `rich`, basta não definir `FORCE_COLOR`. O
`rich` volta a escrever texto simples (e sem barras de progresso) e todo o
restante continua funcionando. A escolha ficaria exposta como preferência
(`Console colorido`) — ver §14, onde o corte dessa preferência está registrado.

## 8. Estados da interface

Correspondência direta com os quadros do protótipo:

| Estado | Formulário | Painel de CLI | Barra de status |
|---|---|---|---|
| **Ocioso** | habilitado | somente leitura; `▶ Executar` ativo se válido | ponto cinza, "Pronto" |
| **Executando** | desabilitado, 50% de opacidade | `Editar comando` desabilitado; botão principal vira `■ Interromper` (vermelho) | ponto azul, SGBD atual e tempo decorrido |
| **Sucesso** (código 0) | habilitado | volta ao normal | ponto verde, tempo total e caminho do log |
| **Erro** (código ≠ 0) | habilitado | volta ao normal | ponto vermelho, código de saída |

O tempo decorrido vem de um `QTimer` na GUI, não da saída da CLI. O caminho do
arquivo de log é capturado do próprio log por expressão regular sobre a linha
`Log file <caminho>` que `cli.main` já emite; se a linha não aparecer, o campo
fica vazio em vez de inventar um caminho.

## 9. Validação e erros

Validação local, antes de habilitar `▶ Executar` (`state.validate`):

- `config_path` definido e existente;
- `sgbd_config_path`, se definido, existente;
- nomes de fonte não vazios, sem `=` e sem repetição;
- caminhos de fonte existentes;
- `only`, quando não vazio, contendo apenas nomes conhecidos.

Cada violação vira uma mensagem curta em português junto ao controle culpado, e
`▶ Executar` fica desabilitado enquanto houver alguma. **Nenhuma validação
semântica do conteúdo dos JSON é feita na GUI** — isso é responsabilidade do
JSON Schema já existente, e o erro correspondente aparece no console quando a
CLI aborta.

**Decisão de projeto a confirmar:** a GUI faz um `json.load` do
`sgbd_config.json` selecionado apenas para descobrir quais SGBDs estão
declarados e desabilitar as caixas de seleção dos demais, evitando uma execução
que a CLI abortaria de saída. É leitura para montar um controle, não um
visualizador de JSON; se a leitura falhar, as cinco caixas ficam todas
habilitadas e nenhum erro é mostrado.

Falhas de processo (`errorOccurred`) — executável ausente, permissão negada —
são escritas no console em vermelho e levam ao estado de erro, com o texto de
`QProcess.error()`.

## 10. Persistência

`QSettings` (organização `UFSC`, aplicação `PolyglotImportCSV`) guarda apenas
conveniências: geometria da janela, posição do divisor, últimos caminhos usados
nos dois *file choosers* e a preferência de console colorido (esta última foi
cortada — ver §14.1). **Nenhuma opção de
execução é persistida** — cada abertura parte dos padrões da CLI, para que o
comando exibido corresponda ao que está na tela e não a uma sessão anterior
esquecida.

## 11. Rótulos e dimensões

Interface em português do Brasil. Os nomes das flags aparecem entre parênteses ao
lado do rótulo (`Estratégia (--strategy)`), o que mantém a correspondência com a
CLI visível sem traduzir a flag. Não há mecanismo de i18n: as cadeias ficam
diretamente no código, como nas demais partes do projeto.

Janela com 1240×1020 px por padrão, como no protótipo, e mínimo de 960×820 px (o piso
vertical é imposto pelos mínimos do formulário e do console, não por 680 px); o divisor
entre formulário e console é arrastável, e o console tem altura mínima de 160 px.

## 12. Empacotamento

- Nova dependência opcional em `pyproject.toml`:
  `[project.optional-dependencies] gui = ["PySide6"]`. A CLI continua instalável
  sem Qt.
- Novo ponto de entrada:
  `polyglotimportcsv-gui = "polyglotimportcsv.gui.app:main"`.
- `polyglotimportcsv.spec` (PyInstaller) ganha um segundo alvo para a GUI, em
  modo `--windowed`, com o desvio `--cli` descrito em §6.1 para que um único
  executável sirva aos dois papéis.

## 13. Testes

Alvo: cobrir por completo o núcleo puro e deixar a camada Qt com verificação de
fumaça. Nada nos testes toca banco de dados.

| Módulo | Teste | Como |
|---|---|---|
| `command.py` | tabela de §4.2, caso a caso; ausência de flags no estado padrão; ordem estável; citação de caminhos com espaço | `pytest` puro |
| `state.py` | cada regra de §9, com `tmp_path` para arquivos existentes e ausentes | `pytest` puro |
| `ansi.py` | SGR básico e estendido; `\r`; `ESC[nA`+`ESC[2K`; sequências desconhecidas; entrada cortada no meio de uma sequência (chega em pedaços do `QProcess`) | `pytest` puro, comparando o HTML resultante |
| `launcher.py` | ramo congelado e ramo de fonte, com `sys.frozen` simulado via `monkeypatch` | `pytest` puro |
| `process.py` | ciclo completo contra um **script de CLI falso** que imprime ANSI, dorme e sai com código configurável | `pytest-qt` |
| `widgets/` | a janela abre; alterar um controle muda o texto do comando; modo de edição desabilita o formulário | `pytest-qt` |

`pytest-qt` entra em `[project.optional-dependencies] dev`. Os testes de widget
são marcados com `@pytest.mark.gui` e pulados quando PySide6 não está instalado,
para que a suíte atual continue rodando em ambiente sem Qt.

Ordem de implementação sugerida, a ser detalhada no plano: núcleo puro com TDD
primeiro (`command`, `state`, `ansi`, `launcher`), depois `process`, depois os
widgets, e por último o empacotamento.

## 14. Riscos

1. **Animação de progresso do `rich` sobre um pipe.** É o item de maior
   incerteza técnica. Mitigado pelo plano B de §7 e pela ordem de implementação
   (o console é validado antes dos widgets).
2. **Divergência entre comando exibido e executado** (§6.1). Mitigada por ser
   exclusivamente o prefixo, por estar documentada na interface e por ir para o
   log de cada execução.
3. **Interrupção deixando gravação parcial.** Inerente a interromper uma
   importação; mitigada por confirmação explícita, não por *rollback* — a CLI não
   tem transação global entre SGBDs.
4. **Prazo.** Três semanas em outubro para implementação. Se apertar, o corte é
   nesta ordem: preferência de console colorido, persistência de `QSettings`,
   leitura do `sgbd_config.json` para filtrar as caixas (§9).

### 14.1 O que foi efetivamente cortado

- **Preferência `Console colorido` (§7 e §10).** Primeiro item da lista de
  cortes acima, e foi o único acionado: `main_window.py` passa `color=True`
  incondicionalmente, e nem a caixa de preferência nem a chave correspondente em
  `QSettings` existem. Dado o que §7 registra sobre a cor no Windows, o controle
  não mudaria nada na plataforma do autor — desligá-lo apenas suprimiria também
  as barras de progresso. O corte fica registrado aqui para que a ausência não
  seja lida como esquecimento.

### 14.2 Riscos conhecidos, ainda não exercitados

- **O desvio `--cli` do executável congelado nunca foi executado.** O alvo da
  GUI é `console=False`, e `launcher.resolve()` inicia `sys.executable --cli`
  para que o filho faça toda a escrita em `stdout`. Se o carregador *windowed*
  do PyInstaller deixa `sys.stdout` utilizável sobre um *handle* redirecionado
  varia conforme a versão. **Precisa de um teste de fumaça com o PyInstaller
  antes da defesa**: gerar os dois alvos, abrir a GUI congelada e executar uma
  importação de ponta a ponta.
- **O arquivo `.spec` do PyInstaller** herda do alvo de CLI preexistente dois
  pontos a revisar no mesmo teste de fumaça: o parâmetro `cipher=`, removido no
  PyInstaller 6.x, e `upx=True`, fonte conhecida de pacotes Qt quebrados.

## 15. Referências

- `src/polyglotimportcsv/cli.py` — superfície de opções espelhada pela GUI.
- `src/polyglotimportcsv/reporting.py` — saída `rich` que o console traduz.
- Protótipo Figma: <https://www.figma.com/design/TM69VaXUwySeeUDdOBMmL5>
- `docs/superpowers/specs/2026-07-08-tcc2-import-modes-design.md` — modos de
  execução expostos pelos controles `--strategy` e `--execution`.
