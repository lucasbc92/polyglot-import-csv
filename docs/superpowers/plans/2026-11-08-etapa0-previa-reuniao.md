# Etapa 0 — Prévia para a reunião de 2026-11-09 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Levar à reunião com o orientador um relatório intermediário com o Cap. 5 reestruturado sobre uma campanha nova (volumes em potências de 2), as correções de texto que ele pediu e a Conclusão unificada, além de notas de resposta às dúvidas dele.

**Architecture:** Nenhum código da ferramenta muda. Uma campanha (tempo + memória) roda destacada sobre o `main` atual. Enquanto ela roda, são feitas as correções que não dependem dos números (Cap. 4, Conclusão). Os números saem dos CSVs por um script de conferência local, e só então o Cap. 5, o veredito da Conclusão e o Resumo são escritos.

**Tech Stack:** `scripts/run_benchmarks.py` (Python 3.14, `.venv`), Docker Compose (cinco SGBDs), LaTeX/abnTeX2 + pgfplots (`latexmk` em `docs-tcc/`), PySide6 `QImage`/`QPainter` para a marcação da figura.

**Spec:** `docs/superpowers/specs/2026-11-08-revisao-ronaldo-v23-design.md` (seção "Etapa 0" e, para o conteúdo do texto, Partes 4a–4c).

## Global Constraints

- Branch `revisao-ronaldo-v23`. Push depois de cada commit. Commits em português, com o trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Todo comando git leva o prefixo `rtk`. Preparar só caminhos explícitos, nunca `git add -A`.
- Não tocar nas mudanças locais do autor fora deste plano: os PDFs em `docs-tcc/` apagados ou modificados, `docs-tcc/main-v2.2.tex` e `docs-tcc/main-v2.4.tex`.
- O código da ferramenta (`src/`) não muda nesta etapa. Os números medidos são do commit `641e8a8` (padrões: bloco de 128 MB, lote de 2048 linhas).
- Volumes: 1024, 16384, 32768, 65536, 131072 e 262144. Modos: multifonte e combinado.
- Docker: só iniciar ou reiniciar com o OK do autor (pendente em 2026-11-08 20:50; ver Task 1, Step 1).
- Durante uma campanha: nada de testes, compilação LaTeX nem renderização pesada (8 GB de RAM). Edições de texto podem seguir.
- Texto em português: "SGBD" (nunca o termo inglês banido pelo guarda de nomenclatura); legenda de figura embaixo, título de tabela em cima, "Fonte:" embaixo; uma frase de introdução antes de cada tabela e figura; nada de prosa sobre o histórico de versões, exceto a ressalva exigida na §4.5.1.
- Shell heredocs comem barras invertidas: editar LaTeX só com as ferramentas Edit/Write.
- Arquivos descartáveis vão para `.superpowers/scratch/`, que já é ignorado pelo git.
- `grep` pelo shell em `data/` ou no repositório inteiro trava: usar a ferramenta Grep com caminho.

## Review Focus

1. **Números do texto divergindo dos CSVs.** Todo número do Cap. 5, da Conclusão e do Resumo sai da saída do script da Task 3. A Task 6, Step 2 confere cada um contra essa saída.
2. **Restos do bloco de 8 MB como padrão e das medições históricas no Cap. 5.** Uma busca por `8~MB`, `bloco padrão`, `históric`, `ingênua`, `materializa` e `QP6` em `ch6avaliacao.tex` deve voltar vazia, exceto onde a §4.5.1 for citada (Task 6, Step 1).
3. **Referências quebradas depois de mover `ch5futuros` para dentro da Conclusão.** `cap:futuros` vira `sec:futuros`. O log do `latexmk` não pode ter `undefined references` (Task 6, Step 3).
4. **Uma campanha que fica incompleta ou repete células.** Ela é conferida antes do commit (Task 1, Step 4) e, se for interrompida, retomada com `--resume`, nunca do zero.
5. **Expoente de escalabilidade calculado sobre o volume 1024, que é dominado pelos custos fixos.** O ajuste usa só N ≥ 16384, e o texto diz isso (Task 3 e Task 5).

---

### Task 1: Campanha intermediária (`benchmarks/v4-preview/`)

