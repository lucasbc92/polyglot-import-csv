# Design — TCC2: modos de entrada, configuração v2, logs e benchmarks

Data: 2026-07-08
Status: aprovado em discussão (brainstorming); aguardando revisão final do autor.

## 1. Contexto e objetivos

O TCC1 entregou o Polyglot Import CSV lendo **um único CSV esparso** (`ecommerce_join.csv`),
em que a coluna `action` discrimina a origem de cada linha e os `filters` do
`import_config.json` fatiam o arquivo por entidade. Para o TCC2 ficaram três pendências:

1. **Indicação da origem das entidades** — repensar como o CSV de entrada declara a que
   entidade cada dado pertence, avaliando qual modo deve ser o padrão.
2. **Avaliação de desempenho** — datasets de tamanhos variados e instrumentação de métricas.
3. **(Bônus, fora deste escopo)** interface gráfica.

Este documento cobre os itens 1 e 2, mais uma refatoração da camada de logs.

### Decisão central: modo padrão

**Um CSV por entidade é o modo padrão/canônico.** Justificativa: é o formato natural de
exports reais (um arquivo por tabela/coleção); elimina a esparsidade (~60% de células
vazias no join atual); dispensa coluna discriminadora e `filters` de origem. O **CSV
combinado** (união vertical com coluna de origem) permanece como modo alternativo para
dados tipo log de eventos. Um terceiro "modo" por ranges de colunas **não existe**: o
caso de join denso (toda linha alimenta todas as entidades) já é atendido citando
colunas por nome com deduplicação por chave; ranges entram apenas como açúcar sintático
na citação de colunas (ver §2.4).

## 2. Formato de configuração v2 (`import_config.json`)

### 2.1 Campo `version`: removido

Não há convivência de formatos: o v2 substitui o v1 integralmente. O campo `version`
sai do schema, dos exemplos e das menções no relatório LaTeX.

### 2.2 Bloco global `sources` (obrigatório)

Cada entrada nomeia uma fonte de dados, em duas formas:

```json
"sources": {
  "stock": "ecommerce_stock.csv",
  "eventos": { "file": "ecommerce_join.csv", "origin_column": true }
}
```

- **Forma string** (CSV por entidade): caminho de um arquivo inteiro daquela fonte.
  Caminhos relativos resolvem a partir do diretório do próprio config.
- **Forma objeto com `origin_column: true`** (CSV combinado): a **coluna 0** do arquivo
  é a origem. Cada valor distinto dela vira automaticamente um nome de fonte
  (ex.: `stock`, `purchase`). A coluna de origem é consumida pelo fatiamento e não
  aparece como atributo comum — mas fica acessível como pseudo-coluna `_source` (§2.6).
- Colisão entre nome de fonte declarado e valor de origem → erro de validação.

### 2.3 Vínculo entidade→fonte

Em cada bloco de SGBD, a entidade liga-se à fonte:

- automaticamente, quando a **chave da entidade tem o mesmo nome** de uma fonte; ou
- explicitamente, por `"source": "nome"`; ou
- por **lista**, `"source": ["a", "b", ...]` → concatenação das fontes (cabeçalho =
  união das colunas; ausentes ficam vazias), com `_source` = nome da fonte de cada linha;
- no modo combinado, vincular ao **nome da fonte combinada** (ex.: `"source": "eventos"`)
  entrega todas as linhas do arquivo, com `_source` = valor da coluna 0.

Propriedade-chave (abordagem "origens viram fontes"): os blocos de SGBD são **idênticos
nos dois modos de entrada** — trocar multi-CSV ↔ combinado altera apenas o bloco `sources`.

### 2.4 Mapeamento de colunas — três níveis + ranges

1. **Sem `columns`** → auto-map: todas as colunas do CSV viram atributos, tipos inferidos.
2. **`columns` + `"auto_map": true`** → auto-map como base; entradas manuais refinam
   colunas específicas (`is_key`, `db_type`, `schema_column`, …).
3. **Só `columns`** → manual puro (comportamento atual).

Campo opcional `csv_columns` restringe o auto-map a um subconjunto, aceitando **nome,
índice e range misturados**: `"csv_columns": ["1-5", "23-28", "user_id"]`.
Indexação: **com** coluna de origem, ela é a coluna 0 e a primeira coluna de dados é 1;
**sem** coluna de origem, a primeira coluna é 1. Sobreposição entre entidades é
permitida. A fragilidade posicional (inserir coluna desloca índices) será documentada.

