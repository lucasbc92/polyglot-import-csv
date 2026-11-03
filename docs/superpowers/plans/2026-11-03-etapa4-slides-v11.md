# Etapa 4: slides v1.1 da defesa

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** atualizar o deck Beamer de `docs-tcc/apresentacao/` para a versão 3.0.0 e para o relatório v2.4, gerando `docs-tcc/TCC2-PolyglotImportCSV-Apresentacao-v1.1.pdf`.

**Architecture:** o deck continua com 25 frames no corpo e 7 cartas (B1–B7), nos mesmos arquivos de `secoes/`. Cada número sai do relatório v2.4 (`docs-tcc/chapters/ch6avaliacao.tex`, `ch4proposta.tex`), e cada afirmação sobre comportamento é conferida no código da 3.0.0. A verificação é o `verificar.sh` do deck, mais um conferidor de números e de vocabulário no rascunho, escrito antes das edições (vermelho) e verde ao fim.

**Tech Stack:** LaTeX Beamer (tema `beamerthemeufsc.sty`), TikZ e pgfplots, `latexmk` do MiKTeX, `pdftoppm` para renderizar páginas, Python do venv com Pillow para medir recortes das capturas.

**Spec:** `docs/superpowers/specs/2026-10-27-fluxo-unico-validacao-previa-design.md` (seção "Slides v1.1"), complementada por `docs/superpowers/specs/2026-10-30-revisao-ronaldo-v22-design.md` (vale este onde divergirem: "camada" vira "etapa").

## Global Constraints

- Saída: `docs-tcc/TCC2-PolyglotImportCSV-Apresentacao-v1.1.pdf`. A v1.0 continua versionada.
- `bash verificar.sh 25 7` passa: compila, fechamento no frame 25, 7 cartas, sem `\tiny`, `\trans`, `\movie`, `\sound`, sem o termo vetado e sem `Overfull`.
- Vocabulário do design de 2026-10-30: "três etapas de validação" (etapa 1, 2 e 3); "passo" para o fluxo de execução; "fluxo" no lugar de "algoritmo"; "leitura em blocos" para o modelo de execução (não "fluxo"); "cenário exemplo"; "SGBD destino"; "SGBD", nunca o termo em inglês que o orientador rejeitou.
- Todo número vem da campanha nova (`benchmarks/v3/`, como citado no relatório v2.4) ou, para QP4–QP6, das medições históricas, marcadas como históricas. Tempo e memória nunca na mesma linha sem declarar a campanha.
- Remissões ao relatório usam os números da v2.4: Figura 10 (etapas), Figura 11 (passos), Figura 12 (exemplo), Tabela 12 (`--dry-run`), Tabela 13 (bloco), Tabela 14 (ambiente), Tabela 15 (fases), Tabela 16 e Figura 18 (escrita por SGBD), Tabela 17 (modos), Tabela 18 (escala), Tabela 19 (custo da validação), Tabela 20 e Figura 19 (QP4), Tabela 21 e Figura 20 (memória histórica), Tabela 22 e Figura 21 (tempo histórico).
- Regras do orientador para slides: frases curtas, revelação gradual, legenda embaixo do gráfico, "Fonte:" embaixo, cerca de um slide por minuto.
- Git: commits em português com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, prefixo `rtk`, push do `fluxo-unico` após cada commit, só caminhos explícitos.

## Review Focus

- Um número do deck que não esteja no relatório v2.4 (ou que seja da v2.3 e tenha mudado): o conferidor recusa os números antigos listados na Tarefa 1.
- Uma frase que ainda descreva a 2.x: `--execution`, "camada", a validação completa só no `--dry-run` e na GUI, tipos inferidos do primeiro bloco, "quatro etapas" do fluxo.
- Recortes da GUI que cortem texto no meio ou mostrem a região errada depois da troca das capturas: cada passo do slide 16 é renderizado e lido.
- Caixas estouradas ou texto abaixo de `\scriptsize` em slides com mais conteúdo (17, 18, 19, 20): `verificar.sh` acusa Overfull; o resto, a leitura das páginas.
- Revelações (`\onslide`, `visivel em`) que mudem o número de páginas sem mudar o de frames: o fechamento tem de continuar no frame 25.

---

### Task 1: Conferidor de números e vocabulário (vermelho)

**Files:**
- Create: `<rascunho>/check_slides.py` (fora do repositório)

