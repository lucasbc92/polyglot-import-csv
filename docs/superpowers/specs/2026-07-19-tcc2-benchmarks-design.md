# Design — TCC2: geradores de dataset e runner de benchmark (Plano 3)

Data: 2026-07-19
Status: aprovado em brainstorming; aguardando revisão final do autor.

Refina a §5 do design aprovado `docs/superpowers/specs/2026-07-08-tcc2-import-modes-design.md`,
resolvendo os pontos que lá ficaram em nível alto: modelo de dados sintético e
integridade referencial, determinismo do gerador, orquestração do runner sobre
bancos vivos, dataset de referência versionado e integração com CI/testes.

## 1. Contexto e objetivo

Os Planos 1 (config v2 + pipeline) e 2 (logs rich + métricas) estão concluídos e
integrados em `main`. O Plano 2 deixou pronto o seam de medição: `run_import(...,
collector: Optional[MetricsCollector] = None)` — quando um coletor é injetado, todas
as fases (leitura, filtro, mapeamento, escrita) por SGBD × entidade são registradas
nele. O Plano 3 usa esse seam para:

1. **Gerar datasets sintéticos** de e-commerce em tamanhos variados, nos dois modos de
   entrada (multi-CSV por entidade e combinado com coluna de origem), de forma
   determinística por semente.
2. **Executar benchmarks** de importação sobre bancos vivos, com repetições e mediana,
   consolidando os resultados para os gráficos do relatório.

Comparar os dois modos de entrada é, ele próprio, um experimento do TCC2, então o
gerador produz ambos a partir da mesma fonte de dados sintética.

## 2. Modelo de dados sintético

### 2.1 Fidelidade de esquema

O gerador emite CSVs com **cabeçalhos idênticos** aos dos CSVs reais em
`data/ecommerce/` (mesmo conjunto de colunas, mesma ordem). Consequência: os configs
já versionados (`import_config.json`, `import_config_combined.json`) rodam sem
alteração sobre dados gerados, via os overrides `--source NOME=CAMINHO` da CLI. O CSV
combinado replica o cabeçalho de `ecommerce_join.csv` (união das colunas das quatro
fontes, com a coluna de origem na posição 0).

As quatro fontes por entidade e suas colunas (conforme os CSVs reais):

- **stock** (`ecommerce_stock.csv`): `timestamp, user_id, user_name, user_email,
  street, neighborhood, state, country, zip_code, product_id, product_name,
  product_variant, product_brand, product_description, product_image, category_id,
  category_name, quantity_available, price, last_restock_date`.
- **purchase** (`ecommerce_purchase.csv`): `timestamp, user_id, user_name, user_email,
  street, neighborhood, state, country, zip_code, order_number, order_date,
  order_status, traded_with, trader_street, trader_neighborhood, trader_state,
  trader_country, trader_zip_code, comment, rating, payment_method, quantity,
  product_id, product_name, product_variant, product_brand, product_description,
  product_image, category_id, category_name, quantity_available, price,
  last_restock_date`.
- **select_product** (`ecommerce_select_product.csv`): `timestamp, user_id, user_name,
  user_email, selected_product_id, suggested_product_count`.
- **add_to_cart** (`ecommerce_add_to_cart.csv`): `timestamp, user_id, user_name,
  user_email, shopping_cart_id, cart_product_id, cart_quantity`.

O combinado (`ecommerce_join.csv`): coluna 0 `action` (valor = nome da fonte:
`stock`/`purchase`/`select_product`/`add_to_cart`) seguida da união de todas as
colunas acima; células ausentes para uma dada origem ficam vazias.

### 2.2 Escala e cardinalidades

O parâmetro `--rows N` ancora o **catálogo**: N = número de produtos. As demais
entidades escalam por razões fixas realistas (muito mais transações que produtos):

| Fonte | Linhas | Observação |
|---|---|---|
| stock | N | um produto por linha, `product_id` = 1..N |
| purchase | 3N | pedidos; `order_number` único |
| select_product | 2N | eventos de seleção |
| add_to_cart | 2N | eventos de carrinho |

