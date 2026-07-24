# Design — TCC2: desempenho de importação (estratégias ingênua e otimizada)

Data: 2026-07-24
Status: aprovado em brainstorming; aguardando revisão final do autor.

Sucede o Plano 3 (`docs/superpowers/specs/2026-07-19-tcc2-benchmarks-design.md`), que
entregou o gerador de datasets e o runner de matriz. A primeira matriz completa
(1k e 10k, `benchmark.log`, 12 execuções) revelou que os números medidos descrevem
sobretudo o laço Python do cliente, não os SGBDs. Este design corrige as causas e,
ao mesmo tempo, transforma a correção em variável experimental do TCC2.

## 1. Contexto: o que a primeira matriz mediu

Vazão mediana por fase, extraída de `benchmark.log` (12 execuções, 1k e 10k):

| SGBD | chamada de escrita | linhas/s (mediana) |
|---|---|---|
| mongodb | `insert_many` (uma chamada) | 20.184 |
| postgres | `execute_values`, lotes de 500 | 8.101 |
| redis | `r.set()` **por linha** | 507 |
| cassandra | `session.execute()` **por linha** | 257 |
| neo4j | `session.run()` **por linha**, autocommit | 93 |

A ordenação coincide exatamente com a divisão entre importadores que agrupam
escritas e importadores que não agrupam. Não é uma propriedade dos bancos.

Três defeitos distintos sustentam esses números.

### 1.1 Conversão de tipos célula a célula (fase `map`, todos os SGBDs)

`casting.cast_frame` percorre cada célula e `casting.cast_value` chama
`pd.to_datetime()` por escalar. Medição sobre o arquivo real
`data/benchmark/generated/10000/ecommerce_stock.csv` (20 colunas, 2 delas datetime):

```
cast_frame (célula a célula):  34,44 s para 10.000 linhas  ->    290 linhas/s
somente datetime, vetorizado:   0,067 s                    ->  517x mais rápido
```

O custo é cobrado do primeiro backend que vincula cada fonte, porque
`runner._run` compartilha `cast_cache` entre backends (`runner.py:136`). Daí a
fase `map` do MongoDB aparecer com 7,5 M linhas/s: é acerto de cache, não
velocidade. Extrapolando para 100k, a fase `map` do Postgres sozinha responde por
~98 dos ~104 minutos estimados da execução — a conversão custa mais que todas as
escritas somadas.

### 1.2 Escrita linha a linha (cassandra, redis, neo4j)

- `redis_importer.py:65-70`: `for _, row in part_df.iterrows(): r.set(k, v)`.
- `cassandra_importer.py:173-183`: `session.execute(prep, values)` por linha,
  síncrono, um round trip cada.
- `neo4j_importer.py:102-114` e `154-170`: `session.run()` por linha em
  autocommit — uma transação por nó e por relacionamento.

Agrava o caso do Neo4j a ausência de índice: sem constraint de unicidade, todo
`MERGE` e todo `MATCH (a {id: $a_id})` faz varredura de label. O custo cresce com
o número de nós já inseridos, de modo que 100k não é apenas lento, é inviável.
`run_neo4j_import` inclusive descarta o parâmetro `create_schema`
(`neo4j_importer.py:41`), então hoje não há onde a constraint ser criada.

Custo secundário, na mesma classe: `materialize.redis_payload_from_row` e
`neo4j_importer.props_from_row` recalculam `flat_leaf_columns()` e
`list(row.index)` a cada linha.

### 1.3 Fronteiras de fase inconsistentes (validade da medição)

Em `mongodb_importer.py:57` os documentos são construídos **antes** de
`metrics.timed_phase` abrir (linha 63). Cassandra, Redis e Neo4j constroem seus
payloads **dentro** do cronômetro. A fase `write` do MongoDB portanto exclui um
trabalho pelo qual os outros são cobrados, e o SGBD que hoje lidera o ranking é
justamente o que tem a fronteira mais favorável. Os 20.184 linhas/s não são
comparáveis aos demais.

Este é um defeito de instrumentação, independente de agrupamento de escritas, e
invalida a comparação entre SGBDs que o TCC2 pretende publicar.

## 2. Objetivo

1. Corrigir os três defeitos, de modo que a matriz meça os SGBDs.
2. Preservar a implementação ingênua como caminho selecionável, para que a
   comparação ingênua × otimizada seja um resultado do TCC2 sobre dados idênticos,
   e não uma correção silenciosa.

## 3. Arquitetura

### 3.1 Eixo de estratégia

