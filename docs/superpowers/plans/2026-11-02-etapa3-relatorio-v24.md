# Etapa 3: relatório v2.4 — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reescrever o relatório para que ele descreva a versão 3.0.0, com as 26 correções do orientador, as convenções de vocabulário, as figuras novas e refeitas e os números da campanha 3.0.0. Ao final, gerar o PDF v2.4 e o diff v2.3→v2.4.

**Architecture:** O trabalho é só de texto, figuras e PDFs em `docs-tcc/`; o código da 3.0.0 não muda. Cada tarefa reescreve uma parte do relatório, confere cada afirmação contra o código e cada número contra os CSVs, compila e lê as páginas renderizadas. Os exemplos saem de execuções reais em cópias temporárias, no rascunho da sessão.

**Tech Stack:** LaTeX abnTeX2 com latexmk/pdflatex (MiKTeX), pgfplots e siunitx; Mermaid CLI 11.4.0 via npx com o Chrome local; latexdiff do MiKTeX; Python do venv (`.venv/Scripts/python.exe`) com pymupdf para localizar páginas; PySide6 para as capturas da GUI.

**Spec:** `docs/superpowers/specs/2026-10-30-revisao-ronaldo-v22-design.md` (mapa das 26 anotações, vocabulário e figura nova). Ele complementa `docs/superpowers/specs/2026-10-27-fluxo-unico-validacao-previa-design.md` (seção "Relatório v2.4"). Onde os dois divergem, vale o de 2026-10-30.

## Global Constraints

