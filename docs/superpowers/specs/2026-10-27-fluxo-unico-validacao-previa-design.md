# Design: fluxo como modo único e validação prévia completa (código, relatório v2.4 e slides v1.1)

- **Data:** 2026-10-27
- **Status:** revisado por um leitor externo e com as respostas do autor; aguarda aprovação
- **Branch:** `fluxo-unico`, criado a partir de `main` em `b4cb3a2`

## Origem e intenção

A revisão final dos slides da defesa encontrou uma afirmação falsa sobre o modo padrão da ferramenta, o fluxo (*streaming*). O relatório v2.3 (§4.2.4/§4.3) e os slides dizem que, se a validação falhar, nada é gravado. No código, porém, a camada 3 da validação (colunas e chaves conferidas contra os CSVs) não roda antes da gravação no fluxo:

- `stream_runner.run_stream_import` nunca chama `validate_backend_entities`;
- uma coluna inexistente vira `None` no MongoDB/Neo4j;
- a mesma coluna inexistente gera `KeyError` no meio da carga no PostgreSQL/Cassandra, depois que outros SGBDs já gravaram.

Só o `--dry-run` (que sempre usa materialização) e a GUI conferem tudo antes. Os dois modos de execução divergiram, e essa divergência é a raiz do problema.

O autor decidiu:

- o fluxo passa a ser o único modo;
- toda e qualquer validação possível acontece antes de gravar, em toda importação, e não só no `--dry-run`;
- o trabalho inteiro (código, relatório e slides) passa a descrever essa versão.

**Mensagem que precisa ficar verdadeira:** "A validação prévia tem três camadas". Se qualquer uma falhar, a importação termina sem gravar nada, em qualquer SGBD.

## Decisões do autor

1. **Fluxo é o único modo.** A materialização sai totalmente do código: a opção `--execution` some da CLI e da GUI. O fluxo faz tudo sozinho: importação, `--dry-run` e `--benchmark`.
2. **A materialização vira histórico.**
   - No relatório, aparece só como histórico, ao lado da evolução ingênua → em lote que já está no §4.5.1.
   - O Cap. 5 mantém as medições em que ela aparece, deixando explícito que esse modo não existe na versão final.
3. **Validação completa, com leitura dos dados.** A importação passa a ler cada CSV três vezes:
   - a leitura de inferência determina o tipo de cada coluna com o arquivo inteiro;
   - a leitura de validação confere os dados com os tipos finais, usando o mesmo código da gravação, só que sem gravar;
   - a leitura de gravação grava.

   Uma leitura só de validação não bastaria: os filtros, os nomes de partição (`each`) e a checagem de chave vazia dependem do tipo final de cada coluna, que só se conhece no fim do arquivo. Custo estimado a partir da v2.3 (100 mil linhas, multifonte: leitura 7,7 s e mapeamento 5,9 s de 150 s): entre 10% e 15% do tempo total, a confirmar na campanha.
4. **`--chunk-size` em MB** controla o orçamento de memória do bloco de leitura:
   - o padrão é também o mínimo seguro, 8 MB;
   - o usuário só pode aumentar, até o teto de 256 MB.
5. **`--batch-size` em linhas** controla o lote de gravação:
   - padrão e mínimo de 1024, teto de 8192;
   - o lote efetivo nunca passa do número de linhas de um bloco da fonte, para que um lote não acumule vários blocos na memória.
6. **Recorte do Cap. 5.**
   - Refazer em fluxo, com as leituras de inferência e de validação:
     - QP1, tempo por fase, agora inferência, validação e escrita;
     - QP2, multifonte × combinado;
     - QP3, crescimento com o volume;
     - um item novo com o custo das leituras de inferência e de validação e o pico de memória com blocos de 8, 64 e 256 MB.
   - Manter como histórico, com os números atuais e marcados como tal: QP4 (ingênua × em lote) e QP5/QP6 (materialização × fluxo).
