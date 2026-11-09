# Design: revisão do Prof. Ronaldo na v2.3 do relatório — tamanho automático, GUI em inglês, nova campanha e reescrita do Cap. 5

- **Data:** 2026-11-08
- **Status:** revisado por um leitor externo e com as respostas do autor; aguarda aprovação
- **Base:** `main` em `641e8a8` (inclui as mudanças do autor nos sliders e nos limites, commits `6b7becc`, `3e4f967`, `e567a1e`, `641e8a8`)
- **Entrada:** `docs-tcc/TCC2-PolyglotImportCSV-Report-v2.3_REVISADO.pdf` (não versionado; não commitar sem perguntar) e o e-mail do orientador de 2026-11-06 ("segue a revisão do restante do texto... quero conversar contigo, pois tive algumas dúvidas")
- **Versão resultante da ferramenta:** 3.2.0 (ver "Versão e release")

## Origem e intenção

O orientador revisou a v2.3 do relatório da §4.6 (interface gráfica) até o fim. São 61 anotações: na §4.6, a interface; no Cap. 5, a avaliação; e, no fim, a estrutura de Atividades Futuras/Considerações Finais. Ele diz no e-mail que ficou com dúvidas, e o autor também acha o Cap. 5 confuso. **O objetivo central é tornar o Cap. 5 claro**: um leitor que não acompanhou o projeto deve entender o que foi medido, como e o que os números significam, e a Conclusão deve dizer se a ferramenta escala (o orientador considera isso uma contribuição importante).

Em paralelo, o autor:

1. aceitou traduzir a GUI para o inglês (pedido do orientador: uso fora do Brasil e coerência com as mensagens da CLI, que já estão em inglês);
2. quer que a ferramenta **escolha sozinha** o tamanho do bloco de leitura e do lote de gravação, de preferência conforme a máquina, e que os controles desses dois valores **saiam da GUI**;
3. pediu que as campanhas sejam medidas de novo, com volumes em potências de 2, só da versão final (escrita em lote + leitura em blocos).

## Decisões do autor (conversa de 2026-11-08)

- **Limites pretendidos:** bloco de 16 a 256 MB; lote de 512 a 8192 linhas. O código em `641e8a8` tem o lote em 256–4096 (`MIN_BATCH_LINES = 256`), o que não era a intenção, e precisa ser corrigido.
- **Tamanho automático:** a ferramenta calcula o bloco e o lote. Pode ser um valor fixo bom para todas as máquinas, mas o autor prefere um valor que dependa da máquina. Os controles saem da GUI. Na CLI, o autor disse "talvez também". **Decisão do Claude:** as opções `--chunk-size` e `--batch-size` continuam na CLI como ajuste manual opcional, com padrão automático, porque sem elas a campanha não consegue variar os valores.
- **Volumes da campanha:** N ∈ {1024, 16384, 32768, 65536, 131072, 262144} (N = total de linhas dos quatro CSVs, como hoje). 500k está fora "por enquanto".
- **Só a versão final é medida.** A estratégia ingênua e a materialização saem do Cap. 5, e com elas as QP4–QP6, as Tabelas/Figuras históricas e a §5.3.7.
- **Justificativa das decisões de projeto:** os números históricos vão, **resumidos**, para o Cap. 4 (§4.5), deixando explícito que vêm de uma versão anterior. Isso atende à nota do orientador na p. 95: "o importante é justificar pq eliminamos a estratégia ingênua e a materialização".
- **Os dois modos de entrada (multifonte e combinado) continuam** na campanha. O autor não objetou à proposta.
- **"Tabela de sobrescrita" → "arquivos CSV".** O cartão passa a chamar-se "CSV files (`--source`)".
- **"Descartado":** usar a formulação do autor, completada com o lado que confundiu o orientador: "enquanto o modo de edição está ativo, é o texto digitado que será executado; ao sair dele, mediante confirmação, esse texto é desconsiderado e substituído pelo comando que a interface representa".
- **"Finished" → "Data import finished": não muda.** A Figura 15 é um `--dry-run`, cuja mensagem é "Finished dry-run — nothing was written" (`runner.py:343`). Uma importação real já diz "Finished import — N partition(s) written" (`runner.py:367`). Isso será explicado ao orientador por e-mail (está na memória do projeto). A legenda da Figura 15 passa a dizer que se trata de uma simulação.
- **"Verificar SGBDs" destacado na Figura 17:** o botão não muda no programa. A figura ganha um retângulo vermelho em volta do botão.
- **Atividades Futuras + Considerações Finais → um capítulo "Conclusão"**, com Atividades Futuras como última seção.

## Parte 1 — Código: tamanho automático do bloco e do lote

### Estado atual (em `641e8a8`)