**Files:**
- Create: `benchmarks/v4-preview/timings/{benchmark_results.csv,benchmark_run_*.json}`, `benchmarks/v4-preview/memory/{benchmark_results.csv,benchmark_run_*.json}`
- Create (não versionado): `.superpowers/scratch/check_campaign.py`

**Interfaces:**
- Produces: os dois CSVs, com o cabeçalho `timestamp,size,mode,chunk_mb,dbms,entity,phase,rows,median_seconds,rows_per_second,peak_memory_mb`, consumidos pela Task 3.

- [ ] **Step 1: Pré-condições (bloqueante)**

O autor escolheu reiniciar o Windows ou autorizou reiniciar o Docker Desktop. `docker version` responde em menos de 30 s, e `docker compose up -d --wait` sobe os cinco SGBDs. Anotar a memória livre com o Docker no ar (`Win32_OperatingSystem.FreePhysicalMemory`); se ficar abaixo de 500 MB, avisar o autor antes de seguir. HEAD em `revisao-ronaldo-v23` e enviado; `src/` idêntico a `641e8a8` (`rtk git diff --stat 641e8a8 -- src` vazio).

- [ ] **Step 2: Campanha de tempo, destacada**

Disparar com `Start-Process` (fora do Claude Code, que encerra shells em segundo plano quando falta memória), com a saída redirecionada para `.superpowers/scratch/timings.log`:

```
.venv/Scripts/python.exe scripts/run_benchmarks.py --sizes 1024,16384,32768,65536,131072,262144 --modes multi,combined --repetitions 3 --no-trace-memory --out benchmarks/v4-preview/timings
```

O primeiro uso de cada volume gera os dados em `data/benchmark/generated/<N>/`, com a semente 42. Duração esperada: cerca de 2 h. Acompanhar pelo log a cada 20–30 min, não mais que isso. Se a campanha for interrompida, repetir o mesmo comando com `--resume`. Expected: o log termina com `benchmark JSON:` e `benchmark CSV:`.

- [ ] **Step 3: Campanha de memória, destacada, depois da de tempo**

```
.venv/Scripts/python.exe scripts/run_benchmarks.py --sizes 1024,16384,32768,65536,131072,262144 --modes multi,combined --repetitions 1 --out benchmarks/v4-preview/memory
```

Saída em `.superpowers/scratch/memory.log`. Cerca de 2 h. Vale a mesma regra do `--resume`.

- [ ] **Step 4: Conferir cada pasta com `.superpowers/scratch/check_campaign.py <pasta> [<pasta_par>]`**

O script confere e imprime `OK` ou a lista de falhas:
- um só `benchmark_results.csv`, um só `benchmark_run_*.json` e nenhum `benchmark_checkpoint.json`;
- um só `timestamp` no CSV;
- nenhuma chave `(size, mode, chunk_mb, dbms, entity, phase)` repetida;
- os 6 volumes × 2 modos presentes;
- `chunk_mb` igual a 128 em todas as linhas;
- `peak_memory_mb` preenchido em todas as linhas de `memory` e vazio em todas as de `timings`;
- as linhas `infer` e `validate` com `rows == size`;
- quando a pasta par é dada, `rows` idêntico entre as duas pastas em toda chave comum.

- [ ] **Step 5: Commit e push de cada pasta conferida**

```
rtk git add benchmarks/v4-preview/timings/benchmark_results.csv benchmarks/v4-preview/timings/benchmark_run_*.json
rtk git commit -m "bench: campanha intermediaria de tempo (1024 a 262144, multi e combinado)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
rtk git push
```

O mesmo para `memory` ("de memoria, 1 repeticao").

---

### Task 2: Correções do Cap. 4 e marcação da Figura 17

Pode rodar durante a campanha.

**Files:**
- Modify: `docs-tcc/chapters/ch4proposta.tex` (§4.5.1 ≈ linhas 1490–1526, §4.5.2 ≈ 1531–1577, §4.6 ≈ 1621–1761)
- Modify: `docs-tcc/images/figure16-gui-verificacao.png` (é a Figura 17 do PDF)
- Create (não versionado): `.superpowers/scratch/mark_figure.py`

