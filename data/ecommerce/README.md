# E-commerce example data

**Language / Idioma / Língua:** [English](#english) · [Português (BR)](#português-br)

## English

| File | Purpose |
|------|---------|
| `ecommerce_stock.csv`, `ecommerce_purchase.csv`, `ecommerce_select_product.csv`, `ecommerce_add_to_cart.csv` | One CSV per entity (default input mode). Each file IS the origin of its rows — no discriminator column needed. |
| `ecommerce_join.csv` | Combined CSV (alternative input mode): column 0 (`action`) is the origin column; each distinct value becomes a source. |
| `import_config.json` | v2 mapping config (multi-CSV `sources`). Default for `./run_example.sh`. |
| `import_config_combined.json` | Same DBMS blocks, `sources` pointing at the combined CSV — demonstrates that switching input modes changes nothing in the per-DBMS mapping. |
| `import_config_invalido.json` | A deliberately invalid config (its `stock` source is a number), to see the validation at work. |
| `dbms_config.json` | Connection settings per DBMS; its `start` blocks point at the Docker Compose services of `../../docker-compose.yml`. Default when `--dbms-config` is omitted. |
| `dbms_config_windows.json` | Same connections; `start` holds Windows service commands (`net start …`). Cassandra, which does not run natively on Windows, keeps the Docker Compose service. |
| `dbms_config_linux.json` | Same connections; `start` holds `sudo systemctl start …` commands. |

The `start` blocks are only shown, never run, when `--check-dbms` (or the check
that precedes every real import) finds a DBMS down. Service names vary between
installations: adjust them to yours.

### Knowing each row's origin

Knowing the **source (entity) of every row** is an essential requirement of the
import process. In the per-entity files the file itself designates the origin.
In the combined `ecommerce_join.csv`, column 0 plays that role: the importer
slices the file by its distinct values and each value becomes a named source
(also exposed to mappings as the `_source` pseudo-column).

For a larger stress test, add another CSV (e.g. `ecommerce_stock_large.csv`) and
override just that source's path:

```bash
python -m polyglotimportcsv --config data/ecommerce/import_config.json \
  --source stock=data/ecommerce/ecommerce_stock_large.csv \
  --dry-run
```

The config must reference columns present in that CSV.

## Português (BR)

| Arquivo | Finalidade |
|---------|------------|
| `ecommerce_stock.csv`, `ecommerce_purchase.csv`, `ecommerce_select_product.csv`, `ecommerce_add_to_cart.csv` | Um CSV por entidade (modo de entrada padrão). Cada arquivo É a origem das suas linhas — não há coluna discriminadora. |
| `ecommerce_join.csv` | CSV combinado (modo alternativo): a coluna 0 (`action`) é a coluna de origem; cada valor distinto vira uma fonte. |
| `import_config.json` | Configuração de mapeamento v2 (`sources` com vários CSVs). Padrão do `./run_example.sh`. |
| `import_config_combined.json` | Os mesmos blocos por SGBD, com `sources` apontando o CSV combinado — mostra que trocar o modo de entrada não muda nada no mapeamento de cada SGBD. |
| `import_config_invalido.json` | Uma configuração inválida de propósito (a fonte `stock` é um número), para ver a validação em ação. |
| `dbms_config.json` | Conexão com cada SGBD; os blocos `start` apontam os serviços do Docker Compose de `../../docker-compose.yml`. É o padrão quando `--dbms-config` é omitido. |
| `dbms_config_windows.json` | As mesmas conexões; `start` traz comandos de serviço do Windows (`net start …`). O Cassandra, que não roda nativamente no Windows, mantém o serviço do Docker Compose. |
| `dbms_config_linux.json` | As mesmas conexões; `start` traz comandos `sudo systemctl start …`. |

Os blocos `start` são só exibidos, nunca executados, quando o `--check-dbms` (ou
a verificação que antecede toda importação real) encontra um SGBD fora do ar.
Os nomes de serviço variam de uma instalação para outra: ajuste-os à sua.

### A origem de cada linha

Saber a **fonte (entidade) de cada linha** é um requisito essencial da
importação. Nos arquivos por entidade, o próprio arquivo designa a origem. No
`ecommerce_join.csv` combinado, a coluna 0 faz esse papel: o importador fatia o
arquivo pelos seus valores distintos e cada valor vira uma fonte nomeada
(também exposta aos mapeamentos como a pseudocoluna `_source`).

Para um teste maior, acrescente outro CSV (por exemplo,
`ecommerce_stock_large.csv`) e sobrescreva só o caminho daquela fonte:

```bash
python -m polyglotimportcsv --config data/ecommerce/import_config.json \
  --source stock=data/ecommerce/ecommerce_stock_large.csv \
  --dry-run
```

A configuração precisa referenciar colunas presentes nesse CSV.