- [ ] **Step 1: Escrever o conferidor.** Lê `docs-tcc/apresentacao/secoes/*.tex` e falha se:
  - aparecer algum número só da v2.3: `91,0`, `136,34`, `7644`, `10865`, `14431`, `3901`, `912` (número inteiro), `109,61`/`109{,}61`, `161,94`, `181,42`, `15,15`, `1009.5`. Os números históricos que a v2.4 mantém (QP4–QP6, como `27494`, `950,7` e `165,03`) podem ficar;
  - aparecer `camada`, `lgoritmo`, `-{}-execution`, `materialize`, `primeiro bloco`, `quatro etapas`, `cenário e-commerce`, `SGBD de destino`, `Completa no`;
  - faltar algum número novo: `209,51`, `78,7`, `13,2`, `8,1`, `901`, `3294`, `5793`, `5845`, `9118`, `237,39`, `66,1`, `54,6`, `6,51`, `22,67`, `39,3`, `21,3`, `66,2`, `131,9`, `149,9`, `204,00`, `190,88`, `110,96`, `164,84`, `89275`, `73660`, `50442`, `49558`, `orders\_state`, `2,7`;
  - faltar `três etapas` ou `leitura de inferência` ou `leitura de validação`.
- [ ] **Step 2: Rodar.** Expected: FALHA, listando os números antigos e os termos da 2.x.

### Task 2: Proposta, parte 1 (slides 5, 8, 9, 10, 11)

**Files:** Modify `secoes/1-introducao.tex` (slide 5), `secoes/3-proposta.tex` (slides 8–11), `secoes/5-conclusao.tex` (objetivo 2 repete a redação do slide 5)

- [ ] Slide 5, objetivo 2: "\destaque{Validação prévia}: um erro na configuração ou nos dados impede qualquer gravação." (§1.2 da v2.4).
- [ ] Slide 8: a nota final diz que o comando valida as configurações e os dados e só então grava nos SGBDs destino.
- [ ] Slide 9: "um bloco por SGBD destino".
- [ ] Slide 10 ("Conexão e validação prévia"): "A validação prévia tem \destaque{três etapas}:". Desenho horizontal, revelado em passos: entradas → etapa 1 (JSON Schema de cada arquivo) → etapa 2 (todo SGBD da importação está na conexão? resta ao menos um destino?) → etapa 3, que recebe os CSVs, com duas partes: cabeçalhos (colunas citadas existem? filtros e relacionamentos coerentes?) e dados (leitura de validação: não converte, `db_type`, chave vazia, referência pendente) → gravação nos SGBDs destino. Caixa de falha única: "Falha em qualquer etapa: a execução termina com código 1 e \textbf{nada é gravado}." Sai a nota "Completa no `--dry-run` e na GUI". Comentário do frame atualizado para a 3.0.0 (Figura 10 e §4.2.4 da v2.4).
- [ ] Slide 11: título "Cenário exemplo"; o título da tabela diz "Tipos de evento do cenário exemplo (e-commerce)".
- [ ] Rodar o conferidor e `bash verificar.sh 25 7`. Expected: o conferidor ainda falha (slides 13 em diante); `verificar.sh` passa.
- [ ] Commit: `docs(slides): validação prévia em três etapas e vocabulário da v2.4 nos slides 5 a 11`.

### Task 3: Proposta, parte 2 (slides 13, 14, 15)

**Files:** Modify `secoes/3-proposta.tex`