- [ ] **Step 1: §4.6, as anotações das p. 76–81** (tabela "4a" do spec)
  - "O terceiro cartão contém a tabela de sobrescrita de caminhos das fontes CSV" → o terceiro cartão recebe os **arquivos CSV de entrada**; se ficar vazio, valem os caminhos do bloco `sources`; cada arquivo escolhido substitui o caminho da fonte correspondente. No parágrafo seguinte, "uma sobrescrita só faz sentido diante das fontes..." e "a sobrescrita gerada" são reescritos sem a palavra "sobrescrita" (por exemplo, "um arquivo só pode ser associado a uma fonte que a configuração declara").
  - "Com uma configuração **combinada**, aceita" → "Uma configuração **combinada** aceita" (correção da p. 76).
  - Apagar de "A alternativa --- omitir o que coincide..." até "...correspondente literal na linha de comando." (linhas ≈ 1673–1679).
  - "Ao sair do modo de edição, o texto digitado é descartado mediante confirmação e o comando é remontado a partir dos controles." → "Enquanto o modo de edição está ativo, é o texto digitado que será executado. Ao sair dele, mediante confirmação, esse texto é desconsiderado e substituído pelo comando que a interface representa."
  - Legenda de `fig:gui-sucesso`: "Simulação (\texttt{-{}-dry-run}) concluída com sucesso, com o tempo total e o arquivo de \textit{log} da sessão na barra de estado."
  - Legenda de `fig:gui-verificacao`: acrescentar "o botão \textbf{Verificar SGBDs}, acionado, aparece destacado em vermelho".
  - Grep na §4.6 por "sobrescrita": nenhuma ocorrência.

- [ ] **Step 2: §4.5.1, justificativa histórica resumida e "conversão vetorizada"**
  - O parágrafo "A estratégia ingênua e a materialização permanecem descritas... (≈ linhas 1524–1526)" é substituído por um parágrafo que apresenta os números como medições feitas com uma versão anterior da ferramenta, sobre uma carga sem a coleção `orders`: escrita em lote 9,3× (multifonte) e 8,5× (combinado) mais rápida que a ingênua em N = 10 000, com materialização (`benchmarks/timings-naive/`); leitura em blocos com pico 12,5× menor que a materialização em N = 100 000 (75,9 contra 950,7 MB, `benchmarks/`), ao custo de +10% de tempo nesse ponto (165,03 contra 149,93 s, `benchmarks/timings/`). O parágrafo termina dizendo que esses números justificam as duas decisões e que o Cap. 5 mede só a versão final. Os valores vêm das Tabelas `tab:naive-optimized`, `tab:memoria` e `tab:tempo-execucao` do `ch6avaliacao.tex` atual; copie-os antes da Task 4 apagá-las.
  - No parágrafo que introduz a conversão "vetorizada" (≈ linha 1502), acrescentar uma frase: a conversão é aplicada a uma coluna inteira de uma vez, por uma operação da biblioteca de dados (pandas) sobre todos os valores, e nenhuma estrutura de índice é criada.

- [ ] **Step 3: §4.5.2, coerência com o código medido**
  - "(8~MB, por padrão, de 8 a 256~MB)" → "(128~MB, por padrão)". "(1024, por padrão, de 1024 a 8192)" → "(2048, por padrão)". Os intervalos ficam de fora até a Etapa 1 definir os definitivos.
  - Acrescentar uma frase: a escolha automática desses dois valores conforme a máquina está em desenvolvimento.
  - A Tabela `tab:bloco` fica, mas a frase final "O padrão de 8~MB privilegia, portanto, a memória, e blocos maiores compensam pouco." passa a "Blocos maiores reduzem pouco o tempo e aumentam bastante o pico de memória."

- [ ] **Step 4: Marcar o botão na Figura 17**

`.superpowers/scratch/mark_figure.py` abre `docs-tcc/images/figure16-gui-verificacao.png` com `PySide6.QtGui.QImage` e desenha, com `QPainter`, um retângulo vermelho (`#E00000`, sem preenchimento, traço de 3 px, 4 px de folga) em volta do botão "Verificar SGBDs". As coordenadas saem da inspeção da imagem; o botão fica na barra do console, à esquerda de "Executar". O script salva no mesmo caminho e guarda o original em `.superpowers/scratch/figure16-original.png`. Conferir o resultado lendo a imagem.

