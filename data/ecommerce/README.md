# E-commerce example data

**Language / Idioma / Língua:** [English](#english) · [Português (BR)](#português-br)

## English

| File | Purpose |
|------|---------|
| `ecommerce_stock.csv`, `ecommerce_purchase.csv`, `ecommerce_select_product.csv`, `ecommerce_add_to_cart.csv` | One CSV per entity (default input mode). Each file IS the origin of its rows — no discriminator column needed. |
| `ecommerce_join.csv` | Combined CSV (alternative input mode): column 0 (`action`) is the origin column; each distinct value becomes a source. |
| `import_config.json` | v2 mapping config (multi-CSV `sources`). Default for `./run_example.sh`. |
| `import_config_combined.json` | Same DBMS blocks, `sources` pointing at the combined CSV — demonstrates that switching input modes changes nothing in the per-DBMS mapping. |
| `import_config_invalido.json` | A deliberately invalid config (its `stock` source is a number), to see the validation at work: the JSON Schema layer refuses it, with exit code 1, before any data is read or written. |
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

The config must reference columns present in that CSV. The dry-run reads the whole
file, in two reads (inference and validation) and in chunks, so it checks the data of
a large file without connecting to any DBMS. In a real import, `--chunk-size` (memory
of each read chunk, 8 to 256 MB) and `--batch-size` (rows per write batch, 1024 to
8192) tune the same reads and the write.

### Seeing the data checks at work

To see the data checks stop an import, copy `ecommerce_purchase.csv` as
`purchase_bad.csv`, change the `order_date` of one row to an invalid date such as
`2023-13-45 99:99:99`, and pass the copy:

```bash
python -m polyglotimportcsv --config data/ecommerce/import_config.json \
  --source purchase=data/ecommerce/purchase_bad.csv \
  --dry-run
```

The command exits with code 1 and prints a table with the rule (`not_convertible`),
where it happened (`postgres · orders`), how many times, and an example with the
file, the line, the column and the value. Without `--dry-run` the result is the same,
and nothing is written in any DBMS.

## Português (BR)

| Arquivo | Finalidade |
|---------|------------|
| `ecommerce_stock.csv`, `ecommerce_purchase.csv`, `ecommerce_select_product.csv`, `ecommerce_add_to_cart.csv` | Um CSV por entidade (modo de entrada padrão). Cada arquivo É a origem das suas linhas — não há coluna discriminadora. |
| `ecommerce_join.csv` | CSV combinado (modo alternativo): a coluna 0 (`action`) é a coluna de origem; cada valor distinto vira uma fonte. |
| `import_config.json` | Configuração de mapeamento v2 (`sources` com vários CSVs). Padrão do `./run_example.sh`. |
| `import_config_combined.json` | Os mesmos blocos por SGBD, com `sources` apontando o CSV combinado — mostra que trocar o modo de entrada não muda nada no mapeamento de cada SGBD. |
| `import_config_invalido.json` | Uma configuração inválida de propósito (a fonte `stock` é um número), para ver a validação em ação: a camada de JSON Schema a recusa, com código de saída 1, antes de ler ou gravar qualquer dado. |
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

A configuração precisa referenciar colunas presentes nesse CSV. O `--dry-run` lê o
arquivo inteiro, em duas leituras (inferência e validação) e em blocos, então confere
os dados de um arquivo grande sem conectar a nenhum SGBD. Em uma importação real,
`--chunk-size` (memória de cada bloco de leitura, de 8 a 256 MB) e `--batch-size`
(linhas por lote de gravação, de 1024 a 8192) ajustam as mesmas leituras e a
gravação.

### Vendo as conferências dos dados em ação

Para ver as conferências dos dados interromperem uma importação, copie
`ecommerce_purchase.csv` como `purchase_bad.csv`, troque o `order_date` de uma linha
por uma data inválida, como `2023-13-45 99:99:99`, e passe a cópia:

```bash
python -m polyglotimportcsv --config data/ecommerce/import_config.json \
  --source purchase=data/ecommerce/purchase_bad.csv \
  --dry-run
```

O comando termina com código 1 e mostra uma tabela com a regra (`not_convertible`),
onde aconteceu (`postgres · orders`), quantas vezes e um exemplo com o arquivo, a
linha, a coluna e o valor. Sem `--dry-run` o resultado é o mesmo, e nada é gravado em
nenhum SGBD.
