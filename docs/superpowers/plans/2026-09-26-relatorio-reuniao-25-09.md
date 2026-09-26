# Relatório: mudanças da reunião de 25/09 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Atualizar o relatório do TCC (LaTeX em `docs-tcc/`) com as mudanças pedidas na reunião de 25/09 e com a interface gráfica resultante da parte 1: "conjunto de dados" no lugar de "assunto", referências ao exemplo de e-commerce do Capítulo 2, o projeto no GitHub, o `naive` como implementação do TCC1, a amostra de dados (`--sample`) e a Seção 4.6 reescrita com as Figuras 12 a 15 recapturadas.

**Architecture:** Três tarefas. A primeira faz as edições pontuais de texto fora da Seção 4.6. A segunda atualiza `scripts/capture_gui_figures.py` e regenera as quatro figuras da interface a partir da janela real. A terceira reescreve a Seção 4.6 para descrever a interface e as figuras novas. Cada tarefa termina com o PDF compilando sem erros e sem referências indefinidas.

**Tech Stack:** LaTeX (abnTeX2, MiKTeX, `latexmk`), Python 3 + PySide6 (script de capturas).

**Spec:** `docs/superpowers/specs/2026-09-26-relatorio-reuniao-25-09-design.md`

## Global Constraints

- **Compilação:** `cd docs-tcc && latexmk -pdf -interaction=nonstopmode main.tex`. Depois, `grep -n "^!" main.log` e `grep -n "undefined" main.log` precisam voltar vazios. `main.pdf` e os artefatos de build são ignorados pelo git; não os adicione.
- **Preferências do orientador (obrigatórias):** legenda de figura **abaixo** da figura, com `\caption` e `\label` depois do `\includegraphics`, e a linha `Fonte:` depois da legenda; legenda de tabela acima; toda listagem com frase de introdução; nunca "backend", sempre "SGBD"; **nenhuma prosa sobre versões anteriores do próprio relatório** ("antes o texto dizia…"). A menção ao TCC1 na Tarefa 1 é sobre a história da **ferramenta**, pedida pelo orientador, e não sobre o texto.
- **Redação:** português acadêmico do Brasil, sem marcas de texto gerado ("é importante notar", "vale ressaltar", "em suma"). Siga a pontuação e os travessões `---` já usados no capítulo.
- **Um único domínio de exemplo:** o e-commerce. Nenhum texto novo sugere outros domínios ou cenários.
- **Não mexer** em números, tabelas ou figuras do Capítulo 6; a Tarefa 1 só acrescenta meia frase ali.
- **Commits:** um por tarefa, mensagem em português no padrão `docs(tcc): ...`, com o trailer `Co-Authored-By: Claude <modelo> <noreply@anthropic.com>`. Faça `git push` logo após cada commit (política do projeto).
- **Não adicionar** `CLAUDE.md` (alteração do usuário, fora deste trabalho), `docs-tcc/TCC2-PolyglotImportCSV-Report-v2.0.pdf` nem `render_after.png`. Nunca use `git add -A`.
- **Interpretador:** `./.venv/Scripts/python.exe`. Nunca use `QT_QPA_PLATFORM=offscreen` para capturas: sem fontes, a janela sai com tamanhos distorcidos.

## Review Focus

- **Referência cruzada que compila mas aponta para o lugar errado** (por exemplo, `\ref{sec:persistencia-poliglota}` posto na seção errada do Capítulo 2): no PDF, o número exibido tem de ser 2.1. Verificação na Tarefa 1, Step 4.
- **Nota de rodapé com URL que estoura a margem:** `\url{}` dentro de `\footnote{}` precisa quebrar a linha ou caber nela; um *overfull hbox* na página da Seção 4.1 é defeito. Verificação na Tarefa 1, Step 4 (`grep -n "Overfull" main.log` na faixa da página).
- **Figura que não corresponde ao texto:** a Figura 15 deixa de mostrar um erro de execução e passa a mostrar um erro barrado antes da execução, e o texto da Tarefa 3 descreve exatamente isso. Verificação visual na Tarefa 2, Step 4, e textual na Tarefa 3, Step 3.
- **Contagem de opções da CLI:** "doze opções" precisa bater com `python -m polyglotimportcsv --help`. Verificação na Tarefa 3, Step 1.
- **Figuras que mostram a interface antiga** (rótulo "Estratégia", caixa "Benchmark", "Automático"): nenhuma das quatro pode mostrar esses elementos. Verificação na Tarefa 2, Step 4.

