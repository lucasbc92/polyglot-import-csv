# Apresentação da Defesa do TCC2 — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produzir o PDF Beamer (16:9) da defesa do TCC2: 25 slides no corpo e 7 cartas na manga, no estilo "C bicolor em diagonal", com conteúdo rastreável ao relatório v2.3.

**Architecture:** Um tema Beamer próprio (`beamerthemeufsc.sty`) concentra a moldura: cabeçalho, rodapé, capa, roteiro, fechamento, painéis e numeração das cartas. Um arquivo principal inclui uma seção por bloco do roteiro. Um script `verificar.sh` compila, confere a contagem de slides e os termos vetados, e renderiza páginas em PNG para inspeção visual. Esse script é o "teste" de cada tarefa.

**Tech Stack:** LaTeX/Beamer (pdflatex + latexmk, MiKTeX local), TikZ, pgfplots 1.18, listings, booktabs, tcolorbox, poppler (`pdftoppm`, `pdffonts`), Git Bash.

**Spec:** `docs/superpowers/specs/2026-10-25-apresentacao-defesa-design.md`. Leia o spec inteiro antes da Tarefa 1. A tabela "Roteiro aprovado" dele diz o conteúdo e a fonte no relatório de cada slide.

## Global Constraints

- Conteúdo em português, frases curtas, sem parágrafos nos slides; nunca "backend", sempre "SGBD".
- Sem "cara de IA": nada de autoelogio ("inovador", "robusto", "poderoso") nem travessões em série.
- Vocabulário idêntico ao relatório: "ingênua (*naive*)" × "em lote (*batch*)"; "multifonte" × "combinado"; "materialização" × "fluxo (*streaming*)"; "arquivo de importação" e "arquivo de conexão"; QP1–QP6.
- Todo número sai de `docs-tcc/chapters/ch6avaliacao.tex` (v2.3), com a campanha declarada quando houver comparação de tempo ou memória; nunca misturar campanhas com e sem instrumentação de memória na mesma comparação.
- Os dados da avaliação são **sintéticos** (§5.1); não repetir o "dados reais" de `consideracoes.tex:17`.
- Cores: azul `#0B3D6E`; borda dos painéis `#C9D6E3`; fundo da faixa de origem `#F1F5F9`; texto `#1D1D1F`.
- Rodapé (texto exato): `Lucas Bueno Cesario · Polyglot Import CSV · Ciência da Computação · UFSC`.
- Capa (textos exatos): "Universidade Federal de Santa Catarina · Centro Tecnológico" / "Departamento de Informática e Estatística · Ciência da Computação" / "Polyglot Import CSV" / "Uma solução para importação de documentos CSV para múltiplos bancos de dados" / "Lucas Bueno Cesario" / "Orientador: Prof. Dr. Ronaldo dos Santos Mello" / faixa inferior: "Defesa de Trabalho de Conclusão de Curso" à esquerda e "Florianópolis, 2026" à direita.
- Sem transições, animações de PDF ou multimídia: só sobreposições do Beamer (`\pause`, `\only`, `\onslide`).
- Nenhum texto do corpo menor que `\scriptsize`: `\tiny` é proibido nas seções.
- Frames com `lstlisting` ou `verbatim` levam `[fragile]`.
- Git: um commit por tarefa, em português, com o trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, e `git push` logo depois (política do autor). Use `rtk git ...`.
- Diretório de trabalho de todos os comandos: `docs-tcc/apresentacao/` (a partir da raiz do repositório), no branch `apresentacao-defesa`.

## Review Focus

- **Conteúdo atrás do rodapé ou do cabeçalho:** texto ou figura que transborda a área útil nem sempre gera "Overfull" no log. A Tarefa 7 renderiza e inspeciona todas as páginas.
- **Legibilidade no projetor e na tela compartilhada:** fonte pequena demais em código e tabelas. Coberto pelo veto a `\tiny` no `verificar.sh` (Tarefa 1) e pela inspeção a 80 dpi de cada tarefa.
- **Fontes não embutidas:** o PDF pode abrir com fontes trocadas no computador da sala. A Tarefa 7 exige `pdffonts` com "emb = yes" em todas as linhas.
- **Acentos dentro de `lstlisting`:** o listings em pdflatex quebra "ç/ã/é" sem `literate`. A Tarefa 1 define `literate` nos estilos, e a Tarefa 3 confere no PNG um trecho com acento.
- **Sobreposições no compartilhamento remoto:** cada passo de revelação é uma página do PDF, e isso funciona em qualquer visualizador. O veto a `\trans`/`\movie`/`\sound` no `verificar.sh` garante que nada depende de recurso do visualizador.