- `stream_source.py`: `MIN_CHUNK_MB = 16`, `MAX_CHUNK_MB = 256`, `DEFAULT_CHUNK_MB = 128`. `chunk_rows()` converte o orçamento em MB em linhas, medindo o tamanho em memória das primeiras mil linhas de cada arquivo.
- `import_plan.py`: `MIN_BATCH_LINES = 256`, `MAX_BATCH_LINES = 4096`, `DEFAULT_BATCH_LINES = 2048`. O lote de cada entidade é limitado às linhas de um bloco (`entity_batch`).
- `cli.py`: `--chunk-size` e `--batch-size` usam `click.IntRange` com esses limites. Os textos de ajuda ainda dizem "(8-256)" e "(1024-8192)".
- GUI: os sliders de `options_panel.py` têm um erro de um passo. A posição inicial é `DEFAULT/MIN`, quando deveria ser `(DEFAULT-MIN)/MIN`, e por isso o comando sai com 144 MB e 2304 linhas enquanto os rótulos mostram 128 MB e 2048 linhas. Os rótulos perderam a opção da CLI ("Bloco lido por vez:"). `gui/state.py` ainda diz "O lote deve ter entre 1024 e 8192 linhas". Oito testes de `tests/test_gui_options_panel.py` e `tests/test_gui_main_window.py` falham (procuram `chunk_spin`/`batch_spin`).
- `benchmark_runner.py` / `scripts/run_benchmarks.py`: há o eixo `--chunk-sizes`, mas não um eixo de lote. A ajuda de `--chunk-sizes` ainda sugere `8,64,256`, que estão fora do intervalo.

A remoção dos sliders (abaixo) resolve o erro da GUI e os testes quebrados. Não há correção separada.

### O que muda

1. **Limites:** bloco 16–256 MB (já está assim); lote **512–8192** linhas. Textos de ajuda da CLI e do executor corrigidos.
2. **Eixo de lote no executor de campanhas:** `--batch-sizes` (lista, como `--chunk-sizes`), com uma coluna `batch_lines` nos resultados e na chave do checkpoint de `--resume`. O cabeçalho do CSV muda, então as campanhas novas vão para pastas novas (`benchmarks/v4/...`). As pastas `v3` ficam como estão.
3. **Modo automático**, padrão da CLI quando `--chunk-size`/`--batch-size` não são passados:
   - **Bloco** (**decisão do Claude** sobre a forma da regra): a campanha exploratória roda numa só máquina, com memória livre quase constante, e por isso não consegue mostrar como o melhor bloco varia com a memória. A regra combina duas partes:
     1. **um teto "de conforto"**, tirado da campanha: o menor bloco cujo tempo total fica dentro da variação entre campanhas (cerca de 3%) do melhor tempo medido. Acima dele, o bloco só gasta memória;
     2. **um limite de segurança por princípio**, tirado da memória livre no início da execução: o maior bloco cujo pico previsto (base + k × bloco, com a base e o k ajustados aos picos da campanha) cabe numa fração fixa da memória livre. Essa fração é de 25% e fica numa constante documentada.

     O bloco escolhido é o menor entre o teto, o limite de segurança e o necessário para ler a maior fonte inteira, e fica entre 16 e 256 MB. Numa máquina com memória sobrando, vale o teto; numa máquina fraca, vale o limite. O relatório explica que o limite de segurança decorre do projeto e não foi calibrado em várias máquinas (ameaça à validade).
   - **Lote:** um valor único para todos os SGBDs (**decisão do Claude**). Ele é o menor lote cujo tempo total fica dentro de cerca de 3% do melhor. Se a campanha mostrar que algum SGBD prefere outro lote (a escrita é cronometrada por SGBD), isso é relatado na QP5 e vira atividade futura, sem lote por SGBD nesta versão.
   - **Registro:** o valor escolhido e o motivo aparecem no log da sessão e no resumo da execução, por exemplo "chunk 128 MB (auto: 5.9 GB free)" e "batch 2048 lines (auto)", e também nas métricas de benchmark. Sem isso, execuções em máquinas diferentes não são comparáveis nem reproduzíveis.
   - **Valores manuais:** passar `--chunk-size` ou `--batch-size` desliga o automático para aquele valor, como hoje.
   - Ler a memória livre funciona em Windows e Linux, que são as plataformas das releases. Fica a critério do implementador usar `psutil` (acrescentá-lo às dependências e conferir o empacotamento PyInstaller) ou a biblioteca padrão (`ctypes` no Windows e `/proc/meminfo` no Linux).
4. **GUI:** os dois sliders saem do cartão de opções. O comando montado não leva `--chunk-size`/`--batch-size`. A §4.6 diz que "todas as opções são explicitadas, inclusive as mantidas no padrão", então o texto passa a explicar que bloco e lote são automáticos e por isso não aparecem. O parágrafo "A alternativa — omitir..." sai de qualquer forma (Parte 4).

