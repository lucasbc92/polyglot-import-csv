# Design — Revisão do capítulo da Proposta (retorno do orientador, out/2026)

Data: 2026-10-05
Status: aprovado em brainstorming; aguardando revisão do autor.
Branch: `revisao-proposta-ronaldo` (a partir de `main`).

## Origem

E-mail do Prof. Ronaldo (`docs-tcc/email-retorno-TCC2-ronaldo.txt`) e anotações
em vermelho em `docs-tcc/TCC2-PolyglotImportCSV-Report-v1.0-REVISADO.pdf`
(págs. 30–36 do relatório, §4.1 até o início da §4.2.4). Ele ainda não leu o
restante, então seções posteriores não estão aprovadas, só não foram revisadas.

Resumo do pedido: a explicação dos arquivos JSON de configuração não é didática.
Para cada arquivo, dar primeiro uma visão geral da finalidade de cada parte e do
que é obrigatório ou opcional; depois explicar cada parte **da raiz até as
folhas do esquema**, com **um exemplo JSON logo no início** de cada parte, sem
alongar a explicação.

**Cuidado com o cruzamento de versões.** As anotações foram feitas sobre a
**v1.0** (96 págs., 02/08). Desde então houve a v2.1 (103 págs., 26/09: GUI,
`--sample`, `--execution`/`--strategy`) e a v2.2 (109 págs., 28/09: verificação
dos SGBDs, `--check-dbms`, descritor `start`, renomeação `sgbd_config` →
`dbms_config`). O fonte LaTeX atual de `main` corresponde à v2.2, e é sobre ele que
o trabalho é feito. Por isso:

- números de página, figura, tabela e seção citados nas anotações são os da
  v1.0; cada anotação foi localizada no fonte atual pelo **texto** marcado, não
  pelo número;
- nomes citados pelo orientador como `sgbd_config` correspondem hoje a
  `dbms_config`;
- a v2.1 já resolveu três anotações ("assunto" virou "conjunto de dados", link do
  repositório na nota de rodapé da §4.1, referência à Fig. 1 do cap. 2), e a v2.2
  as manteve; as demais continuam presentes no texto atual (conferido por busca
  textual nas três versões);
- a §4.2 atual tem conteúdo que o orientador **ainda não viu** (descritor
  `start`, subseção de inicialização, opções novas da §4.1); ele deve receber o
  mesmo tratamento didático, sem ser descrito como novidade.

## Regras de redação (valem para todo o trabalho)

Legenda de figura abaixo, de tabela acima; "Fonte:" sempre abaixo; toda listagem
com frase de introdução que a nomeie ("Listagem~\ref{...}"); `...` em fragmentos
truncados, citado na prosa; nada de "backend" (sempre SGBD); nenhuma prosa sobre
versões anteriores do relatório ou da ferramenta; não envolver `tabular` em
grupo de tamanho de fonte (mata os struts); listagens com trechos fiéis dos
arquivos reais de `data/ecommerce/`, exceto onde o exemplo é declaradamente
ilustrativo.

## Mapa anotação → resposta

| Pág. | Anotação | Resposta |
|---|---|---|
| 31 | "o que é um assunto??" | já resolvido ("conjunto de dados") |
| 31 | argumento posicional da versão anterior | remover a frase |
| 31 | `--dbms-config` pode ser omitida → é opcional | colchetes no comando; prosa diz que é opcional |
| 31 | risco em "são facultativas e" | reescrever: `--config` é a única obrigatória |
| 32 | onde está o repositório? | já resolvido (nota de rodapé da §4.1) |
| 32 | `sources` explicado antes da estrutura | estrutura vem primeiro; `sources` vira parte (a) da §4.2.1 |
| 32–33 | cenário de e-commerce não apresentado | parágrafo e tabela do cenário na abertura da §4.2 |
| 34 | introduzir as partes seguintes | frase-roteiro na abertura da §4.2 e de cada subseção |
| 34 | trazer `sources` para junto da raiz | parte (a) "Raiz e `sources`" |
| 35 | introdução antes dos itens | tabela-resumo e exemplo mínimo abrem a §4.2.1 |
| 35 | ordem raiz→folha, um arquivo por vez, exemplo em cada parte | estrutura A (abaixo) |
| 36 | falta exemplo concreto | exemplo no início de cada parte |
| 36 | "coincidir"/"divergir" obscuro | exemplo de três entradas em (d) |
| 36 | `columns` pode ser omitido? obrigatório × opcional | tabela-resumo + frase explícita em (c) |

