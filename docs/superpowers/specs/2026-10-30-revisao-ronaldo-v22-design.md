# Design: correções do Prof. Ronaldo na v2.2 do relatório (junto da etapa 3 do fluxo único)

- **Data:** 2026-10-30
- **Status:** revisado por um leitor externo e com as respostas do autor; aguarda aprovação
- **Branch:** `fluxo-unico`
- **Entrada:** `docs-tcc/TCC2-PolyglotImportCSV-Report-v2.2-REVISADO.pdf` (não versionado; não commitar sem perguntar ao autor)
- **Complementa:** `docs/superpowers/specs/2026-10-27-fluxo-unico-validacao-previa-design.md` (a spec do fluxo único). Onde os dois divergem, vale este documento. Em particular, "camada" vira "etapa".

## Origem e intenção

O orientador, Prof. Ronaldo dos Santos Mello, revisou a v2.2 do relatório. As anotações vão da pág. 32 à 65 impressas (36 a 69 do PDF), ou seja, o Cap. 4 até o início da §4.6, onde ele escreveu "PAREI AQUI". São 30 anotações com texto, além de destaques e riscos.

O ponto central é que **ele não entendeu as três etapas de validação.** O texto as chama de "camadas", identifica cada uma pelo nome de uma função entre parênteses (`config_parser.merge_configs`, `sources.load_sources`, ...) e só mostra a Figura 10 no fim da seção. As demais anotações pedem:

- exemplos (`each`, `csv_columns`);
- explicações de opções da CLI (`--source`, `--create-schema`, `--check-dbms`);
- cortes de trechos que ele acha desnecessários;
- vocabulário: "fluxo" no lugar de "algoritmo", "cenário exemplo" e "SGBD destino".

O autor decidiu:

1. **As correções entram na etapa 3 do fluxo único (relatório v2.4).** Nenhuma versão corrigida sai antes da campanha (etapa 2). O texto corrigido já descreve a versão 3.0.0. Por isso as anotações sobre o que a 3.0.0 removeu, como `--execution` e a carga inteira na memória, são resolvidas pela reescrita da etapa 3, e não com remendos no texto antigo.
2. **"Camada" vira "etapa".** São "três etapas de validação". A expressão "etapa de validação" é enfatizada onde o texto descreve as conferências. A troca vale para o relatório, os slides (slide 10: "A validação prévia tem três etapas:") e os READMEs. Nas partes em inglês, "layer" vira "stage".
3. **A tabela do arquivo de conexão diz "sim; ao menos os SGBDs de destino".** O código já exige isso: uma configuração sem nenhum SGBD de destino termina com código 1.
4. **Entra uma figura nova** que exemplifica a importação em fluxo com o cenário exemplo (seção "Figura nova").
5. **Ordem de trabalho:** depois deste design vem a etapa 2 (campanha), depois a etapa 3 (relatório, com estas correções) e por fim a etapa 4 (slides).

## Mapa das anotações

Páginas impressas da v2.2. Cada linha é uma anotação ou um grupo de anotações sobre o mesmo ponto, com a ação correspondente no texto da v2.4.