7. **Slide 10** passa a dizer "A validação prévia tem três camadas:". Com a validação completa no código, o slide pode voltar a afirmar que nada é gravado se qualquer camada falhar.
8. **Medições.** O Docker Desktop está ligado, com os cinco SGBDs saudáveis (`docker-compose.yml`). A campanha fica a cargo da implementação.
9. **Referências entre entidades entram na validação.** Hoje duas falhas só aparecem durante ou depois da gravação:
   - no PostgreSQL, uma `foreign_key` que aponta para chave inexistente só falha quando `PostgresSink.close()` recria as FKs, com tudo já gravado;
   - no Neo4j, o `MATCH` de um relacionamento cujo nó de destino não existe não cria a aresta, sem aviso.

   A leitura de validação guarda, de forma compacta, as chaves das entidades que outras referenciam e confere cada referência antes de gravar. A memória dessa conferência cresce com o número de chaves distintas, não com o número de linhas; o autor aceitou essa troca.

## Base técnica (medida em 2026-10-27)

Bloco de 8.192 linhas na base sintética de 100 mil linhas (`benchmark_data.generate_dataset`, semente 42), lido como texto (`dtype=str`), medido com `memory_usage(deep=True)`:

| Fonte | Colunas | Bytes/linha em disco | Bytes/linha em memória | 8.192 linhas |
|---|---|---|---|---|
| `select_product` | 6 | 93 | 381 | 3,0 MB |
| `add_to_cart` | 7 | 140 | 476 | 3,7 MB |
| `stock` | 20 | 252 | 1.209 | 9,5 MB |
| `purchase` | 33 | 388 | 1.967 | 15,4 MB |
| CSV combinado | 39 | 286 | 2.145 | 16,8 MB |

O mesmo número de linhas ocupa de 3 a 17 MB. Por isso o bloco é definido em MB. Como a leitura de inferência usa o arquivo inteiro, o tamanho do bloco deixa de afetar a qualidade da inferência e passa a controlar só a memória.

## Metas

- **Importação em três leituras, nesta ordem:**
  1. camadas 1 e 2 (JSON Schema dos dois arquivos; consistência entre arquivos), como hoje;
  2. camada 3 sobre os cabeçalhos, para **todos** os SGBDs selecionados;
  3. verificação dos SGBDs (`_require_dbms`; o `--dry-run` não conecta);
  4. camada 3 sobre os dados: leitura de inferência e, em seguida, leitura de validação;
  5. leitura de gravação.

  Qualquer erro nos passos 1 a 4 termina a execução com código 1, sem abrir conexão de escrita e sem gravar nada. A ordem 2 → 3 → 4 é escolha minha: as conferências baratas vêm antes das leituras longas.
- **Leitura de inferência:** lê cada fonte declarada em blocos dentro do orçamento de `--chunk-size`, sem conexão com SGBD e com memória limitada aos agregados por coluna. Ela **infere o tipo de cada coluna sobre o arquivo inteiro.** O resultado é o mesmo de `csv_reader.infer_column_kinds` aplicada à coluna inteira, com uma correção: um valor formado só por dígitos nunca conta como evidência de data. Assim, uma coluna de IDs de 4 dígitos com um valor inválido não vira data.
- **Leitura de validação:** lê cada fonte de novo, com os tipos finais, e passa cada bloco pelo **mesmo código** que a gravação usa (filtros, conversão, `each`, montagem das linhas por SGBD), trocando a escrita no SGBD por conferências. Ela:
  - confere cada linha que uma entidade gravaria, depois dos filtros dessa entidade;
  - guarda as chaves das entidades referenciadas por relacionamentos e confere as referências (decisão 9);
  - **coleta erros.** Cada tipo de erro é reportado com contagem e até 5 exemplos, com arquivo, linha, coluna e valor (o limite de 5 é escolha minha);
  - **produz** as contagens por entidade/partição/relacionamento, iguais às da gravação por construção.