## Nova estrutura da §4.2

### §4.1 — ajustes pontuais

- Comando: `[--dbms-config caminho/dbms_config.json]` entre colchetes.
- Parágrafo das opções: `--config` é a **única obrigatória**; `--dbms-config`
  (padrão: `dbms_config.json` no diretório do arquivo de importação) e
  `--source` são opcionais; o parágrafo seguinte começa sem "são facultativas e".
- Remover "por isso não há mais um argumento posicional de arquivo de dados".

### §4.2 Formato de Configuração (JSON Schema) — abertura

1. Os dois arquivos, a separação mapeamento × conexão e o Apêndice A (texto atual,
   enxugado). A regra "SGBD do import precisa estar no de conexão" fica só com
   referência à §4.2.4.
2. **Cenário de exemplo**: retoma a Fig. 1 do cap. 2; os dados de exemplo são
   eventos de uma loja virtual, de quatro tipos. Tabela (legenda acima):

   | Fonte | Evento | Conteúdo principal |
   |---|---|---|
   | `stock` | reposição de estoque | produto, categoria, quantidade, preço |
   | `purchase` | compra | usuário, pedido, produto, avaliação |
   | `select_product` | visualização de produto | usuário, produto selecionado |
   | `add_to_cart` | adição ao carrinho | usuário, carrinho, produto, quantidade |

   Citar os quatro CSVs (`data/ecommerce/ecommerce_*.csv`), o combinado
   `ecommerce_join.csv` e o Apêndice B. O conteúdo de cada linha deve ser
   conferido contra a Tabela do Apêndice B antes de escrever.
3. Frase-roteiro: §4.2.1 arquivo de importação; §4.2.2 particularidades por SGBD;
   §4.2.3 arquivo de conexão; §4.2.4 validação. Cada arquivo é descrito da raiz
   até as folhas.

A antiga subseção "Visão Geral da Estrutura dos Arquivos de Configuração" deixa
de existir; as Figuras 8 e 9 passam a abrir as subseções dos seus arquivos.

### §4.2.1 O Arquivo de Importação

Abertura: Figura 8 + **tabela-resumo** (Parte | Onde | Finalidade | Obrigatória):

- `sources` (raiz): nomeia os CSVs de entrada — **sim**.
- `postgres`, `mongodb`, `cassandra`, `redis`, `neo4j` (raiz): um bloco por SGBD
  de destino — não (apenas os SGBDs usados).
- `entities` (bloco de SGBD): alvos (tabelas, coleções, nós…) — **sim**, se o
  bloco existir.
- `relationships` (PostgreSQL, Neo4j): chaves estrangeiras / arestas — não.
- `source`, `columns`, `auto_map`, `csv_columns`, `filters`,
  `cassandra_partition`, `cassandra_cluster` (entidade) — não; padrões explicados
  em (c).
- `csv_column`, `schema_column`, `is_key`, `db_type` (`columnSpec`) — não.
- Itens de `filters`: `column` e `operator` obrigatórios.

Depois, **exemplo mínimo raiz→folha**: trecho real do `import_config.json` com
`sources` e `postgres` → `entities` → `inventory` → `columns` (duas colunas),
com `...`. A prosa indica que cada nível é detalhado a seguir, nesta ordem.

Subsubseções (`\subsubsection`, numeradas 4.2.1.x):