Total ≈ 8N linhas. Pools compartilhados dimensionados a partir de N:

- **categorias**: `num_categories = max(1, N // 100)` — `category_id` = 1..num_categories.
- **usuários**: `num_users = max(1, N // 10)` — cada usuário tem `user_id` (UUID
  derivado da semente), `user_name`, `user_email` e um endereço fixo por usuário.

### 2.3 Integridade referencial

Todas as chaves estrangeiras são amostradas dos pools já gerados, garantindo
resolução:

- `stock.product_id` = 1..N (único, sequencial); `stock.category_id` ∈ pool de
  categorias; `stock.user_id` ∈ pool de usuários.
- `purchase.product_id` ∈ 1..N; `purchase.user_id` ∈ pool; `purchase.price`,
  `product_name`, `product_brand` etc. **herdados do produto referenciado** (consistência
  produto↔preço, como nos dados reais); `order_number` = `ORD{i}` único.
- `select_product.selected_product_id` ∈ 1..N; `user_id` ∈ pool.
- `add_to_cart.cart_product_id` ∈ 1..N; `user_id` ∈ pool; `shopping_cart_id` =
  `user:{user_id}:cart` (como no CSV real).

Consequência verificável em teste: todo `product_id`/`category_id`/`user_id`
referenciado numa fonte existe na fonte que o define.

### 2.4 Determinismo

Único gerador de aleatoriedade: `random.Random(seed)` da biblioteca padrão. Sem
`numpy` (nenhuma dependência nova). Escrita **streaming** linha a linha via o módulo
`csv` — não materializa o dataset inteiro em memória, viabilizando 1M+ linhas. Mesma
`(N, seed)` produz arquivos **byte-idênticos** em qualquer plataforma (quebra de linha
fixada explicitamente para não divergir entre SO).

### 2.5 CLI do gerador

`scripts/generate_benchmark_data.py`:

- `--rows N` (obrigatório) — número de produtos.
- `--seed S` (default fixo, ex. `42`) — semente.
- `--out DIR` (obrigatório) — diretório de saída.
- `--mode both|multi|combined` (default `both`) — quais formatos gerar.

Saída (nomes iguais aos reais): `ecommerce_stock.csv`, `ecommerce_purchase.csv`,
`ecommerce_select_product.csv`, `ecommerce_add_to_cart.csv` (modo multi) e/ou
`ecommerce_join.csv` (modo combinado).

## 3. Runner de benchmark

### 3.1 Arquitetura

`scripts/run_benchmarks.py`: orquestrador **Python puro**. Assume os bancos já no ar —
subir/derrubar o Docker é pré-requisito documentado (`docker compose up --wait`, ou
`run_example.sh`). Reusa, sem duplicar lógica:

- `polyglotimportcsv.runner.run_import(config, sgbd_config_path=..., collector=...,
  show_data=False, ...)` para importar e medir;
- os limpadores por backend de `scripts/inspect_persisted_data.py` (dispatch
  `CLEANERS[backend](sgbd_cfg)`), para esvaziar cada backend antes de cada repetição
  (medição "a frio").

### 3.2 Laço de execução

```
para cada size em --sizes:
  garantir dataset (gerar em data/benchmark/generated/<size>/ se ausente)
  para cada mode em --modes (multi, combined):
    escolher config (import_config.json vs import_config_combined.json)
    montar overrides --source apontando para os CSVs gerados
    para cada rep em range(--repetitions):
      para cada backend selecionado:
        CLEANERS[backend](sgbd_cfg)            # esvazia
      collector = MetricsCollector()
      run_import(config, sgbd_config_path, collector=collector,
                 only=backends, show_data=False, create_schema=True)
      guardar collector.to_records() rotulado com (size, mode, rep)
    consolidar: mediana de `seconds` por (backend, entidade, fase) entre as R repetições
```

Observações:

- **Uma importação por repetição** cobre todos os backends selecionados (o `run_import`
  já itera os SGBDs); o `clean` de todos os backends acontece antes de cada importação.
- **Mediana**: para cada chave `(backend, entity, phase)`, a mediana de `seconds` entre
  as R repetições; `rows` é constante entre repetições (mesmo dataset), e `rows_per_second`
  é recomputado a partir da mediana de `seconds`.