- [ ] **Step 5: Commit e push**

```
rtk git add docs-tcc/chapters/ch4proposta.tex docs-tcc/images/figure16-gui-verificacao.png
rtk git commit -m "docs(relatorio): correcoes do orientador na secao 4.6 e justificativa historica na 4.5" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
rtk git push
```

---

### Task 3: Números da campanha intermediária

Depende da Task 1.

**Files:**
- Create (não versionado): `.superpowers/scratch/v4preview_numbers.py` e a sua saída `.superpowers/scratch/v4preview_numbers.txt`
- Modify: `benchmarks/README.md` (seções EN "Campaigns of the current version" e PT "Campanhas da versão atual")

**Interfaces:**
- Consumes: os CSVs da Task 1.
- Produces: `v4preview_numbers.txt`, a única fonte dos números das Tasks 4 e 5.

- [ ] **Step 1: Escrever `v4preview_numbers.py`**

Total de uma importação = soma das medianas das fases (`infer`, `validate` e uma linha `write` por SGBD/entidade), como no Cap. 5 atual. O script imprime:
- (a) **Fases em N = 262144:** tempo por fase nos dois modos e participação percentual no multifonte (escrita agregada por SGBD).
- (b) **Escrita por SGBD:** linhas processadas, tempo e linhas/s (multifonte, 262144), mais a participação do Cassandra na escrita e no total.
- (c) **Multifonte × combinado em 262144:** inferência, validação, total e pico, e a diferença percentual do total. Tamanho em MB (10^6 B) dos arquivos de `data/benchmark/generated/262144/`, colunas por arquivo e fração de células vazias do combinado.
- (d) **Escala:** tabela com os 6 volumes × 2 modos (tempo total e pico); razão entre volumes consecutivos; expoente b de `log t = a + b·log N` por mínimos quadrados, só com N ≥ 16384, para tempo e pico, por modo.
- (e) **Validação prévia:** fração `(infer + validate) / total` por volume e modo.
- (f) **Divisão de N entre as fontes** em 262144 (de `benchmark_data._split_rows(262144, 42)`).
- (g) **Registros guardados** para o exemplo de redundância: a contagem de `categories` distintas e de usuários distintos em 262144 é tirada dos CSVs gerados (`stock.category`, `purchase.user_id` ou as colunas equivalentes declaradas em `data/ecommerce/import_config.json`).

- [ ] **Step 2: Rodar e conferir a coerência**

Run: `.venv/Scripts/python.exe .superpowers/scratch/v4preview_numbers.py > .superpowers/scratch/v4preview_numbers.txt`

Expected: as somas de (a) batem com os totais de (d) em 262144; `rows` de `infer` = N.

- [ ] **Step 3: README**

Acrescentar uma subseção "Preliminary campaign (`v4-preview/`)" / "Campanha intermediária (`v4-preview/`)", com:
- o commit medido (`641e8a8`), os padrões de 128 MB e 2048 linhas e os eixos;
- a memória com 1 repetição;
- a tabela de escala (d) e os expoentes;
- a ressalva de que a campanha final da 3.2.0 a substituirá.

Commit "bench: resumo da campanha intermediaria no README" e push.

---

### Task 4: Cap. 5 reescrito com os números intermediários

Depende da Task 3. Conteúdo e ordem: spec, Parte 4b. Aqui ficam só as decisões da prévia.

**Files:**
- Modify: `docs-tcc/chapters/ch6avaliacao.tex` (reescrita completa)

- [ ] **Step 1: Estrutura**

- Abertura (só a versão final; remete à §4.5.1).
- Metodologia: QP1–QP5 em ordem; geração dos dados com a semente explicada; protocolo pareado em linguagem simples, com o fator 3,3× da v3 citado como exemplo; os links.
- Configuração experimental: "máquina em que os experimentos rodaram"; tabela das imagens Docker; referência à Tabela `tab:exemplo-ecommerce` para o que cada SGBD guarda; bloco de 128 MB e lote de 2048, que são os padrões da ferramenta medida; a memória livre do Step 1 da Task 1.
- Resultados, abrindo com a frase do 262144.
- QP1 a QP4.
- QP5 "em andamento".
- Discussão.
- Ameaças à validade.