---

### Task 1: Tema, moldura e verificação

**Files:**
- Create: `docs-tcc/apresentacao/beamerthemeufsc.sty`
- Create: `docs-tcc/apresentacao/apresentacao.tex`
- Create: `docs-tcc/apresentacao/secoes/1-introducao.tex`, `2-fundamentacao.tex`, `3-proposta.tex`, `4-avaliacao.tex`, `5-conclusao.tex`, `6-cartas.tex` (por ora, só a chamada de roteiro de cada bloco; `6-cartas.tex` vazio)
- Create: `docs-tcc/apresentacao/verificar.sh`
- Modify: `docs-tcc/.gitignore` (acrescentar `*.nav`, `*.snm`, `*.vrb`, `apresentacao/apresentacao.pdf`, `apresentacao/render/`)

**Interfaces:**
- Produces (usadas por todas as tarefas seguintes):
  - `\usetheme{ufsc}` com `\documentclass[aspectratio=169,11pt]{beamer}`; `babel` com `brazil`, `inputenc` utf8, `fontenc` T1.
  - Cores `ufscazul`, `ufscborda`, `ufscfundo`, `ufsctexto` (valores nas Global Constraints).
  - `\graphicspath{{../images/}{../}}`: `\includegraphics{figure7-overview}` e `\includegraphics{brasao_UFSC_vertical_sigla}` funcionam.
  - `\capa`: frame `[plain]` com a capa.
  - `\roteiro{n}`: com `n = 0`, o frame numerado "Roteiro" com os cinco blocos em pé de igualdade. Com `n` de 1 a 5, um frame `[noframenumbering]` com o bloco `n` em `ufscazul` negrito e os demais em cinza. Blocos: 1 Introdução; 2 Fundamentação e trabalhos relacionados; 3 Proposta; 4 Avaliação; 5 Conclusão.
  - `\fechamento`: frame `[plain]` "Obrigado! Perguntas?" com a arte da capa. Escreve no log `FECHAMENTO-NUMERO=<número do frame>` (`\typeout`).
  - `\cartasnamanga`: chama `\appendix`. A partir dali, o rodapé mostra `B<n>` no lugar do número (`appendixnumberbeamer`, já instalado).
  - Ambiente `painel`: `\begin{painel}{<título>}{<subtítulo>} ... \end{painel}`. Caixa (tcolorbox) com borda fina `ufscborda`, título em `ufscazul` negrito e subtítulo em cinza.
  - `\destaque{<texto>}`: `ufscazul` + negrito.
  - Estilos de listings `jsonslide` e `bashslide`: mono, `\scriptsize` ou maior, com `literate` para á é í ó ú â ê ô ã õ ç (minúsculas e maiúsculas).
  - `bash verificar.sh <corpo> <cartas> [página ...]`. Compila com `latexmk -pdf -interaction=nonstopmode -halt-on-error apresentacao.tex`. Falha (exit 1) se a compilação falhar; se `FECHAMENTO-NUMERO` ≠ `<corpo>`; se o número de `\begin{frame}` em `secoes/6-cartas.tex` ≠ `<cartas>`; se `backend`, `\tiny`, `\trans`, `\movie` ou `\sound` aparecerem em `apresentacao.tex`, `beamerthemeufsc.sty` ou `secoes/*.tex` (sem diferenciar maiúsculas em "backend"); se o log tiver `Overfull \hbox` ou `Overfull \vbox`. Renderiza cada `[página]` pedida com `pdftoppm -png -r 80 -f P -l P` em `render/pagina-P.png`. Imprime `OK corpo=<n> cartas=<m>` no fim.
