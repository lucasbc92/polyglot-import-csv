# Design — GUI e CLI: mudanças da reunião de 25/09

Data: 2026-09-26
Status: aprovado em brainstorming; aguardando revisão do autor.
Branch: `tcc2-gui` (a GUI ainda não foi mesclada em `main`).

Parte 1 de 3 das mudanças pedidas na reunião de orientação de 25/09. As outras
duas são o relatório (`2026-09-26-relatorio-reuniao-25-09-design.md`) e as
releases (`2026-09-26-releases-github-design.md`). Esta parte vem primeiro: o
relatório descreve a GUI resultante e as releases a empacotam.

Parte do design de 2026-09-20 (`2026-09-20-tcc2-gui-design.md`) e altera apenas
o que está listado aqui. Os princípios continuam valendo: a GUI é um invólucro
fino, o comando exibido é o comando executado, e o núcleo puro (`state`,
`command`, `launcher`, `ansi` e o novo `preflight`) não importa PySide6.

## 1. Resumo das decisões

| # | Item da reunião | Decisão |
|---|---|---|
| 1 | Esclarecer stream, materialize, optimized… | Ícone "i" redondo com *tooltip* ao lado de cada opção cujo nome não se explica sozinho. |
| 2 | Tirar estratégia; sempre `optimized`; tirar `naive` | Sai da **GUI**. A GUI sempre emite `--strategy optimized`. A CLI mantém `--strategy naive|optimized`, porque o Capítulo 6 mede `naive` e precisa continuar reprodutível. |
| 3 | "Automático" → "Amostra", com tamanho escolhido | Nova opção de CLI `--sample N` (padrão 50), que passa a valer também no modo `stream`. |
| 4 | Validar `--config` combinada; botões de fontes | A GUI classifica a configuração (multifonte/combinada) e adapta o cartão de fontes. |
| 5 | Retirar o modo Benchmark | Sai da **GUI**. A CLI mantém `--benchmark`. |
| 6 | Fontes: arrastar e soltar, seleção mais clara | Área de soltar e seleção visível; múltipla na multifonte, única na combinada. |
| 7 | Rótulos de `--show-data` / `--no-data` | "Todos os dados" e "Nenhum dado". |
| 8 | Mais validações antes da execução | JSON Schema, nomes de fonte, arquivos declarados e cabeçalho dos CSVs, tudo pelo código da própria CLI. |
| 9 | Linha de comando colorida | O **comando montado** (destaque de sintaxe) e a **saída** (ANSI real no Windows). |
| 10 | Salvar o log | Botão "Salvar log…" e caminho do log clicável na barra de estado. |

## 2. CLI

### 2.1 `--sample N`

Semântica nova da exibição de dados por entidade:

| Opção | Comportamento |
|---|---|
| *(nenhuma)* ou `--sample N` | Mostra as **primeiras N linhas** de cada entidade e, quando a entidade tem mais que N, a contagem total (`mostrando 50 de 12.000 linhas`). N padrão = 50. |
| `--show-data` | Mostra todas as linhas. |
| `--no-data` | Não mostra linha alguma; só as contagens. |

- `--sample` recebe inteiro ≥ 1 (`click.IntRange(min=1)`).
- `--sample` combinado com `--show-data` ou `--no-data` é `click.UsageError`
  ("--sample só se aplica ao modo de amostra; não combine com --show-data/--no-data").
- `--benchmark` continua implicando `--no-data`.
- Antes, o padrão mostrava tudo até 50 linhas e nada acima disso. Para
  entidades de até N linhas o resultado continua o mesmo; acima de N, passam a
  aparecer as N primeiras em vez de nenhuma.
- O limiar das barras de progresso (`entity_progress`) deixa de reutilizar a
  constante de exibição e ganha a sua própria (`PROGRESS_THRESHOLD = 50`), para
  que mudar o tamanho da amostra não mude quando aparecem as barras.

Implementação: `reporting.dump_entity_frame` passa a receber o modo
(`"sample"`, `"all"` ou `"none"`) e N, no lugar de `force: Optional[bool]`. O
`run_import` recebe `sample_size: int = 50` e repassa aos dois caminhos.

### 2.2 Exibição de dados no modo `stream`

Hoje `_run_stream` não exibe dado algum, e a opção de exibição não tem efeito
no modo padrão. Passa a ter:

- **Amostra:** para cada entidade, guarda as primeiras N linhas conforme os
  blocos são gravados (já projetadas e convertidas, as mesmas que o SGBD
  recebe) e as exibe ao final da entidade, com o total. A memória extra fica
  limitada a N linhas, o que preserva o modelo de memória limitada.
- **Todos os dados:** imprime cada bloco logo depois de gravado. Não acumula
  nada, mas é lento para arquivos grandes. O *tooltip* da GUI avisa disso.
- **Nenhum dado:** como hoje.

O formato de exibição é o mesmo do caminho com materialização
(`dump_rows`), para que os dois modos pareçam iguais para quem lê.

### 2.3 Saída colorida no Windows

Medido em 2026-09-20: com `FORCE_COLOR=1` e a saída num *pipe*, o `Console` de
`reporting.py` escolhe `legacy_windows=True` / `color_system='windows'` e faz
chamadas Win32 que não têm efeito num *pipe*, por isso o filho não emite nenhum
ESC. A correção fica em `reporting.py`: quando `FORCE_COLOR` estiver definido,
o `Console` é criado com `legacy_windows=False` (e `color_system` explícito se a
medição mostrar que é necessário). No terminal comum do Windows 10+, que aceita
VT, nada muda.

Critério de aceite: uma execução real da GUI no Windows produz bytes ESC no
fluxo do filho, e o console integrado mostra cores. `FORCE_COLOR=1` continua
indispensável para as barras de progresso (ver o design de 20/09, §7).

## 3. Núcleo puro

### 3.1 `RunOptions` e `build_argv`

- Removidos: `strategy` e `benchmark`. `STRATEGIES` sai de `state.py`.
- `show_data: Optional[bool]` vira `data_mode: str` (`"sample"`, `"all"` ou
  `"none"`, padrão `"sample"`) mais `sample_size: int = 50`.
- `build_argv` continua explicitando tudo:
  - `--strategy optimized` sempre, logo depois de `--only`. É constante, mas é
    o que roda, e o comando deve mostrar o que roda.
  - Amostra → `--sample N`; todos os dados → `--show-data`; nenhum dado →
    `--no-data`.
  - `--benchmark` nunca é emitido.
- `validate` ganha: `sample_size` ≥ 1.

### 3.2 `gui/preflight.py` (novo)

Validação antes da execução, sem Qt, **chamando o código da CLI** em vez de
reimplementá-lo. Uma função pública:

```python
def check(options: RunOptions) -> Preflight
```

`Preflight` traz `kind` (`"multi"`, `"combined"` ou `None` quando a
configuração ainda não pôde ser lida), `declared` (`{nome: arquivo declarado}`)
e `errors: Dict[str, str]` nas mesmas chaves que `validate` usa (`config_path`,
`sgbd_config_path`, `sources`), para que os painéis continuem mostrando erros
do jeito que já mostram.

Verificações, em ordem; cada uma só roda se a anterior passou:

1. **JSON Schema** dos dois arquivos, com `config_parser.load_import_config` /
   `load_sgbd_config` e a validação que eles já fazem.
2. **Consistência entre os arquivos**, com `config_parser.merge_configs`
   (a configuração de importação só referencia SGBDs declarados na de conexão).
3. **Classificação:** `combined` quando `sources` declara exatamente uma fonte
   e ela é um objeto `{"file": …}`; `multi` em qualquer outro caso, inclusive
   as configurações mistas que o schema admite.
4. **Nomes das sobrescritas:** todo `--source NOME=…` precisa nomear uma fonte
   declarada. Na combinada, no máximo uma sobrescrita.
5. **Arquivos das fontes:** para cada fonte declarada, resolve o caminho como a
   CLI resolve (sobrescrita relativa ao diretório de trabalho; declarado
   relativo à pasta da configuração) e confere que o arquivo existe.
6. **Cabeçalho:** lê só a primeira linha de cada CSV e vincula as entidades a
   uma amostra de zero linhas com `stream_binding.bind_entity_from_sample` e
   `bind_union_entity_from_samples`. Uma coluna referenciada e ausente produz o
   mesmo erro que a CLI daria. Na combinada, também confere que há pelo menos
   duas colunas (origem + dados). **Os valores da coluna de origem não são
   lidos**: fazer isso exigiria percorrer o arquivo inteiro, que pode ser maior
   que a memória. Essa conferência continua sendo feita pela CLI.