## Parte 2 — Código: GUI em inglês

- Todo texto visível da janela passa para o inglês: títulos dos cartões, rótulos, dicas dos ícones de ajuda, botões ("Check DBMSs", "Run", "Stop", "Edit command", "Copy", "Save log…"), barra de estado ("Ready — no import running", "Finished — 9.34 s", ...), diálogos de confirmação, mensagens de validação de `gui/state.py` e `gui/preflight.py` e os textos do arrastar e soltar.
- Cartão de fontes: título "CSV files (`--source`)". A dica explica que, vazia, valem os caminhos do bloco `sources` da configuração de importação, e que cada arquivo escolhido substitui o caminho da fonte correspondente.
- Mensagens da CLI exibidas no console não mudam (já estão em inglês).
- Testes da GUI que conferem textos são atualizados. Os testes de comportamento continuam valendo.
- O registro de métricas de benchmark continua fora da GUI, como hoje.

## Parte 3 — Campanhas

Todas medem a escrita em lote com leitura em blocos, a única da ferramenta, com o protocolo atual: limpeza dos cinco SGBDs antes de cada execução, mediana de 3 repetições e campanhas pareadas sem e com instrumentação de memória (`--no-trace-memory` para tempo; com rastreamento para pico). O Docker é ligado para as campanhas, com autorização do autor em 2026-11-08 ("rode as campanhas de novo"). Elas rodam destacadas (`Start-Process`), fora do Claude Code, porque a máquina tem 8 GB e o Claude Code encerra shells em segundo plano quando falta memória. Cada pasta é conferida antes da próxima campanha.

### 3a. Exploratória (escolha da regra automática)

- **Código medido:** depois dos itens 1–2 da Parte 1 (limites e eixo `--batch-sizes`) e antes do modo automático.
- **Célula:** N = 131072, multifonte (**decisão do Claude:** a maior fonte, `purchase`, ocupa cerca de 95,5 MB em memória nesse volume (medido depois, na própria campanha), então os blocos de 16, 32 e 64 MB a leem em vários pedaços e os de 128 e 256 MB a leem inteira; com 262144, a campanha dobraria de duração).
- **Eixos (um de cada vez):** bloco ∈ {16, 32, 64, 128, 256} MB com o lote fixo em 2048; lote ∈ {512, 1024, 2048, 4096, 8192} com o bloco fixo em 128 MB. São 9 células distintas.
- **Repetições:** tempo, 3 por célula; memória, **1** por célula (**decisão do Claude:** na v3, o pico variou menos de 0,2% entre campanhas; a campanha exploratória serve para escolher a regra, e não é a fonte dos números principais do Cap. 5).
- **Estimativa:** cerca de 2 h para o tempo e 2,5 h para a memória.

### 3b. Final (fonte do Cap. 5)

- **Código medido:** o código final das Partes 1 e 2. **Decisão do Claude:** o executor resolve o automático **uma vez**, no início da campanha, com a mesma função da CLI, e passa os valores resultantes explicitamente a todas as execuções. Se resolvesse a cada execução, a memória livre variaria e as repetições e o par tempo/memória poderiam medir configurações diferentes. Os valores escolhidos e a memória livre no momento ficam nos metadados da campanha e são citados no Cap. 5.
- **Condições de partida** (**decisão do Claude**, vale para 3a e 3b): a mesma pilha `docker compose` e a limpeza atual antes de cada execução. Os resultados ganham uma coluna com a memória livre no início de cada execução, para que a reprodutibilidade possa ser conferida.
- **Matriz:** N ∈ {1024, 16384, 32768, 65536, 131072, 262144} × modo ∈ {multifonte, combinado}.
- **Repetições:** 3, tanto no tempo quanto na memória.
- **Estimativa:** cerca de 509 mil linhas por modo e repetição; cerca de 2 h para o tempo e 6 h para a memória (o rastreamento deixa a execução 3,3× mais lenta). A de memória roda durante a noite.
- **Precisão:** como na v3, uma célula repetida entre as duas campanhas de tempo (por exemplo, N = 131072, multifonte, com o bloco e o lote que o automático escolheu, que também aparecem na exploratória) dá a variação entre campanhas.
- Os dados de 262144 linhas são gerados pelo gerador determinístico atual (semente 42). Ficam em `data/benchmark/generated/`, fora do git, como os demais.

### Resumo dos números

Como na v3, `benchmarks/README.md` ganha uma seção com as campanhas novas (EN e PT), e cada número citado no relatório é recalculado dos CSVs por um script de conferência antes de entrar no texto.

## Parte 4 — Relatório

