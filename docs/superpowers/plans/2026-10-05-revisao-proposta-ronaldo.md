# Revisão do capítulo da Proposta — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganizar a §4.2 do relatório (arquivos JSON de configuração) por arquivo, da raiz até as folhas, com exemplo no início de cada parte e indicação do que é obrigatório, atendendo às anotações do orientador; tornar `connection` obrigatório no `dbms_config`; gerar o relatório v2.3.

**Architecture:** Uma mudança pequena de schema (TDD) e a reescrita de um bloco contíguo de `docs-tcc/chapters/ch4proposta.tex` (linhas 98–678 do arquivo atual), feita em duas metades para que o documento compile ao fim de cada tarefa. A Figura 9 e o Apêndice A acompanham o schema. O texto novo está escrito por inteiro neste plano.

**Tech Stack:** Python 3 + jsonschema + pytest (venv em `.venv/`); LaTeX abnTeX2 com latexmk/pdflatex (MiKTeX); Mermaid CLI 11.4.0 via npx com o Chrome local.

**Spec:** `docs/superpowers/specs/2026-10-05-revisao-proposta-ronaldo-design.md`

## Global Constraints

- Base: o fonte atual de `main` (= v2.2). Nada da v2.2 é revertido.
- Legenda de figura **abaixo**; de tabela **acima**; `Fonte: Elaborado pelo autor (2026).` sempre abaixo, em `\footnotesize`.
- Toda listagem precedida de frase que a nomeie ("A Listagem~\ref{...} mostra ..."); trechos truncados com `...`, citado na prosa.
- Nunca "backend" no texto: sempre "SGBD". Nomes de arquivo e opção: `dbms_config.json`, `--dbms-config`.
- Nenhuma prosa sobre versões anteriores do relatório ou da ferramenta.
- Nunca envolver `tabular` em `{\small ...}` (mata os struts). Para ganhar largura: `\setlength{\tabcolsep}{4pt}` dentro do `table`.
- Listagens de exemplo são trechos fiéis de `data/ecommerce/*.json`, salvo quando o texto as declara ilustrativas.
- Testes: `./.venv/Scripts/python.exe -m pytest tests -q` (nunca `python` puro: pula ~100 testes da GUI).
- Git: um commit por tarefa, **push após cada commit**; mensagens terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Build: `cd docs-tcc && latexmk -pdf -interaction=nonstopmode main.tex`; sucesso = `main.pdf` atualizado e `grep -c "undefined" main.log` igual a 0.

## Review Focus

1. Um `dbms_config` com bloco de SGBD contendo só `start` (sem `connection`) deve ser rejeitado — teste na Tarefa 1.
2. Um bloco PostgreSQL/Redis com `"connection": {}` continua válido (todos os campos têm padrão) — teste na Tarefa 1.
3. `--check-dbms` e a pré-validação da GUI usam `load_config`/`validate_dbms_config`; a mudança tem de chegar a eles sem código novo — a suíte inteira na Tarefa 1 cobre (`tests/test_gui_preflight.py`, `tests/test_dbms_check.py`).
4. Referências cruzadas a rótulos removidos (`sec:raiz`, `sec:visao-schema`, `lst:pg-conn`, `lst:mongo-conn`, `lst:cassandra-conn`, `lst:redis-conn`, `lst:neo4j-conn`) — `grep` + log do LaTeX nas Tarefas 4, 5 e 6.
5. Tabelas novas largas demais ou com linhas sobrepostas — inspeção visual das páginas renderizadas na Tarefa 6.

---

### Task 1: `connection` obrigatório no schema de conexão

**Files:**
- Test: `tests/test_config_parser.py` (acrescentar ao final)
- Modify: `src/polyglotimportcsv/schemas/dbms_config.schema.json`
- Modify: `docs-tcc/chapters/apendiceschemas.tex` (seção "Schema de Conexão", que reproduz o arquivo)

**Interfaces:**
- Consumes: `validate_dbms_config(data) -> None`, que levanta `ConfigError` (já existentes em `polyglotimportcsv.config_parser` e `polyglotimportcsv.business_exception`; ambos já importados no topo de `tests/test_config_parser.py`).
- Produces: o schema exige `connection` em `postgresConnection`, `mongoConnection`, `cassandraConnection`, `redisConnection` e `neo4jConnection`.

- [ ] **Step 1: Escrever os testes**

Acrescentar ao final de `tests/test_config_parser.py`:

```python
_ALL_DBMS = ["postgres", "mongodb", "cassandra", "redis", "neo4j"]


@pytest.mark.parametrize("dbms", _ALL_DBMS)
def test_dbms_schema_requires_connection(dbms):
    # A declared DBMS must say how to reach it; an empty block used to pass and
    # fall back to silent defaults (e.g. MongoDB database "test").
    with pytest.raises(ConfigError):
        validate_dbms_config({"version": 1, dbms: {}})


@pytest.mark.parametrize("dbms", _ALL_DBMS)
def test_dbms_schema_start_alone_is_not_enough(dbms):
    with pytest.raises(ConfigError):
        validate_dbms_config({"version": 1, dbms: {"start": {"command": "x"}}})


@pytest.mark.parametrize("dbms", ["postgres", "redis"])
def test_dbms_schema_accepts_empty_connection_when_every_field_has_a_default(dbms):
    validate_dbms_config({"version": 1, dbms: {"connection": {}}})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config_parser.py -q`
Expected: 10 falhas (`test_dbms_schema_requires_connection` ×5 e `test_dbms_schema_start_alone_is_not_enough` ×5, "DID NOT RAISE"); os 2 testes de `connection` vazio passam.

- [ ] **Step 3: Alterar o schema**

Em `src/polyglotimportcsv/schemas/dbms_config.schema.json`, em cada uma das cinco definições `postgresConnection`, `mongoConnection`, `cassandraConnection`, `redisConnection` e `neo4jConnection`, inserir `"required": ["connection"],` logo após a linha `"type": "object",` da definição (o nível do bloco, **não** dentro de `connection`). Exemplo para o MongoDB:

```json
    "mongoConnection": {
      "type": "object",
      "required": ["connection"],
      "properties": {
        "connection": {
```

- [ ] **Step 4: Rodar a suíte inteira**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: tudo passa (referência anterior: 728 passed, 1 skipped; agora +12). Se algum teste antigo falhar por usar bloco de SGBD sem `connection` em um arquivo que passa pelo schema, acrescentar `"connection": {...}` àquele dado de teste — não relaxar o schema.

- [ ] **Step 5: Sincronizar o Apêndice A**

O `lstlisting` da seção `\section{Schema de Conexão (\texttt{dbms\_config.schema.json})}` em `docs-tcc/chapters/apendiceschemas.tex` reproduz o arquivo. Aplicar as mesmas cinco inserções. Conferir que o conteúdo da listagem é idêntico ao arquivo:

```bash
./.venv/Scripts/python.exe - <<'EOF'
import re, pathlib
tex = pathlib.Path("docs-tcc/chapters/apendiceschemas.tex").read_text(encoding="utf-8")
sec = tex.split(r"\section{Schema de Conexão")[1]
body = re.search(r"\\begin\{lstlisting\}\[[^\]]*\]\n(.*?)\\end\{lstlisting\}", sec, re.S).group(1)
src = pathlib.Path("src/polyglotimportcsv/schemas/dbms_config.schema.json").read_text(encoding="utf-8")
print("IDENTICO" if body.strip() == src.strip() else "DIFERENTE")
EOF
```