- Geometria do cabeçalho e do rodapé (do mockup aprovado; L = largura do slide, 160 mm em 16:9):

```
cabeçalho: altura 0,105·L, a partir do topo
  faixa azul = polígono (0,0) → (L − 0,10·L, 0) → (L − 0,14·L, altura) → (0, altura)
  título do frame em branco, \Large, centrado na vertical, recuo esquerdo 0,04·L
  canto branco = faixa de 0,11·L à direita; brasão colorido (PDF) com altura 0,086·L, centrado nele
  SEM linha nenhuma abaixo do cabeçalho
rodapé: faixa azul de altura ~0,032·L no pé; texto branco \scriptsize;
  rodapé fixo à esquerda (Global Constraints), número do frame (ou B<n>) à direita
```

- [ ] **Step 1:** Criar o esqueleto (`apresentacao.tex`, seções com `\roteiro{n}`, `.gitignore`) e o `verificar.sh`. Em `apresentacao.tex`, a ordem é: `\capa`, `\roteiro{0}`, `\input` das seções 1 a 5 (cada uma começa com `\roteiro{n}`), `\fechamento`, `\cartasnamanga`, `\input{secoes/6-cartas}`.
- [ ] **Step 2:** Rodar `bash verificar.sh 3 0 1 2 3`. Esperado: FALHA, porque o tema ainda não existe.
- [ ] **Step 3:** Implementar o `beamerthemeufsc.sty` com as interfaces acima.
- [ ] **Step 4:** Rodar `bash verificar.sh 3 0 1 2 3 4`. Esperado: `OK corpo=3 cartas=0`. A página 1 é a capa, a 2 o roteiro e a 3 o `\roteiro{1}`, sem número no rodapé.
- [ ] **Step 5:** Abrir `render/pagina-1.png` e `render/pagina-2.png` e comparar com os mockups do spec (`roteiro-v1.html`, `visual-style-c-brasao.html`). Conferir: corte diagonal; brasão colorido no canto branco, sem linha abaixo do cabeçalho; rodapé azul com o texto exato; capa com todos os textos das Global Constraints.
- [ ] **Step 6:** Commit `feat(apresentacao): tema UFSC, moldura e script de verificacao` e push. Conferir com `git status` que nenhum artefato de build (`*.aux`, `*.nav`, `apresentacao.pdf`, `render/`) entrou.

### Task 2: Introdução, fundamentação e trabalhos relacionados (slides 3–7)

**Files:**
- Modify: `docs-tcc/apresentacao/secoes/1-introducao.tex` (slides 3, 4, 5)
- Modify: `docs-tcc/apresentacao/secoes/2-fundamentacao.tex` (slides 6, 7)

**Interfaces:**
- Consumes: `\roteiro`, `painel`, `\destaque`, `verificar.sh` (Tarefa 1).

- [ ] **Step 1:** Escrever os slides 3–6 conforme o roteiro do spec. Slide 3 usa `figure1-polyglot-ecommerce`. Slide 5 traz o objetivo geral e os quatro específicos de `ch1introducao.tex` (§1.2), resumidos, no presente. Slide 6 tem cinco `painel`, um por paradigma, com o SGBD de cada um; as figuras 3–6 só entram se ficarem legíveis.
- [ ] **Step 2:** Escrever o slide 7 com esta tabela (booktabs; ✓ = o Cap. 3 afirma; ✗ = o Cap. 3 nega; — = o Cap. 3 não diz):

| Trabalho | Foco | Destinos | Entrada CSV | Mapeamento declarativo validado | Revisão sem gravar |
|---|---|---|---|---|---|
| Importadores nativos (§3.1) | importação | um SGBD por vez | ✓ (Redis: protocolo bruto) | — | — |
| ArangoDB / `arangoimport` | importação | um SGBD multimodelo | ✓ | — | — |
| dbcrossbar | migração | PostgreSQL, BigQuery, nuvem | ✓ | — | — |
| Hackolade | modelagem visual | dezenas de alvos | ✗ (não importa dados) | — | — |
| Frameworks de acesso (Pereira et al., 2025; Sachdeva et al., 2024) | acesso em tempo de execução | vários SGBDs | ✗ | — | — |
| *Polystores* (BigDAWG) | consulta federada | vários SGBDs | — | — | — |
| **Polyglot Import CSV** | importação | cinco SGBDs, cinco paradigmas | ✓ | ✓ (JSON Schema) | ✓ (`--dry-run`) |

  Se a tabela não couber legível, divida em duas sobreposições (linhas de terceiros, depois a linha da ferramenta).
