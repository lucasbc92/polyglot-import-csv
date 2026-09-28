# Benchmark reference dataset

**Language / Idioma / Língua:** [English](#english) · [Português (BR)](#português-br)

## English

Small, **versioned** synthetic e-commerce dataset for fast tests, CI, and the
mode-equivalence check. Generated deterministically with:

    python scripts/generate_benchmark_data.py --rows 1000 --seed 42 --out data/benchmark --mode both

`--rows` is the **total row count** across all sources; it is split ~1:3:2:2
(stock:purchase:select:cart) with slight seeded jitter that sums to exactly the
total. At `--rows 1000 --seed 42` the split is:

| File | Rows | Notes |
|---|---|---|
| `ecommerce_stock.csv` | 116 | one row per product (`product_id` 1..116) |
| `ecommerce_purchase.csv` | 389 | orders (~3×); FKs reference the product/user pools |
| `ecommerce_select_product.csv` | 254 | selection events (~2×) |
| `ecommerce_add_to_cart.csv` | 241 | cart events (~2×) |
| `ecommerce_join.csv` | 1 000 | combined format (origin column 0); same data as the four above |

Headers are byte-identical to the real `data/ecommerce/` CSVs, so
`import_config.json` and `import_config_combined.json` run unchanged over this
data via `--source NAME=PATH`.

Large sizes (10k, 100k, 1M) are generated on demand into
`data/benchmark/generated/` (git-ignored) by `scripts/run_benchmarks.py`.

## Português (BR)

Dataset e-commerce sintético pequeno e **versionado**, para testes rápidos, CI e
a verificação de equivalência entre modos. Gerado de forma determinística com:

    python scripts/generate_benchmark_data.py --rows 1000 --seed 42 --out data/benchmark --mode both

`--rows` é o **total de linhas** somando todas as fontes; ele é dividido
~1:3:2:2 (stock:purchase:select:cart) com um leve jitter seedado que soma
exatamente o total. Com `--rows 1000 --seed 42` a divisão é:

| Arquivo | Linhas | Observações |
|---|---|---|
| `ecommerce_stock.csv` | 116 | uma linha por produto (`product_id` 1..116) |
| `ecommerce_purchase.csv` | 389 | pedidos (~3×); as FKs referenciam os conjuntos de produtos/usuários |
| `ecommerce_select_product.csv` | 254 | eventos de seleção (~2×) |
| `ecommerce_add_to_cart.csv` | 241 | eventos de carrinho (~2×) |
| `ecommerce_join.csv` | 1 000 | formato combinado (coluna de origem 0); mesmos dados dos quatro acima |

Os cabeçalhos são idênticos, byte a byte, aos CSVs reais de `data/ecommerce/`,
então `import_config.json` e `import_config_combined.json` rodam sem alterações
sobre esses dados via `--source NOME=CAMINHO`.

Os tamanhos maiores (10k, 100k, 1M) são gerados sob demanda em
`data/benchmark/generated/` (ignorado pelo git) por `scripts/run_benchmarks.py`.