**Custo:** `refresh_command` roda a cada clique. `check` guarda em cache o
resultado de cada arquivo lido, com `(caminho, mtime, tamanho)` como chave, e
não relê o que não mudou. Com essa cache, o custo em regime é de algumas
chamadas `stat`.

**Limite do que é validado:** nada que exija conexão com o SGBD ou leitura das
linhas de dados. Tudo o que passar daí continua sendo validado pela CLI na
execução, como hoje.

## 4. Camada Qt

### 4.1 Cartão "Opções de execução"

- Some a linha "Estratégia (--strategy)" e a caixa "Benchmark (--benchmark)".
- **Exibição de dados:** `(•) Amostra [spin 50]` · `( ) Todos os dados (--show-data)`
  · `( ) Nenhum dado (--no-data)`. O `QSpinBox` (1 a 1.000.000) só fica
  habilitado com "Amostra" marcada e mostra `--sample` no *tooltip*.
- **Ícone "i":** um `InfoBadge` (círculo de 14 px desenhado com `QPainter`, na
  mesma linha visual dos indicadores de `gui/indicators.py`), com o texto no
  *tooltip*, que também aparece ao clicar. Vai ao lado de: Execução (um para
  `stream` e outro para `materialize`), Simulação, Criar esquema, Nível de log
  e Exibição de dados. Textos:
  - **stream:** "Importa em fluxo: lê cada CSV em blocos e grava bloco a bloco.
    A memória usada não cresce com o tamanho do arquivo. É o modo recomendado."
  - **materialize:** "Carrega cada fonte inteira na memória, monta todas as
    entidades e só então grava. Útil para inspecionar os dados; exige memória
    proporcional ao arquivo."
  - **Simulação (--dry-run):** "Valida as configurações e mostra quantos
    registros iriam para cada destino, sem conectar a nenhum SGBD. Usa sempre a
    materialização."
  - **Criar esquema:** "Cria tabelas, coleções, keyspace e índices que ainda não
    existirem antes de gravar."
  - **Nível de log:** "Quanto detalhe aparece no console. O arquivo de log da
    sessão sempre registra tudo (DEBUG)."
  - **Exibição de dados:** "Amostra: as primeiras N linhas de cada entidade.
    Todos os dados: todas as linhas; lento em arquivos grandes. Nenhum dado:
    só as contagens."

  O texto do *tooltip* da estratégia de escrita não é necessário, porque a
  linha some. `optimized` continua explicado no relatório.

### 4.2 Cartão "Fontes CSV"

O cartão recebe o `Preflight` e se adapta a `kind`:

| | Multifonte | Combinada |
|---|---|---|
| Rótulo do tipo | "Configuração multifonte: um CSV por conjunto de dados" | "Configuração combinada: um único CSV" |
| Botão de arquivos | "+ Adicionar arquivos" (seleção múltipla) | "+ Adicionar arquivo" (seleção única); desabilitado quando já há uma linha |
| "+ Adicionar pasta" | habilitado | desabilitado, com *tooltip* explicando o motivo |
| Nome da fonte | deduzido como hoje (`_name_for`) | o nome declarado da fonte combinada |
| Seleção na tabela | múltipla (`ExtendedSelection`) | única (`SingleSelection`) |

Com `kind is None` (configuração ainda não escolhida ou ilegível), o cartão se
comporta como multifonte e o rótulo do tipo fica vazio.

- **Arrastar e soltar:** a tabela aceita `.csv` soltos sobre ela (arquivos e,
  na multifonte, pastas, com a mesma regra do "Adicionar pasta"). Enquanto a
  tabela está vazia, mostra ao centro "Arraste arquivos CSV para cá ou use os
  botões acima". Na combinada, soltar mais de um arquivo, ou soltar com uma
  linha já presente, é recusado e a razão aparece no rótulo de erro do cartão.
  Arquivos que não são `.csv` são ignorados, com a contagem informada.
- **Seleção visível:** a linha selecionada ganha fundo `TOKEN_ACCENT` claro e
  borda à esquerda, inclusive sem foco (`QTableWidget::item:selected:!active`
  no *stylesheet*). "− Remover" só fica habilitado quando há seleção.