Um único parâmetro `strategy: str = "optimized"` atravessa
`runner.run_import` → cada importador, e também `casting.cast_frame`. Os valores
são `"naive"` e `"optimized"`.

`"naive"` seleciona verbatim os caminhos de código atuais — conversão célula a
célula e escrita linha a linha — de forma que `benchmark.log` continue
reproduzível fim a fim a partir de qualquer commit posterior.

Um eixo único (e não dois eixos independentes para conversão e escrita) mantém a
matriz em 2×, e ainda assim atribui o ganho a cada defeito separadamente: as
métricas já são registradas **por fase**, então Δ`map` isola a conversão e
Δ`write` isola o agrupamento.

### 3.2 Onde vive a lógica de escrita

Dentro de cada importador, o laço de escrita é dividido em duas funções de
módulo, `_write_naive(...)` e `_write_batched(...)`, escolhidas pela estratégia.
Cada importador ganha um parâmetro opcional de fábrica de cliente, com o driver
real como padrão:

```python
def run_redis_import(backend_cfg, entities, *, dry_run, create_schema,
                     strategy="optimized", client_factory=_default_client):
```

Motivação: hoje **nenhum teste executa o caminho de escrita** — toda a suíte é
dry-run, e é exatamente por isso que estes defeitos sobreviveram. A fábrica
injetável é a menor mudança que torna a escrita testável sem bancos vivos, e
preserva a forma e o layout de arquivos que o Capítulo 4 do TCC já documenta.

Alternativas descartadas: classes `Writer` por backend em `importers/writers/`
(separação mais limpa, mas reestrutura os cinco importadores e obriga a reescrever
o Capítulo 4); e monkeypatch dos módulos de driver nos testes (zero mudança em
produção, mas o seam fica implícito e os testes passam a depender do nome do
atributo de import).

## 4. Correções

### 4.1 `cast_frame` vetorizado

Por coluna, conforme o kind inferido:

- `datetime`: `pd.to_datetime(col, utc=True, errors="coerce").dt.to_pydatetime()`
- `integer` / `float`: `pd.to_numeric(col, errors="coerce")`
- `boolean`: `col.str.strip().str.lower().eq("true")`

**Vazios tratados antes da conversão, não depois.** Em todos os kinds, as células
vazias (`""` e `None`) são mascaradas antes e reinjetadas como `None` ao final —
elas não podem passar pelo conversor. Sem isso os três caminhos divergem do
comportamento atual: `NaT` e `NaN` não são `None`, e `eq("true")` mapearia vazio
para `False` em vez de `None`. A máscara de vazios é a mesma para os três, o que
mantém o tratamento uniforme e verificável em teste.

**Semântica de fallback preservada.** `cast_value` devolve hoje a *string
original* quando a conversão falha, e `cast_frame` conta essas ocorrências para
emitir um aviso. `pd.to_numeric(errors="coerce")` produz NaN, então uma
vetorização ingênua transformaria valores inconversíveis em nulos — perda
silenciosa de dados. A implementação usa `.where(parsed.notna(), original)`
explicitamente e mantém a contagem para o aviso.

Contratos já fixados por `tests/test_casting.py` que continuam valendo: células
vazias viram `None`; inteiros são `int` nativo, nunca `float`; datetimes são
`datetime.datetime`, nunca `pandas.Timestamp`; colunas string ficam intocadas,
inclusive `""`.

### 4.2 Cassandra

`cassandra.concurrent.execute_concurrent_with_args(session, prepared, params,
concurrency=64)` no lugar do `session.execute` por linha. A lista de parâmetros é
montada por coluna, não via `iterrows()`.

### 4.3 Redis

`client.pipeline(transaction=False)`, descarregado a cada 1000 chaves. As chamadas
a `flat_leaf_columns()` e `resolve_csv_column()` saem do laço por linha e passam a
ser calculadas uma vez por entidade.

### 4.4 Neo4j

Três partes:

1. **Constraint de unicidade** sob `create_schema` (parâmetro hoje descartado):
   `CREATE CONSTRAINT ... IF NOT EXISTS FOR (n:Label) REQUIRE n.<key> IS UNIQUE`.
   Sem ela, `MERGE` e `MATCH` fazem varredura de label.
2. **Nós em lote**: `UNWIND $batch AS row MERGE (n:Label {key: row.k}) SET n += row.props`,
   em transações `execute_write` de 1000 linhas.
3. **Relacionamentos em lote**: mesmo formato `UNWIND`, com o `MATCH` das pontas
   agora resolvido por índice.