### 3.3 CLI do runner

- `--sizes 1000,10000,100000` — lista de N (produtos). 1M é opcional/pesado, não default.
- `--modes multi,combined` (default ambos).
- `--repetitions 3` (default).
- `--only postgres,redis,...` — restringe backends (repassado ao `run_import`).
- `--seed S` — semente do gerador.
- `--sgbd-config PATH` (default `data/ecommerce/sgbd_config.json`).
- `--data-dir DIR` (default `data/benchmark/generated`) — onde gerar/achar os grandes.
- `--out DIR` (default `benchmarks/`) — saída dos consolidados.

### 3.4 Saída consolidada

Dois artefatos em `--out`, reaproveitando o formato do Plano 2 quando possível:

- **JSON** `benchmark_run_<timestamp>.json`: `{ "metadata": {...ambiente, seed, sizes,
  modes, repetitions...}, "results": [ {size, mode, backend, entity, phase, rows,
  median_seconds, rows_per_second} ] }`.
- **CSV** consolidável `benchmark_results.csv` (append-only, cabeçalho na criação):
  `timestamp,size,mode,backend,entity,phase,rows,median_seconds,rows_per_second` —
  base direta para os gráficos do relatório (size × modo × SGBD × fase).

`metadata` inclui versão do Python, plataforma, semente, e a lista de tamanhos/modos/
repetições — reaproveitando `metrics.environment_metadata` como ponto de partida.

## 4. Dataset de referência versionado

- `data/benchmark/`: gerado com semente fixa (`42`) e **N=125 produtos (1k linhas
  totais: 125 stock + 375 purchase + 250 select + 250 cart)**, **ambos os modos**,
  commitado no repositório.
- Usos: teste de **equivalência de modos** (dry-run multi vs combinado → contagens por
  entidade idênticas, resultado citável), smoke do gerador e testes rápidos/CI sem
  bancos.
- `.gitignore`: acrescenta `data/benchmark/generated/` (os tamanhos grandes ficam fora
  do versionamento).

## 5. Testes

Unitários (sem bancos, entram na suíte de CI):

- **Determinismo**: gerar duas vezes com a mesma `(N, seed)` → arquivos byte-idênticos;
  sementes diferentes → conteúdo diferente.
- **Integridade referencial**: para um N pequeno, todo `product_id`/`category_id`/
  `user_id` referenciado resolve na fonte que o define; `order_number` único;
  `product_id` de stock = 1..N.
- **Cardinalidades**: contagens de linhas por fonte seguem N, 3N, 2N, 2N.
- **Cabeçalhos**: os CSVs gerados têm cabeçalho idêntico aos reais de `data/ecommerce/`
  (comparação de header).
- **Equivalência de modos**: `run_import` dry-run sobre o dataset versionado, em multi e
  combinado, produz contagens por entidade idênticas.
- **Mediana do runner**: a função de agregação, alimentada por coletores stub (sem DB),
  devolve a mediana correta por `(backend, entity, phase)`.
- **Smoke do gerador**: dry-run de `run_import` sobre o dataset versionado gerado
  (1k linhas) executa sem erro.

Fora do CI (rodados à mão, exigem bancos vivos e são lentos): as execuções reais de
`run_benchmarks.py`. Consistente com os testes de importer atuais, que são dry-run.

## 6. Documentação

- `README.md` (raiz): seção "Benchmarks" — como gerar datasets (`generate_benchmark_data.py`)
  e como rodar o runner (`run_benchmarks.py`), incluindo o pré-requisito de subir os
  bancos. EN + PT.
- `data/benchmark/README.md`: descreve o dataset de referência versionado, a semente e as
  cardinalidades.
- Capítulos novos do relatório TCC2 ficam fora deste escopo (serão escritos depois, com os
  resultados consolidados).

## 7. Fora de escopo

Gerência de ciclo do Docker pelo runner (fica com o usuário / `run_example.sh`); novos
conectores; formatos além de CSV; execução de benchmarks em CI; interface gráfica.