- [ ] Slide 13: título "Fluxo de execução"; "Com as configurações validadas, a importação lê os dados \destaque{três vezes}:". Uma faixa "antes de ler os dados" (passos 1–3: configurações, etapas 1 e 2; cabeçalhos, etapa 3; verificação dos SGBDs, não no `--dry-run`, com a caixa de SGBD fora do ar) e três caixas reveladas: leitura de inferência (passo 4: cada CSV inteiro, em blocos de `--chunk-size`, fixa o tipo de cada coluna), leitura de validação (passo 5: cada linha pelo código da gravação, sem gravar; erro: código 1, nada gravado; o `--dry-run` termina aqui, com as contagens), leitura de gravação (passos 6–9: um SGBD destino por vez; prepara, relê as fontes dele em blocos e grava em lotes de `--batch-size`; fecha). Legenda: "Passos do fluxo de execução (Figura 11 do relatório)."
- [ ] Slide 14: comando igual ao da §4.3.4; a nota de `--dry-run` passa a "valida e conta, sem gravar" (igual); o título da tabela "Linhas a gravar, após os filtros, reportadas pelo \texttt{-{}-dry-run} no cenário exemplo" e a nota "antes da eliminação de duplicatas"; linhas da Tabela 12 da v2.4, incluindo MongoDB `orders\_state\_SP` 2 e `orders\_state\_`CA, RJ, RS, SC, SE e TO, 1 cada.
- [ ] Slide 15 ("Escrita e leitura em blocos"): estratégia de escrita, ingênua (TCC1, linha de base histórica) × em lote (a única da versão final); modelo de execução, materialização (histórico: carregava a fonte inteira; um arquivo maior que a memória não chegaria a ser carregado) × leitura em blocos (o único modelo: bloco `--chunk-size`, 8 MB por padrão, de 8 a 256; lote `--batch-size`, 1024 por padrão, de 1024 a 8192, limitado às linhas de um bloco). Nota final: as linhas de base históricas são as que a avaliação mede (QP4–QP6).
- [ ] Rodar o conferidor e `bash verificar.sh 25 7`; renderizar as páginas dos slides 10, 13, 14 e 15 e lê-las.
- [ ] Commit: `docs(slides): fluxo em três leituras, contagens do dry-run e leitura em blocos`.

### Task 4: Interface gráfica (slide 16)

**Files:** Modify `secoes/3-proposta.tex` (só as coordenadas dos `\recorte`, `\faixa` e `\comandogui` e as legendas)

- [ ] Medir, com Pillow, as faixas das capturas atuais (1240 × 1020 px): cartão "Opções de execução", linha do comando (duas linhas de 14 px), linha de botões do console, saída do console, tabela de métricas, barra de estado, cartão de configuração com o erro (Figura 15) e a tabela de estados com os comandos `net start` (Figura 16).
- [ ] Passos: (1) ocioso: cartão de opções, com "Bloco em MB" e "Lote", e o comando montado; (2) executando: opções bloqueadas, botão Interromper, saída chegando; (3) concluído: tabela de métricas (`dbms`, `infer`, `validate`) e "Finished dry-run", barra de estado com o log; (4) erro antes de executar: mensagem com o caminho do campo (`$.sources.stock`) e botão Executar desabilitado; (5) verificação dos SGBDs. Legendas curtas, como as da §4.6.
- [ ] Renderizar as cinco páginas do slide 16 e conferir que nenhum recorte corta texto.
- [ ] Commit: `docs(slides): recortes das capturas novas da GUI`.

### Task 5: Avaliação (slides 17 a 21)

**Files:** Modify `secoes/4-avaliacao.tex`

- [ ] Slide 17 (metodologia): volumes; três repetições, mediana; campanhas pareadas (tempo sem instrumentação, memória com); bloco de 8 MB e, em 100 mil multifonte, 64 e 256 MB; precisão: 2,7% de tempo e menos de 0,2% de memória entre campanhas numa célula (versão final), cerca de 20% de tempo nas históricas. Painel das QP: QP1 custo por fase e por SGBD, QP2 modos, QP3 escalabilidade, QP7 validação prévia e bloco; históricas: QP4 estratégia de escrita, QP5 modelo de execução, QP6 memória limitada. Ambiente: uma máquina Windows 11 com 8 GB; Docker com 3,88 GiB; Cassandra com 1 GB de *heap*. Fonte: §5.1, §5.2 e Tabela 14.
- [ ] Slide 18, "A escrita domina o tempo (QP1)": barra empilhada da Tabela 15 (multifonte, 100 mil: inferência 8,1%, validação 13,2%, escrita 78,7%, total 209,51 s) e vazão da Figura 18 (Cassandra 901, Neo4j 3294, PostgreSQL 5793, MongoDB 5845, Redis 9118 linhas processadas/s); nota: o Cassandra é 110,96 s dos 164,84 s da escrita, 53% da importação. Fonte: Tabela 15 e Figura 18; campanha sem instrumentação.
- [ ] Slide 19, "Multifonte × combinado e escala (QP2, QP3)": tabela da Tabela 18 (tempo e pico por volume nos dois modos: 6,51/22,67/209,51 s e 10,4/40,1/66,1 MB multifonte; 5,81/27,18/237,39 s e 10,2/44,2/54,6 MB combinado), com a declaração das duas campanhas; pontos: o tempo cresce quase em proporção a partir de 10 mil (9,2× e 8,7× para 10×); o pico cresce bem menos (6,4× e 5,3× para 100×); o combinado leva 13% mais tempo e tem pico menor (54,6 contra 66,1 MB). Fonte: Tabelas 17 e 18.
- [ ] Slide 20, "A validação prévia custa cerca de um quinto do tempo (QP7)": Tabela 19 (39,3/23,4/21,3% multifonte; 38,5/25,9/23,7% combinado) e Tabela 13 (8, 64, 256 MB: pico 66,2/131,9/149,9 MB; total 204,00/192,91/190,88 s; −5,4% e −6,4%); conclusão: o padrão de 8 MB favorece a memória e custa pouco em tempo. Em troca, nenhum problema detectado chega a uma gravação parcial.
- [ ] Slide 21, "Resultados históricos (QP4, QP5, QP6)": marcado como medições com versões anteriores; dois gráficos lado a lado: estratégia de escrita (Tabela 20/Figura 19: 135,74 × 14,54 s e 138,44 × 16,30 s, ~9×) e pico de memória (Tabela 21/Figura 20: 10,5/95,3/950,7 × 10,7/47,8/75,9 MB, 12,5× em 100 mil), com o custo de tempo da leitura em blocos (+61% em mil, +10% em 100 mil; Tabela 22). Rótulos "materialização" e "leitura em blocos".
- [ ] Rodar o conferidor (os números novos de avaliação passam a existir) e `bash verificar.sh 25 7`; renderizar 17–21 e lê-las.
- [ ] Commit: `docs(slides): avaliação com a campanha da 3.0.0 e os resultados históricos marcados`.