- **Erros da camada 3** (a importação para antes de gravar):
  - **Pelos cabeçalhos:** tudo o que `validate_backend_entities` confere hoje:
    - coluna mapeada inexistente;
    - coluna de filtro inexistente;
    - coluna de partição/agrupamento do Cassandra inexistente;
    - relacionamento PostgreSQL/Neo4j com entidade, chave ou propriedade desconhecida;
    - colunas aninhadas em SGBD que só aceita colunas planas.
  - **CSV combinado:**
    - valor de origem vazio. Já é erro hoje e continua;
    - fonte declarada no mapeamento que nunca aparece na coluna de origem. Hoje o `--dry-run` já acusa "unknown source", e o fluxo grava 0 linhas em silêncio. Passa a ser erro, com a lista dos valores de origem encontrados (escolha minha: equivale a faltar um arquivo no multifonte).
  - **Valor que não converte para o tipo inferido da coluna.** Na prática só acontece em datetime, pela regra dos 85%. Hoje esse valor vira `None` com só um aviso.
  - **Valor incompatível com o `db_type` declarado** no arquivo de importação, que o SGBD recusaria. Exemplos: texto em `BIGINT`, número fora da faixa do tipo inteiro, data inválida em `TIMESTAMP`/`DATE`, valor não booleano em `BOOLEAN`.
  - **Chave vazia:**
    - coluna `is_key` vazia: o PostgreSQL descarta a linha em silêncio, o Redis quebra e o `MERGE` do Neo4j com nulo falha;
    - coluna de partição/agrupamento do Cassandra vazia: o Cassandra recusa.
  - **Referência pendente** (decisão 9), nos SGBDs cujo mapeamento declara relacionamentos:
    - PostgreSQL: valor de `foreign_key` nas linhas gravadas na entidade `from` sem valor igual de `references_key` nas linhas gravadas na entidade `to`;
    - Neo4j: chave de extremidade de um relacionamento sem nó correspondente na entidade `from` ou `to`.

    A comparação usa os valores já convertidos para os tipos finais, como o SGBD faria.
- **Não são erros:**
  - `foreign_key` ou chave de extremidade vazia: significa ausência de relacionamento. O PostgreSQL aceita FK nula, e o Neo4j já pula essas linhas em `_rel_rows_for_batch` (escolha minha);
  - chaves repetidas (deduplicação e *upsert* fazem parte do desenho do mapeamento, porque a mesma entidade aparece em várias linhas de evento);
  - linhas excluídas por filtros;
  - entidades com 0 linhas (continuam como aviso);
  - valores de origem do CSV combinado que nenhuma entidade consome (aparecem no resumo, com contagem; escolha minha).
- **Leitura de gravação:** é o fluxo atual (um *sink* por SGBD, na ordem de `BACKENDS`), com três diferenças:
  - usa os tipos da leitura de inferência em vez de inferir pelo primeiro bloco;
  - grava em lotes de `--batch-size`;
  - confere no resumo final as contagens gravadas contra as da leitura de validação. Como as duas usam o mesmo código, uma diferença só aparece por defeito da ferramenta; ela vira aviso, não falha, porque o que já foi gravado não se desfaz (escolha minha).

  Uma falha durante a gravação (SGBD que cai, por exemplo) continua sem desfazer o que já foi gravado. A atomicidade entre SGBDs segue em aberto.
- **`--dry-run`:** roda os passos 1, 2 e 4 completos (inferência e validação) e mostra as contagens, sem conectar. Funciona com arquivos grandes em memória limitada.
- **`--chunk-size N`:**
  - inteiro em MB, padrão 8, mínimo 8, máximo 256; valor fora da faixa é erro de uso da CLI;
  - as linhas por bloco de cada fonte são calculadas pela largura em memória medida no início da fonte;
  - o método de medição fica com o construtor e deve ser documentado no código e no relatório.
- **`--batch-size N`:** inteiro, padrão 1024, mínimo 1024, máximo 8192; o lote efetivo é `min(N, linhas por bloco da fonte)`.
- **`--benchmark` em fluxo:** grava as métricas por fase (inferência; validação; escrita por SGBD) e o pico de memória quando a instrumentação está ligada. O *runner* de campanhas (`benchmark_runner`, `scripts/run_benchmarks.py`) perde o eixo de modo e ganha o eixo de tamanho de bloco para a campanha de memória.
- **GUI:**
  - remove o controle "Execução (`--execution`)";
  - ganha dois campos numéricos, "Bloco (MB)" (`--chunk-size`) e "Lote" (`--batch-size`), com os mesmos limites;
  - a prévia do comando mostra as opções;
  - a pré-verificação continua sobre os cabeçalhos, para resposta rápida durante a edição, mas chama a **mesma** função de validação de cabeçalhos da CLI, para que as regras existam num lugar só;
  - as leituras de inferência e de validação rodam na CLI.