Regras acessórias: `csv_columns` só é válido quando há auto-map (níveis 1 e 2 — no
manual puro é erro de validação); e o campo `csv_column` de uma coluna manual também
aceita índice (não range), cobrindo CSVs com cabeçalhos duplicados sem contorções.

### 2.5 Inferência de tipos

Varredura dos valores não vazios de cada coluna (estende `infer_column_kinds` existente,
que ganha detecção de `boolean`): inteiro → `BIGINT`, decimal → `NUMERIC`,
timestamp ISO → `TIMESTAMPTZ`, booleano → `BOOLEAN`, misto/vazio/texto → `TEXT`.
Vale para o DDL (PostgreSQL/Cassandra) **e** para o cast dos valores em todos os SGBDs
(MongoDB/Redis/Neo4j passam a receber número/booleano nativos). Mapeamento manual
sempre vence a inferência.

### 2.6 Pseudo-coluna `_source`

Disponível em entidades vinculadas à fonte combinada inteira ou a lista de fontes.
Mapeável como qualquer coluna (ex.: `"_source": { "schema_column": "event_type" }`).
Cobre o caso real do `user_activity_log` (Cassandra), que consome todas as origens e
usa a origem como dado.

### 2.7 `filters`, `relationships`, `sgbd_config.json`

`filters` permanece com a sintaxe atual, mas apenas para predicados genuínos
(ex.: `rating >= 4`) — nunca para discriminar origem. `relationships` e o
`sgbd_config.json` ficam inalterados.

## 3. Pipeline de importação

Fluxo: config → carregar todas as fontes → resolver mapeamento efetivo por entidade →
validar → importar por SGBD/entidade, com métricas.

| Módulo | Mudança |
|---|---|
| `csv_reader.py` | Nova `load_sources(sources_cfg, base_dir)` → `{fonte: (DataFrame, kinds)}`. Arquivo combinado é lido uma vez e fatiado pela coluna 0. `infer_column_kinds` ganha `boolean`. |
| `config_parser.py` | Parse/validação do bloco `sources`; resolução de vínculos entidade→fonte; remoção do `version` no merge. |
| `mapping_resolver.py` (novo) | Constrói o mapeamento efetivo: auto-map (com `csv_columns`/ranges resolvidos contra o cabeçalho real) + sobrescritas manuais + tipos inferidos onde não houver `db_type`. |
| `runner.py` | Orquestração por fontes; entrega a cada importer o DataFrame da entidade já fatiado + mapeamento efetivo; dono do `MetricsCollector`. |
| `importers/*` | Assinatura muda de `(bcfg, df_global, kinds, …)` para dados por entidade preparados; casting nativo por kind em todos os SGBDs. |
| `filter_engine.py` | Intacto; aplica sobre o DataFrame da fonte da entidade. |
| `validation.py` | Colunas de cada entidade validadas contra o cabeçalho **da sua fonte** (não mais um df global). |

### 3.1 CLI

- Sai: `--csv` (fontes vêm do config).
- Entra: `--source NOME=CAMINHO` (repetível) para sobrepor caminho de fonte sem editar
  o config (essencial para benchmarks); `--log-level`; `--show-data` / `--no-data`;
  `--benchmark`.
- Inalterados: `--dry-run`, `--only`, `--create-schema`/`--no-create-schema`.
- Dry-run mais informativo: contagens por fonte/entidade **e** mapeamento efetivo com
  tipos inferidos, para conferência antes da importação real.

### 3.2 Hierarquia de exceções (rasa)

Subclasses de `BusinessException` por categoria — CLI continua com um único
`except BusinessException`; testes afirmam o tipo, não o texto da mensagem:

- `ConfigError` — JSON inválido, schema violado, backend sem conexão declarada;
- `SourceError` — fonte desconhecida, arquivo ausente, colisão nome×valor de origem;
- `MappingError` — coluna/índice/range inexistente, entidade sem vínculo resolvível;
- `ImportExecutionError` — falhas durante a escrita nos SGBDs
  (nome evita colidir com o builtin `ImportError`).

## 4. Logs e métricas

### 4.1 Camada de saída sobre `rich`

`console.py` (ANSI manual) é substituído por `reporting.py` sobre a biblioteca `rich`,
integrado ao `logging` padrão via `RichHandler`. Todos os módulos logam por
`logger.debug/info/warning/error` — sem `print` espalhado. Nova dependência: `rich`.