Vale tudo o que o autor já decidiu sobre o estilo: legenda de figura embaixo, título de tabela em cima, "Fonte:" embaixo; uma frase antes de cada tabela e figura; nada de histórico de versões na prosa; "SGBD" no texto em português. A versão do relatório e os nomes dos PDFs ficam a cargo do autor (ele renumerou os PDFs por conta própria antes).

### 4a. Capítulo 4

Anotações das p. 76–81 do PDF anotado:

| Pág. PDF | Anotação | Ação |
|---|---|---|
| 76 | "tabela de sobrescrita" e "sobrescrita": não entendeu; sugere termo ligado ao contexto | O terceiro cartão "recebe os arquivos CSV de entrada"; o texto explica que, vazio, valem os caminhos da configuração e que cada arquivo escolhido substitui o caminho da fonte correspondente. A palavra "sobrescrita" sai da seção. |
| 76 | "Com uma" → "Uma" (correção de estilo) | Aplicar. |
| 77 | Parágrafo "A alternativa — omitir..." é "muita explicação" | Cortar. |
| 78 | "é descartado": não entendeu | Usar a formulação acordada (ver Decisões). |
| 78 | GUI em inglês | Parte 2; a §4.6 cita os rótulos novos ("Check DBMSs", "Edit command", ...). |
| 79 | "Finished" → "Data import finished" | Não muda; a legenda da Figura 15 diz que é uma simulação (`--dry-run`) concluída; explicação no e-mail. |
| 81 | Figura 17 deveria destacar "Verificar SGBDs" | Retângulo vermelho em volta de "Check DBMSs" na figura. |

Além das anotações:

- **§4.5.1** (`sec:estrategias-escrita`): o último parágrafo ("permanecem descritas... linhas de base contra as quais o Cap. 5 mede") é substituído por números resumidos, apresentados como medições de uma versão anterior da ferramenta, sem a carga da coleção `orders`: a escrita em lote foi cerca de 9× mais rápida que a ingênua (N = 10 000, materialização; `benchmarks/timings-naive/`), e a leitura em blocos usou 12,5× menos memória que a materialização em N = 100 000, com sobrecusto de tempo de +10% nesse ponto (`benchmarks/`, `benchmarks/timings/`). Pode ser uma tabela pequena ou texto. Esses números são a justificativa das duas decisões.
- **§4.5.2** (`sec:modelos-execucao`): a descrição de `--chunk-size`/`--batch-size` passa a explicar o modo automático, a regra e os limites manuais. A Tabela `tab:bloco` (v3, bloco de 8 MB) é substituída pelos resultados da campanha exploratória, ou movida para o Cap. 5 com uma referência aqui. A frase "o padrão de 8 MB privilegia a memória" sai. A frase "um arquivo maior que a memória disponível pode ser importado desde que [os conjuntos de chaves] caibam nela" fica, porque descreve o projeto.
- **§4.6:** a descrição do segundo cartão perde os dois controles de tamanho e ganha uma frase sobre o automático. As Figuras 13 a 17 são recapturadas com a GUI em inglês por `scripts/capture_gui_figures.py`, a partir de execuções reais. O retângulo da Figura 17 pode ser acrescentado pelo script, desenhando sobre o `QPixmap`, ou depois, sobre a imagem.
- Qualquer outra menção a "bloco padrão de 8 MB", "1024 linhas" ou intervalos antigos, nos Caps. 1 e 4, no Resumo/Abstract (`main.tex`), nos apêndices e nos READMEs, é atualizada. Antes de fechar, fazer uma busca por `8~MB`, `8 MB`, `1024`, `8192` e `chunk`.

### 4b. Capítulo 5 — reescrita

**Estrutura nova:**

1. **Abertura.** O que o capítulo mede (só a versão final) e por que as alternativas abandonadas não aparecem (remete à §4.5.1).
2. **Metodologia**
   - **Questões de pesquisa**, renumeradas em ordem e todas respondidas com a versão final:
     - QP1: custo por fase e escrita por SGBD;
     - QP2: multifonte × combinado;
     - QP3: escalabilidade;
     - QP4: custo da validação prévia;
     - QP5: efeito do bloco e do lote, e a regra automática.
   - **Geração dos dados.** Explicar a "semente" (o número que inicializa o gerador pseudoaleatório: a mesma semente gera sempre os mesmos arquivos, byte a byte) e que 42 é um valor arbitrário, apenas fixado. Mostrar a divisão de N entre as quatro fontes no maior volume.
   - **Protocolo de medição**, em linguagem simples:
     - medir a memória obriga o Python a registrar cada alocação, o que deixa a execução cerca de 3,3× mais lenta, e de forma desigual entre as fases;
     - por isso, cada configuração roda duas vezes, uma para cronometrar e outra para medir memória;
     - um exemplo concreto com os números de uma fase;
     - a mediana de três repetições e a limpeza dos bancos antes de cada execução.