- **(a) Raiz e `sources`** — listagens atuais dos modos multifonte e combinado
  (`lst:sources-multi`, `lst:sources-combined`), texto curto; fontes derivadas
  no modo combinado; pseudo-coluna `_source` em uma ou duas frases;
  `additionalProperties: false` rejeita chaves desconhecidas (ex.: `postgress`).
  Recebe o rótulo `sec:sources`.
- **(b) Blocos de SGBD** — exemplo do esqueleto
  `"postgres": { "entities": {...}, "relationships": {...} }`; a chave de cada
  entidade é o seu nome no destino; `relationships` só em PostgreSQL e Neo4j,
  detalhado na §4.2.2.
- **(c) Entidade** — exemplo `inventory`; `source` nas três formas (string,
  lista com união, omissão = fonte de mesmo nome), cada uma com exemplo de uma
  linha; `columns`: **se omitido, todas as colunas da fonte são mapeadas
  automaticamente**; com `auto_map: true`, as entradas declaradas se somam às
  automáticas e prevalecem coluna a coluna; `csv_columns` restringe o conjunto
  automático (nome, índice base 1, intervalo `"1-5"`); `filters` com exemplo
  **declaradamente ilustrativo** (`payment_method == credit_card`, ausente do
  cenário) e uma frase sobre `each`; `cassandra_*` remetido à §4.2.2.
  Recebe o rótulo `sec:raiz` (referenciado como "mapeamento automático").
- **(d) Colunas** — exemplo de três entradas:
  ```json
  "product_id": {},
  "timestamp":  { "schema_column": "event_time" },
  "total":      { "csv_column": 7 }
  ```
  A chave JSON dá, por padrão, o nome da coluna lida no CSV e o do atributo
  gravado no SGBD; `csv_column` e `schema_column` aparecem apenas quando um
  desses nomes difere da chave. Tabela 1 (`columnSpec`) mantida. Parágrafo curto
  sobre aninhamento (objeto no lugar da folha → subdocumento MongoDB; exemplo na
  §4.2.2). Inferência de tipos + Tabela 2 mantidas aqui.

### §4.2.2 Particularidades de cada SGBD no arquivo de importação

Mantêm-se as listagens reais de importação (`lst:pg-import`, `lst:mongo-import`,
`lst:cassandra-import`, `lst:redis-import`, `lst:neo4j-import`), com o texto
reduzido ao específico: PostgreSQL (FK, `db_type`/DDL, sem aninhamento); MongoDB
(aninhamento); Cassandra (`cassandra_partition`/`cassandra_cluster`, união de
fontes, `_source`→`event_type`); Redis (exatamente uma `is_key`, `auto_map`);
Neo4j (nós, `MERGE`, arestas). Os parágrafos e listagens de **conexão** saem
daqui. Um parágrafo por SGBD em negrito (não subsubseção) para não aprofundar a
numeração. Recebe o rótulo `sec:importacao-sgbds` se for o alvo atual dele.

### §4.2.3 O Arquivo de Conexão

Abertura: Figura 9 + tabela-resumo: `version` (raiz) obrigatório, versão do
formato (inteiro ≥ 1; atualmente 1); blocos de SGBD opcionais; `connection`
**obrigatório** em cada bloco presente; `schema` (só PostgreSQL) e `start`
opcionais. Exemplo de partida: trecho real do `dbms_config.json` com `version`,
`postgres` e `mongodb` (sem `start`, com `...`).

- **(a) Raiz** — `version` e blocos; SGBD usado no import precisa estar
  declarado aqui (→ §4.2.4).