Os rótulos das seções `sec:metodologia-avaliacao`, `sec:protocolo-medicao`, `sec:config-experimental`, `sec:resultados`, `sec:res-escala`, `sec:discussao-avaliacao` e `sec:ameacas-validade` são mantidos, porque o resto do texto os cita. `sec:res-estrategia`, `sec:res-execucao` e `sec:res-tradeoff` deixam de existir; procurar referências a eles nos outros capítulos e redirecioná-las para `sec:estrategias-escrita`.

- [ ] **Step 2: Avisos da prévia**

Uma frase na abertura e outra na configuração experimental dizem que os números são preliminares: o tempo é a mediana de 3 repetições e a memória vem de uma repetição. A QP5 tem um parágrafo que descreve a campanha exploratória (blocos de 16 a 256 MB e lotes de 512 a 8192, em 131072 linhas) e a escolha automática planejada, sem números.

- [ ] **Step 3: Tabelas e o gráfico**

- Tabela de fases (a); tabela de escrita por SGBD (b); tabela de modos (c); tabela de escala (d), com 6 linhas; tabela da validação prévia (e).
- Nenhuma figura que repita uma tabela.
- Uma figura nova, pgfplots `loglogaxis`, com o tempo total × N nos dois modos e uma reta tracejada de inclinação 1 que passa pelo ponto de 16384 do multifonte, rotulada "crescimento linear". Atenção à armadilha registrada na memória do projeto: em eixo log, os rótulos de `nodes near coords` precisam de `point meta=explicit symbolic`.
- Cada tabela e a figura dizem na legenda de qual campanha vêm, e a "Fonte:" leva a URL `https://github.com/lucasbc92/polyglot-import-csv/tree/main/benchmarks/v4-preview/timings` (ou `/memory`).

- [ ] **Step 4: Veredito de escalabilidade (QP3)**

Uma frase com o expoente b do tempo por modo e a leitura dele: b entre 0,9 e 1,1 → "cresce linearmente com o volume"; b > 1,1 → superlinear; b < 0,9 → sublinear. Outra frase faz o mesmo para o pico de memória. Dizer que os custos fixos de cada execução dominam em 1024 linhas e que por isso esse volume fica fora do ajuste.

- [ ] **Step 5: Commit e push** ("docs(relatorio): capitulo 5 reestruturado com a campanha intermediaria")

---

### Task 5: Conclusão unificada, Cap. 1 e Resumo/Abstract

Os Steps 1 e 2 podem rodar durante a campanha. O Step 3 depende da Task 3.

**Files:**
- Modify: `docs-tcc/chapters/consideracoes.tex`, `docs-tcc/main.tex` (o `\include` de `ch5futuros` e o Resumo/Abstract ≈ linhas 405–470), `docs-tcc/chapters/ch1introducao.tex` (≈ linhas 105–110)
- Delete: `docs-tcc/chapters/ch5futuros.tex` (o conteúdo passa para `consideracoes.tex`)
- Modify: as referências a `cap:futuros` (Grep em `docs-tcc/chapters/`)

- [ ] **Step 1: Unificar**

- `\chapter{Conclusão}`, mantendo `\label{cap:conclusao}`.
- O antigo `ch5futuros.tex` entra como `\section{Atividades Futuras}\label{sec:futuros}` ao fim. O texto de abertura dele passa de "esta seção" e "Concluídas a implementação..." para algo que funcione como seção. No item "Aprofundamento da avaliação", "até cem mil linhas" vira "até 262.144 linhas".
- O parágrafo "Como trabalho futuro (Capítulo~\ref{cap:futuros}), destacam-se..." sai.
- A frase "Consolida-se, assim, ... modelagem de dados heterogêneos." é substituída pelo texto do orientador citado no spec (Parte 4c), começando por "Consolida-se, assim, a \textit{PolyglotImportCSV} como um artefato resultante de uma pesquisa na área de modelagem poliglota de dados."
- Tirar `\include{chapters/ch5futuros}` do `main.tex`.
- Grep por `cap:futuros` em `docs-tcc/chapters/` e `docs-tcc/main.tex`: toda ocorrência vira `sec:futuros` com o texto ajustado ("Seção~" no lugar de "Capítulo~").