3. **Configuração experimental**
   - "Hospedeiro" passa a ser "a máquina em que os experimentos rodaram" (memória, CPU e sistema).
   - A Tabela das imagens Docker continua.
   - Uma tabela nova, ou uma referência explícita à Tabela `tab:exemplo-ecommerce` da §4.3, lembra **quais dados do cenário cada SGBD guarda**. A seção de escrita por SGBD remete a ela (pedido da p. 86).
   - "Bloco padrão" sai: o automático informa os valores escolhidos nesta máquina.
   - Os dados de cada tabela são apontados por link completo no GitHub (`https://github.com/lucasbc92/polyglot-import-csv/tree/main/benchmarks/v4/...`) ou por uma nota de rodapé única com a URL base (pedido da p. 86).
4. **Resultados.** A primeira frase diz que **só a seção de escalabilidade cobre todos os volumes; as demais usam o maior, N = 262144** (pedido da p. 85).
   - **QP1.** Tabela de fases (sem a Figura 18, redundante com a tabela) e tabela de escrita por SGBD (sem figura). O exemplo de redundância responde à p. 87: a tabela `categories` recebe uma linha por produto do estoque, mas guarda só as categorias distintas, e o Neo4j recebe um comprador por compra, mas guarda só os usuários distintos. Isso vem em uma frase e um exemplo concreto de linhas do CSV, antes dos números.
   - **QP2.** Mesma análise de hoje, sem a Figura 19. A frase "a causa dessa diferença não foi isolada" vira "a causa dessa diferença não foi investigada neste trabalho" (p. 88). "Registro único de eventos" vira "registro único de vários tipos de eventos" (p. 88).
   - **QP3 (o centro).** Uma tabela com os 6 volumes × 2 modos (tempo e pico). Um **gráfico log-log** do tempo total × N, nos dois modos, com uma reta de referência de inclinação 1 (crescimento linear). O **expoente ajustado** (regressão de log t sobre log N, nos volumes a partir de 16384, onde os custos fixos pesam pouco) e a razão entre volumes consecutivos (cada volume dobra o anterior; se o tempo dobra, o crescimento é linear). Um **veredito explícito**: linear, superlinear ou sublinear, e até onde vale. O mesmo para o pico de memória. As Figuras 20 e 21, redundantes, saem; o gráfico novo é o único da seção.
   - **QP4.** A fração de inferência + validação por volume. Os problemas que a validação prévia detecta são listados de novo de forma resumida, sem remeter apenas à §4.2.4 (p. 90).
   - **QP5.** A campanha exploratória: tempo e pico por bloco e por lote, e a regra automática que sai deles.
5. **Discussão**
   - Verbos no presente: "acelera", "reduz" (p. 94).
   - O trecho "importar arquivos maiores que a memória... desde que os conjuntos de chaves caibam nela" sai da discussão (p. 95). A ideia permanece só na §4.5.2, como propriedade do projeto.
6. **Ameaças à validade**
   - Saem "medições históricas", a incerteza de 20% e "cargas diferentes" (p. 95).
   - A frase sobre as campanhas pareadas passa a explicar o motivo, em vez de só afirmar que "impede a leitura das duas métricas de uma mesma execução" (p. 95). O autor e o orientador vão conversar sobre isso, então o texto deve deixar a explicação autoexplicativa.
   - Acrescenta-se que a regra automática foi calibrada em uma única máquina.

Também é preciso explicar "conversão vetorizada" (p. 83: "o que é exatamente? é gerada alguma estrutura de índice?"). Como as QPs históricas saem, a explicação vai para a §4.5.1, onde o termo já aparece: converter uma coluna inteira de uma vez, com uma operação da biblioteca de dados sobre todos os valores, em vez de célula a célula; nenhum índice é criado.

### 4c. Conclusão

- `consideracoes.tex` passa a ser "Conclusão" (`\chapter{Conclusão}`, rótulo `cap:conclusao` mantido). `ch5futuros.tex` vira a sua última seção, "Atividades Futuras" (o rótulo `cap:futuros` vira `sec:futuros` e as referências são atualizadas). O `\include` de `ch5futuros` sai de `main.tex`.
- O parágrafo "Como trabalho futuro (Capítulo 6), destacam-se..." é substituído pela seção nova (p. 98).
- A frase de fecho ("Consolida-se... alinhado à literatura...") é substituída pelo texto do orientador (p. 98), ajustado apenas na redação:
  > "...como um artefato resultante de uma pesquisa na área de modelagem poliglota de dados. Uma vez aplicada uma metodologia para projeto poliglota de dados e definidos os modelos de dados alvo sobre os quais os dados devem ser persistidos, caso existam fontes de dados exportáveis em CSV, a PolyglotImportCSV é capaz de realizar a carga de dados destas fontes respeitando o projeto poliglota realizado."