| # | Pág. | Pedido do orientador | Ação |
|---|---|---|---|
| 1 | 32 | Título do capítulo: riscou "Proposta da" | `\chapter{A Ferramenta PolyglotImportCSV}`; conferir as remissões ao título em outros capítulos |
| 2 | 32 | "começar novo parágrafo aqui", em "O processamento é disparado..." | Novo parágrafo |
| 3 | 33 | "retirar essa parte em amarelo. Melhor explicar os modos de uso na seção que explica os arquivos de configuração" (parágrafo "Diferentemente de uma importação amarrada a um único arquivo... dois modos de uso...") | Sai de §4.1. Multifonte e combinado passam a ser explicados na §4.2, junto do bloco `sources`. O roteiro das seções e a frase que introduz o comando continuam em §4.1, sem os modos |
| 4 | 34 | `--source`: "que separador (, ou ; ou…)?" | Explicar que não há separador: a opção se repete, uma vez por fonte. Mostrar um exemplo com duas fontes (`--source purchase=... --source stock=...`). A opção é `multiple=True` em `cli.py` |
| 5 | 34 | `--create-schema`: "no caso de um BD relacional... o que acontece se o usuário setar no create schema??" | A opção sai (decisão 1). O texto explica o que a ferramenta cria em cada SGBD destino antes de gravar e que reaproveita o que já existe (ver "Achados no código") |
| 6 | 34 | "definir novo parágrafo aqui", em "O segundo define como importar" | Novo parágrafo. Na 3.0.0, esse conjunto passa a ser `--chunk-size` e `--batch-size` |
| 7 | 34 | §4.2: retirar "A separação atende a duas preocupações distintas: ... (desenvolvimento, testes, produção)." | Remover a frase |
| 8 | 35 | Figura 8: "aumentar um pouco essa figura" | Refazer a partir do `.mmd`, com um arranjo que deixe o texto da figura maior na largura do texto (vertical ou dividida em duas). Critério: o texto da figura fica legível sem zoom, aproximadamente do tamanho de uma nota de rodapé |
| 9 | 39 | "sugiro sempre escrever 'cenário exemplo' em todo o texto" | "cenário exemplo", exatamente assim, em todo o relatório (Cap. 1 a 5, apêndices, legendas). Hoje o texto alterna "cenário", "cenário de e-commerce" e "cenário de exemplo" |
| 10 | 39 | Operador `each`: "não entendi como essa divisão ocorre… Tens como mostrar um exemplo?" | Uma listagem com o trecho real do cenário exemplo, a coleção `orders` do MongoDB com `each` sobre `state` e `target_suffix` `state_{value}` (decisão 2), e as coleções que ele gera (`orders_state_<valor>`). O texto diz que o valor vazio não gera alvo e que um relacionamento não pode apontar para uma entidade dividida. Os nomes saem de uma execução real (`--dry-run` sobre `data/ecommerce/`) |
| 11 | 41 | `csv_columns`: "não vi um exemplo... seria bom mostrar" | Uma listagem com `auto_map` + `csv_columns` (nome e intervalo, como `"1-5"`), conferida numa execução real |
| 12 | 41 | "Os cinco blocos de SGBD" → "...SGBD destino..." | "Os cinco blocos de SGBD destino" |
| 13 | 45 | Retirar ", sem nenhuma informação de mapeamento" | Remover |
| 14 | 45 | `tab:partes-conexao`, "Obrigatória?": "aqui não deveria ser 'sim'? Pois ao menos 1 SGBD precisa ser informado" | "sim; ao menos os SGBDs de destino" (decisão do autor). A mesma correção vale para `tab:partes-importacao` ("não; só os SGBDs de destino" → "sim; ..."), que ele não marcou mas tem o mesmo erro. **Escolha minha.** Os JSON Schemas não exigem nenhum bloco de SGBD; quem recusa é a execução, com código 1 (`runner._dbms_targets`, inclusive quando `--only` não deixa nenhum SGBD). Nas Figuras 8 e 9, o asterisco marca só o que o JSON Schema exige. O texto passa a dizer isso e a explicar que a exigência de ao menos um SGBD é conferida na execução. O *schema* não muda. **Escolha minha** |
| 15 | 49 | Nomes entre parênteses: "são classes da tua implementação...? Explicar…" e "Tu tens que referenciar a figura do fluxo aqui" | A §4.2.4 abre com a Figura 10 e descreve cada etapa de validação pelo que ela confere. Os nomes de função saem do texto corrido |
| 16 | 49, 53 | "esse termo 'camada' está estranho…" (duas vezes) | "etapa de validação" (decisão 2) |
| 17 | 49 | A Figura 10 "deveria ser explicada logo no início da seção" | Ver item 15 |
| 18 | 51, 53, 55 | Título "ALGORITMO" → "FLUXO"; "usar 'fluxo' ao invés de 'algoritmo', pois vc não mostrou um algoritmo formal"; "fluxo" em §4.3.2 | §4.3 passa a "Fluxo de Execução da Importação". "Algoritmo" sai do relatório (Cap. 1, Cap. 4, apêndice dos CSVs, legenda da Figura 11) |
| 19 | 55 | `--check-dbms`: "onde essa opção é setada? na linha de comando do polyglotImport? Explicar…" | Dizer que é uma opção da linha de comando da ferramenta, apresentada em §4.1, e que a GUI tem o botão "Verificar SGBDs". Mostrar o comando completo uma vez |
| 20 | 56 | `last_restock_date`: "onde está essa coluna? Não achei…" | A coluna existe em `data/ecommerce/ecommerce_stock.csv`, mas a `tab:csv-stock` não a mostra. Mostrá-la na tabela ou dizer, na legenda e no texto, que ela está entre as colunas omitidas e onde encontrá-la |
| 21 | 61 | "que extensão C é essa?" (driver do Cassandra no `--dry-run`) | Remover a menção. **Escolha minha** |
| 22 | 61 | `tab:dryrun`, "Registros (após projeção/deduplicação)": "é feita alguma deduplicação?? em que situação?" | Na 3.0.0 as contagens do `--dry-run` são linhas depois dos filtros e **antes** de qualquer deduplicação, então o cabeçalho atual está errado. Novo cabeçalho no sentido de "linhas a gravar (após os filtros)" e um parágrafo curto sobre a deduplicação, conferido no código (ver "Achados no código") |
| 23 | 61 | `docker compose up -d`: "isso tem que ser feito manualmente pelo usuário?" | Sim. A ferramenta nunca inicia SGBDs. Quem os inicia é o usuário, com `docker compose up -d` (o `docker-compose.yml` acompanha os pacotes), com o `run_example.sh` ou com instalações nativas. Conferir o que o `run_example.sh` faz antes de citá-lo |
| 24 | 62 | Variáveis de ambiente do *log* (`POLYGLOT_NO_LOG`, `POLYGLOT_DEBUG_LOG`): "Vale a pena entrar nesse nível de detalhe?" | Remover a frase. **Escolha minha** |
| 25 | 62 | Métricas, "mapeamento (*map*, o vínculo com a fonte...)": "aqui não seria o vínculo 'com o SGBD destino'?" | O parágrafo é reescrito para as fases da 3.0.0 (`infer`, `validate`, `write` por SGBD). A pergunta deixa de existir |
| 26 | 63 | `--execution` carrega "por inteiro na memória": "e se o arquivo for muito grande e não couber na memória, o que acontece?" | A §4.5 da 3.0.0 descreve a leitura em blocos (`--chunk-size`). A materialização entra só como histórico, e é aí que o texto responde: ela falharia por falta de memória, e essa é a motivação do fluxo |

