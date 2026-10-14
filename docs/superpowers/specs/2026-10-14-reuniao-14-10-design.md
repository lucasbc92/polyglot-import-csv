# Design — Reunião de 14/10: estratégia única, cabeçalho e multifonte × combinado

Data: 2026-10-14
Status: aprovado em brainstorming; aguardando revisão do autor.
Branch: `reuniao-14-10` (a partir de `main`).

## Origem

Resultado da reunião com o orientador (14/10), incluindo perguntas antecipadas da banca:

1. Eliminar a estratégia `naive`, deixando só a atual; a opção `--strategy` deixa de
   existir. No relatório, a ingênua continua documentada como primeira tentativa.
2. Confirmar se o modo multifonte tem desempenho muito melhor no modelo `stream`.
3. Verificar a obrigatoriedade do cabeçalho do CSV de entrada e documentá-la.
4. Banca: qual a vantagem do multifonte sobre o combinado (desempenho, tamanho,
   organização, outras)?
5. Banca: por que a estratégia ingênua está documentada — ela surgiu no TCC1 e evoluiu
   para a estratégia atual.

## Fatos verificados (base do design)

**Multifonte × combinado** (campanhas de agosto; tempo de `benchmarks/timings/`, memória de
`benchmarks/`, `N = 100 000`):

| Critério | Multifonte | Combinado |
|---|---|---|
| Tamanho dos arquivos (`data/benchmark/generated/100000/`) | 23,75 MB (4 arquivos) | 28,55 MB (+20%; +21% em 1k e 10k) |
| Células vazias | 0% (20, 33, 6 e 7 colunas) | 45% (39 colunas) |
| Fase de leitura (materialize) | 7,69 s | 15,15 s (2×) |
| Tempo total materialize / stream | 149,9 s / 165,0 s | 161,9 s / 181,4 s |
| Pico de memória materialize / stream | 950,7 MB / 75,9 MB | 1009,5 MB / 79,8 MB |

- Tempo total: +8% (materialize) e +10% (stream), abaixo da incerteza de ~20% declarada
  no capítulo: **empate**. O stream não favorece o multifonte: reduz a memória ~12× e custa
  ~10% de tempo nos **dois** modos.
- Leitura 2× mais lenta no combinado e memória +5–6% (a memória reproduz-se com <0,1%):
  diferenças reais.
- Organização (conferido no código): um cabeçalho por tipo × um cabeçalho comum a todos
  (`sources.py`); `--source` substitui uma fonte isolada, enquanto no combinado só o arquivo
  inteiro pode ser substituído (`load_sources` recusa nomes derivados da coluna de origem);
  no stream, a amostragem de entidades com união de fontes lê só o primeiro bloco de cada
  arquivo multifonte, mas varre o combinado até achar cada origem
  (`stream_source.sample_union_sources`); arquivos separados podem vir de sistemas
  distintos e ser atualizados independentemente.
- Vantagem do combinado: um único arquivo, formato natural quando a origem já é um log de
  eventos.

**Cabeçalho:** `csv_reader.read_csv` e `stream_source._read_chunks` usam `pd.read_csv` com o
padrão `header=0`: a primeira linha é **sempre** o cabeçalho, sem validação. Um CSV sem
cabeçalho perde a primeira linha de dados, que vira nomes de coluna, e o mapeamento por nome
falha. No combinado, a primeira coluna do cabeçalho é a de origem.

**Versões:** `pyproject.toml` está em 1.1.0 e `docs/releases/v1.1.0.md` existe, mas a única
tag é `v1.0.0`. O merge `1553f30` tem a versão 1.1.0; depois dele, o único commit de código é
`8365d43` (`connection` obrigatório). O workflow de release dispara em tags `v*`.

## Decisões

- Remoção **completa** da estratégia ingênua (abordagem A).
- Nomenclatura no relatório: "estratégia ingênua (*naive*)" × "estratégia em lote
  (*batch*)", com o termo inglês em itálico na primeira ocorrência. "Em lote" é definida uma
  vez como conversão de tipos por coluna inteira (vetorizada) **mais** gravação em lotes,
  para não esconder que o ganho de 42× do mapeamento vem da vetorização.
- A pergunta 2 é respondida com os dados existentes; nenhuma campanha nova. O caminho de
  escrita da estratégia em lote não mudou desde agosto.