---

### Task 1: Edições pontuais fora da Seção 4.6

**Files:**
- Modify: `docs-tcc/chapters/ch2fundamentacao.tex:3`
- Modify: `docs-tcc/chapters/ch4proposta.tex` (Seção 4.1, Seção 4.2.1, linha ~321, linha ~751, linha ~1034, Seção 4.4, Seção 4.5.1)
- Modify: `docs-tcc/chapters/ch6avaliacao.tex:~126`

**Interfaces:**
- Produces: `\label{sec:persistencia-poliglota}` na Seção 2.1, usado pela Tarefa 3.

- [ ] **Step 1: Rótulo da Seção 2.1**

Em `ch2fundamentacao.tex`, troque:

```latex
\section{Persistência Poliglota}
```

por:

```latex
\section{Persistência Poliglota}
\label{sec:persistencia-poliglota}
```

- [ ] **Step 2: Edições no Capítulo 4**

Faça cada troca abaixo em `ch4proposta.tex`. O texto antigo aparece uma única vez; confira antes de trocar.

(a) Visão geral, fim do primeiro parágrafo. Troque:

```latex
configuração, dentre os suportados: PostgreSQL, MongoDB, Cassandra, Redis e Neo4j.
```

por:

```latex
configuração, dentre os suportados: PostgreSQL, MongoDB, Cassandra, Redis e Neo4j.
A ferramenta é um projeto de código aberto, hospedado no GitHub sob o nome
\texttt{polyglot-import-csv}\footnote{Disponível em
\url{https://github.com/lucasbc92/polyglot-import-csv}.}; todos os caminhos de arquivo
citados neste trabalho, como \texttt{data/\allowbreak ecommerce/} ou
\texttt{docker-compose.yml}, são relativos à raiz desse repositório.
```

(b) Visão geral, "assunto". Troque:

```latex
próprio (um arquivo por assunto); no modo \textbf{combinado}, um único CSV largo carrega
todos os assuntos, distinguidos por uma coluna de origem. Ambos os modos e o formato
```

por:

```latex
próprio (um arquivo por conjunto de dados); no modo \textbf{combinado}, um único CSV largo
carrega todos os conjuntos de dados, distinguidos por uma coluna de origem. Ambos os modos
e o formato
```

(c) Bloco de sintaxe da CLI. Troque o bloco `lstlisting` inteiro que começa em `python -m polyglotimportcsv \` e termina em `[--benchmark]` por:

```latex
\begin{lstlisting}[style=bashstyle]
python -m polyglotimportcsv \
  --config caminho/import_config.json \
  --sgbd-config caminho/sgbd_config.json \
  [--source NOME=CAMINHO] \
  [--dry-run] \
  [--create-schema / --no-create-schema] \
  [--only postgres,redis] \
  [--execution stream|materialize] \
  [--strategy optimized|naive] \
  [--log-level INFO] \
  [--sample N | --show-data | --no-data] \
  [--benchmark]