Expected: `IDENTICO`. Se já era `DIFERENTE` antes da mudança (rodar o script com `git stash` para conferir), basta garantir que as cinco linhas novas estão presentes.

- [ ] **Step 6: Commit e push**

```bash
git add tests/test_config_parser.py src/polyglotimportcsv/schemas/dbms_config.schema.json docs-tcc/chapters/apendiceschemas.tex
git commit -m "feat(schema): connection obrigatorio em todo bloco de SGBD do dbms_config

Um bloco vazio passava na validacao e caia em padroes silenciosos (banco
\"test\" no MongoDB, keyspace \"ecommerce\" no Cassandra). Apendice A atualizado.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```

---

### Task 2: Figura 9 com `connection` obrigatório

**Files:**
- Modify: `docs-tcc/images/figure9-dbms-schema.mmd`
- Regenerate: `docs-tcc/images/figure9-dbms-schema.png`

A Figura 8 (`figure8-import-schema.mmd`) já marca `sources*` e `entities*`; não muda.

- [ ] **Step 1: Substituir os nós de conexão**

Em `figure9-dbms-schema.mmd`, trocar as cinco linhas `PGC`…`NJC` por:

```
    PG --> PGC["connection* (host, port, database,\nuser, password)\nschema"]
    MG --> MGC["connection* (uri*, database*)"]
    CS --> CSC["connection* (hosts*, port, keyspace*,\nprotocol_version, request_timeout)"]
    RD --> RDC["connection* (host, port, db, password)"]
    NJ --> NJC["connection* (uri*, user*,\npassword*, database)"]
```

- [ ] **Step 2: Renderizar**

```bash
SCRATCH="<diretório de rascunho da sessão>"
printf '{"executablePath": "C:/Program Files/Google/Chrome/Application/chrome.exe"}' > "$SCRATCH/puppeteer.json"
printf '{"theme": "default"}' > "$SCRATCH/mermaid.json"
git show HEAD:docs-tcc/images/figure9-dbms-schema.png > "$SCRATCH/old9.png"
cd docs-tcc/images
npx -y @mermaid-js/mermaid-cli@11.4.0 -p "$SCRATCH/puppeteer.json" -c "$SCRATCH/mermaid.json" \
  -b white -s 2 -w 766 -i figure9-dbms-schema.mmd -o figure9-dbms-schema.png
cd ../..
```

- [ ] **Step 3: Conferir visualmente**

Abrir `docs-tcc/images/figure9-dbms-schema.png` e `$SCRATCH/old9.png` (ferramenta Read). Tema, cores e fonte iguais; os cinco nós mostram `connection*`; nenhum texto cortado. Se o tema diferir, ajustar `mermaid.json` e renderizar de novo.

- [ ] **Step 4: Commit e push**

```bash
git add docs-tcc/images/figure9-dbms-schema.mmd docs-tcc/images/figure9-dbms-schema.png
git commit -m "docs(tcc): figura 9 marca connection como obrigatorio

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```

---

### Task 3: Ajustes da §4.1 (comando e opções)

**Files:**
- Modify: `docs-tcc/chapters/ch4proposta.tex:47-74`

- [ ] **Step 1: Marcar `--dbms-config` como opcional no comando**

Na listagem `bashstyle` (linha 50), trocar `  --dbms-config caminho/dbms_config.json \` por:

```
  [--dbms-config caminho/dbms_config.json] \
```

- [ ] **Step 2: Reescrever o parágrafo das opções obrigatória e de arquivos**

Substituir o parágrafo que começa em `Cada parte do comando tem o seguinte papel.` (linhas 63–72) por:

```latex
Cada parte do comando tem o seguinte papel. A opção \texttt{-{}-config} é a única
\textbf{obrigatória} e indica o caminho do arquivo JSON de importação, que contém, em seu
bloco \texttt{sources}, os caminhos dos CSVs a carregar. As demais opções, entre
colchetes, são opcionais. A opção \texttt{-{}-dbms-config} indica o caminho do arquivo
JSON de conexão dos SGBDs; quando não é informada, a ferramenta usa o arquivo
\texttt{dbms\_config.json} do mesmo diretório do arquivo de importação. A opção
\texttt{-{}-source} \texttt{NOME=CAMINHO} \textbf{sobrescreve}, em tempo de execução, o
caminho de uma fonte declarada no bloco \texttt{sources} sem editar o arquivo de
configuração (por exemplo, para apontar a mesma configuração a um conjunto de dados
maior); pode ser repetida uma vez por fonte.
```

- [ ] **Step 3: Ajustar o início do parágrafo seguinte**

Na linha 74, trocar `As demais opções são facultativas e agrupam-se em três conjuntos. O primeiro controla` por:

```latex
As outras opções agrupam-se em três conjuntos. O primeiro controla
```

- [ ] **Step 4: Compilar**

Run: `cd docs-tcc && latexmk -pdf -interaction=nonstopmode main.tex; grep -c "undefined" main.log; cd ..`
Expected: compila; contagem 0.

- [ ] **Step 5: Commit e push**

```bash
git add docs-tcc/chapters/ch4proposta.tex
git commit -m "docs(tcc): secao 4.1 indica --dbms-config como opcional