- **(b) `connection` por SGBD** — tabela única no lugar das cinco listagens de
  conexão (padrões verificados no código):

  | SGBD | Campos | Obrigatórios | Padrões |
  |---|---|---|---|
  | PostgreSQL | host, port, database, user, password | — | 127.0.0.1, 5432, postgres, postgres, vazio |
  | MongoDB | uri, database | uri, database | — |
  | Cassandra | hosts, port, keyspace, protocol_version, request_timeout | hosts, keyspace | port 9042; request_timeout conforme código |
  | Redis | host, port, db, password | — | 127.0.0.1, 6379, 0, sem senha |
  | Neo4j | uri, user, password, database | uri, user, password | database: padrão do servidor |

  Mais uma frase sobre `schema` do PostgreSQL (padrão `public`). Se a tabela não
  couber na largura em tamanho normal, mover a coluna Padrões para a prosa
  (`\tabcolsep` reduzido antes de qualquer `\small`).
- **(c) `start`** — atual "Inicialização dos SGBDs" (`lst:start-windows`),
  praticamente sem alteração. Mantém o rótulo `sec:inicializacao-sgbds`.

### §4.2.4 Validação

Inalterada salvo renumeração; rótulo `sec:validacao` mantido.

## Código

Branch `revisao-proposta-ronaldo`, TDD:

1. Teste que falha: em `tests/`, para cada SGBD, um `dbms_config` válido exceto
   pela ausência de `connection` no bloco (ex.: `{"version": 1, "mongodb": {}}`)
   deve ser rejeitado pela validação de schema (`ConfigError`).
2. `dbms_config.schema.json`: `"required": ["connection"]` em
   `postgresConnection`, `mongoConnection`, `cassandraConnection`,
   `redisConnection` e `neo4jConnection`.
3. Ajustar fixtures/testes existentes que usem blocos sem `connection`; conferir
   `gui/preflight.py` e `--check-dbms`, que usam o mesmo schema.
4. Não alterar os padrões dos importadores/sinks (banco `"test"` no MongoDB,
   keyspace `"ecommerce"` no Cassandra); só registrar no relato final que ficaram
   em grande parte inalcançáveis.
5. Atualizar READMEs se descreverem `connection` como opcional.

Verificação: `./.venv/Scripts/python.exe -m pytest tests -q` com a suíte
inteira passando (referência: 728 passed / 1 skipped antes da mudança, mais os
novos testes).

## Figuras e apêndices

- `images/figure9-dbms-schema.mmd`: `connection*` (obrigatório) e `start`
  (opcional) em cada bloco; re-renderizar o PNG com
  `npx @mermaid-js/mermaid-cli` (`-p` com `executablePath` do Chrome local e
  configuração de tema clássico).
- `images/figure8-import-schema.mmd`: marcar `entities*`; re-renderizar.
- Apêndice A (`apendiceschemas.tex`): atualizar o schema de conexão serializado
  para refletir o arquivo novo.

## Referências cruzadas

Rótulos usados fora da §4.2 (`sec:sources`, `sec:raiz`, `sec:visao-schema`,
`sec:inicializacao-sgbds`, `sec:importacao-sgbds`, `sec:validacao`,
`fig:import-schema`, `fig:dbms-schema`, `tab:columnspec`, `tab:kinds`, rótulos
das listagens) devem continuar resolvendo: mantidos no alvo equivalente ou,
quando a seção sumir (`sec:visao-schema`), com as referências reapontadas.
Conferir com grep em `docs-tcc/chapters/` antes e no log do LaTeX depois
(nenhum "undefined").

## Entrega e verificação

- Compilar `docs-tcc/main.tex` (latexmk), sem referências indefinidas.
- Gerar `docs-tcc/TCC2-PolyglotImportCSV-Report-v2.3.pdf` (v2.2 mantida).
- Ler as páginas renderizadas da §4.1–§4.2 e conferir: ordem raiz→folha;
  exemplo no início de cada parte; legendas (tabela acima, figura abaixo);
  frase de introdução em toda listagem; cada linha do mapa anotação→resposta
  atendida; tabelas sem linhas sobrepostas.
- Commits coerentes (código; figuras e apêndice; texto; PDF), cada um com push.

## Fora de escopo

Capítulos e seções posteriores à §4.2 (exceto ajustes de referência); renomear
"backend" no código legado; mudar padrões de conexão dos importadores; versão
nova da ferramenta ou release.