\end{lstlisting}
```

(d) Parágrafo das opções facultativas. Troque:

```latex
exemplo, \texttt{-{}-only postgres,redis}). O segundo conjunto governa a
\textbf{observabilidade} da execução --- \texttt{-{}-log-level} ajusta o nível de detalhe
das mensagens no terminal, \texttt{-{}-show-data}/\texttt{-{}-no-data} força ou suprime a
exibição dos dados materializados e \texttt{-{}-benchmark} registra métricas de
desempenho por fase ---; essas três opções são descritas em detalhe na
seção~\ref{sec:observabilidade}.
```

por:

```latex
exemplo, \texttt{-{}-only postgres,redis}). As opções \texttt{-{}-execution} e
\texttt{-{}-strategy} escolhem, respectivamente, o modelo de execução e a estratégia de
escrita, descritos na seção~\ref{sec:execucao-estrategias}. O segundo conjunto governa a
\textbf{observabilidade} da execução --- \texttt{-{}-log-level} ajusta o nível de detalhe
das mensagens no terminal; \texttt{-{}-sample}~\texttt{N} exibe as primeiras
\texttt{N} linhas de cada entidade (50, por padrão), enquanto \texttt{-{}-show-data}
exibe todas as linhas e \texttt{-{}-no-data}, nenhuma; e \texttt{-{}-benchmark} registra
métricas de desempenho por fase ---; essas opções são descritas em detalhe na
seção~\ref{sec:observabilidade}.
```

(e) Seção 4.2.1, primeira aparição do cenário no capítulo. Troque:

```latex
corresponde a um assunto do domínio, com o seu próprio arquivo. A
Listagem~\ref{lst:sources-multi} mostra o bloco \texttt{sources} do cenário de e-commerce
nesse modo: quatro fontes, uma por tipo de evento da loja.
```

por:

```latex
corresponde a um conjunto de dados do domínio, com o seu próprio arquivo. O exemplo
adotado ao longo deste capítulo é o cenário de e-commerce apresentado na
Seção~\ref{sec:persistencia-poliglota} (Figura~\ref{fig:polyglot-ecommerce}), em que cada
categoria de dado da loja virtual é destinada ao SGBD mais adequado ao seu uso. A
Listagem~\ref{lst:sources-multi} mostra o bloco \texttt{sources} desse cenário no modo
multifonte: quatro fontes, uma por tipo de evento da loja.
```

(f) Legenda da listagem. Troque `(um CSV por assunto)` por `(um CSV por conjunto de dados)`.

(g) Modo combinado. Troque:

```latex
"origin\_column": true \}}, indicando que um \textbf{único} CSV largo reúne todos os
assuntos, sendo a sua \textbf{primeira coluna} o rótulo de origem de cada linha. A
```

por:

```latex
"origin\_column": true \}}, indicando que um \textbf{único} CSV largo reúne todos os
conjuntos de dados, sendo a sua \textbf{primeira coluna} o rótulo de origem de cada linha. A
```

(h) Filtros (linha ~321). Troque `em que cada assunto já vem de uma fonte` por `em que cada conjunto de dados já vem de uma fonte`.

(i) Cenário de exemplo (linha ~751). Troque `ao seu assunto.` por `ao seu conjunto de dados.`

(j) Exemplo de uso (linha ~1034). Troque `materializando o cenário poliglota da seção 2.1.` por `materializando o cenário poliglota da Seção~\ref{sec:persistencia-poliglota}.`

(k) Seção 4.4, exibição de dados. Troque:

```latex
ambiente. Para inspeção dos dados, a ferramenta exibe uma amostra de cada entidade
materializada até um limite de 50 linhas --- exibição que \texttt{-{}-show-data} força
e \texttt{-{}-no-data} suprime.
```

por:

```latex
ambiente. Para inspeção dos dados, a ferramenta exibe as primeiras linhas de cada
entidade --- 50, por padrão, número ajustável por \texttt{-{}-sample}~\texttt{N} ---,
acompanhadas da contagem total; \texttt{-{}-show-data} exibe todas as linhas e
\texttt{-{}-no-data} suprime a exibição. A amostra vale nos dois modelos de execução da
seção~\ref{sec:modelos-execucao}: no modelo em fluxo, as linhas são retidas à medida que
os lotes são gravados, até o tamanho da amostra, de modo que a exibição não compromete o
consumo limitado de memória.
```

(l) Seção 4.5.1, fim do último parágrafo. Troque:

```latex
ingênua tem valor sobretudo metodológico: é a \textit{linha de base} contra a qual o ganho
da via otimizada é medido no Capítulo~\ref{cap:avaliacao}.
```

por:

```latex
ingênua tem valor sobretudo metodológico: é a \textit{linha de base} contra a qual o ganho
da via otimizada é medido no Capítulo~\ref{cap:avaliacao}. Ela corresponde, de fato, à
implementação original da ferramenta, desenvolvida na primeira etapa deste Trabalho de
Conclusão de Curso (TCC1); no TCC2, foi mantida apenas como referência de comparação. Por
isso, continua acessível pela CLI (\texttt{-{}-strategy naive}), mas não é oferecida na
interface gráfica (Seção~\ref{sec:interface-grafica}), que emprega sempre a estratégia
otimizada.
```

- [ ] **Step 3: Meia frase no Capítulo 6**

Em `ch6avaliacao.tex`, troque:

```latex
\texttt{naive} serve de linha de base e foi medida apenas no ponto $N = 10\,000$, no modo de
```

por:

```latex
\texttt{naive} --- a implementação original da ferramenta, do TCC1
(seção~\ref{sec:estrategias-escrita}) --- serve de linha de base e foi medida apenas no
ponto $N = 10\,000$, no modo de
```

- [ ] **Step 4: Compilar e verificar**

```bash
cd docs-tcc && latexmk -pdf -interaction=nonstopmode main.tex > /dev/null 2>&1; echo exit=$?
grep -n "^!" main.log; grep -n "undefined" main.log
grep -n -i "assunto" chapters/*.tex
```

Expected: `exit=0`; as três buscas vazias.

Confira no PDF, com `pdftotext -layout main.pdf - | grep -n -A3 "hospedado no GitHub"` e `grep -n "Seção 2.1"`, que (1) a frase do GitHub aparece e a nota de rodapé traz a URL completa; (2) as referências novas imprimem "Seção 2.1" e "Figura 1"; (3) `grep -n "Overfull" main.log` não aponta linha nova na página da Seção 4.1 (compare com o `main.log` anterior à mudança, se houver dúvida). Se a URL estourar a margem, troque `\url{...}` por `\url{https://github.com/}\allowbreak\url{lucasbc92/polyglot-import-csv}`.

- [ ] **Step 5: Commit**

```bash
git add docs-tcc/chapters/ch2fundamentacao.tex docs-tcc/chapters/ch4proposta.tex docs-tcc/chapters/ch6avaliacao.tex
git commit -m "docs(tcc): conjunto de dados, referencias ao e-commerce e ao GitHub e --sample" -m "Troca assunto por conjunto de dados, liga o exemplo do capitulo 4 a secao 2.1, registra o repositorio no GitHub, descreve a amostra de dados e apresenta o naive como a implementacao do TCC1 mantida como linha de base." -m "Co-Authored-By: Claude <modelo> <noreply@anthropic.com>"
git push
```

---

### Task 2: Script de capturas e Figuras 12 a 15

**Files:**
- Modify: `scripts/capture_gui_figures.py`
- Modify (regeneradas): `docs-tcc/images/figure12-gui-ocioso.png`, `figure13-gui-executando.png`, `figure14-gui-sucesso.png`, `figure15-gui-erro.png`

**Interfaces:**
- Consumes: a GUI da parte 1 (`MainWindow`, `OptionsPanel.show_data_buttons` com as chaves `"sample"`/`"all"`/`"none"`, `ConfigPanel.error_label`).
- Produces: as quatro figuras que a Tarefa 3 descreve:
  - 12: estado ocioso, configuração multifonte, exibição de dados em **Amostra** (padrão), comando colorido;
  - 13: execução em andamento (`--dry-run`), saída colorida chegando ao console;
  - 14: execução concluída, tempo e caminho do log na barra de estado, "Salvar log…" habilitado;
  - 15: erro barrado **antes** da execução: `import_config_invalido.json` escolhido, mensagem do *JSON Schema* no cartão de configuração, botão Executar desabilitado, console vazio.

- [ ] **Step 1: Ajustar o script**

Em `scripts/capture_gui_figures.py`:

1. Em `new_window`, apague a linha que marca `show_data_buttons["none"]`: as figuras passam a mostrar a exibição padrão (**Amostra**, 50 linhas), que é a novidade.
2. Troque o bloco da Figura 15 por:

```python
        # Figure 15: a configuration whose "stock" source is a number, which
        # satisfies neither branch of the schema. The pre-run validation
        # rejects it before anything runs: the CLI's own message sits in the
        # configuration card and the Run button stays disabled, so there is
        # deliberately no on_run() here.
        failing = new_window(app, settings_path, INVALID)
        pump(app, 0.3)
        assert not failing.console_panel.run_button.isEnabled(), "run must be blocked"
        assert failing.config_panel.error_label.text(), "the schema error must be shown"
        grab(failing, "figure15-gui-erro.png")
        failing.hide()
```

3. No docstring do módulo, troque "All four runs use ``--dry-run``, so no database has to be up." por "Figures 12-14 are one ``--dry-run``, so no database has to be up; figure 15 never runs at all, because the pre-run validation blocks it." e troque "the "Executando:" line in figures 13 and 15" por "the "Executando:" line in figures 13 and 14".

- [ ] **Step 2: Regenerar**

```bash
./.venv/Scripts/python.exe scripts/capture_gui_figures.py
```

Expected: quatro linhas `figureNN-... — <status>`; a da Figura 14 com "Concluído"; a da 15 com "Pronto — nenhuma importação em execução".

- [ ] **Step 3: Conferir as imagens**

Abra as quatro imagens (ferramenta Read) e confira, uma a uma:
- nenhuma mostra "Estratégia", "Benchmark" ou "Automático";
- 12: rótulo "Configuração multifonte…", ícones "i", comando colorido com `--sample 50`;
- 13: saída colorida chegando ao console;
- 14: tabela "Import metrics" com bordas simples e alinhadas, status "Concluído — …", caminho do log;
- 15: mensagem de erro de schema em vermelho no cartão de configuração e Executar desabilitado.

Se alguma não atender, ajuste o script (tempo de `pump`, ponto de captura) e regenere. Não edite imagens à mão.

- [ ] **Step 4: Commit**

```bash
git add scripts/capture_gui_figures.py docs-tcc/images/figure12-gui-ocioso.png docs-tcc/images/figure13-gui-executando.png docs-tcc/images/figure14-gui-sucesso.png docs-tcc/images/figure15-gui-erro.png
git commit -m "docs(tcc): recaptura as figuras da interface grafica" -m "Figuras 12 a 14 mostram a interface nova (amostra, icones de ajuda, comando e saida coloridos); a 15 passa a mostrar um erro barrado pela validacao previa, antes da execucao." -m "Co-Authored-By: Claude <modelo> <noreply@anthropic.com>"
git push
```

---

### Task 3: Reescrita da Seção 4.6 (Interface Gráfica)

**Files:**
- Modify: `docs-tcc/chapters/ch4proposta.tex` (do `\section{Interface Gráfica}` ao fim do arquivo)

**Interfaces:**
- Consumes: `\label{sec:persistencia-poliglota}` (Tarefa 1); as figuras regeneradas (Tarefa 2); os rótulos existentes `sec:config-format`, `sec:validacao`, `sec:modelos-execucao`, `cap:avaliacao`, `cap:futuros`.

- [ ] **Step 1: Conferir a contagem de opções**

```bash
./.venv/Scripts/python.exe -m polyglotimportcsv --help
```

Conte as opções, tratando `--create-schema/--no-create-schema` e `--show-data/--no-data` como uma opção cada e sem contar `--help`. Expected: 12 (`--config`, `--sgbd-config`, `--dry-run`, `--create-schema`, `--only`, `--strategy`, `--execution`, `--source`, `--log-level`, `--show-data`, `--sample`, `--benchmark`). Se o número for outro, use-o por extenso no primeiro parágrafo abaixo.

- [ ] **Step 2: Substituir a seção**

Substitua tudo, de `\section{Interface Gráfica}` até o fim de `ch4proposta.tex`, por:

```latex
\section{Interface Gráfica}
\label{sec:interface-grafica}

Todas as capacidades descritas até aqui são acionadas por uma interface de linha de comando
governada por doze opções, que precisam ser digitadas corretamente a cada execução e cujos
erros de sintaxe só se manifestam depois que o comando é submetido. Para reduzir essa barreira
--- sem esconder a ferramenta de quem deseja aprendê-la --- foi construída uma
\textbf{interface gráfica} \textit{desktop} sobre a CLI já existente. O princípio que orienta
o seu projeto é deliberadamente didático: \textbf{o comando exibido é o comando executado}.
Cada opção da CLI corresponde a um controle gráfico, e o comando resultante permanece visível
o tempo todo, de modo que a interface \textbf{ensina} a linha de comando em vez de substituí-la.

A interface é um \textbf{invólucro fino}: ela não reimplementa nenhuma etapa da importação.
O seu núcleo traduz o estado do formulário na lista de argumentos da CLI e a executa como
\textbf{processo filho}, capturando a saída do processo e apresentando-a em um console
integrado. Duas consequências decorrem dessa escolha. A primeira é de correção: como quem
importa é a própria CLI, não existe risco de a interface e a linha de comando divergirem em
comportamento, e toda a validação por \textit{JSON Schema} descrita na
Seção~\ref{sec:config-format} continua sendo exercida pelo mesmo código. A segunda é
de arquitetura: os módulos que montam o comando, validam as entradas, resolvem o executável e
traduzem a saída não dependem da biblioteca gráfica, podendo ser testados sem instanciar uma
aplicação de janelas.

A janela divide-se em duas regiões, separadas por um divisor ajustável, como mostra a
Figura~\ref{fig:gui-ocioso}. Na metade superior estão três cartões de formulário. O primeiro
seleciona, por diálogos de arquivo, os dois arquivos de configuração. O segundo reúne as
opções de execução, com um controle para cada \textit{flag}: os SGBDs de destino, o modelo de
execução discutido na Seção~\ref{sec:modelos-execucao}, os modificadores de simulação e de
criação de esquema, o nível de \textit{log} e a exibição de dados --- uma amostra das
primeiras linhas de cada entidade, em quantidade escolhida pelo usuário, todos os dados ou
nenhum. Ao lado de cada opção cujo nome não se explica sozinho há um \textbf{ícone de ajuda}
que, ao receber o cursor ou um clique, descreve o efeito da opção; o de \texttt{stream}, por
exemplo, explica que a memória usada não cresce com o tamanho do arquivo. Duas opções da CLI
não aparecem no formulário: a estratégia de escrita, fixada em \texttt{optimized}, e o
registro de métricas de \textit{benchmark}. Ambas são instrumentos da avaliação de
desempenho do Capítulo~\ref{cap:avaliacao}, e não do uso cotidiano da ferramenta, e
continuam disponíveis na linha de comando. O terceiro cartão contém a tabela de sobrescrita
de caminhos das fontes CSV. Na metade inferior está o console integrado, que exibe o comando
montado e, abaixo dele, a saída da execução.

O cartão de fontes adapta-se ao arquivo de importação escolhido. Sem uma configuração de
importação válida, ele não aceita fontes, pois uma sobrescrita só faz sentido diante das
fontes que a configuração declara. Com uma configuração \textbf{multifonte}, aceita vários
arquivos --- escolhidos um a um, de uma pasta inteira ou arrastados sobre a tabela ---, e o
nome de cada fonte é deduzido comparando o arquivo com o bloco \texttt{sources}, de modo que
a sobrescrita gerada se refira a uma fonte que de fato existe. Com uma configuração
\textbf{combinada}, aceita um único arquivo, associado à única fonte declarada. Trocar de
configuração não descarta as linhas já escolhidas: as que deixam de caber na nova
configuração são apontadas como erro até que o usuário as remova.

Antes de executar, a interface faz uma \textbf{validação prévia} com o próprio código da
CLI. Os dois arquivos de configuração passam pelo mesmo \textit{JSON Schema} e pela mesma
verificação de consistência entre si descritos na Seção~\ref{sec:validacao}; em seguida,
cada CSV envolvido tem apenas o seu cabeçalho lido, e as entidades são vinculadas a fontes
sem linhas pelo mesmo mecanismo empregado na importação. Uma coluna referenciada na
configuração e ausente do arquivo produz, assim, exatamente a mensagem que a CLI emitiria,
só que antes da execução, e o botão de execução permanece desabilitado enquanto houver
pendências. A validação prévia tem um limite deliberado: nada que exija conexão com um SGBD
ou a leitura das linhas de dados é verificado nessa etapa, porque os arquivos podem ser
maiores que a memória disponível. Essas verificações continuam a cargo da CLI, durante a
execução.

\begin{figure}[H]
  \centering
  \includegraphics[width=0.95\textwidth]{images/figure12-gui-ocioso}
  \caption{Interface gráfica no estado ocioso: configuração multifonte escolhida, ícones de
  ajuda e comando montado, colorido, em modo somente leitura.}
  \label{fig:gui-ocioso}
  \par\vspace{4pt}
  {\footnotesize Fonte: Elaborado pelo autor (2026).}
\end{figure}

O comando montado é, por padrão, \textbf{somente leitura}, e \textbf{explicita todas as
opções}, inclusive aquelas mantidas no valor padrão da CLI. A alternativa --- omitir o que
coincide com o padrão, de modo a permanecer tão curto quanto aquilo que uma pessoa realmente
digitaria --- contraria o propósito didático da interface: um controle deixado no padrão não
produziria alteração visível no texto, e o clique pareceria ter sido ignorado. Escrever a
opção por extenso custa alguns caracteres e devolve ao comando a propriedade que justifica
exibi-lo --- a de que cada controle do formulário tem um correspondente literal na linha de
comando. Para facilitar a leitura, o comando é colorido: o nome do programa, as opções e os
seus valores recebem cores distintas. Um \textbf{modo de edição} permite editar o texto
diretamente; ao entrá-lo, o formulário é \textbf{bloqueado}, sinalizando que o texto passou
a ser a fonte da verdade. Essa decisão é intencional e tem uma razão precisa: \textbf{não
existe analisador de comando} na ferramenta. O caminho do formulário para o texto é de mão
única, e manter os dois editáveis ao mesmo tempo exigiria reconstruir o estado do formulário
a partir de uma cadeia de caracteres arbitrária --- precisamente o tipo de acoplamento que a
interface se propõe a evitar. Ao sair do modo de edição, o texto digitado é descartado
mediante confirmação e o comando é remontado a partir dos controles.

Durante a execução, o formulário permanece desabilitado, o botão principal passa a oferecer
a interrupção do processo e a saída da CLI chega ao console de forma incremental, com as
mesmas cores que teria em um terminal, como ilustra a Figura~\ref{fig:gui-executando}. Ao
término, a barra de estado informa o desfecho: a Figura~\ref{fig:gui-sucesso} mostra uma
execução concluída, com o tempo total e o caminho do arquivo de \textit{log} da sessão. Um
clique nesse caminho abre a pasta em que o arquivo está, e o botão \textbf{Salvar log}
copia-o para um local escolhido pelo usuário. O arquivo salvo é o \textit{log} completo da
sessão, em nível \texttt{DEBUG}, e não apenas o texto exibido no console.

\begin{figure}[H]
  \centering
  \includegraphics[width=0.95\textwidth]{images/figure13-gui-executando}
  \caption{Execução em andamento: formulário bloqueado, botão de interrupção e saída colorida
  da CLI chegando ao console em tempo real.}
  \label{fig:gui-executando}
  \par\vspace{4pt}
  {\footnotesize Fonte: Elaborado pelo autor (2026).}
\end{figure}

\begin{figure}[H]
  \centering
  \includegraphics[width=0.95\textwidth]{images/figure14-gui-sucesso}
  \caption{Execução concluída com sucesso, com o tempo total e o arquivo de \textit{log} da
  sessão na barra de estado.}
  \label{fig:gui-sucesso}
  \par\vspace{4pt}
  {\footnotesize Fonte: Elaborado pelo autor (2026).}
\end{figure}

Os erros aparecem em dois momentos. Os que a validação prévia detecta são apresentados no
próprio formulário, junto ao cartão a que se referem, como mostra a
Figura~\ref{fig:gui-erro}: a mensagem é a mesma que a CLI produziria, e a execução fica
bloqueada. Quando o usuário corrige o arquivo em um editor externo e retorna à janela, a
validação é refeita automaticamente. Os erros que só surgem durante a importação, como a
falha de conexão com um SGBD, aparecem no console exatamente como apareceriam no terminal, e
a barra de estado informa o código de saída do processo. Como a interface executa a CLI
real, não há tradução intermediária que pudesse mascarar a mensagem.

\begin{figure}[H]
  \centering
  \includegraphics[width=0.95\textwidth]{images/figure15-gui-erro}
  \caption{Erro detectado antes da execução: a configuração de importação viola o
  \textit{JSON Schema}, a mensagem da CLI aparece no cartão de configuração e o botão de
  execução permanece desabilitado.}
  \label{fig:gui-erro}
  \par\vspace{4pt}
  {\footnotesize Fonte: Elaborado pelo autor (2026).}
\end{figure}

Uma limitação de escopo deve ser registrada: a interface \textbf{monta, valida e executa} o
comando, mas não \textbf{edita} os arquivos JSON de configuração, que continuam a ser
mantidos em um editor de texto externo. Ampliar a interface para editar a configuração de
forma assistida é uma das atividades futuras discutidas no Capítulo~\ref{cap:futuros}.
```

- [ ] **Step 3: Compilar e ler as páginas**

```bash
cd docs-tcc && latexmk -pdf -interaction=nonstopmode main.tex > /dev/null 2>&1; echo exit=$?
grep -n "^!" main.log; grep -n "undefined" main.log
pdfinfo main.pdf | grep Pages
```

Expected: `exit=0`, buscas vazias. Anote o número de páginas.

Localize as páginas da Seção 4.6 (`pdftotext -layout main.pdf - | grep -n "Interface Gráfica"`) e renderize-as para PNG (`pdftoppm -f <ini> -l <fim> -r 70 -png main.pdf <dir-temporario>/p`, com o diretório temporário fora do repositório). Leia cada página e confira: legendas abaixo das figuras, `Fonte:` abaixo da legenda, cada figura perto do parágrafo que a cita, nenhuma página quase vazia por figura empurrada e texto da Figura 15 coerente com a imagem.

- [ ] **Step 4: Commit**

```bash
git add docs-tcc/chapters/ch4proposta.tex
git commit -m "docs(tcc): reescreve a secao da interface grafica" -m "Descreve os icones de ajuda, a amostra de dados, as opcoes que ficam so na CLI, o cartao de fontes por tipo de configuracao, a validacao previa com o codigo da CLI, o comando e a saida coloridos e o Salvar log; remove a limitacao de cor, que deixou de existir." -m "Co-Authored-By: Claude <modelo> <noreply@anthropic.com>"
git push
```