- **Uma regra, um lugar.** Uma única implementação de cada regra de validação, usada pela CLI, pelo `--dry-run` e pela GUI. Nenhum caminho de código paralelo.
- **Versão do pacote: 3.0.0**, porque a remoção de `--execution` muda a CLI de forma incompatível (escolha minha). Publicar o *release* no GitHub só com o OK do autor.

## Relatório v2.4 (`docs-tcc/`)

- **Fluxo como modo único** em todo o texto:
  - §4.3: o algoritmo em três leituras (inferência, validação, gravação); a Figura 11 é refeita a partir do `.mmd`;
  - §4.2.4: as três camadas, todas antes da gravação, incluindo as leituras de inferência e de validação e a conferência de referências entre entidades;
  - §4.5:
    - o fluxo como modelo de execução;
    - `--chunk-size` e `--batch-size` com a tabela de medição acima;
    - a materialização entra na subseção de evolução da estratégia (§4.5.1), ao lado de ingênua → em lote, como etapa do projeto avaliada no Cap. 5 e ausente da versão final;
  - §4.3.4: o exemplo de CLI e o `tab:dryrun`;
  - §4.6: capturas novas da GUI, refeitas com `scripts/capture_gui_figures.py`.
- **Cap. 5:**
  - tabelas e gráficos novos para QP1 (fases: inferência, validação e escrita), QP2 e QP3 e para o item de custo das leituras de inferência e validação e de memória por bloco;
  - QP4 e QP5/QP6 com os números atuais, num texto que deixa claro que comparam um modo que não existe mais;
  - §5.1.1 corrigido: N é o total de linhas dos quatro CSVs, como em `benchmark_data.py`;
  - §5.4 corrigido: o Cassandra roda com fator de replicação 1;
  - a QP6 descrita como "achata", não "constante";
  - ameaças à validade revistas.
- **Correções factuais:**
  - §3.1: o `cqlsh COPY FROM` importa CSV direto; o SSTable é exigência do `sstableloader`;
  - `consideracoes.tex:17`: os dados são sintéticos, não reais.
- **Resumo, Abstract, Introdução e Conclusão:** alinhados ao modo único e à validação completa.
- **Saídas:**
  - `docs-tcc/TCC2-PolyglotImportCSV-Report-v2.4.pdf`;
  - `docs-tcc/TCC2-PolyglotImportCSV-Report-diff-v2.3-v2.4.pdf`, no padrão dos diffs anteriores.

## Slides v1.1 (`docs-tcc/apresentacao/`)

- **Slide 10:** "A validação prévia tem três camadas:", com a garantia de que nada é gravado se qualquer camada falhar (agora verdadeira); a nota "Completa no `--dry-run` e na GUI" sai.
- **Slide 13:** o algoritmo em três leituras.
- **Slide 14:** o comando de exemplo atualizado.
- **Slide 15:** o fluxo com bloco e lote configuráveis; a materialização só como histórico.
- **Slide 16:** capturas novas.
- **Slides 17–21:** números novos de QP1, QP2 e QP3 e do item de validação; QP4 e QP5/QP6 marcadas como histórico.
- **Slide 22:** a evidência do objetivo 2 sem ressalva.
- **Cartas:** B1 (só falhas durante a gravação continuam sem desfazer), B2 (inferência sobre o arquivo inteiro e regra das datas), B5/B6 (números e ameaças novos).
- **Saída:** `docs-tcc/TCC2-PolyglotImportCSV-Apresentacao-v1.1.pdf`. A v1.0 continua versionada (escolha minha). O `bash verificar.sh` passa.

## Não-metas

- Atomicidade entre SGBDs (transação distribuída ou *rollback*). A validação completa reduz as falhas no meio da gravação, mas não as elimina.
- Lacunas de estrutura da monografia: tabela comparativa no Cap. 3, posição do capítulo de trabalhos futuros, citação de Araujo, Silva e Mello (2025). Essa rodada pode usar o EQD de Lilian Araujo (`docs-tcc/relacionados/EQD2026_Lilian/`), uma primeira revisão ainda não definitiva. Esses arquivos ficam fora do repositório, que é público.
- Novos SGBDs (Elasticsearch continua como trabalho futuro) e edição da configuração na GUI.
- Remedir QP4 e QP5/QP6.