- [ ] **Step 2: Cap. 1**

A frase das linhas ≈ 105–110, que lista o que a avaliação mede ("efeito do tamanho do bloco de leitura e, como linha de base, o ganho da escrita em lote..."), passa a listar o que o novo Cap. 5 mede: custo por fase e por SGBD, modos de importação, escalabilidade, custo da validação prévia e efeito do bloco e do lote.

- [ ] **Step 3: Veredito e números (depois da Task 3)**

- No parágrafo da avaliação, na Conclusão: "Em cem mil linhas, a escrita... quatro quintos..." passa a usar os números de 262144 de (a)/(e). Acrescentar o veredito de escalabilidade da Task 4, Step 4. Os números históricos ("nove vezes", "doze vezes") ficam, com a ressalva "medidos em uma versão anterior (Seção~\ref{sec:estrategias-escrita})". Os verbos ficam no presente.
- Resumo e Abstract: "cerca de um quinto do tempo de uma importação de cem mil linhas" passa a usar a fração de (e) em 262144. Acrescentar meia frase com o veredito de escalabilidade, e os números históricos ganham a mesma ressalva.

- [ ] **Step 4: Commit e push** ("docs(relatorio): Conclusao unificada com as atividades futuras e veredito de escalabilidade")

---

### Task 6: Compilação e conferência do relatório intermediário

Depende das Tasks 2, 4 e 5 e da campanha terminada (Docker pode continuar ligado).

- [ ] **Step 1: Restos.** Grep em `docs-tcc/chapters/ch6avaliacao.tex` por `8~MB|bloco padrão|históric|ingênua|materializa|QP6|QP7`: vazio, exceto as remissões à `sec:estrategias-escrita`. Grep em `docs-tcc/chapters/` por `cem mil` e `100\\,000|100000`: cada ocorrência que restar está correta no contexto (por exemplo, a §4.5.1 histórica).
- [ ] **Step 2: Números.** Para cada número do Cap. 5, da Conclusão e do Resumo/Abstract, encontrar o valor correspondente em `.superpowers/scratch/v4preview_numbers.txt`. Listar os conferidos no relato da task.
- [ ] **Step 3: Compilar.** Run: `cd docs-tcc && latexmk -pdf -interaction=nonstopmode main.tex`. Expected: `main.pdf` gerado, sem `undefined references` nem `Citation ... undefined` no `main.log`.
- [ ] **Step 4: Olhar o PDF.** Ler as páginas do Cap. 5, da §4.6 (Figura 17 com o retângulo) e da Conclusão. O gráfico log-log precisa estar legível e com a legenda embaixo, e o sumário precisa mostrar "Conclusão" com a seção "Atividades Futuras".
- [ ] **Step 5: Entregar o PDF ao autor** como `docs-tcc/main.pdf`. O nome versionado fica com ele; o PDF não é commitado sem o OK dele.

---

### Task 7: Notas para a reunião

**Files:**
- Create (não versionado; o autor decide se commita): `docs-tcc/notas-reuniao-2026-11-09.md`

- [ ] **Step 1: Escrever, em português e em tópicos curtos:**
  - **O que mudou na prévia**, com as páginas do PDF novo.
  - **Respostas às dúvidas dele:**
    - por que tempo e memória vêm de execuções separadas: o rastreamento de alocações deixa a importação 3,3× mais lenta, e de forma desigual entre as fases;
    - por que as cargas eram diferentes: a ingênua e a materialização não existem mais no código, e a coleção `orders` veio depois. Por isso saíram do Cap. 5;
    - a semente 42;
    - "hospedeiro" = a máquina dos experimentos;
    - o bloco de 8 MB era o **menor**, não o maior;
    - "Finished" é de uma simulação (`--dry-run`), e uma importação real já diz "Finished import — N partition(s) written";
    - "isolada" = não investigada.
  - **O que vem depois:** a escolha automática do bloco e do lote (a ideia, em três linhas), a GUI em inglês e a campanha final.
  - **Perguntas para ele:** se a análise de escalabilidade atende e se a justificativa resumida na §4.5 basta.