- Cabeçalho: documentar e fixar o comportamento com um teste; nenhuma validação nova.
- Publicar `v1.1.0` (tag em `1553f30`), a última versão com a ingênua, citada no relatório
  para reproduzir a QP4; ao fim, versão `2.0.0` (duas mudanças incompatíveis: sem
  `--strategy`; `connection` obrigatório).

## Parte 1 — Código

Remover, de ponta a ponta:

- `cli.py`: opção `--strategy` e o parâmetro repassado ao runner. Uma chamada com
  `--strategy` passa a ser opção desconhecida (erro do click).
- `runner.py`: parâmetro `strategy`, o aviso "--strategy naive is ignored under --execution
  stream" e o repasse a `resolve_backend_entities` e aos importadores.
- `casting.py`: caminho célula a célula de `cast_frame`; a função perde o parâmetro
  `strategy` e mantém só o caminho por coluna. Ajustar comentários que citam o ramo naive.
- `mapping_resolver.py`: parâmetro `strategy` e o seu lugar na chave do cache de conversão.
- `stream_runner.py`: `strategy="optimized"` na chamada de `cast_frame`.
- Importadores: `importers/base.py` (assinatura), `postgres_importer.py` e
  `mongodb_importer.py` (parâmetro ignorado), `redis_importer.py` (`_write_naive`),
  `cassandra_importer.py` (`_write_naive`), `neo4j_importer.py` (`_merge_nodes_naive`,
  `_merge_rels_naive`). As funções em lote mantêm os nomes atuais.
- GUI: `gui/state.py` (`STRATEGY` e a sua exportação), `gui/command.py` (deixa de escrever
  `--strategy optimized`), docstrings de `gui/widgets/options_panel.py` e `gui/command.py`.
- Benchmarks: `benchmark_runner.py` (`_VALID_STRATEGIES`, dimensão da matriz, chave de
  retomada), `benchmark_results.py` (coluna `strategy` e chave da mediana),
  `scripts/run_benchmarks.py`, `scripts/run_benchmarks_100k.py`,
  `scripts/benchmark_tracemalloc_ab.py`, conforme o que cada um usa.
- Os resultados de agosto em `benchmarks/` (com coluna `strategy`) **não** mudam: são a
  proveniência do relatório. `benchmarks/README.md` ganha uma nota: a campanha ingênua foi
  medida com a versão 1.1.0, a última que contém essa estratégia.
- READMEs (seções EN e PT de `README.md`, e `packaging/README.md` se citar): remover
  `--strategy`, a coluna `strategy` do CSV de resultados e a menção à estratégia na GUI.

Testes: remover os que existem só para a ingênua (equivalência ingênua × em lote, escrita
linha a linha); adaptar os que passam `strategy` sem depender dela; adicionar um teste de CLI
garantindo que `--strategy` é rejeitada e um teste de GUI garantindo que o comando montado não
contém `--strategy`. Arquivos afetados (busca por `naive|strategy`): `test_casting_vectorized`,
`test_importer_write_batching`, `test_mapping_resolver`, `test_stream_memory`,
`test_benchmark_results`, `test_metrics`, `test_inference_probe`,
`test_benchmark_trace_flag`, `test_benchmark_output`, `test_gui_options_panel`,
`test_benchmark_resume`, `test_benchmark_runner`, `test_benchmark_tracemalloc_ab`,
`test_cli`, `test_gui_command`, `test_gui_main_window`, `test_gui_state`,
`test_runner_registry`.

Cabeçalho: teste que documenta o comportamento: um CSV cuja primeira linha é de dados tem
essa linha lida como nomes de coluna (materialize e stream), e uma entidade que mapeia uma
coluna pelo nome falha com a mensagem atual de coluna ausente.

Verificação: `./.venv/Scripts/python.exe -m pytest tests -q` com a suíte inteira passando
(referência antes: 728 passed / 1 skipped); relatar a nova contagem e quantos testes saíram
com a ingênua. `grep -rn "naive\|--strategy\|STRATEGY" src tests scripts` vazio, salvo
ocorrências sem relação (ex.: `SimpleStrategy` do Cassandra).

## Parte 2 — Relatório (v2.4)

Regra: nenhuma prosa sobre versões anteriores do **relatório**; a evolução da **ferramenta**
(TCC1 → TCC2) foi pedida pelo orientador e entra, curta e factual.

Cap. 4 (`ch4proposta.tex`):

- §4.1: remover `[--strategy optimized|naive]` do comando; o grupo "como importar" passa a
  ter só `--execution` (reescrever a frase dos três conjuntos sem `--strategy`).