- [ ] **Step 3:** Conferir cada célula contra `chapters/ch3relacionados.tex`. Uma célula sem respaldo no texto vira "—".
- [ ] **Step 4:** Rodar `bash verificar.sh 8 0 4 5 6 7 8 9`. Esperado: `OK corpo=8 cartas=0`. Inspecionar os PNGs: no máximo uns 5 itens por slide, frases curtas, nada encostando no rodapé.
- [ ] **Step 5:** Commit `feat(apresentacao): introducao, fundamentacao e trabalhos relacionados` e push.

### Task 3: Proposta, parte 1 (slides 8–12)

**Files:**
- Modify: `docs-tcc/apresentacao/secoes/3-proposta.tex`

**Interfaces:**
- Consumes: `painel`, `\destaque`, `jsonslide`, `verificar.sh` (Tarefa 1).

- [ ] **Step 1:** Slide 8 usa `figure7-overview`. Slide 9 traz um trecho curto **fiel** de `data/ecommerce/import_config.json` (as mesmas chaves do arquivo real; a parte cortada termina em `...`), com uma frase dizendo o que o trecho mostra. Slide 10 redesenha em TikZ, na horizontal e com revelação passo a passo, o fluxo da Figura 10 (`docs-tcc/images/figure10-config-pipeline.mmd` é a fonte), deixando claro que nada é gravado se houver erro. Slide 11 mostra os quatro tipos de evento (tabela de `ch4proposta.tex`, `tab:eventos-ecommerce`) e multifonte × combinado.
- [ ] **Step 2:** Slide 12 segue a seção "Slide 12 — conteúdo fiel ao §4.3.3" do spec. Layout do mockup: faixa de cima com o fio condutor (`user1` e `Product2`); cinco `painel` lado a lado (PostgreSQL relacional, MongoDB documento, Cassandra colunar, Redis chave-valor, Neo4j grafo), revelados um por vez (`\onslide<k->`). Cada painel indica a sua fonte: PostgreSQL `inventory` ← `stock`; MongoDB `product_catalog` ← `stock`; Cassandra `user_activity_log` ← as quatro fontes (partição do `user1`); Redis `shopping_cart` ← `add_to_cart`; Neo4j `(:User)-[:PURCHASED {order_number: "ORD1"}]->(:Product)` ← `stock` e `purchase`. Os valores e nomes de campo saem de `tab:pg-inventory`, `lst:mongo-doc`, `tab:cassandra-particao`, `lst:redis-pares` e `lst:neo4j-grafo`, abreviados com `...` e nunca renomeados.
- [ ] **Step 3:** Rodar `bash verificar.sh 13 0` e depois renderizar as páginas dos slides 8–12, incluindo o último passo de revelação do slide 12. A página exata depende das sobreposições; use `pdfinfo` e o `.nav` para achá-la. Esperado: `OK corpo=13 cartas=0`.
- [ ] **Step 4:** Inspecionar os PNGs. O trecho JSON do slide 9 está legível; um acento num comentário ou num texto ao redor (se houver) sai certo; o último passo do slide 12 mostra os cinco painéis sem cortar texto.
- [ ] **Step 5:** Commit `feat(apresentacao): proposta - configuracao, cenario e os cinco modelos` e push.

### Task 4: Proposta, parte 2 (slides 13–16)

**Files:**
- Modify: `docs-tcc/apresentacao/secoes/3-proposta.tex`

**Interfaces:**
- Consumes: `bashslide`, `verificar.sh` (Tarefa 1).