## Convenções de vocabulário (relatório inteiro, não só as páginas anotadas)

O orientador anotou só o Cap. 4. Mesmo assim, as convenções valem para o relatório inteiro, para que ele não encontre o termo antigo nas próximas páginas que ler:

- **"etapa de validação"** (1, 2 e 3) no lugar de "camada". Outros usos de "camada", como "camada de observabilidade" e "camada de acesso da aplicação" (Cap. 3), significam outra coisa e ficam como estão. **Escolha minha:** o orientador não os marcou.
- **"passo"** para os passos da Figura 11 e do fluxo de execução, que hoje também se chamam "etapas", para que "etapa" fique reservada à validação. **Escolha minha.**
- **"fluxo"** no lugar de "algoritmo". Na 3.0.0 o fluxo deixou de ser um dos dois modos, então o nome não colide. A leitura em pedaços se chama "leitura em blocos", como nas notas da 3.0.0. **Escolha minha.**
- **"cenário exemplo"**, exatamente assim.
- **"SGBD destino"** onde o texto fala dos SGBDs para onde os dados vão.
- **"gravar" no lugar de "materializar"** quando o sentido é guardar dados num SGBD (por exemplo, `tab:materializacao`, "relação materializada no PostgreSQL"), porque "materialização" é o nome do modo removido. **Escolha minha.**
- Continua valendo a regra antiga: "SGBD", nunca "backend".

## Figura nova: a importação em fluxo no cenário exemplo

**Intenção:** mostrar com um exemplo concreto o caminho de uma importação, para que o leitor veja onde cada etapa de validação acontece e o que ela barra. É a figura que faltou para o orientador entender as etapas.

**Conteúdo mínimo:**

- as entradas do cenário exemplo: os dois arquivos JSON e os CSVs;
- a **etapa 1 de validação** (JSON Schema dos dois arquivos) e a **etapa 2** (consistência entre os arquivos), antes de abrir qualquer CSV;
- a **etapa 3** sobre os cabeçalhos dos CSVs;
- a verificação dos SGBDs;
- a **leitura de inferência**, em blocos de `--chunk-size`, que fixa o tipo de cada coluna, com um exemplo de coluna e o tipo inferido;
- a **leitura de validação** (etapa 3 sobre os dados), com exemplos do que ela barra: valor que não converte, chave vazia, referência pendente. Um erro termina a execução sem gravar nada;
- a **leitura de gravação**, em lotes de `--batch-size`, para os SGBDs destino.