- **Ramo:** `fluxo-unico`. Cada commit leva `rtk`, termina com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` e é seguido de `rtk git push` (do `fluxo-unico`). O `main` local já tem o merge da etapa 2 (`364c911`) e **não é enviado** até o fim da etapa 4, por ordem do autor (2026-11-02). Mensagens como `docs(tcc): ...`, em português.
- **Preparar só caminhos explícitos.** Nunca commitar `docs-tcc/TCC2-PolyglotImportCSV-Report-v2.2-REVISADO.pdf` nem nada de `docs-tcc/relacionados/EQD2026_Lilian/`.
- **Compilação:** `cd docs-tcc && latexmk -pdf -interaction=nonstopmode main.tex`. Sucesso: `main.pdf` atualizado, `grep -c "undefined" main.log` igual a 0 e nenhum `Overfull \hbox` visível no PDF nas páginas da tarefa.
- **Regras do orientador:**
  - legenda de figura embaixo e título de tabela em cima, com "Fonte: Elaborado pelo autor (2026)." embaixo;
  - uma frase de introdução nomeia cada listagem ("a Listagem~\ref{...} mostra ...") e cada tabela;
  - trechos de JSON terminam em `...`, e o texto depois da listagem diz que há mais conteúdo;
  - jargão definido no primeiro uso; as partes de cada comando mostrado são explicadas;
  - nenhuma prosa sobre o histórico de versões do relatório;
  - dados em tabela formatada, nunca CSV cru;
  - um `tabular` nunca fica dentro de um grupo de tamanho de fonte (`{\small ...}`), porque isso mata os *struts* das linhas; para ganhar largura, usar `\setlength{\tabcolsep}{3pt}`.
- **Vocabulário** (design de 2026-10-30, relatório inteiro):
  - "etapa de validação" (1, 2 e 3) no lugar de "camada"; ficam "camada de observabilidade" e "camada de acesso da aplicação";
  - "passo" para os passos da Figura 11 e do fluxo de execução;
  - "fluxo" no lugar de "algoritmo"; "leitura em blocos" para a leitura em pedaços;
  - "cenário exemplo", exatamente assim;
  - "SGBD destino" para os SGBDs que recebem os dados;
  - "gravar" no lugar de "materializar" quando o sentido é guardar dados num SGBD. "Materialização" só nomeia o modo histórico (§4.5.1 e Cap. 5);
  - "SGBD", nunca o termo em inglês que o orientador rejeitou.
- **Nomes de função** (`config_parser.merge_configs`, `stream_runner`, ...) não aparecem no texto corrido. Nomes de opção da CLI e de campo do JSON continuam, porque o usuário os digita.
- **Rótulos LaTeX não mudam** (`sec:algoritmo`, `sec:modelos-execucao`, `fig:import-algorithm`, ...), mesmo quando o título muda. Remissões só por `\ref`, nunca "Figura 12" escrito à mão.
- **Números:** os da 3.0.0 vêm de `benchmarks/v3/` (ver `benchmarks/README.md`, "Campaigns of the current version"); os históricos (QP4, QP5/QP6, materialização), de `benchmarks/`, `benchmarks/timings/`, `benchmarks/naive/` e `benchmarks/timings-naive/`. Tempo só de campanha sem tracemalloc e memória só de campanha com tracemalloc, nunca na mesma linha. Cada legenda declara a pasta. Número decimal com vírgula (`209{,}51`) e milhar com `\num{}`.
- **Afirmações sobre comportamento** são conferidas no código da 3.0.0 no momento de escrever. A prova (arquivo:linha) vai para o ledger.
- **Exemplos** (`each`, `csv_columns`, contagens, mensagens de erro, tipos inferidos) saem de execuções reais. As cópias alteradas ficam em `<rascunho>/etapa3/` e nunca são versionadas. `<rascunho>` é o diretório de rascunho da sessão.
- **Docker:** os cinco SGBDs estão no ar. Parar, iniciar ou reiniciar qualquer contêiner só com o OK explícito do autor.
- **Execuções longas** (capturas, compilação do diff) rodam em primeiro plano. Com o Docker ligado, a máquina tem uns 700 MB livres, e o Claude Code encerra shells ociosos em segundo plano.

## Review Focus

1. **Afirmação que o código não sustenta.** Os pontos mais arriscados:
   - o que a ferramenta cria em cada SGBD destino antes de gravar;
   - que nada é gravado se qualquer etapa de validação falhar, inclusive as referências pendentes;
   - que a inferência lê o arquivo inteiro;
   - os critérios de deduplicação;
   - que `--source` se repete;
   - que a ferramenta nunca inicia SGBDs.

   Cada uma tem uma linha no ledger com arquivo:linha (Tasks 2 a 8).
2. **Número que não sai das campanhas certas**, ou que mistura campanhas com e sem tracemalloc. O script de conferência da Task 8 recalcula cada número do Cap. 4 (§4.5) e do Cap. 5 a partir dos CSVs.
3. **Termo antigo fora do Cap. 4** (Resumo, Abstract, Caps. 1, 2, 3, 6, considerações, apêndices, legendas). O portão de `grep` da Task 10 cobre o relatório inteiro.
4. **Figura ilegível ou alta demais na página.** O script de legibilidade da Task 1 mede a fonte efetiva de cada figura Mermaid refeita.
5. **Remissão quebrada ou número de figura escrito à mão.** É coberto por "undefined = 0" em cada compilação, mais um `grep` por "Figura [0-9]" e "Tabela [0-9]" no texto, na Task 11.

---

### Task 1: Figuras 8, 10, 11 e a figura nova

**Files:**
- Modify: `docs-tcc/images/figure8-import-schema.mmd`, `figure10-config-pipeline.mmd`, `figure11-import-algorithm.mmd`
- Create: `docs-tcc/images/figure11b-import-example.mmd` (e `figure11c-import-example.mmd`, se a figura nova for dividida)
- Regenerate: os `.png` correspondentes

**Interfaces:**
- Produces: os arquivos de imagem e a largura de inclusão de cada um. As Tasks 4, 5 e 6 incluem as figuras com essas larguras e escrevem o texto que as acompanha. O rótulo da figura nova é `fig:import-example` (`fig:import-example-b` para a segunda parte).

- [ ] **Step 1: Medir a legibilidade atual**

Escrever `<rascunho>/fig_font.py`. Ele recebe pares `png largura_em_cm` e imprime, para cada um, a fonte efetiva e a altura na página:

```
fonte_pt = 16 * (largura_cm * 28.4528) / (largura_png_px / 2)
altura_pt = (altura_png_px / largura_png_px) * largura_cm * 28.4528
```

O 16 é o tamanho padrão da fonte do Mermaid em px, e o 2 é o `-s 2` da renderização. A largura do texto é 16 cm (A4 com margens de 3 e 2 cm), e a altura útil é 24,7 cm (703 pt).
Run: `.venv/Scripts/python.exe <rascunho>/fig_font.py docs-tcc/images/figure8-import-schema.png 16 docs-tcc/images/figure10-config-pipeline.png 14 docs-tcc/images/figure11-import-algorithm.png 12`
Expected: as três ficam abaixo de 9 pt (8: cerca de 6,2; 10: cerca de 7,5; 11: cerca de 4,7). É esse o problema que o orientador apontou na Figura 8.

**Critério de aceite de cada figura refeita:** fonte efetiva ≥ 9 pt e altura ≤ 600 pt (cerca de 85% da altura útil, para caber com a legenda). Se não couber, dividir em duas, que é a preferência do orientador.

- [ ] **Step 2: Execuções reais para a figura nova**

Em `<rascunho>/etapa3/`, com o venv e as configurações de `data/ecommerce/`, fazer o seguinte e registrar cada comando e sua saída em `<rascunho>/etapa3/execucoes.md`:
1. **Caminho bem-sucedido:** `--dry-run` multifonte do cenário exemplo. Guardar as contagens por entidade, os nomes `orders_state_*` e os tipos inferidos que a saída mostrar.
2. **Linha acompanhada:** a mesma linha de `stock` que a §4.3.3 acompanha (localizá-la no texto da §4.3.3).
3. **Erros induzidos**, cada um numa cópia da configuração ou do CSV:
   - valor que não converte (o `purchase_bad.csv` do rascunho, com `order_date` `2023-13-45 99:99:99`);
   - chave vazia;
   - referência pendente, por exemplo um `product_id` de `purchase` que não existe em `stock`.

   Cada um com a mensagem exata impressa e o código de saída 1.

Expected: o caminho bem-sucedido termina com código 0, e cada erro induzido, com código 1, sem conectar a nenhum SGBD.

- [ ] **Step 3: Refazer as figuras**

- **Figura 8:** a árvore do arquivo de importação num arranjo vertical (`flowchart TB`), ou dividida em duas (raiz e `sources`; entidade e colunas). O conteúdo é o atual, mais o que a 3.0.0 mudou no *schema*: `target_suffix` com `{value}`. Os asteriscos continuam marcando só o que o JSON Schema exige.
- **Figura 10:** as três etapas de validação da 3.0.0, todas antes de gravar:
  - etapa 1: JSON Schema dos dois arquivos;
  - etapa 2: consistência entre os arquivos;
  - etapa 3: cabeçalhos, depois a leitura de inferência e a leitura de validação, com conversão, `db_type`, chave vazia, referência pendente e fonte ausente no combinado.

  Usar "Etapa 1/2/3 de validação", e nenhum nome de função.
- **Figura 11:** os passos do fluxo de execução da 3.0.0: carregar e validar a configuração; conferir os cabeçalhos; verificar os SGBDs (`--check-dbms`); leitura de inferência; leitura de validação; preparar cada SGBD destino; leitura de gravação em lotes; fechar (recriar as FKs) e as métricas. Usar "passo", e nenhum "algoritmo".
- **Figura nova (`figure11b-import-example`):** o conteúdo mínimo do design ("Figura nova"), com os valores do Step 2. Os erros induzidos ficam num ramo à parte, marcado como "exemplo induzido". Se ficar densa, dividir em duas: até a validação, e a gravação.

Renderizar cada uma com a receita da v2.3:

```bash
printf '{"executablePath": "C:/Program Files/Google/Chrome/Application/chrome.exe"}' > "<rascunho>/puppeteer.json"
printf '{"theme": "default"}' > "<rascunho>/mermaid.json"
cd docs-tcc/images
npx -y @mermaid-js/mermaid-cli@11.4.0 -p "<rascunho>/puppeteer.json" -c "<rascunho>/mermaid.json" \
  -b white -s 2 -i <figura>.mmd -o <figura>.png