- O parágrafo da avaliação ganha o **veredito de escalabilidade** da QP3, em uma ou duas frases com os números (p. 97). Os números históricos citados ali ("nove vezes", "doze vezes") ficam só se a §4.5.1 os mantiver, e com a ressalva de que são de uma versão anterior.
- O Resumo/Abstract (`main.tex`, linhas ~419–470) cita os mesmos números históricos e os do Cap. 5, e é atualizado de forma coerente.
- O item "Aprofundamento da avaliação" das Atividades Futuras é atualizado: os volumes medidos vão até 262144, e os próximos seriam milhões de linhas e outras máquinas para calibrar a regra automática.

## Versão e release

- As tags `v3.1.0` (`3e4f967`) e `v3.1.1` (`e567a1e`) existem no `origin`, mas os dois workflows de release falharam (ImportError nos testes), e nenhuma release foi publicada. A última publicada é a `v3.0.0`. O `pyproject.toml` ainda diz `3.0.0`.
- **Decisão do Claude:** este trabalho sai como **3.2.0**. Tags enviadas não são reaproveitadas. As notas `docs/releases/v3.2.0.md` descrevem também o que as 3.1.x mudaram (limites de bloco e lote, sliders que depois saíram) e dizem que essas tags não têm release.
- Merge, tag e release só com o OK do autor. O push acontece a cada commit, como sempre.
- **Branch** (**decisão do Claude**, como nos trabalhos anteriores): `revisao-ronaldo-v23`, a partir do `main`. Os links do Cap. 5 apontam para `tree/main/benchmarks/v4/...` e passam a funcionar quando o autor fizer o merge, que precisa acontecer antes de o PDF ser enviado.

## Ordem de trabalho

1. Parte 1, itens 1–2 (limites e eixo `--batch-sizes`), com testes.
2. Campanha exploratória (3a).
3. Parte 1, itens 3–4 (modo automático, saída dos sliders), com a regra escolhida a partir de 3a.
4. Parte 2 (GUI em inglês). A ordem entre 3 e 4 é livre; os dois precisam estar prontos antes de 5.
5. Campanha final (3b) e resumo em `benchmarks/README.md`.
6. Parte 4 (Cap. 4, Cap. 5, Conclusão, Resumo/Abstract) e recaptura das figuras da GUI.
7. Release 3.2.0 (com o OK do autor) e rascunho do e-mail ao orientador: explicação do "Finished", o que mudou e o que ficou para conversar.

## Fora de escopo

- Volumes acima de 262144 linhas.
- Medir de novo a estratégia ingênua ou a materialização.
- Os slides da defesa (deck v1.1). Os números que mudarem neles são um trabalho separado, depois.
- Editar os arquivos JSON de configuração pela GUI (continua como atividade futura).

## Respostas do autor às perguntas do revisor

- **Prazo:** a entrega do relatório está bem adiante, então cabem as duas campanhas completas. Mas o orientador quer conversar em 2026-11-09 (segunda-feira, provavelmente à noite), e o autor quer levar **um resultado intermediário no Cap. 5 e as correções pedidas** (ver "Etapa 0").
- **PDFs anotados no repositório público** (`...-v2.2-REVISADO.pdf`, que entrou no `6b7becc`, e `...-v1.0-REVISADO.pdf`): **ficam como estão**. Nada é removido e o histórico não é reescrito.

## Resultado da campanha exploratória (2026-11-09)

Dados em `benchmarks/v4-explore/` (commits `d5c065f`, `759b8bb`, `2daead8`, `795db6f`), medidos sobre o commit `491a64f`, com N = 131072 e modo multifonte. O tempo é a mediana de 3 repetições; o pico vem de 1 repetição. As quatro pastas passaram na conferência, e as pastas pares têm contagens de linhas idênticas.

**Eixo do bloco** (lote 2048):

| Bloco | Total (s) | vs. melhor | Pico (MB) |
|---:|---:|---:|---:|
| 16 | 275,08 | +10,9% | 103,6 |
| 32 | 304,36 | +22,7% | 127,9 |
| 64 | 282,19 | +13,8% | 144,9 |
| 128 | 248,00 | — | 195,5 |
| 256 | 251,00 | +1,2% | 195,5 |

**Eixo do lote** (bloco 128 MB):

| Lote | Total (s) | vs. melhor | Pico (MB) |
|---:|---:|---:|---:|
| 512 | 211,97 | +8,5% | 200,4 |
| 1024 | 206,57 | +5,8% | 197,0 |
| 2048 | 195,34 | — | 195,5 |
| 4096 | 208,00 | +6,5% | 195,6 |
| 8192 | 202,80 | +3,8% | 197,1 |

**Tempo total de cada execução, por repetição** (tirado dos logs da sessão; o CSV guarda só as medianas). As células rodam nesta ordem dentro de cada repetição:

| Campanha | Repetição | 16 / 512 | 32 / 1024 | 64 / 2048 | 128 / 4096 | 256 / 8192 |
|---|---|---:|---:|---:|---:|---:|
| blocos | 1 | 319,6 | 256,2 | 262,4 | 247,1 | 241,5 |
| blocos | 2 | 267,4 | 299,4 | 282,1 | 230,6 | 236,4 |
| blocos | 3 | 302,9 | 352,8 | 387,2 | 471,2 | 324,9 |
| lotes | 1 | 244,0 | 211,0 | 196,3 | 211,7 | 201,3 |
| lotes | 2 | 209,1 | 210,3 | 193,8 | 207,4 | 211,4 |
| lotes | 3 | 195,9 | 194,8 | 189,6 | 195,8 | 187,9 |

**Leituras:**

- **A deriva entre campanhas é grande.** A célula comum (128 MB, 2048) levou 248,00 s numa campanha e 195,34 s na outra, 27% de diferença; o Docker foi reiniciado entre elas. A terceira repetição da campanha de blocos também derivou para cima, com uma execução de 471 s. Dentro de uma campanha, a mesma célula variou de 3,5% a 24% entre repetições na campanha de lotes.
- **Bloco:** nas repetições 1 e 2, feitas na mesma passada, os blocos que leem a maior fonte inteira (128 e 256 MB; a `purchase` precisa de cerca de 95,5 MB em 131072 linhas) foram de 16% a 30% mais rápidos que os de 16 a 64 MB. A diferença é maior que o ruído medido. Nas medianas, os blocos menores ficam de 11% a 23% atrás. O pico satura quando o bloco passa a conter a fonte inteira: 195,5 MB em 128 e em 256 MB.
- **Lote:** as medianas ficam a até 8,5% da melhor (2048), dentro do ruído entre repetições. Em cada repetição, nenhum lote é sistematicamente mais rápido. O pico quase não muda (de 195 a 200 MB). Nas campanhas de memória, de uma repetição só, o tempo cai a cada execução nos dois eixos (blocos: 903 → 636 s; lotes: 815 → 621 s). É efeito da ordem de execução, que é sempre a mesma com uma repetição, e não do bloco nem do lote: com o rastreamento ligado, esses tempos não são lidos como desempenho. O melhor lote de escrita de cada SGBD nas medianas (PostgreSQL 8192, Redis 4096, os demais 2048) não se sustenta contra esse ruído.
- **Nenhum lote foi limitado pelas linhas de um bloco.** Mesmo com 16 MB, um bloco da `purchase` tem 8523 linhas, mais que qualquer lote abaixo de 8192.
- **Pico em função do bloco efetivo** (o menor entre o bloco e o tamanho da maior fonte), em 131072 linhas: `pico ≈ 87,0 + 1,078 × bloco efetivo` (MB), com erro de até 8% nos quatro pontos distintos.
- **A base cresce com os dados.** A campanha intermediária (bloco de 128 MB, multifonte, seis volumes) dá base = pico − 1,078 × bloco efetivo, e essa base acompanha o tamanho das fontes em disco: `base ≈ 22,2 + 2,31 × MiB das fontes em disco`. O ajuste é feito de 32768 linhas em diante e acerta 91,0 contra 92,5 MB em 131072 e 161,3 contra 162,0 MB em 262144. Uma base fixa de 87 MB subestimaria o pico de 262144 linhas em cerca de 25%.

**Regra adotada** (substitui a da Parte 1, item 3, onde houver conflito). Na campanha final, a de memória reaproveita os blocos que a de tempo resolveu (`--auto-chunks-from`), para que o par meça a mesma configuração:

- **Tolerância** (decisão do Claude, registrada no ledger): a "variação entre campanhas" da Parte 1 mediu 27% e, aplicada literalmente, escolheria um bloco de 16 MB e um lote de 512. Isso foi descartado, porque esses 27% são deriva do ambiente entre campanhas, e não diferença entre células. As células são comparadas dentro da mesma campanha e da mesma repetição, como mostra a tabela acima. Com essa comparação, o bloco que lê a fonte inteira vence com folga (16% a 30%), e o lote não faz diferença mensurável. Se o autor preferir priorizar a memória, basta trocar o teto por 16 MB; o código fica igual.
- **bloco automático** = mín(256; MB necessários para ler a maior fonte declarada inteira; limite de segurança), preso a [16, 256] e arredondado a um inteiro: **para cima** quando quem decide é a fonte inteira, para que ela caiba num bloco só; para baixo nos demais casos, para não ultrapassar o limite de segurança (se arredondar para cima ultrapassaria o limite, decide o limite). **Decisão do autor em 2026-11-09**, depois de a revisão final da etapa 2 mostrar que o arredondamento para baixo podia ler uma fonte de 17,91 MB em dois blocos de 17 MB. O "teto de conforto" da Parte 1 virou "ler a maior fonte inteira", porque foi isso que os dados mostraram: o ganho vem de ler a fonte de uma vez.
  - MB necessários de uma fonte = linhas da fonte / linhas por MB, com as linhas por MB tiradas da mesma estimativa de `stream_source.chunk_rows`.
  - O número de linhas exige contar a fonte (uma leitura a mais). Como alternativa, a implementação pode usar `tamanho do arquivo × (MB em memória por MB em disco, medido nas primeiras mil linhas)`, que não exige outra leitura. A escolha fica com o implementador, desde que a estimativa seja documentada.