### Task 6: Conclusão e cartas (slides 22 a 24, B1, B2, B5, B6)

**Files:** Modify `secoes/5-conclusao.tex`, `secoes/6-cartas.tex`

- [ ] Slide 22: objetivo 2 com a redação do slide 5; evidência sem ressalva: "três etapas de validação antes de qualquer gravação: os arquivos, a consistência entre eles e os próprios dados; verificação dos SGBDs". Objetivo 3: "sete questões de pesquisa (QP1–QP7), três delas históricas". Objetivo 4: CLI com `--dry-run`, `--only` e `--chunk-size`.
- [ ] Slide 23: a linha da atomicidade diz que a validação prévia barra os erros de configuração e de dados, mas uma falha durante a gravação, como a queda de um SGBD, ainda deixa carga parcial.
- [ ] Slide 24: igual, conferido contra o Cap. 6 da v2.4.
- [ ] B1: antes de gravar, as três etapas de validação e a verificação dos SGBDs; só as falhas durante a gravação ficam sem desfazer (código 1, com os SGBDs já gravados); um SGBD por vez, na ordem PostgreSQL, MongoDB, Cassandra, Redis, Neo4j; reexecução com `--only` como hoje (conferir nos *sinks*).
- [ ] B2: a leitura de inferência percorre o arquivo inteiro, em blocos; regras da §4.2 (booleana, inteira ou real, data/hora acima de 85% dos não vazios, texto, vazia); um valor que não converte é apontado pela leitura de validação, e nada é gravado; `db_type` recusaria o valor → também apontado. Sai "Em fluxo, o tipo sai do primeiro bloco".
- [ ] B5: Tabela 16 da v2.4 (linhas processadas, tempo e linhas/s), "110,96 s dos 164,84 s da escrita, cerca de 67%"; fonte com bloco de 8 MB, campanha sem instrumentação.
- [ ] B6: ameaças da §5.4.1 da v2.4 (2,7% numa célula; cerca de 20% nas históricas; cargas diferentes entre as épocas; 650 a 800 MB livres; bloco de 256 MB já lê cada fonte inteira).
- [ ] B3, B4, B7: conferir; mudar só o que a v2.4 contradiz.
- [ ] Rodar o conferidor (Expected: PASSA) e `bash verificar.sh 25 7`.
- [ ] Commit: `docs(slides): conclusão e cartas na versão 3.0.0`.

### Task 7: PDF v1.1 e leitura final

**Files:** Create `docs-tcc/TCC2-PolyglotImportCSV-Apresentacao-v1.1.pdf`

- [ ] `bash verificar.sh 25 7` com todas as páginas renderizadas; ler o PDF inteiro, página a página.
- [ ] Copiar `apresentacao.pdf` para `docs-tcc/TCC2-PolyglotImportCSV-Apresentacao-v1.1.pdf`.
- [ ] Commit: `docs(slides): apresentação v1.1`. Push.