Atende as anotacoes do orientador sobre o comando: --config e a unica opcao
obrigatoria e sai a frase sobre o argumento posicional.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```

---

### Task 4: Abertura da §4.2 e §4.2.1 "O Arquivo de Importação"

**Files:**
- Modify: `docs-tcc/chapters/ch4proposta.tex` — substituir o bloco que vai de `\section{Formato de Configuração (JSON Schema)}` (linha 98) até o fim do parágrafo `\textbf{Filtros.}` (linha 345, imediatamente antes de `\subsection{PostgreSQL}`).
- Modify: o mesmo arquivo, subseção `\subsection{O Cenário de Exemplo e os Arquivos de Dados}` (`sec:exemplo-linha`, linhas 871–887 do arquivo original): o cenário passa a ser apresentado na §4.2.

**Interfaces:**
- Produces (rótulos usados nas Tarefas 5 e 6): `sec:config-format`, `tab:eventos-ecommerce`, `sec:arquivo-importacao`, `fig:import-schema`, `tab:partes-importacao`, `lst:import-minimo`, `sec:sources`, `lst:sources-multi`, `lst:sources-combined`, `sec:blocos-sgbd`, `lst:bloco-postgres`, `sec:entidade`, `lst:entidade`, `lst:filtro`, `sec:colunas`, `lst:colunas`, `tab:columnspec`, `tab:kinds`.
- Consumes (definidos na Tarefa 5; a Tarefa 4 os referencia, então o log terá referências indefinidas até a Tarefa 5 — aceitável só entre as Tarefas 4 e 5): `sec:importacao-por-sgbd`, `sec:arquivo-conexao`, `lst:cassandra-import`, `lst:redis-import`, `lst:mongo-import`.
- Remove: `sec:visao-schema` e `sec:raiz` (nenhuma referência fora do bloco substituído; conferir com `grep -n "sec:visao-schema\|sec:raiz" docs-tcc/chapters/*.tex` após a edição — esperado: nada).

- [ ] **Step 1: Conferir fatos antes de escrever**

Os seguintes fatos foram verificados no código em 05/10 e fundamentam o texto; reconferir se o código mudou desde então:
- `entity_utils.FLAT_BACKENDS = {"postgres", "redis", "cassandra", "neo4j"}` → só o MongoDB aceita `columns` aninhado.
- `filter_engine.expand_each`: um filtro `each` por entidade; cada valor distinto gera o alvo `<entidade>_<sufixo>`, sufixo = `target_suffix` ou o valor normalizado.
- `schema_generator.build_postgres_create_tables`: coluna manual sem `db_type` vira `TEXT`; auto-mapeada recebe o tipo da Tabela `tab:kinds` (`mapping_resolver.py:161`).
- Schema de importação: raiz exige só `sources`; bloco de SGBD exige `entities`; entidade e `columnSpec` sem campos obrigatórios; `filter` exige `column` e `operator`.

- [ ] **Step 2: Substituir o bloco das linhas 98–345**

Novo conteúdo (as figuras e tabelas reaproveitadas mantêm os seus rótulos):

```latex
\section{Formato de Configuração (JSON Schema)}
\label{sec:config-format}

A configuração da ferramenta é dividida em \textbf{dois arquivos JSON}. O arquivo de
\textbf{importação} (\texttt{import\_config.json}) declara as fontes de dados e o
\textbf{mapeamento} das suas colunas para entidades e relacionamentos em cada SGBD; o
arquivo de \textbf{conexão} (\texttt{dbms\_config.json}) declara quais SGBDs estão
disponíveis e como alcançá-los. A separação atende a duas preocupações distintas: o
mapeamento muda conforme o domínio dos dados, enquanto a conexão muda conforme o ambiente
(desenvolvimento, testes, produção). Cada arquivo é validado por um \textbf{JSON Schema}
próprio, embutido na ferramenta em \texttt{src/\allowbreak polyglotimportcsv/\allowbreak
schemas/} e reproduzido no Apêndice~\ref{ap:schemas}.

Os exemplos desta seção vêm do cenário de e-commerce apresentado na
Seção~\ref{sec:persistencia-poliglota} (Figura~\ref{fig:polyglot-ecommerce}), cujos
arquivos acompanham o repositório da ferramenta em \texttt{data/\allowbreak ecommerce/}.
Os dados desse cenário registram os eventos de uma loja virtual, de quatro tipos,
resumidos na Tabela~\ref{tab:eventos-ecommerce}. Todo evento registra o instante em que
ocorreu e o usuário envolvido; a tabela indica os demais dados de cada tipo.

\begin{table}[H]
  \caption{Tipos de evento do cenário de e-commerce.}
  \label{tab:eventos-ecommerce}
  \centering
  \begin{tabular}{>{\ttfamily}l l >{\raggedright\arraybackslash}p{6.4cm}}
    \toprule
    \normalfont\textbf{Tipo} & \textbf{Evento} & \textbf{Demais dados registrados} \\
    \midrule
    stock           & reposição de estoque & produto, categoria, quantidade disponível e preço \\
    purchase        & compra               & pedido, produto, contraparte da venda, pagamento e avaliação \\
    select\_product & seleção de produto   & produto selecionado \\
    add\_to\_cart   & adição ao carrinho   & carrinho, produto e quantidade \\
    \bottomrule
  \end{tabular}
  \par\vspace{4pt}
  {\footnotesize Fonte: Elaborado pelo autor (2026).}
\end{table}

Cada tipo de evento tem o seu próprio CSV, com oito linhas: \texttt{ecommerce\_stock.csv},
\texttt{ecommerce\_purchase.csv}, \texttt{ecommerce\_select\_product.csv} e
\texttt{ecommerce\_add\_to\_cart.csv}. Os mesmos eventos estão também reunidos em um único
arquivo, \texttt{ecommerce\_join.csv}, cuja primeira coluna (\texttt{action}) indica o
tipo de cada linha. O Apêndice~\ref{ap:csv} reproduz esses dados em forma tabular.

As subseções seguintes descrevem cada arquivo da raiz até as folhas do seu schema: a
Seção~\ref{sec:arquivo-importacao} apresenta o arquivo de importação; a
Seção~\ref{sec:importacao-por-sgbd}, o que esse arquivo tem de específico em cada SGBD; a
Seção~\ref{sec:arquivo-conexao}, o arquivo de conexão; e a Seção~\ref{sec:validacao}, as
validações aplicadas aos dois antes da importação.

\subsection{O Arquivo de Importação}
\label{sec:arquivo-importacao}

A Figura~\ref{fig:import-schema} mostra a estrutura do schema do arquivo de importação,
da raiz (à esquerda) até as folhas (à direita); os campos marcados com asterisco são
obrigatórios. A Tabela~\ref{tab:partes-importacao} resume a finalidade de cada parte e
indica quais podem ser omitidas.

\begin{figure}[H]
  \centering
  \includegraphics[width=\textwidth]{images/figure8-import-schema}
  \caption{Estrutura do JSON Schema de importação (\texttt{import\_config}).}
  \label{fig:import-schema}
  \par\vspace{4pt}
  {\footnotesize Fonte: Elaborado pelo autor (2026).}
\end{figure}

\begin{table}[H]
  \caption{Partes do arquivo de importação.}
  \label{tab:partes-importacao}
  \centering
  \setlength{\tabcolsep}{4pt}
  \begin{tabular}{>{\raggedright\arraybackslash\ttfamily}p{3.5cm} >{\raggedright\arraybackslash}p{2.6cm} >{\raggedright\arraybackslash}p{4.6cm} >{\raggedright\arraybackslash}p{3.6cm}}
    \toprule
    \normalfont\textbf{Parte} & \textbf{Onde} & \textbf{Finalidade} & \textbf{Obrigatória?} \\
    \midrule
    sources & raiz & nomear os CSVs de entrada & sim \\
    postgres, mongodb, cassandra, redis, neo4j & raiz & mapear dados para um SGBD & não; só os SGBDs de destino \\
    entities & bloco de SGBD & declarar os alvos (tabelas, coleções, nós\ldots) & sim \\
    relationships & bloco PostgreSQL ou Neo4j & declarar chaves estrangeiras ou arestas & não \\
    source & entidade & indicar a fonte lida & não; padrão: a fonte de mesmo nome \\
    columns & entidade & mapear as colunas & não; se omitido, todas as colunas da fonte \\
    auto\_map, csv\_columns & entidade & controlar o mapeamento automático & não \\
    filters & entidade & selecionar linhas & não \\
    cassandra\_partition, cassandra\_cluster & entidade do Cassandra & definir a chave primária & não; a partição é exigida para criar a tabela \\
    csv\_column, schema\_column, is\_key, db\_type & coluna & ligar uma coluna do CSV a um atributo & não \\
    \bottomrule
  \end{tabular}
  \par\vspace{4pt}
  {\footnotesize Fonte: Elaborado pelo autor (2026).}
\end{table}

A Listagem~\ref{lst:import-minimo} mostra um trecho do arquivo de importação do cenário
que percorre essa estrutura da raiz até as folhas: o bloco \texttt{sources}, o bloco do
PostgreSQL, uma de suas entidades e duas de suas colunas. As reticências (\texttt{...})
marcam o conteúdo omitido; o arquivo completo está no Apêndice~\ref{ap:config}.

\begin{lstlisting}[style=jsonstyle,caption={Trecho do arquivo de importação, da raiz até as colunas.},label={lst:import-minimo}]
"sources": {
  "stock":    "ecommerce_stock.csv",
  "purchase": "ecommerce_purchase.csv",
  ...
},
"postgres": {
  "entities": {
    "inventory": {
      "source": "stock",
      "columns": {
        "product_id": { "is_key": true, "db_type": "BIGINT" },
        "price":      { "db_type": "NUMERIC(14,2)" },
        ...
      }
    },
    ...
  }
},
...
\end{lstlisting}

Lido de cima para baixo, o trecho diz que: o bloco \texttt{sources} nomeia os arquivos de
dados; o bloco \texttt{postgres} indica que parte dos dados vai para o PostgreSQL; a
entidade \texttt{inventory} será uma tabela, alimentada pela fonte \texttt{stock}; e cada
entrada de \texttt{columns} cria uma coluna dessa tabela. As subseções a seguir explicam
cada um desses níveis, nessa ordem.

\subsubsection{Raiz e bloco \texttt{sources}}
\label{sec:sources}

A raiz do arquivo admite apenas o bloco \texttt{sources}, obrigatório, e um bloco por SGBD
de destino. Qualquer outra chave é rejeitada (\texttt{additionalProperties: false}), de
modo que um erro de digitação como \texttt{postgress} é apontado na validação em vez de
ser ignorado.

O bloco \texttt{sources} dá um \textbf{nome} a cada arquivo CSV de entrada, e as entidades
referem-se às fontes por esse nome. Há duas formas de declarar as fontes, que
correspondem aos dois modos de importação. No modo \textbf{multifonte}, cada nome aponta
diretamente para um CSV, como na Listagem~\ref{lst:sources-multi}: uma fonte por tipo de
evento.

\begin{lstlisting}[style=jsonstyle,caption={Bloco \texttt{sources} no modo multifonte (um CSV por conjunto de dados).},label={lst:sources-multi}]
"sources": {
  "stock":          "ecommerce_stock.csv",
  "purchase":       "ecommerce_purchase.csv",
  "select_product": "ecommerce_select_product.csv",
  "add_to_cart":    "ecommerce_add_to_cart.csv"
}
\end{lstlisting}

No modo \textbf{combinado}, uma única fonte aponta para o CSV que reúne todos os eventos, e
\texttt{"origin\_column": true} indica que a primeira coluna desse arquivo identifica a
origem de cada linha, como na Listagem~\ref{lst:sources-combined}.

\begin{lstlisting}[style=jsonstyle,caption={Bloco \texttt{sources} no modo combinado (um CSV com coluna de origem).},label={lst:sources-combined}]
"sources": {
  "ecommerce": { "file": "ecommerce_join.csv", "origin_column": true }
}
\end{lstlisting}

Ao carregar uma fonte combinada, a ferramenta separa as linhas pelo valor da primeira
coluna e registra, além da própria fonte, uma fonte para cada valor distinto. Assim, os
nomes \texttt{stock}, \texttt{purchase}, \texttt{select\_product} e \texttt{add\_to\_cart}
ficam disponíveis como no modo multifonte, e o restante do arquivo de importação é
idêntico nos dois modos. Em ambos, cada linha recebe ainda uma \textbf{pseudo-coluna}
\texttt{\_source} com o nome da sua fonte, que pode ser mapeada como qualquer outra
coluna (um exemplo aparece na Listagem~\ref{lst:cassandra-import}).

\subsubsection{Blocos de SGBD}
\label{sec:blocos-sgbd}

Cada bloco de SGBD (\texttt{postgres}, \texttt{mongodb}, \texttt{cassandra},
\texttt{redis} ou \texttt{neo4j}) descreve o que será gravado naquele SGBD; só aparecem os
blocos dos SGBDs que se deseja alimentar. A Listagem~\ref{lst:bloco-postgres} mostra o
esqueleto do bloco do PostgreSQL no cenário, com o conteúdo de cada entrada omitido.

\begin{lstlisting}[style=jsonstyle,caption={Esqueleto do bloco \texttt{postgres} do arquivo de importação.},label={lst:bloco-postgres}]
"postgres": {
  "entities": {
    "categories": { ... },
    "products":   { ... },
    "inventory":  { ... },
    "orders":     { ... }
  },
  "relationships": {
    "product_category": { ... },
    "order_product":    { ... }
  }
}
\end{lstlisting}

O mapa \texttt{entities}, obrigatório, contém as entidades a criar, cada uma identificada
pelo nome que terá no SGBD --- aqui, quatro tabelas. O mapa \texttt{relationships},
opcional, existe apenas nos blocos do PostgreSQL, onde declara chaves estrangeiras, e do
Neo4j, onde declara arestas; ambos são detalhados na Seção~\ref{sec:importacao-por-sgbd}.

\subsubsection{Entidade}
\label{sec:entidade}

Uma entidade representa um alvo no SGBD: uma tabela no PostgreSQL ou no Cassandra, uma
coleção no MongoDB, um conjunto de chaves no Redis ou um rótulo de nó no Neo4j. Todos os
SGBDs usam a mesma definição de entidade, exemplificada na Listagem~\ref{lst:entidade}
pela entidade \texttt{inventory} do PostgreSQL.

\begin{lstlisting}[style=jsonstyle,caption={Entidade \texttt{inventory} do arquivo de importação.},label={lst:entidade}]
"inventory": {
  "source": "stock",
  "columns": {
    "product_id":         { "is_key": true, "db_type": "BIGINT" },
    "quantity_available": { "db_type": "BIGINT" },
    "last_restock_date":  { "db_type": "TIMESTAMPTZ" },
    "price":              { "db_type": "NUMERIC(14,2)" }
  }
}
\end{lstlisting}

Todos os campos de uma entidade são opcionais:

\begin{itemize}
  \item \texttt{source} indica a fonte da qual a entidade lê. Pode ser o nome de uma fonte,
  como na listagem; uma lista de nomes (\texttt{"source": ["stock", "purchase"]}), caso em
  que as linhas das fontes são unidas em uma só entidade, com valores vazios nas colunas
  que faltam em alguma delas; ou ser omitido, caso em que a entidade lê da fonte que tem o
  seu próprio nome.
  \item \texttt{columns} lista as colunas da entidade (Seção~\ref{sec:colunas}). Se for
  omitido, a entidade recebe \textbf{todas} as colunas da fonte, com os nomes do CSV e
  tipos inferidos dos próprios dados; é o \textbf{mapeamento automático}, que
  \texttt{auto\_map} e \texttt{csv\_columns} ajustam, como descreve a mesma seção.
  \item \texttt{filters} restringe as linhas da fonte que participam da entidade, como
  descrito a seguir.
  \item \texttt{cassandra\_partition} e \texttt{cassandra\_cluster} definem a chave
  primária no Cassandra (Seção~\ref{sec:importacao-por-sgbd}).
\end{itemize}

No cenário, cada tipo de evento já vem de uma fonte própria, e nenhuma entidade precisa de
filtros. A Listagem~\ref{lst:filtro} mostra um filtro ilustrativo, que não faz parte do
cenário: aplicado a uma entidade que lê da fonte \texttt{purchase}, ele manteria apenas as
compras pagas com cartão de crédito.

\begin{lstlisting}[style=jsonstyle,caption={Filtro ilustrativo sobre a coluna \texttt{payment\_method}.},label={lst:filtro}]
"filters": [
  { "column": "payment_method", "operator": "==", "value": "credit_card" }
]
\end{lstlisting}

Cada filtro exige a coluna (\texttt{column}) e o operador (\texttt{operator}), que pode ser
\texttt{==}, \texttt{!=}, \texttt{>}, \texttt{<}, \texttt{>=}, \texttt{<=}, \texttt{in},
\texttt{not\_in} ou \texttt{each}; \texttt{value} é o valor comparado. O operador
\texttt{each} não restringe as linhas, e sim divide a entidade: cada valor distinto da
coluna gera um alvo próprio, cujo nome é o da entidade seguido de um sufixo derivado do
valor (ou definido em \texttt{target\_suffix}).

\subsubsection{Colunas}
\label{sec:colunas}

O mapa \texttt{columns} associa cada atributo da entidade a uma coluna do CSV. A
Listagem~\ref{lst:colunas} mostra três entradas: as duas primeiras pertencem à entidade
\texttt{user\_activity\_log} do Cassandra (Listagem~\ref{lst:cassandra-import}); a
terceira é ilustrativa.

\begin{lstlisting}[style=jsonstyle,caption={Três formas de mapear uma coluna.},label={lst:colunas}]
"columns": {
  "product_id": {},
  "timestamp":  { "schema_column": "event_time" },
  "preco":      { "csv_column": "price" }
}
\end{lstlisting}

A chave de cada entrada dá, por padrão, dois nomes ao mesmo tempo: o da coluna lida no CSV
e o do atributo gravado no SGBD. Na primeira entrada, os dois nomes são iguais à chave
(\texttt{product\_id}), e o objeto vazio basta. Na segunda, a coluna \texttt{timestamp} do
CSV é gravada com outro nome, \texttt{event\_time}, indicado em \texttt{schema\_column}.
Na terceira, o atributo se chama \texttt{preco} no SGBD, mas é lido da coluna
\texttt{price} do CSV, indicada em \texttt{csv\_column}; esse campo também aceita a
posição da coluna, a partir de 1, útil em CSVs sem cabeçalho. A
Tabela~\ref{tab:columnspec} resume os quatro campos que uma entrada pode ter.

\begin{table}[H]
  \caption{Campos de mapeamento de coluna (\texttt{columnSpec}).}
  \label{tab:columnspec}
  \centering
  \begin{tabular}{>{\ttfamily}l l l >{\raggedright\arraybackslash}p{5cm}}
    \toprule
    \normalfont\textbf{Campo} & \textbf{Tipo} & \textbf{Obrigatório} & \textbf{Descrição} \\
    \midrule
    csv\_column    & \textit{string} ou inteiro ($\geq 1$) & não & Cabeçalho CSV ou posição da coluna (base 1). Padrão: a chave. \\
    schema\_column & \textit{string} & não & Nome do atributo no SGBD destino. Padrão: a chave. \\
    is\_key        & booleano & não & Chave primária, chave de \texttt{MERGE} (Neo4j) ou chave Redis. \\
    db\_type       & \textit{string} & não & Tipo SQL/CQL para geração de DDL. \\
    \bottomrule
  \end{tabular}
  \par\vspace{4pt}
  {\footnotesize Fonte: Elaborado pelo autor (2026).}
\end{table}

No lugar de uma entrada simples, \texttt{columns} pode conter um novo mapa de colunas.
Esse \textbf{aninhamento} só é aceito no MongoDB, onde produz um subdocumento
(Listagem~\ref{lst:mongo-import}).

\textbf{Mapeamento automático.} Quando \texttt{columns} é omitido, a entidade recebe todas
as colunas da sua fonte, com os nomes do CSV. Com \texttt{"auto\_map": true}, as colunas
declaradas em \texttt{columns} somam-se às automáticas e prevalecem sobre elas: na
Listagem~\ref{lst:redis-import}, a entidade \texttt{shopping\_cart} declara apenas a
coluna-chave e recebe as demais automaticamente. Nos dois casos, \texttt{csv\_columns}
limita o mapeamento automático às colunas indicadas, por nome, por posição (a partir de 1)
ou por intervalo, como \texttt{"1-5"}.

\textbf{Inferência de tipos.} Todos os valores são lidos inicialmente como texto,
preservando o conteúdo original do arquivo. Em seguida, a ferramenta classifica cada
coluna segundo o tipo predominante entre os seus valores --- inteiro, real, data/hora,
booleano, texto ou vazia --- e converte os valores para o tipo nativo correspondente.
Essa classificação também define o tipo de destino (\texttt{db\_type}) usado na geração de
DDL quando a coluna é auto-mapeada, segundo a correspondência da
Tabela~\ref{tab:kinds}; uma coluna declarada sem \texttt{db\_type} é criada como
\texttt{TEXT}.

\begin{table}[H]
  \caption{Correspondência entre tipo inferido e tipo de destino na geração de DDL.}
  \label{tab:kinds}
  \centering
  \begin{tabular}{l l}
    \toprule
    \textbf{Tipo inferido} & \textbf{Tipo de destino (\texttt{db\_type})} \\
    \midrule
    inteiro (\textit{integer})   & \texttt{BIGINT} \\
    real (\textit{float})        & \texttt{NUMERIC} \\
    data/hora (\textit{datetime}) & \texttt{TIMESTAMPTZ} \\
    booleano (\textit{boolean})  & \texttt{BOOLEAN} \\
    texto (\textit{string}) ou vazia & \texttt{TEXT} \\
    \bottomrule
  \end{tabular}
  \par\vspace{4pt}
  {\footnotesize Fonte: Elaborado pelo autor (2026).}
\end{table}
```

Nota: a Figura 8 deixa de ser `\begin{figure}` flutuante e passa a `[H]`, para ficar junto da frase que a apresenta. Se isso produzir um grande espaço em branco no PDF, voltar para `\begin{figure}` sem `[H]`.

- [ ] **Step 3: Ajustar a subseção do cenário na §4.3**

Substituir os dois primeiros parágrafos de `\subsection{O Cenário de Exemplo e os Arquivos de Dados}` (do `Para concretizar o algoritmo,` até `organizado por ação.`) por:

```latex
Para concretizar o algoritmo, esta subseção e a seguinte acompanham as linhas do cenário
de e-commerce apresentado na seção~\ref{sec:config-format}
(Tabela~\ref{tab:eventos-ecommerce}) pelo núcleo do algoritmo; a execução completa do
cenário é demonstrada na seção~\ref{sec:exemplo-uso}. O exemplo adota o modo multifonte,
em que cada tipo de evento tem o seu próprio CSV.
```

O parágrafo seguinte (`A Tabela~\ref{tab:csv-stock} apresenta...`) e a tabela permanecem.

- [ ] **Step 4: Conferir rótulos removidos**

Run: `grep -n "sec:visao-schema\|sec:raiz\|ref{sec:importacao-sgbds}" docs-tcc/chapters/*.tex`
Expected: apenas `apendiceconfig.tex:13` e a definição `\label{sec:importacao-sgbds}` (§4.3, rótulo que continua existindo). Nenhuma ocorrência de `sec:visao-schema` ou `sec:raiz`.

- [ ] **Step 5: Compilar**

Run: `cd docs-tcc && latexmk -pdf -interaction=nonstopmode main.tex; grep -o "Reference \`[^']*' .*undefined" main.log | sort -u; cd ..`
Expected: compila. Referências indefinidas permitidas **somente**: `sec:importacao-por-sgbd`, `sec:arquivo-conexao` (criadas na Tarefa 5). Qualquer outra é erro desta tarefa.

- [ ] **Step 6: Commit e push**

```bash
git add docs-tcc/chapters/ch4proposta.tex
git commit -m "docs(tcc): arquivo de importacao explicado da raiz as folhas

Abre a secao 4.2 com o cenario de e-commerce (antes so apresentado na 4.3) e
reorganiza a explicacao do import_config: tabela do que e obrigatorio, trecho
da raiz as colunas e um exemplo no inicio de cada nivel, conforme o orientador.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```

---

### Task 5: §4.2.2 "Particularidades de Cada SGBD" e §4.2.3 "O Arquivo de Conexão"

**Files:**
- Modify: `docs-tcc/chapters/ch4proposta.tex` — substituir o bloco que vai de `\subsection{PostgreSQL}` até o fim da subseção `\subsection{Inicialização dos SGBDs}` (o parágrafo que termina em `são exemplos a ajustar.`), imediatamente antes de `\subsection{Validação, Consistência entre Arquivos e Fluxo de Carregamento}`.
- Modify: mesma arquivo, §4.3 `\subsection{A Importação em Cada SGBD}`: `(Listagem~\ref{lst:pg-conn})` → `(Listagem~\ref{lst:conexao-exemplo})`.
- Modify: `docs-tcc/chapters/apendiceschemas.tex:5-7` (frase de abertura).

**Interfaces:**
- Consumes: rótulos da Tarefa 4 (`sec:entidade`, `sec:colunas`, `tab:kinds`, `fig:import-schema`, `sec:validacao`).
- Produces: `sec:importacao-por-sgbd`, `lst:pg-import`, `lst:mongo-import`, `lst:cassandra-import`, `lst:redis-import`, `lst:neo4j-import`, `sec:arquivo-conexao`, `fig:dbms-schema`, `tab:partes-conexao`, `lst:conexao-exemplo`, `tab:conexao-sgbd`, `sec:inicializacao-sgbds`, `lst:start-windows`.
- Remove: `lst:pg-conn`, `lst:mongo-conn`, `lst:cassandra-conn`, `lst:redis-conn`, `lst:neo4j-conn`.

- [ ] **Step 1: Conferir os padrões de conexão no código**

Os valores da Tabela `tab:conexao-sgbd` vêm de: `importers/postgres_importer.py:45-49` (127.0.0.1, 5432, postgres, postgres, senha vazia); `importers/redis_importer.py:23-26` (127.0.0.1, 6379, 0, sem senha); `importers/cassandra_importer.py:41,191` (`DEFAULT_REQUEST_TIMEOUT = 30.0`, porta 9042); `sinks/neo4j_sink.py:53` (`database` ausente → padrão do servidor). Reconferir com `grep -n "conn.get" src/polyglotimportcsv/importers/*.py`.

- [ ] **Step 2: Substituir o bloco**

Novo conteúdo:

```latex
\subsection{Particularidades de Cada SGBD no Arquivo de Importação}
\label{sec:importacao-por-sgbd}

Os cinco blocos de SGBD usam a mesma definição de entidade, mas cada SGBD acrescenta
regras próprias, decorrentes do seu modelo de dados. Esta subseção apresenta essas regras,
cada uma com o trecho correspondente do arquivo de importação do cenário; o arquivo
completo está no Apêndice~\ref{ap:config}.

\textbf{PostgreSQL.} As entidades são tabelas e só admitem colunas simples, sem
aninhamento. O campo \texttt{db\_type} de cada coluna define o tipo usado na criação da
tabela (\texttt{CREATE TABLE}) quando \texttt{-{}-create-schema} está ativo, e as colunas
com \texttt{is\_key} formam a chave primária. O mapa \texttt{relationships} declara chaves
estrangeiras: \texttt{from} é a tabela que contém a chave, \texttt{to} é a tabela
referenciada, \texttt{foreign\_key} é a coluna de \texttt{from} e \texttt{references\_key}
é a coluna de \texttt{to} (por padrão, a de mesmo nome). A
Listagem~\ref{lst:pg-import} mostra a entidade \texttt{products} e a chave estrangeira que
a liga às categorias.

\begin{lstlisting}[style=jsonstyle,caption={Fragmento de importação PostgreSQL com chave estrangeira.},label={lst:pg-import}]
"postgres": {
  "entities": {
    "products": {
      "source": "stock",
      "columns": {
        "product_id":   { "is_key": true, "db_type": "BIGINT" },
        "product_name": { "db_type": "TEXT" },
        "category_id":  { "db_type": "BIGINT" },
        ...
      }
    },
    ...
  },
  "relationships": {
    "product_category": {
      "from": "products",
      "to":   "categories",
      "foreign_key":    "category_id",
      "references_key": "category_id"
    },
    ...
  }
}
\end{lstlisting}

As reticências omitem três colunas de \texttt{products} (variante, marca e preço), as
outras três entidades (\texttt{categories}, \texttt{inventory} e \texttt{orders}) e a
segunda chave estrangeira (\texttt{order\_product}, de pedidos para produtos).

\textbf{MongoDB.} As entidades são coleções, e o MongoDB é o único SGBD que aceita
\textbf{aninhamento} em \texttt{columns}: uma chave cujo valor é um novo mapa de colunas
produz um subdocumento, sem nenhum campo adicional. Na Listagem~\ref{lst:mongo-import}, as
chaves \texttt{category} e \texttt{stock} não são colunas do CSV, e sim agrupam outras
colunas em dois subdocumentos de cada documento \texttt{product\_catalog}.

\begin{lstlisting}[style=jsonstyle,caption={Fragmento de importação MongoDB com subdocumentos.},label={lst:mongo-import}]
"mongodb": {
  "entities": {
    "product_catalog": {
      "source": "stock",
      "columns": {
        "product_id":   {},
        "product_name": {},
        ...
        "category": {
          "category_id": {},
          "category_name": {}
        },
        "stock": {
          "quantity_available": {},
          "last_restock_date": {}
        }
      }
    }
  }
}
\end{lstlisting}

As reticências omitem as demais colunas cadastrais do produto (variante, marca,
descrição, imagem e preço), mapeadas da mesma forma que \texttt{product\_id} e
\texttt{product\_name}.

\textbf{Apache Cassandra.} As entidades são tabelas com colunas simples, e a chave
primária é definida por dois campos próprios: \texttt{cassandra\_\allowbreak partition},
a lista de colunas da chave de partição, e \texttt{cassandra\_\allowbreak cluster}, as
colunas de agrupamento. A partição é exigida para criar a tabela, pois a linguagem CQL
requer ao menos uma coluna de partição na chave primária; por isso a sua ausência só é
apontada quando \texttt{-{}-create-schema} está ativo. No Cassandra, \texttt{is\_key} não
participa da chave primária. A Listagem~\ref{lst:cassandra-import} mostra uma entidade
que \textbf{une} as quatro fontes em uma tabela de eventos.

\begin{lstlisting}[style=jsonstyle,caption={Fragmento de importação Cassandra com união de fontes e chave composta.},label={lst:cassandra-import}]
"cassandra": {
  "entities": {
    "user_activity_log": {
      "source": ["stock", "purchase", "select_product", "add_to_cart"],
      "columns": {
        "user_id":             {},
        "timestamp":           { "schema_column": "event_time" },
        "_source":             { "schema_column": "event_type" },
        "product_id":          {},
        "order_number":        {},
        "selected_product_id": {},
        "shopping_cart_id":    {}
      },
      "cassandra_partition": ["user_id"],
      "cassandra_cluster":   ["timestamp"]
    }
  }
}
\end{lstlisting}

A pseudo-coluna \texttt{\_source}, que guarda a fonte de cada linha, é gravada na coluna
\texttt{event\_type}, distinguindo os tipos de evento na tabela; a chave primária é
formada pelo usuário (partição) e pelo instante do evento (agrupamento).

\textbf{Redis.} Cada entidade gera um conjunto de pares chave-valor e deve ter
\textbf{exatamente uma} coluna com \texttt{is\_key}: o valor dessa coluna, tal como aparece
no CSV, torna-se a chave Redis, e os demais campos mapeados compõem o valor, armazenado em
JSON. Na Listagem~\ref{lst:redis-import}, \texttt{shopping\_cart} declara apenas a chave e
usa \texttt{auto\_map} para receber as demais colunas da fonte \texttt{add\_to\_cart};
\texttt{user\_session} usa como chave o identificador do usuário e renomeia
\texttt{timestamp} para \texttt{last\_seen}, registrando a última navegação de cada
usuário.

\begin{lstlisting}[style=jsonstyle,caption={Fragmento de importação Redis (e-commerce), com mapeamento automático.},label={lst:redis-import}]
"redis": {
  "entities": {
    "shopping_cart": {
      "source": "add_to_cart",
      "auto_map": true,
      "columns": {
        "shopping_cart_id": { "is_key": true }
      }
    },
    "user_session": {
      "source": "select_product",
      "columns": {
        "user_id":    { "is_key": true },
        "user_name":  {},
        "user_email": {},
        "timestamp":  { "schema_column": "last_seen" }
      }
    }
  }
}
\end{lstlisting}

\textbf{Neo4j.} Cada entidade é um rótulo (\textit{label}) de nó e deve ter exatamente uma
coluna com \texttt{is\_key}, usada para identificar o nó na operação \texttt{MERGE} da
linguagem Cypher, que só cria o nó se ele ainda não existir. O mapa
\texttt{relationships} declara arestas: \texttt{from} e \texttt{to} são os rótulos de
origem e de destino, \texttt{type} é o tipo da aresta e \texttt{columns}, opcional, lista as
propriedades da aresta. Na Listagem~\ref{lst:neo4j-import}, o nó \texttt{User} lê da fonte
\texttt{purchase} (os compradores) e o nó \texttt{Product}, da fonte \texttt{stock}; a
aresta \texttt{PURCHASED} liga cada comprador ao produto comprado, com quantidade, preço e
nota da avaliação.

\begin{lstlisting}[style=jsonstyle,caption={Fragmento de importação Neo4j (nós e aresta).},label={lst:neo4j-import}]
"neo4j": {
  "entities": {
    "User": {
      "source": "purchase",
      "columns": {
        "user_id":    { "is_key": true },
        "user_name":  {},
        "user_email": {}
      }
    },
    "Product": {
      "source": "stock",
      "columns": {
        "product_id":    { "is_key": true },
        "product_name":  {},
        "product_brand": {}
      }
    }
  },
  "relationships": {
    "PURCHASED": {
      "from": "User",
      "to":   "Product",
      "type": "PURCHASED",
      "columns": {
        "order_number": { "is_key": true },
        "quantity":     {},
        "price":        {},
        "rating":       {}
      }
    }
  }
}
\end{lstlisting}

\subsection{O Arquivo de Conexão}
\label{sec:arquivo-conexao}

O arquivo de conexão diz \textit{onde} alcançar cada SGBD, sem nenhuma informação de
mapeamento. A Figura~\ref{fig:dbms-schema} mostra a estrutura do seu schema, também com
os campos obrigatórios marcados com asterisco: a raiz, um bloco por SGBD e, dentro de cada
bloco, os parâmetros de acesso. A Tabela~\ref{tab:partes-conexao} resume a finalidade de
cada parte.

\begin{figure}[H]
  \centering
  \includegraphics[width=0.85\textwidth]{images/figure9-dbms-schema}
  \caption{Estrutura do JSON Schema de conexão (\texttt{dbms\_config}).}
  \label{fig:dbms-schema}
  \par\vspace{4pt}
  {\footnotesize Fonte: Elaborado pelo autor (2026).}
\end{figure}

\begin{table}[H]
  \caption{Partes do arquivo de conexão.}
  \label{tab:partes-conexao}
  \centering
  \setlength{\tabcolsep}{4pt}
  \begin{tabular}{>{\raggedright\arraybackslash\ttfamily}p{3.5cm} >{\raggedright\arraybackslash}p{2.6cm} >{\raggedright\arraybackslash}p{4.6cm} >{\raggedright\arraybackslash}p{3.6cm}}
    \toprule
    \normalfont\textbf{Parte} & \textbf{Onde} & \textbf{Finalidade} & \textbf{Obrigatória?} \\
    \midrule
    version & raiz & versão do formato do arquivo (atualmente, 1) & sim \\
    postgres, mongodb, cassandra, redis, neo4j & raiz & dar acesso a um SGBD & não; só os SGBDs de destino \\
    connection & bloco de SGBD & parâmetros de acesso & sim \\
    schema & bloco PostgreSQL & schema de destino das tabelas & não; padrão: \texttt{public} \\
    start & bloco de SGBD & como iniciar o SGBD & não \\
    \bottomrule
  \end{tabular}
  \par\vspace{4pt}
  {\footnotesize Fonte: Elaborado pelo autor (2026).}
\end{table}

A Listagem~\ref{lst:conexao-exemplo} mostra o início do arquivo de conexão do cenário,
com os blocos do PostgreSQL e do MongoDB. As reticências marcam os descritores
\texttt{start}, tratados na Seção~\ref{sec:inicializacao-sgbds}, e os blocos dos demais
SGBDs; o arquivo completo está no Apêndice~\ref{ap:config}.

\begin{lstlisting}[style=jsonstyle,caption={Início do arquivo de conexão do cenário (\texttt{dbms\_config.json}).},label={lst:conexao-exemplo}]
{
  "version": 1,
  "postgres": {
    "connection": {
      "host": "127.0.0.1", "port": 5432,
      "database": "ecommerce",
      "user": "postgres", "password": "postgres"
    },
    "schema": "public",
    ...
  },
  "mongodb": {
    "connection": {
      "uri": "mongodb://127.0.0.1:27017",
      "database": "ecommerce"
    },
    ...
  },
  ...
}
\end{lstlisting}

\subsubsection{Raiz e blocos de SGBD}

A raiz exige o campo \texttt{version} e aceita um bloco por SGBD; como no arquivo de
importação, chaves desconhecidas são rejeitadas. Todo SGBD que aparece no arquivo de
importação precisa ter o seu bloco aqui; caso contrário, a importação é recusada antes de
começar (Seção~\ref{sec:validacao}). Cada bloco presente deve conter o descritor
\texttt{connection}.

\subsubsection{Parâmetros de conexão}

Os campos de \texttt{connection} dependem do SGBD, pois seguem os parâmetros do
\textit{driver} de cada um. A Tabela~\ref{tab:conexao-sgbd} lista esses campos, os
obrigatórios e os valores usados quando um campo opcional é omitido.

\begin{table}[H]
  \caption{Campos do descritor \texttt{connection} por SGBD.}
  \label{tab:conexao-sgbd}
  \centering
  \setlength{\tabcolsep}{4pt}
  \begin{tabular}{l >{\raggedright\arraybackslash\ttfamily}p{4.4cm} >{\raggedright\arraybackslash\ttfamily}p{2.8cm} >{\raggedright\arraybackslash}p{4.8cm}}
    \toprule
    \textbf{SGBD} & \normalfont\textbf{Campos} & \normalfont\textbf{Obrigatórios} & \textbf{Padrões} \\
    \midrule
    PostgreSQL & host, port, database, user, password & \normalfont --- & \texttt{127.0.0.1}, \texttt{5432}, \texttt{postgres}, \texttt{postgres}, senha vazia \\
    MongoDB & uri, database & uri, database & --- \\
    Cassandra & hosts, port, keyspace, protocol\_version, request\_timeout & hosts, keyspace & porta \texttt{9042}; \texttt{request\_timeout} de 30 s; protocolo negociado pelo \textit{driver} \\
    Redis & host, port, db, password & \normalfont --- & \texttt{127.0.0.1}, \texttt{6379}, \texttt{0}, sem senha \\
    Neo4j & uri, user, password, database & uri, user, password & \texttt{database}: o banco padrão do servidor \\
    \bottomrule
  \end{tabular}
  \par\vspace{4pt}
  {\footnotesize Fonte: Elaborado pelo autor (2026).}
\end{table}

No MongoDB e no Neo4j, o endereço é uma URI no formato do respectivo \textit{driver}
(\texttt{mongodb://\ldots} e \texttt{bolt://\ldots}), que pode incluir usuário e senha. No
Cassandra, \texttt{hosts} é uma lista, pois um \textit{cluster} pode ter vários nós, e
\texttt{request\_timeout} é o tempo máximo, em segundos, de cada requisição.

\subsubsection{Inicialização dos SGBDs}
\label{sec:inicializacao-sgbds}

O descritor \texttt{connection} diz \textit{onde} alcançar cada SGBD, mas não o que fazer
quando ele não responde. Para esse caso, cada bloco de SGBD aceita um descritor opcional
\texttt{start}, que registra \textit{como} iniciá-lo, em uma de duas formas mutuamente
exclusivas: \texttt{command}, uma linha de comando para um SGBD instalado na própria
máquina, ou \texttt{compose}, que indica um arquivo do Docker Compose e o serviço
correspondente. A ferramenta \textbf{nunca executa} esse comando: ela o exibe, pronto
para ser copiado para um terminal, quando a verificação descrita na
Seção~\ref{sec:verificacao-sgbds} encontra o SGBD fora do ar. A escolha é deliberada:
iniciar um serviço do sistema operacional costuma exigir privilégios de administrador,
que a ferramenta não tem nem deve pedir. A Listagem~\ref{lst:start-windows} mostra dois
blocos do arquivo de conexão de exemplo para Windows, um em cada forma.
```

Seguem, **sem alteração**, a listagem `lst:start-windows` e o parágrafo que começa em `Na listagem, o conteúdo dos descritores \texttt{connection}` e termina em `são exemplos a ajustar.` (copiar do arquivo atual).

- [ ] **Step 3: Corrigir a referência na §4.3**

Em `\subsection{A Importação em Cada SGBD}`, trocar `no arquivo de conexão (Listagem~\ref{lst:pg-conn}).` por `no arquivo de conexão (Listagem~\ref{lst:conexao-exemplo}).`

- [ ] **Step 4: Ajustar a abertura do Apêndice A**

Em `docs-tcc/chapters/apendiceschemas.tex`, trocar

```latex
de ambos é descrita na seção~\ref{sec:config-format}; os fragmentos por SGBD são
apresentados nas respectivas subseções do capítulo~4.
```

por

```latex
de ambos é descrita nas seções~\ref{sec:arquivo-importacao} e~\ref{sec:arquivo-conexao}.
```

- [ ] **Step 5: Conferir rótulos removidos**

Run: `grep -n "lst:pg-conn\|lst:mongo-conn\|lst:cassandra-conn\|lst:redis-conn\|lst:neo4j-conn" docs-tcc/chapters/*.tex`
Expected: nada.

- [ ] **Step 6: Compilar**

Run: `cd docs-tcc && latexmk -pdf -interaction=nonstopmode main.tex; grep -c "undefined" main.log; cd ..`
Expected: compila; contagem 0.

- [ ] **Step 7: Commit e push**

```bash
git add docs-tcc/chapters/ch4proposta.tex docs-tcc/chapters/apendiceschemas.tex
git commit -m "docs(tcc): particularidades por SGBD e arquivo de conexao separados

O arquivo de importacao por SGBD e o arquivo de conexao passam a ter
subsecoes proprias; uma tabela com campos obrigatorios e padroes substitui
as cinco listagens de conexao.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```

---

### Task 6: Verificação visual e relatório v2.3

**Files:**
- Create: `docs-tcc/TCC2-PolyglotImportCSV-Report-v2.3.pdf`

- [ ] **Step 1: Compilação limpa**

Run: `cd docs-tcc && latexmk -pdf -interaction=nonstopmode main.tex; grep -c "undefined" main.log; grep -c "Overfull \\\\hbox" main.log; cd ..`
Expected: `undefined` = 0. Para os `Overfull`, olhar só os que o log atribui a `ch4proposta.tex` na faixa da §4.1 à §4.2.4 e corrigir os que forem visíveis no PDF (texto invadindo a margem).

- [ ] **Step 2: Localizar as páginas**

```bash
./.venv/Scripts/python.exe -c "
import pymupdf
d=pymupdf.open('docs-tcc/main.pdf')
for i,p in enumerate(d):
    t=p.get_text()
    for k in ['4.1 VISÃO GERAL','Formato de Configuração','O Arquivo de Importação','Particularidades de Cada SGBD','O Arquivo de Conexão','Validação, Consistência']:
        if k.lower() in t.lower(): print(i+1,k)
print(len(d))"
```

- [ ] **Step 3: Ler as páginas renderizadas**

Abrir com a ferramenta Read (`pages`) da §4.1 até o início da §4.2.4. Conferir, item por item:
1. Ordem: §4.2 abertura (cenário + Tabela de eventos + roteiro) → §4.2.1 (Fig. 8, tabela de partes, trecho raiz→colunas, raiz/`sources`, blocos, entidade, colunas) → §4.2.2 → §4.2.3 (Fig. 9, tabela de partes, exemplo, raiz, parâmetros, inicialização) → §4.2.4.
2. Cada parte tem exemplo JSON logo no início.
3. Legendas: tabelas acima, figuras abaixo, "Fonte:" abaixo.
4. Toda listagem tem frase de introdução que a nomeia.
5. Tabelas novas (`tab:eventos-ecommerce`, `tab:partes-importacao`, `tab:partes-conexao`, `tab:conexao-sgbd`) cabem na largura e não têm linhas sobrepostas.
6. Mapa anotação→resposta da spec: cada linha atendida (comando com `[--dbms-config ...]`, sem "argumento posicional", sem "são facultativas e", cenário antes dos termos `stock`/`purchase`…, "coincidir/divergir" substituído pelo exemplo de três entradas, `columns` omitido explicado).

Corrigir no `.tex` o que falhar, recompilar e reler as páginas afetadas.

- [ ] **Step 4: Rodar a suíte uma última vez**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: tudo passa.

- [ ] **Step 5: Gerar a v2.3, commit e push**

```bash
cp docs-tcc/main.pdf docs-tcc/TCC2-PolyglotImportCSV-Report-v2.3.pdf
git add docs-tcc/TCC2-PolyglotImportCSV-Report-v2.3.pdf docs-tcc/chapters/ch4proposta.tex
git commit -m "docs(tcc): relatorio v2.3 com a revisao do capitulo da Proposta

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```

(Se o Step 3 não alterou o `.tex`, o `git add` dele é inócuo.)