### 4.2 Níveis e destinos

| Nível | Conteúdo |
|---|---|
| `DEBUG` | Comandos SQL/CQL/Cypher, mapeamento efetivo coluna a coluna, decisões de inferência, lotes enviados |
| `INFO` | Fases do pipeline, sumário por entidade, tabela final de métricas |
| `WARNING` | Coerção que caiu para texto, fonte/entidade sem linhas, chave duplicada sobrescrita |
| `ERROR` | Falhas (`BusinessException` e subclasses) |

Dois destinos independentes: **terminal** respeita `--log-level` (default `INFO`);
**arquivo de sessão** em `logs/` grava sempre em `DEBUG`, texto puro sem cor
(substitui o tee de stdout atual).

### 4.3 Dump de dados

Por entidade: até **50 linhas** → registros exibidos (JSON com highlight) em INFO;
acima, só contagens. `--show-data` / `--no-data` forçam. O exemplo didático
(8 linhas/entidade) continua verboso sozinho; benchmarks nunca despejam dados.

### 4.4 Progresso e métricas

- **Barra de progresso** (rich Progress) automática em entidades acima do limiar de
  dump, com linhas/s ao vivo; suprimida quando a saída não é terminal.
- **`MetricsCollector`** (sempre ativo): por SGBD × entidade × fase (leitura, filtro,
  mapeamento, escrita) — linhas, duração, linhas/s. Tabela-resumo rich ao final.
- **`--benchmark`**: grava `benchmarks/benchmark_<timestamp>.json` (+ CSV consolidável)
  com metadados de ambiente (versão do Python, semente, tamanhos).

## 5. Datasets e benchmark (híbrido)

- `scripts/generate_benchmark_data.py`: cenário e-commerce sintético, `--rows N
  --seed S`, gera **os dois formatos** (CSVs por entidade e combinado com coluna de
  origem) — comparar os modos de entrada é, ele próprio, um experimento do TCC2.
- Referência pequena **versionada**: `data/benchmark/` (~1 mil linhas) para testes
  rápidos/CI.
- Tamanhos grandes (10k, 100k, 1M) gerados sob demanda em `data/benchmark/generated/`
  (gitignored).
- `scripts/run_benchmarks.py`: laço tamanhos × modos × SGBDs com repetições (mediana de
  N execuções), consolidando os JSONs para os gráficos do relatório.

## 6. Migração do exemplo e-commerce

- `import_config.json` reescrito em v2: `sources` com os quatro CSVs por entidade
  (entrada padrão do `run_example.sh`); `filters` de `action` removidos.
- CSVs divididos **regenerados sem a coluna `action`** (no modo multi-CSV o arquivo é
  a origem).
- `import_config_combined.json`: variante demonstrando o modo combinado sobre
  `ecommerce_join.csv` — blocos de SGBD idênticos; só o `sources` muda.
- `user_activity_log` (Cassandra) migra via `_source` (§2.6).
- Exemplo de colunas duplicadas atualizado para v2.

## 7. Testes

- **Unitários novos:** parser de índices/ranges; resolução de vínculos; semântica
  auto-map + sobrescritas; inferência (boolean, colunas mistas); fatiamento do
  combinado; `_source`; fontes em lista; hierarquia de exceções (asserção por tipo);
  limiar de dump; `MetricsCollector`.
- **Suíte existente adaptada** às novas assinaturas, mantendo o padrão de registry stub.
- **Equivalência de modos:** dry-run do e-commerce em multi-CSV e combinado produz
  contagens idênticas por entidade (resultado citável no relatório).
- **Smoke do gerador:** 1k linhas com semente fixa validadas por dry-run.

## 8. Documentação

- READMEs (raiz e `data/ecommerce/`) reescritos para v2: modos, `sources`, novos flags.
- `import_config.schema.json` reescrito (`sources`, `source`, `csv_columns`,
  `auto_map`, sem `version`); `sgbd_config.schema.json` intacto.
- LaTeX: remover menções ao campo `version` (cap. 4 e Apêndice C) para o relatório não
  divergir do código. Capítulos novos do TCC2 ficam fora deste escopo.

## 9. Fora de escopo

Interface gráfica (bônus do TCC2), suporte TSV/Excel, processamento *chunked*,
novos conectores.