```

- [ ] **Step 4: Conferir**

Run: `fig_font.py` nas quatro (ou cinco) com as larguras de inclusão escolhidas (registrar no ledger: figura → largura).
Expected: todas ≥ 9 pt e ≤ 600 pt de altura. Depois abrir cada PNG com a ferramenta Read: nenhum texto cortado, tema e cores iguais aos das Figuras 7 e 9, e cada valor da figura nova igual a `execucoes.md`.

- [ ] **Step 5: Commit**

```bash
rtk git add docs-tcc/images/figure8-import-schema.mmd docs-tcc/images/figure8-import-schema.png docs-tcc/images/figure10-config-pipeline.mmd docs-tcc/images/figure10-config-pipeline.png docs-tcc/images/figure11-import-algorithm.mmd docs-tcc/images/figure11-import-algorithm.png docs-tcc/images/figure11b-import-example.mmd docs-tcc/images/figure11b-import-example.png
rtk git commit -m "docs(tcc): figuras 8, 10 e 11 refeitas para a 3.0.0 e figura nova do fluxo no cenario exemplo" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
rtk git push
```

(Se houver `figure11c-*`, incluí-la no `add`.)

---

### Task 2: §4.1 Visão Geral e o título do capítulo (itens 1, 2, 3, 4, 5, 6, 19)

**Files:**
- Modify: `docs-tcc/chapters/ch4proposta.tex` (`\chapter` e §4.1, de `sec:visao-geral` até `sec:config-format`)
- Modify: as remissões ao título do capítulo em outros arquivos, se houver (procurar "Proposta da Ferramenta" e "Proposta" em `docs-tcc/chapters/*.tex` e `main.tex`)

- [ ] **Step 1: Ler a §4.1 inteira e o `cli.py` da 3.0.0** (as opções, os padrões e `--source` com `multiple=True`)

- [ ] **Step 2: Execuções reais**

Registrar em `execucoes.md`:
- um comando com duas fontes substituídas, `--source purchase=<cópia> --source stock=<cópia>`, com `--dry-run`, terminando com código 0;
- `--check-dbms` com os cinco SGBDs no ar e a saída dele.

- [ ] **Step 3: Reescrever, item por item**

- **Item 1:** `\chapter{A Ferramenta PolyglotImportCSV}`. Conferir as remissões ao título.
- **Item 2:** novo parágrafo em "O processamento é disparado...".
- **Item 3:** sai da §4.1 o parágrafo dos dois modos de uso. O roteiro das seções e a frase que introduz o comando ficam.
- **Item 4:** `--source` não tem separador. A opção se repete, uma vez por fonte, e o exemplo do Step 2 aparece como listagem com frase de introdução.
- **Item 5:** a lista de opções não tem mais `--create-schema`. Uma frase diz o que a ferramenta prepara antes de gravar, conferido no código e registrado no ledger:
  - PostgreSQL: tabelas que faltam; as FKs são removidas antes da carga e recriadas no fim;
  - Cassandra: *keyspace* e tabelas;
  - Neo4j: restrições de unicidade;
  - MongoDB e Redis: nada;
  - o que já existe é reaproveitado.

  Se o detalhe couber melhor na §4.3, a §4.1 remete a ela.
- **Item 6:** novo parágrafo em "O segundo define como importar". Esse grupo agora tem `--chunk-size` (MB, padrão 8, de 8 a 256) e `--batch-size` (linhas, padrão 1024, de 1024 a 8192, limitado às linhas de um bloco).
- **Item 19, parte:** `--check-dbms` aparece entre as opções da linha de comando, com o comando completo uma vez. A GUI tem o botão "Verificar SGBDs".
- Nada de `--execution`, "materialização" ou "algoritmo" na §4.1.

- [ ] **Step 4: Conferir**

Run: compilação (Global Constraints); `rtk grep -n "create-schema\|--execution\|lgoritmo\|amada" docs-tcc/chapters/ch4proposta.tex`, olhando só as linhas da §4.1.
Expected: undefined = 0; nenhum dos termos na §4.1. Ler as páginas da §4.1 no PDF (pymupdf para achar a página e a ferramenta Read com `pages`): cada item do mapa atendido, a listagem com frase de introdução e as partes do comando explicadas.

- [ ] **Step 5: Commit** (`docs(tcc): secao 4.1 da 3.0.0 com --source repetida, bloco e lote e o que a ferramenta cria`)

---

### Task 3: §4.2 abertura, §4.2.1 e §4.2.2 (itens 3, 7, 8, 9, 10, 11, 12, 13)

**Files:**
- Modify: `docs-tcc/chapters/ch4proposta.tex` (de `sec:config-format` até `sec:arquivo-conexao`)

**Interfaces:**
- Consumes: `figure8-import-schema.png` e a sua largura de inclusão (Task 1, ledger)

- [ ] **Step 1: Ler o trecho e o *schema*** `src/polyglotimportcsv/schemas/import_config.schema.json` da 3.0.0

- [ ] **Step 2: Execução real do `csv_columns`**

Numa cópia da configuração, criar uma entidade com `auto_map` e `csv_columns`, por nome e por intervalo (`"1-5"`). Rodar `--dry-run` e registrar em `execucoes.md` o trecho JSON exato e as colunas que a entidade recebeu.
Expected: código 0, e as colunas recebidas batem com o intervalo e os nomes.

- [ ] **Step 3: Reescrever**

- **Item 3:** os modos multifonte e combinado passam a ser explicados junto do bloco `sources` (§4.2.1, "Raiz e bloco `sources`"), com o que diferencia cada um.
- **Item 7:** remover a frase "A separação atende a duas preocupações distintas: ... (desenvolvimento, testes, produção)."
- **Item 8:** incluir a Figura 8 refeita, com a largura do ledger, e ajustar o texto se a figura foi dividida.
- **Item 9:** "cenário exemplo" em todo o trecho.
- **Item 10:** listagem com o trecho real da coleção `orders` (`data/ecommerce/import_config.json`), o filtro `each` sobre `state` com `"target_suffix": "state_{value}"`, e as coleções geradas no `--dry-run` (`orders_state_CA`, ...; de `execucoes.md`). O texto diz ainda:
  - `{value}` é obrigatório no modelo;
  - o valor vazio não gera alvo;
  - um relacionamento não pode apontar para uma entidade dividida.

  Conferir as duas últimas regras no código (ledger).
- **Item 11:** listagem do Step 2, com frase de introdução.
- **Item 12:** "Os cinco blocos de SGBD destino".
- **Item 13:** remover ", sem nenhuma informação de mapeamento".

- [ ] **Step 4: Conferir**

Expected:
- compilação com undefined = 0;
- no trecho, nenhum "cenário de exemplo", "cenário de e-commerce" ou "materializ" no sentido de gravar;
- páginas lidas no PDF: cada item atendido, cada listagem com introdução e `...`, e a Figura 8 legível.

- [ ] **Step 5: Commit** (`docs(tcc): secao 4.2 com os modos junto de sources, exemplos de each e csv_columns e figura 8 maior`)

---

### Task 4: §4.2.3 e §4.2.4 (itens 14, 15, 16, 17)

**Files:**
- Modify: `docs-tcc/chapters/ch4proposta.tex` (de `sec:arquivo-conexao` até `sec:algoritmo`)

**Interfaces:**
- Consumes: `figure10-config-pipeline.png` e a sua largura (Task 1)

- [ ] **Step 1: Ler o trecho**, mais `config_parser.py`, `validation.py`, `data_validation.py` e a recusa sem SGBD destino no `runner`.

- [ ] **Step 2: Reescrever**

- **Item 14:**
  - `tab:partes-conexao` e `tab:partes-importacao`, na coluna "Obrigatória?" dos blocos de SGBD: "sim; ao menos os SGBDs de destino";
  - uma frase diz que o JSON Schema não exige nenhum bloco de SGBD e que a exigência de ao menos um é conferida na execução, que termina com código 1 (inclusive quando `--only` não deixa nenhum);
  - os asteriscos das Figuras 8 e 9 marcam só o que o *schema* exige.
- **Itens 15 e 17:** a §4.2.4 abre com a Figura 10 e descreve cada etapa de validação pelo que ela confere, sem nomes de função:
  - etapa 1: os dois JSON Schemas, com o erro citando o caminho JSON do campo (`... at $.sources.stock: ...`);
  - etapa 2: a consistência entre os arquivos;
  - etapa 3: cabeçalhos, leitura de inferência sobre o arquivo inteiro e leitura de validação com o mesmo código da gravação. A leitura de validação confere conversão, `db_type`, chave vazia, referência pendente e, no combinado, fonte que nunca aparece.

  Cada tipo de problema é reportado com a contagem e até 5 exemplos (arquivo, linha, coluna, valor). Qualquer problema termina com código 1 antes de gravar qualquer coisa. Conferir no código (ledger).
- **Item 16:** "etapa de validação" no lugar de "camada".
- A remissão à figura nova (`fig:import-example`), que mostra o caminho no cenário exemplo.

- [ ] **Step 3: Conferir**

Expected:
- compilação com undefined = 0;
- nenhum "amada" no sentido de validação no trecho;
- nenhum nome de função no texto corrido do trecho (procurar `\texttt{` seguido de um ponto entre identificadores, como `config_parser.`);
- páginas lidas: a Figura 10 no início da §4.2.4 e as tabelas sem linhas sobrepostas.

- [ ] **Step 4: Commit** (`docs(tcc): secoes 4.2.3 e 4.2.4 com as tres etapas de validacao da 3.0.0`)

---

### Task 5: §4.3 Fluxo de Execução da Importação (itens 18, 19, 20, 21, 22, 23)

**Files:**
- Modify: `docs-tcc/chapters/ch4proposta.tex` (de `sec:algoritmo` até `sec:observabilidade`)

**Interfaces:**
- Consumes: `figure11-import-algorithm.png`, `figure11b-import-example.png` e as larguras deles (Task 1); `execucoes.md` (Tasks 1 e 2)

- [ ] **Step 1: Ler o trecho**, mais `stream_runner.py`, os *sinks* (`ensure_partition`, `create_schema`, `close`), `row_shaping.py`, `run_example.sh` e `docker-compose.yml`.

- [ ] **Step 2: Execução real do `--dry-run`** multifonte e combinado do cenário exemplo, com a saída completa em `execucoes.md`, para a `tab:dryrun` e a §4.3.4.

- [ ] **Step 3: Reescrever**

- **Item 18:**
  - `\section{Fluxo de Execução da Importação}`, com o rótulo `sec:algoritmo` mantido;
  - a Figura 11 refeita;
  - o texto descreve as três leituras (inferência, validação, gravação) e usa "passo" e "fluxo";
  - a figura nova entra onde o texto acompanha a linha de `stock`, com a sua legenda e fonte.
- **Item 19:** a §4.3.1 diz que `--check-dbms` é uma opção da linha de comando (remissão à §4.1) e que a GUI tem o botão "Verificar SGBDs".
- **Item 20:** a legenda e o texto da `tab:csv-stock` remetem à tabela vertical do apêndice B, onde está `last_restock_date`. A tabela é feita na Task 9; usar `\ref` para o rótulo que ela vai ter, `tab:csv-stock-completa`.
- **§4.3.3:** "gravar" no lugar de "materializar" (por exemplo, na relação gravada no PostgreSQL). O que cada SGBD prepara antes de gravar fica conforme a Task 2.
- **Item 21:** remover a menção à extensão C do driver do Cassandra.
- **Item 22:** novo cabeçalho da `tab:dryrun` no sentido de "linhas a gravar (após os filtros)", com as contagens do Step 2. Um parágrafo curto sobre a deduplicação, conferido no código (ledger):
  - PostgreSQL: dentro do lote vence a última linha, e entre lotes, com `ON CONFLICT DO NOTHING`, vence a primeira; não prometer um critério único;
  - Neo4j: vence a primeira, e `MERGE`;
  - Cassandra e Redis: *upsert* pela chave;
  - MongoDB: nenhuma.
- **Item 23:** a ferramenta nunca inicia SGBDs. Quem os inicia é o usuário, com `docker compose up -d` (o `docker-compose.yml` acompanha os pacotes), com o `run_example.sh` (conferir o que ele faz antes de citar) ou com instalações nativas.
- O exemplo de CLI da §4.3.4 sem `--execution` e com as opções da 3.0.0.

- [ ] **Step 4: Conferir**

Expected:
- compilação com undefined = 0;
- no trecho, nenhum "lgoritmo", "amada" no sentido de validação, `--execution`, "create-schema" ou "extensão C";
- as contagens da `tab:dryrun` iguais a `execucoes.md`;
- páginas lidas: as figuras 11 e nova legíveis, perto do texto que as cita.

- [ ] **Step 5: Commit** (`docs(tcc): secao 4.3 vira fluxo de execucao com tres leituras, figura nova e dry-run da 3.0.0`)

---

### Task 6: §4.4 Observabilidade e §4.5 Estratégia de Escrita e Modelos de Execução (itens 24, 25, 26)

**Files:**
- Modify: `docs-tcc/chapters/ch4proposta.tex` (de `sec:observabilidade` até `sec:interface-grafica`)

- [ ] **Step 1: Ler o trecho**, mais `metrics.py` e `stream_source.chunk_rows`.

- [ ] **Step 2: Reescrever**

- **Item 24:** remover a frase das variáveis de ambiente do *log*.
- **Item 25:** as métricas por fase da 3.0.0: `infer` e `validate`, uma vez por importação, e `write`, uma por SGBD. Junto delas, o pico de memória por importação com tracemalloc e o porquê das duas campanhas.
- **Item 26:**
  - a §4.5.2 (`sec:modelos-execucao`) passa a descrever o fluxo como modelo de execução: leitura em blocos de `--chunk-size`, gravação em lotes de `--batch-size` limitados às linhas de um bloco, e a estimativa de linhas por bloco a partir de uma amostra das linhas;
  - uma tabela com o efeito do bloco (8, 64 e 256 MB; 100 mil linhas, multifonte), com pico de `v3/chunks-memory` e tempos de `v3/chunks-timings`, os mesmos números do `benchmarks/README.md`. O texto diz que, em 100 mil linhas, o bloco de 256 MB já lê cada fonte inteira;
  - a materialização entra na §4.5.1, ao lado de ingênua → em lote, como etapa do projeto avaliada no Cap. 5 e ausente da versão final;
  - a resposta ao orientador ("e se o arquivo não couber na memória?"): a materialização falharia por falta de memória, e é essa a motivação do fluxo.

- [ ] **Step 3: Conferir**

Expected:
- compilação com undefined = 0;
- os números da tabela de bloco iguais aos do `benchmarks/README.md` (o script da Task 8 também os confere);
- páginas lidas.

- [ ] **Step 4: Commit** (`docs(tcc): secoes 4.4 e 4.5 com as fases da 3.0.0, bloco e lote e a materializacao como historico`)

---

### Task 7: §4.6 Interface Gráfica: capturas novas e texto

**Files:**
- Regenerate: `docs-tcc/images/figure12-gui-ocioso.png` a `figure16-gui-verificacao.png`
- Modify: `docs-tcc/chapters/ch4proposta.tex` (§4.6)
- Modify, se preciso: `scripts/capture_gui_figures.py` (só se ele ainda usar algum controle removido)

- [ ] **Step 1: Ler a §4.6 e o `capture_gui_figures.py`.** Confirmar que o script não usa os controles removidos ("Execução", "Criar esquema"). Se usar, ajustá-lo e rodar `.venv/Scripts/python.exe -m pytest -q tests/test_gui_*.py` (esperado: tudo passa).

- [ ] **Step 2: Capturar as Figuras 12 a 15**

Run: `.venv/Scripts/python.exe scripts/capture_gui_figures.py`, da raiz.
Expected:
- as quatro primeiras capturas regravadas;
- o script recusa a Figura 16 se o MongoDB e o Neo4j estiverem no ar, por projeto;
- a Figura 15 mostra a mensagem de JSON Schema com o caminho JSON.

- [ ] **Step 3: PARAR e pedir o OK do autor para a Figura 16.**

Ela exige `docker compose stop mongodb neo4j`, a captura e `docker compose start mongodb neo4j` (com `docker ps` mostrando os cinco "healthy" de novo). Sem o OK, a Figura 16 fica como está, e isso é registrado no ledger.

- [ ] **Step 4: Atualizar o texto da §4.6**

- os campos "Bloco em MB (`--chunk-size`)" e "Lote (`--batch-size`)";
- nenhuma menção a "Execução" nem a "Criar esquema";
- a validação prévia da GUI descrita com as mesmas etapas, sem regra própria;
- o vocabulário.

- [ ] **Step 5: Conferir.** Abrir cada PNG com a ferramenta Read e conferir: sem os controles removidos, com os campos novos, e a Figura 15 com o caminho JSON. Depois, compilação com undefined = 0 e as páginas da §4.6 lidas.

- [ ] **Step 6: Commit** (`docs(tcc): capturas da GUI da 3.0.0 e texto da secao 4.6`), incluindo o script se ele mudou.

---

### Task 8: Cap. 5, Avaliação de Desempenho (`ch6avaliacao.tex`)

**Files:**
- Modify: `docs-tcc/chapters/ch6avaliacao.tex`

- [ ] **Step 1: Ler o capítulo inteiro**, o `benchmarks/README.md` (seção da versão atual e as ressalvas) e `src/polyglotimportcsv/benchmark_data.py` (`_split_rows`).

- [ ] **Step 2: Reescrever**

- **Abertura e QPs:**
  - QP1 passa a "inferência, validação e escrita";
  - QP5/QP6 viram histórico explícito;
  - entra a **QP7**: o custo das leituras de inferência e de validação e o pico de memória com blocos de 8, 64 e 256 MB.
- **§5.1.1:** N é o total de linhas dos quatro CSVs, dividido entre as fontes pelo gerador (em 100 mil: `stock` 11.609, `purchase` 38.833, `select_product` 25.445, `add_to_cart` 24.113). Não é o número de produtos.
- **§5.1.2 (protocolo):**
  - as duas campanhas pareadas da 3.0.0 e as duas de bloco;
  - o efeito do tracemalloc medido na 3.0.0: 3,3× no total em 100 mil multifonte, 6,2× no `infer`, 2,1× na escrita do Cassandra;
  - a precisão: uma célula medida em duas campanhas diferiu 2,7% em tempo e 0,2% em memória (66,1 × 66,2 MB). É uma célula só, então não generalizar. Para as comparações históricas, continua valendo a incerteza de cerca de 20% das campanhas da 2.x.
- **§5.2:**
  - Windows 11 *build* 10.0.26300 e Python 3.14.5;
  - Docker com 3,88 GiB e 8 CPUs, Cassandra com *heap* de 1 GB e **fator de replicação 1** (`cassandra_importer._cassandra_keyspace_ddl`);
  - hospedeiro de 8 GB, com 650 a 800 MB livres durante as campanhas;
  - a campanha de memória interrompida e retomada com `--resume`.
- **QP1 (`sec:res-fases`):**
  - `tab:fases-100k` com `infer`, `validate`, `write` por SGBD e o total, multifonte e combinado, de `v3/timings`;
  - `tab:escrita-sgbd` e `fig:throughput-sgbd` com a vazão de `v3/timings`;
  - a fração do Cassandra: 67% da escrita e 53% da importação, no multifonte.
- **QP2 (`sec:res-modos`):** `tab:multi-combined` com os números da 3.0.0:
  - tamanho, colunas e células vazias, recalculados dos arquivos de `data/benchmark/generated/100000/`;
  - `infer` e `validate` de `v3/timings`;
  - total de `v3/timings`;
  - pico de `v3/memory`.

  O texto relata o que os números mostram: em 100 mil linhas, o combinado leva 13% mais tempo e tem **pico menor** (54,6 × 66,1 MB). Não repetir conclusões da 2.x que os números novos contradizem.
- **QP3:** uma tabela de crescimento (1k/10k/100k × multi/combinado; total de `v3/timings`, pico de `v3/memory`) e as razões (100× linhas → 32× e 41× em tempo; 6,4× e 5,3× em pico). Um gráfico em pgfplots, se ajudar (cuidado com `ymode=log` e `nodes near coords`: usar rótulos explícitos).
- **QP7, nova subseção:**
  - a fração de `infer` + `validate` no total (21,3% e 23,7%);
  - a tabela de bloco (pico, total, `infer`, `validate`), igual à da §4.5, ou remetendo a ela, sem duplicar a tabela;
  - a ressalva: a economia de 5–6% no total com blocos maiores fica perto do dobro da variação entre campanhas;
  - a troca: o pico dobra;
  - por que o pico cresce com as linhas: a leitura de validação guarda as chaves referenciadas, decisão 9 da spec do fluxo único. Conferir no código (`data_validation.py`) antes de afirmar.
- **QP4, QP5/QP6 e `sec:res-tradeoff`:** os números da 2.x ficam. O texto deixa claro que comparam a escrita ingênua e a materialização, que não existem na versão final, e que a carga da 2.x não tinha a coleção `orders`. QP6: o pico "achata", não "fica constante".
- **§5.4, Análise e Discussão:**
  - a frase de que o Cassandra "aplica escrita replicada" está errada: o *keyspace* é criado com `replication_factor` 1, num nó só. O texto atribui a lentidão ao limite do ambiente (*heap* de 1 GB) sem inventar outra causa;
  - "memória constante" vira "o pico achata".
- **Ameaças à validade:**
  - campanhas com e sem tracemalloc nunca misturadas;
  - uma única célula repetida entre campanhas;
  - pouca memória livre no hospedeiro;
  - o Cassandra no limite do ambiente;
  - a carga diferente da 2.x;
  - a variação histórica de 15–38%.

- [ ] **Step 3: Script de conferência dos números**

Escrever `<rascunho>/check_cap5_numbers.py` no padrão de `check_readme_numbers.py` do rascunho da etapa 2 (`C:\Users\lbc92\AppData\Local\Temp\claude\D--UFSC-TCC1-polyglot-import-csv\30dff64f-00e4-43f1-b53d-4f23ae7a9e1e\scratchpad\check_readme_numbers.py`). Ele recalcula, a partir dos CSVs, cada número da 3.0.0 que o Cap. 5 e a tabela de bloco da §4.5 citam e confere se cada um aparece no `.tex`, com vírgula decimal e `\num{}` para milhar. Os números históricos são conferidos contra os CSVs da 2.x.
Run: `.venv/Scripts/python.exe <rascunho>/check_cap5_numbers.py .`
Expected: `N numbers checked, 0 missing`.

- [ ] **Step 4: Conferir**

Expected:
- compilação com undefined = 0;
- cada legenda declara a pasta e a campanha;
- páginas lidas: tabelas e gráficos sem sobreposição;
- o portão de vocabulário da Task 10 no capítulo.

- [ ] **Step 5: Commit** (`docs(tcc): capitulo de avaliacao com a campanha 3.0.0 e QP7`)

---

### Task 9: Apêndices A, B e dos *schemas*

**Files:**
- Modify: `docs-tcc/chapters/apendiceconfig.tex`, `apendicecsv.tex`, `apendiceschemas.tex`

- [ ] **Step 1: Ler os três apêndices**, os arquivos que eles reproduzem e os quatro CSVs do cenário exemplo.

- [ ] **Step 2: Reescrever**

- **Apêndice A:** as configurações atuais de `data/ecommerce/` (multifonte e combinada), com a coleção `orders`, iguais aos arquivos.
- **Apêndice B:**
  - as tabelas por ação (`stock`, `purchase`, `select_product`, `add_to_cart`) passam a ser verticais: uma linha da tabela por coluna do CSV e uma coluna da tabela por linha de dados, com todas as colunas daquela ação, inclusive `last_restock_date`;
  - se não couber na largura, dividir (linhas 1–4 e 5–8);
  - as abreviações já documentadas continuam;
  - a tabela de `stock` recebe o rótulo `tab:csv-stock-completa`, que a Task 5 já usa.
- **Apêndice dos *schemas*:** os trechos iguais aos *schemas* da 3.0.0 (a descrição e o padrão de `target_suffix`; nenhuma descrição que fale em "materialization"). Conferir com `git diff` entre o trecho e o arquivo.
- Vocabulário: "cenário exemplo", "gravar", remissão a `sec:algoritmo` pelo título novo.

- [ ] **Step 3: Conferir**

Script descartável que compara cada célula das tabelas do apêndice B com os CSVs e cada listagem do apêndice A com os arquivos.
Expected:
- 0 diferenças;
- compilação com undefined = 0;
- páginas lidas, com as tabelas cabendo na largura.

- [ ] **Step 4: Commit** (`docs(tcc): apendices com a colecao orders, tabelas verticais dos CSVs e schemas da 3.0.0`)

---

### Task 10: Resumo, Abstract, Caps. 1, 2, 3, 6, considerações e varredura do vocabulário

**Files:**
- Modify: `docs-tcc/main.tex` (Resumo e Abstract), `docs-tcc/chapters/ch1introducao.tex`, `ch2fundamentacao.tex`, `ch3relacionados.tex`, `ch5futuros.tex`, `consideracoes.tex`

- [ ] **Step 1: Reescrever**

- **Resumo e Abstract:**
  - o fluxo como modo único e a validação completa antes de gravar;
  - os números da 3.0.0 que sustentam a frase de desempenho;
  - o ganho da escrita em lote e a redução de memória do fluxo citados como resultados históricos medidos, com os números da 2.x.

  As duas línguas dizem a mesma coisa.
- **Cap. 1:** "fluxo" no lugar de "algoritmo de importação" (linha 117) e alinhamento com o modo único.
- **Cap. 3 (§3.1):** o `cqlsh COPY FROM` importa CSV direto; o SSTable é exigência do `sstableloader`. Corrigir a frase da linha 138.
- **Considerações (`consideracoes.tex`):** os dados da avaliação são sintéticos, não "reais" (linha 17); o fluxo como modo único; a validação completa.
- **Cap. 6 (trabalhos futuros, `ch5futuros.tex`):** nada que já tenha sido feito (validação completa, bloco e lote configuráveis).
- **Cap. 2:** "materializa-se" (linha 223) é sentido figurado e fica.

- [ ] **Step 2: Portão de vocabulário, no relatório inteiro**

Run: a ferramenta Grep em `docs-tcc/chapters/` e `docs-tcc/main.tex` com cada padrão: `lgoritmo`, `amada`, `aterializ`, `cenário de exemplo`, `cenário de e-commerce`, `back[e]nd`, `--execution`, `create-schema`, `\[Ss\]treaming`.
Expected: cada ocorrência que sobra está numa lista de exceções aceitas, registrada no ledger com o motivo:
- "camada de observabilidade";
- "camada de acesso da aplicação";
- "materializa-se" no Cap. 2;
- "materialização" como nome do modo histórico na §4.5.1 e no Cap. 5;
- *streaming* como termo técnico definido no primeiro uso, se mantido.

- [ ] **Step 3: Conferir.** Compilação com undefined = 0. Ler as páginas do Resumo, do Abstract e das considerações.

- [ ] **Step 4: Commit** (`docs(tcc): resumo, abstract, introducao e consideracoes alinhados a 3.0.0 e vocabulario no relatorio inteiro`)

---

### Task 11: PDF v2.4 e diff v2.3→v2.4

**Files:**
- Create: `docs-tcc/TCC2-PolyglotImportCSV-Report-v2.4.pdf`, `docs-tcc/TCC2-PolyglotImportCSV-Report-diff-v2.3-v2.4.pdf`

- [ ] **Step 1: Compilação limpa e conferências finais**

Run: compilação; `grep -c "undefined" docs-tcc/main.log`; a ferramenta Grep por `Figura [0-9]` e `Tabela [0-9]` em `docs-tcc/chapters/`.
Expected: undefined = 0, e nenhum número de figura ou tabela escrito à mão.

- [ ] **Step 2: Leitura do PDF inteiro**

Ler o PDF com a ferramenta Read, 20 páginas por vez, e conferir:
- legendas e "Fonte:" em todas as figuras e tabelas;
- nenhuma tabela ou figura invadindo a margem;
- as figuras novas legíveis.

Cada uma das 26 linhas do mapa do design ganha uma linha no ledger com a página da v2.4 onde foi atendida.

- [ ] **Step 3: Gerar o diff**

O fonte da v2.3 é o *commit* `72294fe`. Extraí-lo para `<rascunho>/v23/` (`git archive 72294fe docs-tcc | tar -x -C <rascunho>/v23`) e copiar o fonte atual para `<rascunho>/v24/`. Depois:

```bash
latexdiff --flatten --config="PICTUREENV=(?:picture|tikzpicture|DIFnomarkup|lstlisting)[\w\d*@]*" <rascunho>/v23/docs-tcc/main.tex <rascunho>/v24/docs-tcc/main.tex > <rascunho>/v24/docs-tcc/diff.tex
cd <rascunho>/v24/docs-tcc && latexmk -pdf -interaction=nonstopmode diff.tex
```

Se uma tabela reescrita por inteiro quebrar a compilação, ela aparece só na versão nova, como no diff anterior (`d673fa0`). Registrar no ledger quais foram tratadas assim.
Expected: `diff.pdf` gerado; o texto novo em azul e o removido em vermelho riscado; as páginas das 26 correções mostram a mudança.

- [ ] **Step 4: Commit**

```bash
cp docs-tcc/main.pdf docs-tcc/TCC2-PolyglotImportCSV-Report-v2.4.pdf
cp <rascunho>/v24/docs-tcc/diff.pdf docs-tcc/TCC2-PolyglotImportCSV-Report-diff-v2.3-v2.4.pdf
rtk git add docs-tcc/TCC2-PolyglotImportCSV-Report-v2.4.pdf docs-tcc/TCC2-PolyglotImportCSV-Report-diff-v2.3-v2.4.pdf
rtk git commit -m "docs(tcc): relatorio v2.4 e diff da v2.3 para a v2.4" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
rtk git push
```

---

### Depois das tarefas

- A revisão final, num contexto novo e no modelo mais capaz, compara o relatório inteiro com o código da 3.0.0 e com os CSVs. Ela usa os pontos da Review Focus e as linhas `Ruling:` do ledger.
- O estado da sessão e a memória são atualizados: etapa 3 concluída e o que a etapa 4 (slides v1.1) herda.
- O `main` só é enviado no fim da etapa 4, com outro merge do `fluxo-unico`. A tag `v3.0.0` continua dependendo do OK do autor.