- [ ] **Step 1:** Slide 13 redesenha em TikZ, na horizontal e passo a passo, o algoritmo da Figura 11 (fonte: `docs-tcc/images/figure11-import-algorithm.mmd`): verificação dos SGBDs → leitura → mapeamento → escrita. Slide 14 traz o comando da CLI de `ch4proposta.tex` §4.3.4 (`python -m polyglotimportcsv --config ... --dbms-config ... --dry-run`), com cada parte explicada em uma linha, e as contagens de `tab:dryrun`. Slide 15 apresenta os conceitos ingênua × em lote e materialização × fluxo (§4.5), sem números, que ficam para a avaliação. Slide 16 mostra as capturas `figure12-gui-ocioso` a `figure16-gui-verificacao`, uma ou duas por passo de revelação.
- [ ] **Step 2:** Rodar `bash verificar.sh 17 0` e renderizar as páginas dos slides 13–16. Esperado: `OK corpo=17 cartas=0`.
- [ ] **Step 3:** Inspecionar: as capturas da GUI legíveis a 80 dpi; o comando inteiro visível, sem quebra no meio de uma opção.
- [ ] **Step 4:** Commit `feat(apresentacao): proposta - algoritmo, execucao e interface grafica` e push.

### Task 5: Avaliação (slides 17–21)

**Files:**
- Modify: `docs-tcc/apresentacao/secoes/4-avaliacao.tex`

**Interfaces:**
- Consumes: `verificar.sh` (Tarefa 1); preâmbulo com `pgfplots` (`compat=1.18`), `siunitx` e o formato numérico brasileiro, os mesmos do `docs-tcc/main.tex`. Se faltar algo no tema, acrescente lá.

Fontes no `chapters/ch6avaliacao.tex` (linha do `\label` na v2.3): `tab:ambiente-sgbds` 108, `tab:naive-optimized` 150, `fig:naive-optimized` 193, `tab:fases-100k` 213, `tab:escrita-sgbd` 240, `fig:throughput-sgbd` 276, `tab:multi-combined` 296, `tab:memoria` 362, `fig:memoria` 404, `tab:tempo-execucao` 419, `fig:tempo-execucao` 458, `tab:tradeoff-memoria` 480.

- [ ] **Step 1:** Slide 17 traz a metodologia (§5.1, §5.2): gerador sintético determinístico, volumes, repetições e mediana, ambiente (`tab:ambiente-sgbds`) e a lista QP1–QP6 com os nomes do capítulo.
- [ ] **Step 2:** Slides 18–21 refazem os gráficos em pgfplots com as coordenadas **copiadas** do `.tex`, legíveis a distância (fonte maior, uma mensagem por gráfico, título que diz a conclusão). Slide 18 (QP4): `fig:naive-optimized`, com "~9×" em destaque. Slide 19 (QP1 e QP3): a escrita passa de 90% em 100 mil linhas (`tab:fases-100k`) e a vazão por SGBD (`fig:throughput-sgbd`); o crescimento com o volume (`fig:tempo-execucao`) entra como passo de revelação. Slide 20 (QP2): o empate no tempo total, a leitura 2× mais rápida e 5–6% menos memória (`tab:multi-combined`), como tabela pequena. Slide 21 (QP5 e QP6): `fig:memoria`, pico 12,5× menor em 100 mil linhas, a +10% de tempo, constante no tamanho do arquivo. Cada gráfico declara a campanha numa linha de "Fonte:" (por exemplo, "campanha sem instrumentação de memória"). Em `ymode=log`, use `point meta=explicit symbolic` com o rótulo explícito.
- [ ] **Step 3:** Conferir cada número que aparece nos slides 17–21 contra o `.tex`: para cada um, um `grep -n` em `chapters/ch6avaliacao.tex` precisa achar o mesmo valor. Lembre que o `.tex` usa `{,}` como vírgula decimal: 12,5 aparece como `12{,}5`.
- [ ] **Step 4:** Rodar `bash verificar.sh 22 0` e renderizar as páginas dos slides 17–21. Esperado: `OK corpo=22 cartas=0`. Inspecionar: rótulos dos eixos legíveis, nenhuma legenda sobreposta às barras.
- [ ] **Step 5:** Commit `feat(apresentacao): avaliacao de desempenho (QP1-QP6)` e push.

### Task 6: Conclusão, fechamento e cartas na manga (slides 22–24, B1–B7)