## Anti-metas (fracasso mesmo que funcione)

- Uma leitura de inferência ou de validação que carregue um arquivo inteiro na memória, ou cujo pico cresça com o número de linhas além dos agregados por coluna e dos conjuntos de chaves referenciadas (estes crescem com o número de chaves distintas, decisão 9).
- Uma regra de validação que faça falhar os exemplos do projeto (`data/ecommerce/` em multifonte e combinado, e a base sintética do gerador). Se isso acontecer, o construtor para e reporta antes de afrouxar a regra.
- Dois caminhos de código com a mesma responsabilidade, ou uma regra de validação duplicada entre CLI e GUI.
- Qualquer número no relatório ou nos slides que não venha da campanha nova (ou, para o histórico, da v2.3), ou que misture campanhas com e sem instrumentação de memória.
- Afirmação no relatório ou nos slides que o código não sustenta. Cada afirmação sobre comportamento é conferida no código.
- Texto que explique o histórico de versões do próprio relatório (o orientador não gosta disso). A materialização entra como etapa técnica avaliada, não como "versões anteriores do texto diziam".
- "backend" em qualquer texto em português; sempre "SGBD".

## Restrições

- Python 3.12, pandas, a suíte do projeto: `.venv/Scripts/python.exe -m pytest`. O pytest sem o venv pula cerca de 100 testes de GUI.
- A suíte passa ao fim de cada etapa. Testes que só existem para a materialização (por exemplo, `test_mode_equivalence.py` e testes de `importers/` que não servem aos *sinks*) são removidos ou convertidos. Funções auxiliares usadas pelos *sinks* (conexão, DDL, novas tentativas, montagem de linhas) continuam, mesmo que mudem de módulo.
- Ambiente de medição igual ao da v2.3 (`tab:ambiente-sgbds`): mesma máquina, Docker com cerca de 3,8 GB, Cassandra com heap de 1 GB. Volumes, repetições e mediana como no §5.1, em duas campanhas (com e sem instrumentação de memória).
- Regras do orientador para o texto:
  - legenda de figura embaixo, título de tabela em cima, "Fonte:" embaixo;
  - frase de introdução antes de cada listagem;
  - trechos de JSON terminam em `...`;
  - jargão definido no primeiro uso;
  - partes de cada comando explicadas;
  - SGBD, nunca "backend".
- Git: commits em português com o *trailer* `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, push após cada commit, comandos com prefixo `rtk`.
- READMEs e documentos de uso (`README.md`, `docs/ARCHITECTURE.md`, `benchmarks/README.md`, `data/ecommerce/README.md`, scripts de exemplo e o *completion* do bash) sem `--execution` e com as opções novas. Arquivos históricos (`docs/releases/v1.0.0.md`, resultados antigos em `benchmarks/`) ficam como estão.

## Etapas (cada uma com o seu plano)

1. **Código:**
   - modo único;
   - três leituras (inferência, validação, gravação), com a conferência de referências;
   - `--chunk-size` e `--batch-size`;
   - GUI;
   - testes e documentos de uso;
   - versão 3.0.0.
2. **Campanha de medição** em fluxo, com os resultados versionados em `benchmarks/` e o resumo das medianas.
3. **Relatório v2.4** e o PDF de diff.
4. **Slides v1.1.**

As etapas 3 e 4 só começam com os números da etapa 2.

## Deixado para o construtor

- A arquitetura interna das leituras de inferência e de validação (agregados de inferência por coluna, coleta de exemplos de erro, o "sink que só confere") e onde moram as funções compartilhadas.
- A forma compacta dos conjuntos de chaves referenciadas e a ordem em que chaves e referências são coletadas e conferidas, desde que o resultado seja exato (sem alarme falso) e a memória cresça só com as chaves distintas.
- O método de estimar as linhas por bloco a partir dos MB.
- O texto exato das mensagens de erro (em inglês, como o resto da CLI) e a apresentação do resumo de validação no terminal.
- O mapa `db_type` → verificação de valor por SGBD, a partir dos tipos que `schema_generator` e o Cassandra já usam.
- A redação do relatório e dos slides, dentro das regras acima.