- Trocar para uma configuração combinada com mais de uma linha na tabela **não
  apaga nada**: o `preflight` acusa "A configuração combinada aceita um único
  arquivo" e a execução fica bloqueada até o usuário remover o excesso. A GUI
  não descarta o que o usuário escolheu.

### 4.3 Console

- **Comando colorido:** um `QSyntaxHighlighter` no `command_edit` pinta o
  programa, as opções (`--config`) e os valores com três cores da paleta do
  console. A classificação dos tokens é uma função pura nova em `command.py`
  (`classify(text) -> List[(início, fim, tipo)]`), testável sem Qt. Funciona
  também no modo de edição, porque colore o texto digitado.
- **Saída colorida:** vem da §2.3. Do lado da GUI nada muda: o `AnsiRenderer`
  já traduz as cores.
- **"Salvar log…":** botão na barra de ações do console, habilitado quando uma
  execução termina (com sucesso ou falha) e o caminho do log foi capturado.
  Abre "Salvar como" com o nome da sessão sugerido e copia o arquivo
  (`shutil.copyfile`). É o log da sessão (DEBUG, sem cores), não o texto do
  console. Se a cópia falhar, uma mensagem de erro é exibida e nada mais muda.
- **Caminho do log clicável:** o `log_path_label` da barra de estado vira um
  link que abre a pasta do log no gerenciador de arquivos do sistema
  (`QDesktopServices.openUrl` na pasta).

## 5. Testes

- **Núcleo:** `build_argv` (sem `--benchmark`, sempre `--strategy optimized`,
  os três modos de dados), `validate` (`sample_size`), `command.classify`,
  `preflight.check` com as configurações de `data/ecommerce/` (multifonte,
  combinada, inválida) e com CSVs temporários de cabeçalho quebrado,
  sobrescrita com nome desconhecido, combinada com duas sobrescritas, e o
  cache (um arquivo não é relido sem mudança de `mtime`).
- **CLI:** `--sample N` nos dois caminhos; `--sample` combinado com
  `--show-data` gera `UsageError`; amostra no modo `stream` guarda no máximo N
  linhas, testada com um *sink* falso, sem SGBD; `FORCE_COLOR` gera um
  `Console` que emite ESC num *pipe*.
- **Qt (`pytest-qt`):** cartão de fontes nos dois modos (botões, rótulo,
  arrastar e soltar simulado com `QMimeData`, recusa de dois arquivos na
  combinada), habilitação do "Remover", *spin* ligado só em "Amostra", ausência
  dos controles removidos, "Salvar log…" com o diálogo injetado (o mesmo
  artifício de `confirm_discard`).
- Suíte executada com `.venv/Scripts/python.exe -m pytest tests -q`, lendo a
  contagem total; o `python` do sistema não tem `pytest-qt`.
- Teste manual final: `scripts/capture_gui_figures.py` e uma execução real no
  Windows conferindo as cores.

## 6. Fora do escopo

- Remover `naive` ou `--benchmark` da CLI.
- Ler os valores da coluna de origem na GUI (ver §3.2, item 6).
- Editar os arquivos JSON na GUI (continua como atividade futura).
- Salvar o texto do console em HTML ou com cores.

## 7. Riscos

- **`legacy_windows=False` num *pipe*:** a hipótese é que o `rich` passa a
  emitir ANSI; precisa ser **medida** na implementação, como foi feito em 20/09.
  Se falhar, a alternativa é `Console(force_terminal=True, color_system="truecolor",
  legacy_windows=False)`. Se nem isso funcionar, a limitação é mantida e
  documentada como antes, e o comando colorido (que não depende disso) segue.
- **Custo do *preflight* por clique:** mitigado pelo cache por `mtime`. Se a
  vinculação por cabeçalho se mostrar lenta em configurações grandes, ela passa
  a rodar com atraso de 300 ms (`QTimer` de disparo único) em vez de a cada
  clique.
- **Mudança do padrão de exibição na CLI:** entidades acima de 50 linhas passam
  a exibir 50 linhas em vez de nenhuma. Testes que verificam o comportamento
  antigo (`tests/test_reporting.py`) são atualizados, e nenhum script de
  `scripts/` depende da ausência de linhas (os benchmarks usam `--no-data`
  implícito).