Um detalhe concreto acompanha o caminho: a mesma linha da fonte `stock` que a §4.3.3 já acompanha, ou um trecho dela. Assim o texto e a figura contam a mesma história.

**Restrições:**

- legível na largura do texto, com o mesmo critério do item 8;
- se ficar densa, dividir em duas (preferência do orientador);
- legenda embaixo, com "Fonte: Elaborado pelo autor (2026)."
- cada valor e cada contagem na figura sai de uma execução real.

**Lugar:** na §4.3, onde o texto acompanha o cenário exemplo (hoje §4.3.2–§4.3.3), com remissão a partir da §4.2.4. Os papéis das figuras não se sobrepõem:

- **Figura 10:** o que cada etapa de validação confere. É atualizada para a 3.0.0 e para o termo "etapa".
- **Figura 11:** os passos do fluxo em geral. Já seria refeita na etapa 3.
- **Figura nova:** o exemplo concreto.

**Escolha minha:** o formato segue o das Figuras 10 e 11 (Mermaid `.mmd` → PNG, com a receita registrada no projeto). TikZ fica como alternativa se o Mermaid não der conta da legibilidade.

**De onde vêm os exemplos (escolha minha).** `data/ecommerce/` passa em todas as validações e não usa `csv_columns`. O `each` passa a existir nele (decisão 2). Por isso:

- o exemplo de `each` (item 10) sai da configuração real;
- o exemplo de `csv_columns` (item 11) e os erros barrados que aparecem na figura saem de cópias alteradas da configuração e dos CSVs, numa pasta temporária fora do repositório;
- na figura, os erros barrados aparecem marcados como exemplos induzidos, e não como parte do caminho bem-sucedido da linha de `stock`;
- as mensagens de erro reproduzidas são as que a execução real imprimiu;
- nada disso é versionado. As listagens no texto já bastam para reproduzir os exemplos. `data/ecommerce/import_config_invalido.json` continua sendo o único exemplo inválido versionado.

## Achados no código

Esta seção registra o que muda no código. O pedido do autor exige cuidado especial com isso.

### `--create-schema` / `--no-create-schema` não faz o que o texto diz

O relatório (§4.1, §4.3) diz que `--no-create-schema` impede a criação de tabelas. Na 3.0.0, a gravação chama `sink.ensure_partition` antes do primeiro lote de cada partição. Esse método **sempre** executa `CREATE TABLE IF NOT EXISTS` no PostgreSQL (`postgres_sink.ensure_partition`) e no Cassandra (`cassandra_sink.ensure_partition`). A opção só decide se `create_schema()` roda (`stream_runner.py`, perto da linha 324), e o efeito depende do SGBD:

- **PostgreSQL:** remove as FKs, que `close()` recria. Com `--no-create-schema`, uma nova carga sobre FKs de uma carga anterior pode violar FK no meio da gravação.
- **Cassandra:** cria o *keyspace*. Sem ele, a gravação falha.
- **Neo4j:** cria as restrições de unicidade.
- **MongoDB e Redis:** nada.

A mensagem do *runner* "existing schema only (--no-create-schema)" é falsa. A GUI tem a caixa "Criar esquema (`--create-schema`)", que aparece nas capturas da §4.6.

A divergência já existia no modo fluxo da v2.x. A materialização respeitava a opção.

**Decisão 1 (do autor): a opção sai, e o que ela fazia fica explicado com clareza.**

- `--create-schema`/`--no-create-schema` sai da CLI e da caixa "Criar esquema" da GUI. Sai também do *runner* e do `stream_runner`, em que `create_schema()` passa a rodar sempre. Saem ainda o `run_example.sh`, o *completion* do bash, o `benchmark_runner`, os READMEs e os testes que passam a opção. Os testes do método `create_schema()` dos *sinks* continuam. A remoção entra na 3.0.0, que ainda não foi lançada.
- **"Deixar bem claro o que a opção fazia":**
  - **Notas da 3.0.0, em "Mudanças incompatíveis" (inglês e português).** Dizem que a opção foi removida e que ela nunca impediu a criação de tabelas, porque `CREATE TABLE IF NOT EXISTS` rodava sempre no PostgreSQL e no Cassandra. Dizem também o que `--no-create-schema` desligava: o *keyspace* do Cassandra, as restrições de unicidade do Neo4j e a remoção e recriação das FKs do PostgreSQL em volta da carga. Por isso uma nova carga podia violar uma FK no meio da gravação. Por fim, que agora a ferramenta faz tudo isso sempre e reaproveita as estruturas existentes.
  - **Relatório.** O texto responde à pergunta do orientador descrevendo o comportamento atual, sem histórico de versões: o que a ferramenta cria em cada SGBD destino antes de gravar, que o que já existe é reaproveitado e que MongoDB e Redis não precisam de estrutura prévia.