**Deduplicação primeiro-vence preservada.** O caminho atual mantém um conjunto
`seen` e ignora chaves repetidas, registrando quantas foram puladas. `UNWIND` +
`MERGE` faria a última linha vencer, então a deduplicação acontece antes do
agrupamento, mantendo o comportamento e a contagem do aviso.

### 4.5 Fronteiras de fase consistentes

A construção de payload do MongoDB passa para dentro do cronômetro `write`, de
modo que os cinco backends meçam o mesmo intervalo: transformar as linhas
vinculadas em payload do driver, mais a escrita. O número do MongoDB vai **piorar**
e ficar honesto.

### 4.6 Postgres e MongoDB

Nenhuma mudança no caminho de escrita: `execute_values` e `insert_many` já
agrupam. Para esses dois, `--strategy naive` afeta apenas a fase `map`.

## 5. Métricas e saída consolidada

- `benchmark_results.median_results`: `strategy` entra na chave de agrupamento.
- `_RESULT_FIELDS`: `strategy` entra logo após `mode`.
- `benchmark_runner.run_matrix`: novo parâmetro `strategies`; o laço passa a ser
  tamanhos × modos × **estratégias** × repetições.

**Guarda de esquema do CSV.** `benchmark_io.write_json_and_csv` escreve cabeçalho
apenas quando o arquivo é novo (`benchmark_io.py:43`). Como
`benchmarks/benchmark_results.csv` já existe com 9 colunas, acrescentar `strategy`
faria linhas de 10 valores serem anexadas sob um cabeçalho de 9 — corrupção
silenciosa. A função passa a validar o cabeçalho existente contra `csv_fields` e a
falhar com erro explícito nomeando o arquivo. O arquivo atual é renomeado para
`benchmark_results_naive_baseline.csv`, preservando as 12 execuções já medidas sob
um nome que diz o que elas são.

Observação: `benchmarks/benchmark_checkpoint.json` ainda está em disco, o que
indica que a última matriz abortou antes de consolidar — foi a execução
interrompida pelo erro de tipo no Postgres, já corrigido em `csv_reader.py`.

## 6. CLI

- `scripts/run_benchmarks.py`: `--strategies optimized` (lista separada por
  vírgula; `naive,optimized` roda as duas).
- `scripts/run_benchmarks_100k.py`: `MEASURED_ROWS_PER_S` re-derivado da
  reexecução pós-correção de 1k/10k, em vez de estimado; o aviso "um round trip
  por linha" passa a ser condicionado a `--strategies naive`.
- `src/polyglotimportcsv/cli.py`: flag `--strategy` correspondente, para que uma
  importação comum use qualquer um dos caminhos.

## 7. Testes

Todos sem bancos vivos, na suíte de CI.

- **`tests/test_importer_write_batching.py`** (novo): um cliente falso por backend,
  afirmando as duas direções — `optimized` emite ⌈n/lote⌉ chamadas em bloco e zero
  chamadas por linha; `naive` emite n chamadas por linha. É a primeira cobertura
  que o caminho de escrita recebe.
- **`tests/test_casting_vectorized.py`** (novo): equivalência célula a célula entre
  os dois caminhos sobre um fixture que cobre os seis kinds, incluindo valores
  inconversíveis e a contagem do aviso.
- **Neo4j**: a constraint é emitida sob `create_schema`; a deduplicação
  primeiro-vence sobrevive ao agrupamento.
- **Fronteiras de fase**: teste fixando que os cinco backends constroem payload
  dentro do cronômetro `write`.
- **`tests/test_benchmark_runner.py`**: atualizado para o eixo `strategies`.
- **`benchmark_io`**: cabeçalho incompatível falha com erro explícito em vez de
  anexar.

## 8. Validação

Reexecutar a matriz de 1k e 10k sob as duas estratégias antes de qualquer coisa:
valida os ganhos e produz a tabela antes/depois do TCC2. Só então executar 100k
com `optimized`.

## 9. Fora de escopo

- **`COPY` no Postgres**: mais rápido que `execute_values`, mas não expressa
  `ON CONFLICT DO NOTHING`, o que mudaria a semântica de deduplicação.
- **Paralelizar backends**: destruiria o isolamento das medições por SGBD.
- **`clean_postgres` com TRUNCATE em vez de DROP**
  (`scripts/inspect_persisted_data.py:252`): questão separada, já registrada.
- Novos conectores, formatos além de CSV, interface gráfica.