**Files:**
- Modify: `docs-tcc/apresentacao/secoes/5-conclusao.tex`
- Modify: `docs-tcc/apresentacao/secoes/6-cartas.tex`

**Interfaces:**
- Consumes: `\fechamento` e `\cartasnamanga` (já chamados no `apresentacao.tex`), `painel`, `verificar.sh` (Tarefa 1).

- [ ] **Step 1:** Slide 22 retoma os quatro objetivos específicos, um a um, cada um com a evidência no trabalho. Slide 23 segue a seção "Slide 23 — resolve × em aberto" do spec e cita "(ARAUJO; SILVA; MELLO, 2025)"; precisa deixar explícito que o artigo trata de evolução de esquemas e o trabalho, de importação. Slide 24 traz o Elasticsearch como sexto paradigma (motor de busca), a edição da configuração na GUI, volumes de milhões de linhas e, no máximo, mais dois itens de `chapters/ch5futuros.tex`.
- [ ] **Step 2:** Antes de escrever B1 e B2, investigar no código (`src/polyglotimportcsv/`) o que acontece quando um SGBD falha no meio da importação (os outros ficam gravados? há rollback?) e quando um valor do CSV não converte para o tipo nativo. Escrever B1 e B2 só com o que o código confirma, citando arquivo e função no relatório da tarefa. Se o comportamento não for claro, o slide diz o que se sabe e a dúvida vai para o relatório da tarefa, sem suposição.
- [ ] **Step 3:** Escrever B3–B7 conforme o roteiro do spec. B4 mostra os cinco importadores nativos do §3.1 (`COPY`, `redis-cli --pipe`, `mongoimport`, `cqlsh`/`sstableloader`, `neo4j-admin`) e o que cada um exige. B5 traz o limite do Cassandra (heap de 1 GB numa VM de ~3,8 GB, §5.2/§5.4.1). B6 traz as ameaças de `sec:ameacas-validade`. B7 traz as referências em ABNT, só das obras citadas nos slides; os dados bibliográficos saem de `docs-tcc/references.bib`, e o de Araujo et al. sai do spec (ERBD 2025, DOI 10.5753/erbd.2025.7322).
- [ ] **Step 4:** Rodar `bash verificar.sh 25 7` e renderizar as páginas dos slides 22–25 e das cartas B1 e B7. Esperado: `OK corpo=25 cartas=7`. Conferir: o rodapé das cartas mostra "B1" … "B7"; o fechamento repete a arte da capa.
- [ ] **Step 5:** Commit `feat(apresentacao): conclusao, fechamento e cartas na manga` e push.

### Task 7: Revisão final e PDF de entrega

**Files:**
- Create: `docs-tcc/TCC2-PolyglotImportCSV-Apresentacao-v1.0.pdf` (cópia de `apresentacao/apresentacao.pdf`)
- Modify: qualquer seção em que a revisão encontrar problema

- [ ] **Step 1:** Rodar `bash verificar.sh 25 7` e renderizar **todas** as páginas: `pdftoppm -png -r 80 apresentacao.pdf render/todas`.
- [ ] **Step 2:** Inspecionar todas as páginas. Nada atrás do cabeçalho ou do rodapé; nenhum slide com mais de uns 5 itens ou com frase longa; nenhuma figura complexa sem revelação; o visual igual em todos os slides.
- [ ] **Step 3:** Rodar `pdffonts apresentacao.pdf`. Esperado: "yes" na coluna `emb` de todas as linhas.
- [ ] **Step 4:** Rodar `pdfinfo apresentacao.pdf`. Esperado: `Page size: 453.54 x 255.12 pts` (160 mm × 90 mm, 16:9; tolerância de 1 pt).
- [ ] **Step 5:** Corrigir o que as etapas 2–4 apontarem, rodar `bash verificar.sh 25 7` de novo e copiar o PDF para `docs-tcc/TCC2-PolyglotImportCSV-Apresentacao-v1.0.pdf`.
- [ ] **Step 6:** Commit `docs(tcc): apresentacao da defesa v1.0 (PDF de entrega)` e push. Conferir com `git status` que só fontes e o PDF de entrega foram versionados.