- §4.2.1.1 (Raiz e `sources`): parágrafo sobre o cabeçalho obrigatório: a primeira linha de
  todo CSV é o cabeçalho e dá nome às colunas; sem ele, a primeira linha de dados viraria
  nomes de coluna e o mapeamento por nome falharia; no combinado, a primeira coluna do
  cabeçalho é a de origem. Conferir se a descrição de `csv_column` (posição da coluna)
  sugere suporte a CSV sem cabeçalho e ajustar se sim.
- §4.5.1 passa a "Evolução da Estratégia de Escrita": a implementação do TCC1 convertia e
  gravava linha a linha (ingênua, *naive*); no TCC2 evoluiu para a estratégia em lote
  (*batch*), definida uma vez, que é a única da ferramenta; a ingênua segue descrita por ser a
  linha de base da QP4. Remover "continua acessível pela CLI" e a referência à GUI.
- §4.5.2: ajustar "a estratégia ingênua só… / o fluxo emprega sempre a via otimizada" e
  "otimizada, vetorizada".
- §4.6: remover a frase sobre a estratégia ausente do formulário (manter a do
  `--benchmark`); "treze opções" → contagem real das opções da CLI após a remoção.
- Título da §4.5 e referências cruzadas: conferir.
- Figuras 12–16 (interface gráfica): o comando exibido nelas contém
  `--strategy optimized`. Recapturá-las com `scripts/capture_gui_figures.py` depois da
  remoção; a figura 16 exige a pilha de exemplo no ar com só MongoDB e Neo4j parados
  (`docker compose up -d --wait` e `docker compose stop mongodb neo4j`), o que depende do
  autor. (Adendo descoberto ao escrever o plano.)

Cap. Avaliação (`ch6avaliacao.tex`):

- Protocolo: a dimensão estratégia permanece (a campanha existiu), com os nomes novos e uma
  frase de proveniência: a ingênua foi medida com a versão 1.1.0 da ferramenta, a última que
  a contém.
- QP4: título "Estratégia de Escrita: Em Lote *versus* Ingênua (QP4)"; "otimizada" → "em
  lote" no texto, na tabela `tab:naive-optimized` e na figura correspondente; números
  inalterados. Enunciado da QP4 na lista de questões idem.
- QP2 vira a resposta à banca: tabela nova (legenda acima, "Fonte:" abaixo, declarando a
  campanha de cada número) com tamanho dos arquivos, células vazias, fase de leitura e pico
  de memória por modo; texto com empate no tempo total nos dois modelos de execução
  (responde à pergunta do stream), leitura 2× mais rápida e memória 5–6% menor no
  multifonte, vantagens de organização (cabeçalho por tipo, `--source` por fonte, amostragem
  no stream, origem dos dados) e a vantagem do combinado. A tabela atual
  `tab:multi-combined` pode ser fundida à nova se ficar redundante.
- Demais ocorrências de "otimizada" no capítulo → "em lote", exceto onde designam outra
  coisa.

Terminologia nos demais pontos: Resumo e Abstract (`main.tex`, "em lote"/*batch*), cap. 1
(`ch1introducao.tex`), Atividades Futuras (`ch5futuros.tex`) e Considerações Finais
(`consideracoes.tex`).

Verificação: compilar com latexmk sem referências indefinidas; grep sem `--strategy`,
`optimized`, "otimizad" fora do contexto histórico; conferir nas páginas renderizadas
legendas (tabela acima, figura abaixo), frase de introdução em listagens e tabelas sem
linhas sobrepostas; gerar `docs-tcc/TCC2-PolyglotImportCSV-Report-v2.4.pdf`.

## Parte 3 — Entrega

- Antes do código: tag anotada `v1.1.0` em `1553f30` e push da tag (dispara o workflow de
  release; conferir que os quatro zips foram publicados). Conferir `git tag` depois.
- Commits coerentes (código; testes junto do código que cobrem; READMEs; relatório; PDF),
  cada um seguido de push.
- Versão 2.0.0: `pyproject.toml`, `__init__.py` se tiver versão, e
  `docs/releases/v2.0.0.md` bilíngue (remoção de `--strategy`; `connection` obrigatório;
  correções desde a 1.1.0).
- Ao fim, com aprovação do autor: merge `--no-ff` em `main`, push, tag `v2.0.0` e conferência
  da release.

## Fora de escopo

Leitura seletiva de fontes com `--only`; validação nova de cabeçalho; nova campanha de
benchmarks; mudanças nos capítulos além das listadas; `protocol_version` do Cassandra
(pendência anterior).