- **Interpretação minha da resposta** "Remova e deixe bem claro o que essa função `--no-create-schema` faz": remover a opção e explicar o que ela fazia, nas notas, e o que a ferramenta faz, no relatório.

### `target_suffix` do `each` anula a divisão

`filter_engine.expand_each` usa `target_suffix`, quando informado, como sufixo fixo. Todas as partições recebem então o mesmo nome. Execução real: com `target_suffix: "r"`, as partições de `South` e `North` viram `sales_r` e `sales_r`. O *schema* descreve o campo como "optional template", mas nenhum modelo é aplicado. Nenhum teste nem exemplo do projeto usa o campo, e o relatório só o mostra no apêndice dos *schemas*.

**Decisão 2 (do autor): `target_suffix` vira modelo, e o cenário exemplo passa a usá-lo, dividindo por `state` e aparecendo no apêndice.**

- **Semântica (escolha minha):**
  - `target_suffix` é um modelo com o marcador `{value}`, substituído pelo valor normalizado (`_slugify`) de cada partição;
  - o nome do alvo continua `<entidade>_<sufixo>`;
  - sem `target_suffix`, o sufixo é o valor normalizado, como hoje;
  - o JSON Schema exige exatamente um `{value}`, com só letras, dígitos e `_` em volta (padrão `^[A-Za-z0-9_]*\{value\}[A-Za-z0-9_]*$`). Assim, um modelo sem o marcador, que daria o mesmo nome a todas as partições, é recusado na etapa 1 de validação, com uma regra num lugar só, usada pela CLI e pela GUI;
  - a descrição do campo no *schema* passa a dizer isso.
- **Testes:**
  - `filter_engine.expand_each` com modelo, por exemplo `{"column": "region", "operator": "each", "target_suffix": "r_{value}"}` → `sales_r_North`, `sales_r_South`;
  - o *schema* recusa `"r"` e `"r_{value}_{value}"`;
  - o exemplo do e-commerce produz as partições esperadas.
- **Cenário exemplo (escolha minha da entidade):**
  - **onde:** uma entidade nova no bloco `mongodb` de `data/ecommerce/import_config.json` e de `import_config_combined.json`. A coleção `orders` lê da fonte `purchase` e tem um filtro `{"column": "state", "operator": "each", "target_suffix": "state_{value}"}`;
  - **partições:** uma coleção por estado do comprador, como `orders_state_CA`. No exemplo são 8 estados, e na base sintética, 4 (`CA`, `SC`, `NY`, `TX`);
  - **por que `orders`:** cada compra é um pedido, então não há documentos repetidos. O MongoDB não deduplica, e uma coleção de clientes lida das compras repetiria o mesmo cliente;
  - **colunas:** ficam com o construtor, a partir das que o `orders` do PostgreSQL já usa;
  - **o que fica intacto:** as entidades existentes não mudam, nem as saídas do relatório que dependem delas. Nenhum relacionamento aponta para a entidade nova.
- **O apêndice A** (`apendiceconfig.tex`) reproduz as configurações atualizadas, e o item 10 do mapa (exemplo de `each`) passa a usar esse trecho real, em vez de uma cópia temporária.
- **Efeito na campanha:** `scripts/run_benchmarks.py` usa as configurações de `data/ecommerce/`. A entidade nova entra, portanto, na carga medida. Por isso a mudança vem antes da campanha.
  - O limpador entre repetições (`CLEANERS` de `scripts/inspect_persisted_data.py`) precisa apagar as coleções `orders_state_*`, ou a carga deixa de ser a frio. O construtor confere e corrige se for preciso.
  - Na v2.4, os números novos não são comparados com os totais da v2.3 como se a carga fosse a mesma.

### Deduplicação (item 22), para o texto

O texto descreve o que o código faz, conferido no código no momento de escrever:

- **PostgreSQL:** `row_shaping` descarta chaves repetidas dentro do lote (`keep="last"`), e `ON CONFLICT (pks) DO NOTHING` resolve entre lotes, onde a primeira gravação vence. Os dois critérios divergem: dentro do lote vence a última linha, entre lotes vence a primeira. Esta rodada não muda isso. Fica registrado como observação, e o texto não promete um critério único.
- **Neo4j:** `_dedupe_props` (vence a primeira) e `MERGE`.
- **Cassandra e Redis:** *upsert* pela chave.
- **MongoDB:** nenhuma.

### Mudanças só de texto no código

- Docstring de `business_exception.py:21`: "validation layer 3" → "validation stage 3".
- READMEs: `README.md` (inglês e português), `data/ecommerce/README.md`: "camada"/"layer" → "etapa"/"stage" nas validações. `docs/ARCHITECTURE.md` fala de camadas de arquitetura e fica como está.

## Metas

- Cada uma das 26 linhas do mapa resolvida na v2.4, com o texto conferido contra o código da 3.0.0.
- As convenções de vocabulário aplicadas ao relatório inteiro.
- A Figura nova incluída, e as Figuras 8 e 10 refeitas.
- As decisões 1 e 2 executadas no código e no cenário exemplo **antes da campanha (etapa 2)**, com testes. A decisão 2 muda a carga medida (a coleção `orders` dividida por estado), e a campanha precisa rodar sobre o código e o exemplo finais.
- Slides v1.1 com "três etapas de validação" e o mesmo vocabulário. A figura nova pode ser reaproveitada ou redesenhada em TikZ na horizontal, como as Figuras 10 e 11 nos slides.

## Planos (escolha minha)

1. **Plano das correções de código + etapa 2.** Executa as decisões 1 e 2 com testes: a remoção de `--create-schema`, o modelo `target_suffix` e a coleção `orders` dividida por estado no cenário exemplo, com o limpador da campanha conferido. Inclui as notas da 3.0.0, a docstring e os READMEs ("etapa"/"stage"). A suíte roda em dois processos. Em seguida roda a campanha da spec do fluxo único, com `--out` numa pasta nova de `benchmarks/` e o resumo das medianas. A campanha exige o Docker Desktop com os cinco SGBDs no ar, e quem liga o Docker é o autor.
2. **Plano da etapa 3**, escrito com os números da campanha em mãos. Cobre as 26 linhas do mapa, as convenções de vocabulário, as Figuras 8, 10 e 11 e a figura nova, além do que a spec do fluxo único já previa para a v2.4.
3. **Plano da etapa 4** (slides v1.1).

As figuras ficam para a etapa 3, mesmo sem depender dos números. Durante a campanha a máquina precisa ficar quieta, porque a renderização com Chrome e Mermaid distorceria os tempos.

## Não-metas

- A §4.6 em diante não foi revisada pelo orientador. Recebe só as convenções de vocabulário e as mudanças que a spec do fluxo único já previa.
- Unificar o critério de deduplicação do PostgreSQL.
- Mudar qualquer comportamento do código além das decisões 1 e 2.
- Responder ao orientador item a item por escrito. Se o autor quiser essa resposta, é outro pedido.

## Anti-metas

- Texto que remende a v2.3 em vez de descrever a 3.0.0.
- Explicações novas com nomes de função no texto corrido. O orientador não os entendeu. Nomes de opção da CLI e de campo do JSON continuam, porque o usuário os digita.
- Figura nova ou refeita que não se leia na largura do texto.
- Exemplo (`each`, `csv_columns`, contagens) que não saia de uma execução real.
- Commitar o PDF revisado pelo orientador ou qualquer arquivo de `docs-tcc/relacionados/EQD2026_Lilian/`.

## Restrições

As da spec do fluxo único (git com `rtk` e push a cada commit, testes em dois processos, regras do orientador para o texto). Além delas:

- o PDF revisado continua fora do repositório, salvo ordem do autor;
- as remissões da v2.2 (páginas, números de figura) não valem para a v2.4. O construtor localiza cada trecho pelo texto.

## Deixado para o construtor

- A redação de cada correção, dentro das convenções.
- A coluna e os valores dos exemplos de `each` e `csv_columns`, desde que venham do cenário exemplo e de execuções reais.
- O arranjo das Figuras 8, 10 e da nova.
- Onde o roteiro das seções fica em §4.1 depois do corte do item 3.