- **limite de segurança** = (0,25 × memória livre − base) / 1,078, com base = 22,2 + 2,31 × (MiB em disco das fontes que a importação lê). Constantes nomeadas: `PEAK_BASE_MB = 22.2`, `PEAK_BASE_PER_DISK_MB = 2.31`, `PEAK_MB_PER_CHUNK_MB = 1.078`, `FREE_MEMORY_FRACTION = 0.25`.
  - Os coeficientes vêm de uma máquina, do modo multifonte e de picos de uma repetição, e isso vira ameaça à validade. A fração de 25% é uma margem escolhida, não medida.
  - Se a memória livre for ilegível (`available_mb()` devolve `None`), o limite não se aplica, e o bloco é o necessário para ler a maior fonte inteira, preso a [16, 256]. O motivo é registrado no log.
- **O que a regra dá nesta máquina** (cerca de 890 MiB livres com o Docker no ar):
  - 131072 linhas (29,9 MiB em disco): base 91 MB, limite 121 MB, fonte inteira 95,5 MB → **bloco de 96 MB**, que lê a `purchase` inteira;
  - 262144 linhas (60,3 MiB): base 162 MB, limite 56 MB, fonte inteira 191 MB → **bloco de 56 MB**, limitado pela segurança;
  - com 2048 MiB livres e 262144 linhas: limite 325 MB → bloco de 191 MB.

  O resultado é sensível à memória livre: em 131072 linhas, abaixo de cerca de 776 MiB livres o limite cai abaixo de 95,5 MB, e a `purchase` passa a ser lida em dois blocos. Nesta máquina, a memória livre variou de 717 a 1030 MiB durante as campanhas. Esse é o comportamento pretendido, que troca tempo por memória quando ela falta, e o log registra o motivo. A campanha final resolve o automático uma só vez, no início, e cita o valor e a memória livre.
- **lote automático** = 2048, fixo. Ele foi o melhor nas medianas e é o do meio do intervalo; nenhum lote mostrou vantagem acima do ruído. O efeito do lote por SGBD vira atividade futura.

## Etapa 0 — prévia para a reunião de 2026-11-09

Vem antes da "Ordem de trabalho" abaixo e não muda o código da ferramenta.

1. **Campanha intermediária** (**decisão do Claude**), sobre o código atual do `main` (`641e8a8`; a CLI funciona, e só os testes da GUI estão quebrados), com os padrões atuais (bloco de 128 MB, lote de 2048):
   - os 6 volumes × 2 modos;
   - tempo com 3 repetições (cerca de 2 h) e memória com 1 repetição (cerca de 2 h);
   - pasta `benchmarks/v4-preview/`.

   Começa logo após a aprovação, com o Docker ligado (autorizado). Dá a curva de escalabilidade de que o orientador mais precisa. Se o automático escolher 128 MB e 2048 nesta máquina, esses números podem até ser reaproveitados, mas a decisão fica para depois da campanha final.
2. **Relatório intermediário**, gerado no branch `revisao-ronaldo-v23`; o nome do PDF fica com o autor:
   - Cap. 5 já na estrutura nova (Parte 4b), com os números da campanha intermediária. A QP5 (bloco e lote) aparece como "em andamento", com um parágrafo que descreve a campanha exploratória e o modo automático planejados. A abertura e a configuração experimental dizem que os números são preliminares, medidos com o bloco de 128 MB e o lote de 2048;
   - Cap. 4: as correções de texto da §4.6 e o resumo histórico da §4.5.1. As figuras da GUI ficam como estão (em português, com os campos numéricos), porque serão recapturadas depois da tradução, e o texto diz isso numa nota. As únicas exceções são o retângulo na Figura 17 e a legenda da 15, que já entram;
   - a Conclusão já unificada, com o veredito de escalabilidade da campanha intermediária.
3. **Notas para a reunião** (fora do relatório): respostas às dúvidas dele (protocolo pareado, cargas diferentes, "Finished" no dry-run, semente 42) e o plano do tamanho automático. O autor decide se usa.
