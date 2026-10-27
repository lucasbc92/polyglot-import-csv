# Fluxo único e validação prévia completa — Plano da Etapa 1 (código)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** fazer do fluxo o único modo de execução. A importação passa a ter três etapas de leitura (inferência, validação e gravação) e toda a validação roda antes de gravar, inclusive a das referências entre entidades. Entram `--chunk-size` e `--batch-size`, a GUI é ajustada, a materialização sai do código e a versão vai a 3.0.0.

**Architecture:** a inferência lê cada fonte inteira e produz um `ImportPlan`, com o perfil de cada fonte e o vínculo de cada entidade. O motor de fluxo (`DbmsStream`) consome esse plano e roda duas vezes:
- **validação:** uma única leitura alimenta, para todos os SGBDs, *sinks* que só conferem (`CheckingSink`);
- **gravação:** os *sinks* reais, um SGBD por vez, como hoje.

As regras de cabeçalho ficam em `validation.py`, e a CLI e a GUI usam essa mesma função.

**Tech Stack:** Python 3.12, pandas, click, PySide6, pytest.

**Spec:** `docs/superpowers/specs/2026-10-27-fluxo-unico-validacao-previa-design.md`

## Global Constraints

- **Testes:** `.venv/Scripts/python.exe -m pytest`. Sem o venv, cerca de 100 testes da GUI são pulados. A suíte inteira passa ao fim de cada tarefa.
- **Git:**
  - prefixo `rtk` em todo comando git;
  - commits em português, terminando com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`;
  - `rtk git push` após cada commit;
  - branch `fluxo-unico`.
- **Idioma:**
  - código, mensagens da CLI e logs em inglês;
  - textos da GUI em português;
  - em texto em português, sempre "SGBD", nunca "backend";
  - READMEs bilíngues (inglês e português).
- **`--chunk-size`:**
  - inteiro em MB (2^20 bytes), padrão 8, mínimo 8, máximo 256;
  - valor fora da faixa é erro de uso da CLI;
  - internamente as funções recebem `chunk_mb: float` sem faixa, para que os testes possam usar valores minúsculos.
- **`--batch-size`:**
  - inteiro, padrão 1024, mínimo 1024, máximo 8192;
  - lote efetivo de uma entidade = `min(batch_size, linhas por bloco de cada fonte da entidade)`;
  - internamente aceita qualquer inteiro ≥ 1.
- **Exemplos de erro:**
  - até `MAX_EXAMPLES = 5` por grupo de erro, cada um com arquivo, linha, coluna e valor;
  - linha = índice da linha de dados no arquivo + 2 (o cabeçalho é a linha 1).
- **Uma regra, um lugar:** cada regra de validação tem uma única implementação, usada pela CLI, pelo `--dry-run` e pela GUI. Nenhum caminho de código paralelo.
- **Memória:**
  - as leituras de inferência e de validação nunca carregam um arquivo inteiro;
  - o pico só cresce com o número de linhas por meio de agregados por coluna e de conjuntos de chaves distintas referenciadas.
- **Anti-meta:** se uma regra nova fizer falhar `data/ecommerce/` (multifonte ou combinado), a base de referência em `data/benchmark/` ou a base sintética do gerador, o executor para e reporta antes de afrouxar a regra.
- **Versão:** 3.0.0, sem release no GitHub.
- **Docker:** a verificação final (Task 11) usa os cinco SGBDs de `docker-compose.yml`, que já estão saudáveis.

## Review Focus

1. **CSV multifonte só com cabeçalho (0 linhas):** o perfil sai com `rows=0`, o vínculo é criado e aparece o aviso de entidade com 0 linhas, sem erro. Testes na Task 3 e na Task 7.
2. **CSV combinado agrupado por origem, com uma origem que só aparece depois do primeiro bloco:** a inferência encontra a origem, e o vínculo de união sai dos perfis, sem reler amostras. Teste na Task 3.
3. **Arquivo com BOM UTF-8 e quebras CRLF:** o cabeçalho sai sem BOM, `chunk_rows` funciona e a linha dos exemplos de erro está correta. Testes na Task 3 e na Task 6.
4. **`--only` com subconjunto de SGBDs:** a inferência não lê as fontes que nenhum SGBD selecionado usa, mas os arquivos declarados continuam obrigatórios. Teste na Task 3.
5. **FK que aponta para uma linha excluída pelo filtro da entidade-alvo:** vira erro de referência pendente. Teste na Task 6.

## Mapa de arquivos

| Arquivo | Responsabilidade | Tarefas |
|---|---|---|
| `src/polyglotimportcsv/csv_reader.py` | `ColumnStats` (inferência acumulável) e `infer_column_kinds` sobre ela | 1 |
| `src/polyglotimportcsv/validation.py` | regras de cabeçalho; `validate_headers` compartilhada | 2 |
| `src/polyglotimportcsv/stream_source.py` | leitura em blocos, tamanho do bloco em MB, cabeçalhos, conferência de `--source` | 2, 3, 4 |
| `src/polyglotimportcsv/source_profile.py` (novo) | perfil de cada fonte inteira (leitura de inferência) | 3 |
| `src/polyglotimportcsv/stream_binding.py` | vínculo da entidade a partir dos perfis | 3, 4 |
| `src/polyglotimportcsv/import_plan.py` (novo) | `ImportPlan` e `plan_import` | 3 |
| `src/polyglotimportcsv/stream_runner.py` | `DbmsStream`, `run_stream_import`, `run_single_pass` | 4 |
| `src/polyglotimportcsv/db_type_checks.py` (novo) | valor × `db_type` (PostgreSQL) e × tipo CQL (Cassandra) | 5 |
| `src/polyglotimportcsv/data_validation.py` (novo) | relatório de erros, conferência por linha, *sinks* de conferência, `validate_data` | 6 |
| `src/polyglotimportcsv/runner.py`, `cli.py`, `metrics.py` | fluxo de três leituras, opções novas, fases | 7 |
| `src/polyglotimportcsv/benchmark_runner.py`, `benchmark_results.py`, `scripts/run_benchmarks.py`, `scripts/benchmark_tracemalloc_ab.py` | eixo de tamanho de bloco | 8 |
| `importers/*`, `sources.py`, `mapping_resolver.py`, `reporting.py`, `materialize.py` → `row_shaping.py` | remoção da materialização | 9 |
| `src/polyglotimportcsv/gui/*` | campos "Bloco (MB)" e "Lote"; sem "Execução" | 2, 10 |
| documentos de uso, `pyproject.toml`, `__init__.py`, `docs/releases/v3.0.0.md` | documentação e versão | 11 |

---

### Task 1: Estatística de tipo por coluna (inferência acumulável)

**Files:**
- Modify: `src/polyglotimportcsv/csv_reader.py`
- Create: `tests/test_column_stats.py`
- Modify: `tests/test_inference_probe.py` (oráculo ingênuo)

**Interfaces:**
- Consumes: `casting.is_boolean_series`, `csv_reader._parse_datetimes`, `_DATETIME_THRESHOLD`, `_DATETIME_PROBE_CHUNK`.
- Produces:
  - `@dataclass class ColumnStats`, com os campos `non_empty: int = 0`, `all_boolean: bool = True`, `all_numeric: bool = True`, `all_integral: bool = True`, `dates_min: int = 0` e `dates_max: int = 0`, e os métodos:
    - `update(self, values: pd.Series) -> None`, que recebe os textos crus de uma coluna em um bloco;
    - `merged(self, other: "ColumnStats") -> "ColumnStats"`;
    - `kind(self) -> str`.
  - `_datetime_evidence(non_empty: pd.Series, threshold: float) -> Tuple[int, int]`, que devolve `(parsed, failed)`.
  - `infer_column_kinds(df) -> Dict[str, str]`, com a mesma assinatura de hoje, agora implementada com `ColumnStats`.

- [ ] **Step 1: Escrever os testes que falham** em `tests/test_column_stats.py`:

```python
def test_digit_only_values_never_count_as_dates():
    ids = [str(n) for n in range(1000, 1100)] + ["X-1"]
    assert infer_column_kinds(pd.DataFrame({"id": ids}))["id"] == "string"

@pytest.mark.parametrize("values", [BOOLS, INTS, FLOATS, ISO_DATES, DATES_WITH_10PCT_JUNK, NAMES, DIGITS_THEN_TEXT])
@pytest.mark.parametrize("cut", [1, 7, 50])
def test_chunked_stats_match_the_whole_column(values, cut):
    s = pd.Series(values, dtype=str)
    acc = ColumnStats()
    for start in range(0, len(s), cut):
        part = ColumnStats(); part.update(s.iloc[start:start + cut]); acc = acc.merged(part)
    assert acc.kind() == infer_column_kinds(pd.DataFrame({"c": s}))["c"]

def test_a_late_non_boolean_value_breaks_boolean():
    a, b = ColumnStats(), ColumnStats()
    a.update(pd.Series(["true", "false"] * 50)); b.update(pd.Series(["maybe"]))
    assert a.merged(b).kind() == "string"

def test_undecided_date_bounds_resolve_to_string():
    st = ColumnStats(non_empty=100, all_boolean=False, all_numeric=False, dates_min=80, dates_max=90)
    assert st.kind() == "string"

def test_empty_values_do_not_count():
    st = ColumnStats(); st.update(pd.Series(["", "", ""]))
    assert st.non_empty == 0 and st.kind() == "empty"
```

As listas `BOOLS`, `INTS`, ... são constantes do próprio teste, com pelo menos 120 valores cada. `DATES_WITH_10PCT_JUNK` deve dar `datetime`, e `DIGITS_THEN_TEXT` (dígitos seguidos de um valor de texto) deve dar `string`.

Em `tests/test_inference_probe.py`, troque o oráculo ingênuo para que valores formados só por dígitos contem como falha.

- [ ] **Step 2: Rodar os testes e confirmar que falham.** Run: `.venv/Scripts/python.exe -m pytest tests/test_column_stats.py -v`. Expected: FAIL com `ImportError: ColumnStats`.

- [ ] **Step 3: Implementar em `csv_reader.py`.** Algoritmo de `update(values)`:
  1. `s2 = values.replace("", pd.NA).dropna()`; `n = len(s2)`; se `n == 0`, retornar.
  2. `non_empty += n`; `all_boolean &= is_boolean_series(s2)`.
  3. `num = pd.to_numeric(s2, errors="coerce")`; `numeric_chunk = num.notna().all()`; `all_numeric &= numeric_chunk`; se `numeric_chunk`, `all_integral &= (num % 1 == 0).all()`.
  4. Datas:
     - se `numeric_chunk`, `dates_max +=` número de valores que não são só dígitos (depois de `strip`) e `dates_min` não muda, sem nenhuma chamada de parse;
     - senão, `(p, f) = _datetime_evidence(s2, _DATETIME_THRESHOLD)`, `dates_min += p` e `dates_max += n - f`.

  `_datetime_evidence` é o laço atual de `_exceeds_datetime_share`, com duas mudanças:
  - valores cujo `strip()` só tem dígitos ASCII contam como falha, sem chamar o parse;
  - a função devolve `(parsed_weight, failed_weight)` no ponto em que parou.

  `_exceeds_datetime_share` continua existindo como invólucro: `parsed > threshold * total`.

  `kind()` segue a ordem de hoje, com `T = _DATETIME_THRESHOLD`:
  1. `"empty"` se `non_empty == 0`;
  2. `"boolean"`;
  3. `"integer"` ou `"float"`, quando `all_numeric`;
  4. `"datetime"` se `dates_min > T * non_empty`;
  5. `"string"` se `dates_max <= T * non_empty`;
  6. no caso indeciso, `"string"`.

  Escreva essa exceção na docstring: ela só ocorre quando blocos discordam perto do limiar.

  `merged` soma os contadores e faz o E lógico das bandeiras. `infer_column_kinds` mantém os retornos antecipados por `dtype` e, para cada coluna de texto, faz `ColumnStats().update(col)` e chama `.kind()`.

- [ ] **Step 4: Rodar e confirmar que passam.** Run: `.venv/Scripts/python.exe -m pytest tests/test_column_stats.py tests/test_inference_probe.py tests/test_inference_performance.py -v`. Expected: PASS. O teste `test_reference_csvs_keep_a_stable_kind_per_column` continua verde.

- [ ] **Step 5: Rodar a suíte inteira.** Run: `.venv/Scripts/python.exe -m pytest -q`. Expected: tudo passa.

- [ ] **Step 6: Commit e push.**

```bash
rtk git add src/polyglotimportcsv/csv_reader.py tests/test_column_stats.py tests/test_inference_probe.py
rtk git commit -m "feat(inferencia): estatistica acumulavel por coluna; digitos puros nao contam como data

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
rtk git push
```

---

### Task 2: Validação de cabeçalhos compartilhada (CLI e GUI)

**Files:**
- Modify: `src/polyglotimportcsv/validation.py`
- Modify: `src/polyglotimportcsv/stream_source.py`
- Modify: `src/polyglotimportcsv/gui/preflight.py`
- Test: `tests/test_validation.py`, `tests/test_stream_source.py`, `tests/test_gui_preflight.py`

**Interfaces:**
- Consumes: `mapping_resolver.bind_entity_source`, `expand_entity_columns`, `union_data_cols`, `BoundEntity`; `sources._resolve_path`, `SOURCE_COLUMN`, `SourceData`.
- Produces:
  - `stream_source.check_source_overrides(sources_cfg: Dict[str, Any], overrides: Optional[Dict[str, str]]) -> None`. Lança `SourceError` com a mesma mensagem de hoje em `sources.load_sources` para nomes de `--source` não declarados.
  - `stream_source.read_source_headers(sources_cfg, base_dir, overrides) -> Dict[str, List[str]]`. Devolve o cabeçalho de dados de cada fonte declarada, sem a coluna de origem nos arquivos combinados, lido com as opções de `_read_chunks` e `nrows=0`. Lança `SourceError` para arquivo ausente e para arquivo combinado com menos de 2 colunas, com as mensagens de hoje.
  - `validation.validate_headers(config: Dict[str, Any], headers: Dict[str, List[str]], combined: Collection[str], dbms_names: Sequence[str]) -> None`. Monta um registro só de cabeçalhos (`SourceData` com DataFrame vazio e tipos `"string"`). Se houver fontes combinadas, cada nome de origem desconhecido recebe a união dos cabeçalhos combinados, como a GUI já faz. Para cada SGBD, vincula as entidades com `bind_entity_source` e `expand_entity_columns`, monta `BoundEntity` e chama `validate_backend_entities`.
  - Regras novas em `validate_backend_entities`, todas com `MappingError`:
    - entidade do `redis` ou do `neo4j` sem exatamente uma coluna folha `is_key` (`"Entity '{e}' in '{b}' must have exactly one is_key column."`);
    - entidade do `cassandra` sem `cassandra_partition` ou com a lista vazia;
    - relacionamento do `postgres` ou do `neo4j` cujo `from` ou `to` tem filtro `each`;
    - relacionamento do `neo4j` cuja fonte da entidade `from` não tem a coluna CSV da chave de alguma das duas pontas. As duas chaves são resolvidas com `resolve_csv_column` nas colunas da fonte `from`.

- [ ] **Step 1: Escrever os testes que falham.**

```python
# tests/test_validation.py
def test_validate_headers_reports_unknown_mapped_column():
    cfg = {"sources": {"s": "s.csv"}, "postgres": {"entities": {"t": {"source": "s", "columns": {"nope": {}}}}}}
    with pytest.raises(MappingError, match="unknown column: nope"):
        validate_headers(cfg, {"s": ["a", "b"]}, (), ["postgres"])

def test_validate_headers_gives_unknown_names_the_combined_header():
    cfg = {"sources": {"e": {"file": "j.csv"}}, "redis": {"entities": {"purchase": {"columns": {"a": {"is_key": True}}}}}}
    validate_headers(cfg, {"e": ["a", "b"]}, ("e",), ["redis"])  # no error

@pytest.mark.parametrize("dbms", ["redis", "neo4j"])
def test_kv_and_graph_entities_need_exactly_one_key(dbms): ...  # zero keys and two keys -> MappingError

def test_cassandra_entity_needs_a_partition(): ...
def test_relationship_endpoint_cannot_use_each(): ...      # postgres and neo4j
def test_neo4j_relationship_needs_both_key_columns_in_the_from_source(): ...

# tests/test_stream_source.py
def test_unknown_override_name_raises(tmp_path): ...       # message lists the declared names
def test_read_source_headers_strips_the_origin_column(tmp_path): ...
def test_read_source_headers_reports_a_missing_file(tmp_path): ...
```

Em `tests/test_gui_preflight.py`, acrescente um teste que verifica que `preflight` chama `validation.validate_headers`: um *monkeypatch* que lança `MappingError("x")` faz a mensagem `"x"` aparecer em `Preflight.errors`.

- [ ] **Step 2: Rodar e confirmar que falham.** Run: `.venv/Scripts/python.exe -m pytest tests/test_validation.py tests/test_stream_source.py tests/test_gui_preflight.py -v`. Expected: FAIL (as funções novas não existem).

- [ ] **Step 3: Implementar.** Em `gui/preflight.py`, `_bind_and_validate_headers` continua lendo os arquivos com cache e com as mensagens em português. O bloco que monta o registro e chama `resolve_backend_entities` e `validate_backend_entities` passa a ser uma única chamada `validate_headers(import_cfg, headers, combined_names, dbms_names)`, com captura de `BusinessException` e `ValueError` como hoje. Atualize a docstring do módulo, que não deve mais citar a materialização.

- [ ] **Step 4: Rodar e confirmar que passam.** Mesmo comando do Step 2. Expected: PASS.

- [ ] **Step 5: Conferir os exemplos.** Run:

```bash
.venv/Scripts/python.exe -c "import json;from pathlib import Path;from polyglotimportcsv.stream_source import read_source_headers;from polyglotimportcsv.validation import validate_headers,BACKENDS
for f in ['import_config.json','import_config_combined.json']:
    c=json.loads(Path('data/ecommerce/'+f).read_text(encoding='utf-8'));s=c['sources']
    validate_headers(c,read_source_headers(s,Path('data/ecommerce'),{}),[n for n,d in s.items() if isinstance(d,dict)],[b for b in BACKENDS if b in c]);print(f,'ok')"
```

Expected: `import_config.json ok` e `import_config_combined.json ok`. Se falhar, siga a anti-meta: pare e reporte.

- [ ] **Step 6: Rodar a suíte inteira.** Expected: tudo passa.

- [ ] **Step 7: Commit e push.** Mensagem: `feat(validacao): regras de cabecalho num lugar so, usadas pela CLI e pela GUI`.

---

### Task 3: Plano de importação (bloco em MB, perfis das fontes, vínculos)

**Files:**
- Modify: `src/polyglotimportcsv/stream_source.py`
- Create: `src/polyglotimportcsv/source_profile.py`
- Modify: `src/polyglotimportcsv/stream_binding.py`
- Create: `src/polyglotimportcsv/import_plan.py`
- Test: `tests/test_source_profile.py`, `tests/test_import_plan.py`, `tests/test_stream_source.py`, `tests/test_stream_binding.py`

**Interfaces:**
- Consumes: `ColumnStats` (Task 1); `read_source_headers`, `check_source_overrides` e `validate_headers` (Task 2); `mapping_resolver.bind_entity_source`, `expand_entity_columns`.
- Produces:
  - Em `stream_source`:
    - constantes `DEFAULT_CHUNK_MB = 8`, `MIN_CHUNK_MB = 8`, `MAX_CHUNK_MB = 256` e `PROBE_ROWS = 1000`;
    - `chunk_rows(path: Path, chunk_mb: float) -> int`, que lê as primeiras `PROBE_ROWS` linhas com as opções de `_read_chunks` e faz `bytes_por_linha = memory_usage(deep=True, index=False).sum() / linhas` e `max(1, int(chunk_mb * 2**20 // bytes_por_linha))`. Um arquivo sem linhas dá `1`. A docstring diz que o orçamento é aproximado, porque a largura é medida no início do arquivo;
    - `iter_entity_chunks(..., rows_per_chunk: Optional[Mapping[str, int]] = None)`: quando o mapa é informado, ele dá as linhas por bloco de cada fonte declarada. O parâmetro `chunksize` continua por ora e sai na Task 4.
  - Em `source_profile`:
    - `@dataclass class SourceProfile`, com os campos `name: str` (nome multifonte ou valor de origem), `declared: str` (fonte declarada que contém o arquivo), `path: Path`, `header: List[str]`, `rows: int` e `stats: Dict[str, ColumnStats]`, e a propriedade `kinds -> Dict[str, str]`;
    - `profile_sources(sources_cfg, base_dir, overrides, rows_per_chunk: Mapping[str, int]) -> Dict[str, SourceProfile]`. Faz uma leitura de cada fonte declarada. Uma fonte multifonte sem linhas ganha perfil com `rows=0` e o cabeçalho lido. Em arquivo combinado, cria um perfil por valor de origem visto. Lança `SourceError` quando o mesmo nome aparece duas vezes, seja um valor de origem igual a um nome declarado, seja a mesma origem em dois arquivos combinados, com a mensagem de colisão de hoje;
    - **colunas indecisas:** depois da leitura, as colunas cujas `ColumnStats` têm `decided()` falso são resolvidas com contagem exata. Cada arquivo que tem alguma coluna indecisa é relido só com essas colunas (`usecols`; num arquivo combinado, mais a coluna de origem, para rotear as linhas), com as mesmas linhas por bloco. As estatísticas dessas colunas são refeitas do zero com `update(values, exact=True)`. Assim, a inferência sobre o arquivo inteiro dá sempre o mesmo resultado de `infer_column_kinds` sobre a coluna inteira. A releitura só acontece quando os blocos discordam;
    - `union_kinds(profiles: Sequence[SourceProfile], columns: Sequence[str]) -> Dict[str, str]`. Para cada coluna, junta (`merged`) as `ColumnStats` dos perfis que a têm e devolve o `kind()`. Coluna ausente de todos os perfis dá `"empty"`.
  - Em `stream_binding`:
    - `bind_entity(ename: str, ecfg: Dict[str, Any], profiles: Dict[str, SourceProfile]) -> EntityBinding`. Monta um registro de `SourceData` só de cabeçalhos a partir dos perfis e chama `bind_entity_source`, para que a regra de resolução do `source` continue num lugar só;
    - os tipos vêm de `profiles[n].kinds`; numa união, de `union_kinds(...)` sobre as colunas da união, mais `SOURCE_COLUMN: "string"`;
    - `cfg["columns"] = expand_entity_columns(...)` com esses tipos;
    - `source_name = "+".join(nomes)`;
    - as funções antigas `bind_entity_from_sample` e `bind_union_entity_from_samples` continuam por ora e saem na Task 4.
  - Em `import_plan`:
    - constantes `DEFAULT_BATCH_SIZE = 1024`, `MIN_BATCH_SIZE = 1024` e `MAX_BATCH_SIZE = 8192`;
    - `@dataclass class ImportPlan`, com os campos `config: Dict[str, Any]`, `base_dir: Path`, `overrides: Dict[str, str]`, `dbms_names: List[str]`, `batch_size: int`, `sources_cfg: Dict[str, Any]` (só as fontes que o plano lê), `rows_per_chunk: Dict[str, int]` (fonte declarada → linhas por bloco), `profiles: Dict[str, SourceProfile]` e `bindings: Dict[str, Dict[str, EntityBinding]]` (SGBD → entidade → vínculo), e o método `entity_batch(self, dbms: str, ename: str) -> int`, igual a `min(batch_size, min(rows_per_chunk[profiles[n].declared] for n in fontes_da_entidade))`;
    - `plan_import(config, base_dir, *, dbms_names, overrides=None, chunk_mb: float = DEFAULT_CHUNK_MB, batch_size: int = DEFAULT_BATCH_SIZE) -> ImportPlan`, descrita a seguir.

  `plan_import` funciona assim:
  1. **Fontes necessárias:** para cada entidade dos SGBDs em `dbms_names`, toma os nomes de fonte (lista, texto ou, se faltar, o nome da entidade). Entram os nomes que são fontes multifonte declaradas. Se algum nome não for uma delas, entram também todas as fontes combinadas.
  2. **Linhas por bloco:** `rows_per_chunk` vem de `chunk_rows` sobre cada fonte necessária.
  3. **Perfis:** `profiles = profile_sources(...)`. O tempo dessa leitura é medido pelo chamador, na Task 7.
  4. **Origem ausente:** cada nome de fonte de entidade precisa estar em `profiles`. Se faltar, `MappingError` com a entidade, o SGBD, o nome e a lista dos valores de origem encontrados.
  5. **Vínculos:** `bind_entity` para cada entidade.

- [ ] **Step 1: Escrever os testes que falham.**

```python
# tests/test_stream_source.py
def test_chunk_rows_follows_the_memory_budget(tmp_path):
    narrow, wide = _csv(tmp_path, "n.csv", cols=3, rows=5000), _csv(tmp_path, "w.csv", cols=30, rows=5000)
    assert chunk_rows(narrow, 1) > chunk_rows(wide, 1) >= 1
    assert chunk_rows(narrow, 2) >= 2 * chunk_rows(narrow, 1) - 1

def test_chunk_rows_reads_a_bom_crlf_file(tmp_path):            # Review Focus 3
    p = tmp_path / "b.csv"; p.write_bytes("\ufeffa,b\r\n1,x\r\n2,y\r\n".encode("utf-8"))
    assert chunk_rows(p, 8) >= 1
    assert read_source_headers({"b": "b.csv"}, tmp_path, {}) == {"b": ["a", "b"]}

# tests/test_source_profile.py
def test_whole_file_inference_sees_a_value_past_the_first_chunk(tmp_path):
    # flag column: "true"/"false" for 3000 rows, then "maybe"
    prof = profile_sources({"s": "s.csv"}, tmp_path, {}, {"s": 500})["s"]
    assert prof.kinds["flag"] == "string" and prof.rows == 3001

def test_header_only_source_gets_a_zero_row_profile(tmp_path):   # Review Focus 1
    prof = profile_sources({"s": "s.csv"}, tmp_path, {}, {"s": 100})["s"]
    assert prof.rows == 0 and prof.header == ["a", "b"] and prof.kinds["a"] == "empty"

def test_combined_origin_first_seen_after_many_chunks(tmp_path): # Review Focus 2
    # 2000 'stock' rows then 10 'purchase' rows, 100 rows per chunk
    profs = profile_sources({"e": {"file": "j.csv"}}, tmp_path, {}, {"e": 100})
    assert set(profs) == {"stock", "purchase"} and profs["purchase"].rows == 10
    assert profs["purchase"].declared == "e"

def test_undecided_column_is_resolved_by_an_exact_reread(tmp_path, monkeypatch):
    # dirty block (repeated junk) then unique ISO dates; small probe round so
    # the cheap pass leaves the column undecided (see tests/test_column_stats.py)
    prof = profile_sources({"s": "s.csv"}, tmp_path, {}, {"s": 500})["s"]
    assert prof.stats["d"].decided() and prof.kinds["d"] == infer_column_kinds(whole)["d"] == "datetime"

def test_no_reread_when_every_column_is_decided(tmp_path, monkeypatch): ...  # _read_chunks called once per file

def test_origin_equal_to_a_declared_name_collides(tmp_path): ...  # SourceError, "collision"
def test_union_kinds_merge_whole_file_stats(): ...                # int in A + float in B -> "float"; absent -> "empty"

# tests/test_import_plan.py
def test_only_reads_the_sources_the_selected_dbms_use(tmp_path, monkeypatch):  # Review Focus 4
    # config: redis uses 'cart', postgres uses 'stock'; dbms_names=["redis"]
    plan = plan_import(cfg, tmp_path, dbms_names=["redis"])
    assert set(plan.sources_cfg) == {"cart"} and "stock" not in plan.profiles

def test_unknown_origin_lists_the_origins_found(tmp_path):
    with pytest.raises(MappingError, match=r"purchse.*purchase.*stock"):
        plan_import(cfg_with_typo, tmp_path, dbms_names=["redis"])

def test_entity_batch_is_capped_by_rows_per_chunk(tmp_path):
    plan = plan_import(cfg, tmp_path, dbms_names=["postgres"], chunk_mb=0.01, batch_size=10_000)
    assert plan.entity_batch("postgres", "t") == plan.rows_per_chunk["s"] < 10_000

def test_union_binding_uses_whole_file_kinds(tmp_path): ...       # union column int in A, float only late in B -> "float"
```

- [ ] **Step 2: Rodar e confirmar que falham.** Run: `.venv/Scripts/python.exe -m pytest tests/test_stream_source.py tests/test_source_profile.py tests/test_import_plan.py tests/test_stream_binding.py -v`. Expected: FAIL (os módulos novos não existem).

- [ ] **Step 3: Implementar** as interfaces acima. `profile_sources` reaproveita `iter_entity_chunks(..., rows_per_chunk=...)`. Cada bloco entregue atualiza as `ColumnStats` do nome entregue, apenas sobre as colunas de dados, e soma suas linhas. O `SourceError` de origem vazia continua vindo de `iter_entity_chunks`.

- [ ] **Step 4: Rodar e confirmar que passam.** Mesmo comando do Step 2. Expected: PASS.

- [ ] **Step 5: Conferir o plano dos exemplos.** Run:

```bash
.venv/Scripts/python.exe -c "import json;from pathlib import Path;from polyglotimportcsv.import_plan import plan_import
for f in ['import_config.json','import_config_combined.json']:
    c=json.loads(Path('data/ecommerce/'+f).read_text(encoding='utf-8'));p=plan_import(c,Path('data/ecommerce'),dbms_names=[b for b in ('postgres','mongodb','cassandra','redis','neo4j') if b in c])
    print(f,{n:x.rows for n,x in p.profiles.items()})"
```

Expected: imprime as contagens por fonte ou origem dos dois arquivos, sem exceção.

- [ ] **Step 6: Rodar a suíte inteira.** Expected: tudo passa; o motor antigo ainda não usa o plano.

- [ ] **Step 7: Commit e push.** Mensagem: `feat(fluxo): plano de importacao com inferencia sobre o arquivo inteiro e bloco em MB`.

---

### Task 4: Motor de fluxo sobre o plano (`DbmsStream`)

**Files:**
- Modify: `src/polyglotimportcsv/stream_runner.py`
- Modify: `src/polyglotimportcsv/stream_source.py`: remove `READ_CHUNK`, o parâmetro `chunksize` e `sample_union_sources`; `rows_per_chunk` passa a ser obrigatório.
- Modify: `src/polyglotimportcsv/stream_binding.py`: remove `bind_entity_from_sample`, `bind_union_entity_from_samples` e `_sample_source_data`.
- Modify: `src/polyglotimportcsv/runner.py`: `_run_stream` monta o plano.
- Test: `tests/test_stream_runner.py`, `tests/test_stream_source.py`, `tests/test_stream_binding.py`, `tests/test_stream_memory.py`, `tests/test_runner_registry.py`, `tests/test_csv_header.py`, `tests/test_sinks.py`

**Interfaces:**
- Consumes: `ImportPlan` e `plan_import` (Task 3); `filter_engine.apply_filters`, `expand_each`; `casting.cast_frame`.
- Produces:
  - `@dataclass class StreamCounts`, com `written: Dict[str, Dict[str, int]]` (SGBD → partição, ou `":TYPE"` para relacionamentos → linhas) e `entity_rows: Dict[str, Dict[str, int]]` (SGBD → entidade → linhas depois dos filtros).
  - `class DbmsStream`:
    - `__init__(self, dbms: str, plan: ImportPlan, sink: DbmsSink, on_batch: Optional[Callable[[str, str, pd.DataFrame], None]] = None)`;
    - atributos `written: Dict[str, int]` e `entity_rows: Dict[str, int]`;
    - `feed(self, source: str, chunk: pd.DataFrame) -> None`, a passagem dos nós;
    - `finish_nodes(self) -> None`, que descarrega o que sobrou nos buffers;
    - `relationship_sources(self) -> Dict[str, Any]`, que devolve `{}` se o *sink* não tem `write_relationships` ou se o SGBD não declara relacionamentos;
    - `feed_relationships(self, source: str, chunk: pd.DataFrame) -> None`.
  - Ganchos opcionais do *sink*, achados com `getattr` como já se faz com `write_relationships`:
    - `inspect_rows(source: str, partition: str, binding: EntityBinding, raw: pd.DataFrame, cast: pd.DataFrame) -> None`: chamado para cada (bloco, entidade, partição) antes do buffer. `raw` são as linhas filtradas e ainda não convertidas e `cast` são as convertidas, com o mesmo índice, igual à posição da linha de dados no arquivo;
    - `inspect_relationship_rows(source: str, rname: str, rspec: Dict[str, Any], from_binding: EntityBinding, to_binding: EntityBinding, cast: pd.DataFrame) -> None`: chamado antes de `write_relationships`.
  - `_process_chunk(chunk, ecfg, binding) -> Tuple[pd.DataFrame, pd.DataFrame, List[Dict[str, Any]]]`, que devolve `(raw_filtrado, convertido, filtros)`.
  - `run_stream_import(plan: ImportPlan, *, sink_factories: Dict[str, SinkFactory], create_schema: bool = True, on_batch=None, collector: Optional[MetricsCollector] = None) -> StreamCounts`. Grava um SGBD por vez, na ordem de `plan.dbms_names`, cada SGBD com a sua própria leitura das fontes, como hoje. Com `collector`, registra `(dbms, "*", "write", rows=soma de written[dbms], seconds)` para cada SGBD.
  - `run_single_pass(plan: ImportPlan, sinks: Dict[str, DbmsSink], *, on_batch=None) -> StreamCounts`. Faz uma leitura de `plan.sources_cfg` que alimenta todos os `DbmsStream`, depois `finish_nodes` de todos, depois uma leitura da união de `relationship_sources()` que alimenta `feed_relationships` de todos e, por fim, `sink.close()` de cada um.

O lote de cada partição é `plan.entity_batch(dbms, entidade)`. Os vínculos vêm prontos de `plan.bindings[dbms]`. Uma entidade cuja fonte tem 0 linhas tem vínculo, mas nenhuma linha. A regra de lista `source` vazia continua coberta pelo esquema JSON e por `bind_entity_source`; o teste antigo de lista vazia passa a usar `plan_import`.

- [ ] **Step 1: Escrever os testes que falham e adaptar os existentes** em `tests/test_stream_runner.py`:

```python
def test_single_pass_and_per_dbms_runs_count_the_same(tmp_path):
    plan = plan_import(cfg_pg_and_neo4j_with_rel, tmp_path, dbms_names=["postgres", "neo4j"], chunk_mb=0.01, batch_size=7)
    a = run_stream_import(plan, sink_factories={"postgres": lambda c: _FakeSink(), "neo4j": lambda c: _FakeSink()})
    b = run_single_pass(plan, {"postgres": _FakeSink(), "neo4j": _FakeSink()})
    assert a.written == b.written and a.entity_rows == b.entity_rows
    assert b.written["neo4j"][":PURCHASED"] > 0

def test_single_pass_reads_each_source_once(tmp_path, monkeypatch):
    calls = Counter(); real = stream_source._read_chunks
    monkeypatch.setattr(stream_source, "_read_chunks", lambda p, n: (calls.update([p.name]), real(p, n))[1])
    run_single_pass(plan_two_dbms_no_rels, {"postgres": _FakeSink(), "redis": _FakeSink()})
    assert all(v == 1 for v in calls.values())

def test_batches_never_exceed_the_rows_of_one_chunk(tmp_path):
    plan = dataclasses.replace(plan_import(cfg, tmp_path, dbms_names=["postgres"], batch_size=1000), rows_per_chunk={"stock": 300})
    fake = _FakeSink(); run_stream_import(plan, sink_factories={"postgres": lambda c: fake})
    assert max(len(b) for _, b in fake.batches) <= 300

def test_inspect_rows_sees_file_row_positions(tmp_path):
    seen = []
    class Spy(_FakeSink):
        def inspect_rows(self, source, partition, binding, raw, cast):
            assert list(raw.index) == list(cast.index); seen.extend(cast.index)
    run_single_pass(plan_with_filter_keeping_rows_3_and_7, {"postgres": Spy()})
    assert seen == [2, 6]   # data rows 3 and 7 -> positions 2 and 6

def test_run_stream_import_records_one_write_metric_per_dbms(tmp_path): ...
```

Adapte para `plan_import` e `StreamCounts` os testes que já existem nos arquivos listados:
- *batches* e partições;
- uniões heterogêneas;
- relacionamentos depois dos nós;
- `on_batch`;
- os testes de pico de memória de `test_stream_memory.py`;
- o teste de fluxo de `test_csv_header.py`.

Apague os testes de equivalência com a materialização em `test_stream_memory.py` (`test_stream_matches_materialize_rows`, `test_stream_union_matches_materialize_rows` e `test_stream_union_and_rel_purchased_matches_materialize`) e o teste de materialização de `test_csv_header.py`. Os testes de `test_runner_registry.py` que exercitam o fluxo passam a esperar o plano.

- [ ] **Step 2: Rodar e confirmar que falham.** Run: `.venv/Scripts/python.exe -m pytest tests/test_stream_runner.py tests/test_stream_memory.py -v`. Expected: FAIL.

- [ ] **Step 3: Implementar `DbmsStream`, `run_stream_import` e `run_single_pass`**, movendo o corpo do laço atual para a classe. `_flush_ready` e `_flush_remainder` continuam com o mesmo comportamento. Em `runner._run_stream`:
  1. `plan = plan_import(config, config_path.parent, dbms_names=_dbms_targets(config, only), overrides=source_overrides or {})`;
  2. `counts = run_stream_import(plan, ...)`;
  3. as linhas do resumo passam a ser `[{dbms}] {partition}: {rows} row(s)`.

  Esse ajuste é provisório; a Task 7 refaz o fluxo inteiro.

- [ ] **Step 4: Rodar e confirmar que passam.** Run: `.venv/Scripts/python.exe -m pytest tests/test_stream_runner.py tests/test_stream_memory.py tests/test_stream_source.py tests/test_stream_binding.py tests/test_sinks.py tests/test_csv_header.py tests/test_runner_registry.py -v`. Expected: PASS.

- [ ] **Step 5: Rodar a suíte inteira.** Expected: tudo passa.

- [ ] **Step 6: Commit e push.** Mensagem: `refactor(fluxo): motor DbmsStream sobre o plano; leitura unica para todos os SGBDs`.

---

### Task 5: Conferência de valores contra o tipo declarado

**Files:**
- Create: `src/polyglotimportcsv/db_type_checks.py`
- Test: `tests/test_db_type_checks.py`

**Interfaces:**
- Produces:
  - `postgres_value_problem(db_type: str, value: Any) -> Optional[str]`;
  - `cassandra_value_problem(cql_type: str, value: Any) -> Optional[str]`.

  As duas devolvem `None` quando o SGBD aceitaria o valor; caso contrário, um motivo curto em inglês (por exemplo, `"out of BIGINT range"`). O `value` é o que o *sink* enviaria: `None`, `int`, `float`, `bool`, `datetime` ou `str`.

**Regras do PostgreSQL.** O tipo é normalizado com `upper()`; a base é o texto antes de `(` e os números entre parênteses são os parâmetros. `None` é sempre aceito (a chave vazia tem regra própria, na Task 6). Tipos fora desta tabela, como `TEXT`, `JSONB` e `UUID`, não são conferidos.

| Família (bases) | Aceita | Recusa |
|---|---|---|
| `SMALLINT`/`INT2` (±2^15), `INTEGER`/`INT`/`INT4` (±2^31), `BIGINT`/`INT8` (±2^63) | `int` (exceto `bool`) dentro da faixa; `float` com `is_integer()` e dentro da faixa; `str` que case com `\s*[+-]?\d+\s*` e caiba na faixa | `bool`, `datetime`, `float` não inteiro (escolha deste plano: o PostgreSQL arredondaria em silêncio), `str` fora do formato |
| `NUMERIC`/`DECIMAL` [(p[,s])], `REAL`/`FLOAT4`, `DOUBLE PRECISION`/`FLOAT8`/`FLOAT` | `int`/`float` (exceto `bool`); `str` que `float()` aceite. Com `NUMERIC(p,s)` e valor finito, exige `abs(round(v, s)) < 10**(p - s)` | `bool`, `datetime`, `str` não numérica, estouro de `NUMERIC(p,s)` |
| `BOOLEAN`/`BOOL` | `bool`; `str` em `t,true,y,yes,on,1,f,false,n,no,off,0` (sem diferença de caixa, com `strip`) | `int`, `float`, `datetime`, outros textos |
| `TIMESTAMP`, `TIMESTAMPTZ`, `TIMESTAMP WITH TIME ZONE`, `TIMESTAMP WITHOUT TIME ZONE`, `DATE` | `datetime`; `str` que `pd.to_datetime(errors="coerce")` converta | `int`, `float`, `bool`, `str` sem data |
| `VARCHAR(n)`, `CHARACTER VARYING(n)`, `CHAR(n)`, `CHARACTER(n)` | `str` com `len <= n`; outros tipos, sem conferência | `str` com `len > n` |

**Regras do Cassandra.** Os tipos são os de `_cassandra_type_for`.

| Tipo | Aceita | Recusa |
|---|---|---|
| `text` | qualquer valor | — |
| `bigint` | `int` (exceto `bool`) em ±2^63 | `bool`, `float`, `str`, `datetime` |
| `double` | `int`/`float` (exceto `bool`) | `bool`, `str`, `datetime` |
| `boolean` | `bool` | qualquer outro tipo (o *driver* converteria texto para `True` em silêncio) |
| `timestamp` | `datetime`, `date`, `int`/`float` (exceto `bool`) | `str`, `bool` |

- [ ] **Step 1: Escrever os testes que falham.** Use testes parametrizados com uma linha para cada célula das tabelas acima; por exemplo:

```python
@pytest.mark.parametrize("db_type,value,ok", [
    ("BIGINT", 5, True), ("BIGINT", 2**63, False), ("BIGINT", "12", True), ("BIGINT", "3.0", False),
    ("BIGINT", 3.5, False), ("BIGINT", True, False), ("int4", 2**31, False), ("NUMERIC(14,2)", 1e12, True),
    ("NUMERIC(14,2)", 1e12 * 100, False), ("BOOLEAN", "yes", True), ("BOOLEAN", 1, False),
    ("TIMESTAMPTZ", "2024-01-02", True), ("TIMESTAMPTZ", "abc", False), ("TIMESTAMPTZ", 5, False),
    ("VARCHAR(3)", "abcd", False), ("TEXT", object(), True), ("BIGINT", None, True),
])
def test_postgres_value_problem(db_type, value, ok):
    assert (postgres_value_problem(db_type, value) is None) is ok
```

Faça o mesmo para `cassandra_value_problem`.

- [ ] **Step 2: Rodar e confirmar que falham.** Run: `.venv/Scripts/python.exe -m pytest tests/test_db_type_checks.py -v`. Expected: FAIL com `ModuleNotFoundError`.

- [ ] **Step 3: Implementar** as duas funções em `db_type_checks.py`, guiado pelas tabelas.

- [ ] **Step 4: Rodar e confirmar que passam.** Mesmo comando. Expected: PASS.

- [ ] **Step 5: Commit e push.** Mensagem: `feat(validacao): conferencia de valores contra db_type do PostgreSQL e tipos CQL`.

---

### Task 6: Leitura de validação (relatório, sinks de conferência, referências)

**Files:**
- Create: `src/polyglotimportcsv/data_validation.py`
- Modify: `src/polyglotimportcsv/business_exception.py`
- Test: `tests/test_data_validation.py`

**Interfaces:**
- Consumes: `run_single_pass`, `StreamCounts` e os ganchos `inspect_rows` e `inspect_relationship_rows` (Task 4); `ImportPlan` (Task 3); `postgres_value_problem` e `cassandra_value_problem` (Task 5); `entity_utils`; `importers.cassandra_importer._cassandra_column_plan`; `importers.neo4j_importer._rel_rows_for_batch`; `materialize.cell_scalar` (que vira `row_shaping` na Task 9).
- Produces:
  - `business_exception.DataValidationError(BusinessException)`, com a docstring "Data rows break the import configuration (validation layer 3).";
  - `MAX_EXAMPLES = 5`;
  - `@dataclass class Example`, com `file: str`, `line: int`, `column: str`, `value: Any` e `reason: str = ""`;
  - `@dataclass class ProblemGroup`, com `rule: str`, `where: str`, `detail: str`, `count: int` e `examples: List[Example]`;
  - `class ValidationReport`:
    - `add(self, rule: str, where: str, detail: str, example: Example) -> None`, que conta todas as ocorrências e guarda até `MAX_EXAMPLES` exemplos por `(rule, where, detail)`;
    - `groups(self) -> List[ProblemGroup]`, na ordem da primeira ocorrência;
    - `ok(self) -> bool`;
    - `total(self) -> int`;
  - as regras (`rule`) são `"not_convertible"`, `"db_type"`, `"empty_key"` e `"dangling_reference"`;
  - `check_rows(report: ValidationReport, dbms: str, file_label: str, partition: str, binding: EntityBinding, raw: pd.DataFrame, cast: pd.DataFrame) -> None`;
  - `class CheckingSink`, que implementa `DbmsSink` sem conectar a nada:
    - `__init__(self, dbms: str, plan: ImportPlan, report: ValidationReport)`;
    - `create_schema` e `ensure_partition` não fazem nada; `write_batch` devolve `len(batch)`;
    - `inspect_rows` chama `check_rows` e coleta as chaves;
    - `close()` faz a conferência de referências do PostgreSQL;
  - `class Neo4jCheckingSink(CheckingSink)`, que acrescenta:
    - `inspect_relationship_rows`, que confere as pontas e a conversão das colunas de propriedade;
    - `write_relationships(...)`, que devolve `len(_rel_rows_for_batch(...))`, a mesma contagem do *sink* real;
  - `validate_data(plan: ImportPlan, *, on_batch=None) -> Tuple[ValidationReport, StreamCounts]`, que monta um *sink* de conferência por SGBD (`Neo4jCheckingSink` para `neo4j`) e chama `run_single_pass`;
  - `print_validation_report(report: ValidationReport) -> None`, uma tabela `rich` com `box.SQUARE` (colunas Rule, Where, Count, Examples) e, nos exemplos, `file:line column=value (reason)`.

**O que `check_rows` confere.** As colunas vêm de `iter_leaf_columns(binding.cfg)` resolvidas com `resolve_csv_column(fk, spec, list(cast.columns))`. A linha de cada exemplo é `int(índice) + 2`.

1. **`not_convertible`:** vale para todos os SGBDs, sobre as colunas mapeadas mais a coluna do filtro `each`, se houver. É falha quando o texto cru não é vazio e:
   - `integer`/`float`: o valor convertido é `str` (a conversão devolveu o texto original);
   - `datetime`: o valor convertido é `None`.

   O campo `where` é `"{dbms} · {entity}"`, e `detail` diz a coluna e o tipo.
2. **`empty_key`:** o valor convertido é `None` ou `""`. Vale para:
   - as folhas `is_key` no `postgres`, no `redis` e no `neo4j`. No MongoDB, `is_key` não tem efeito, por isso ele fica de fora (escolha deste plano);
   - as colunas de `cassandra_partition` e `cassandra_cluster` no `cassandra`.
3. **`db_type`:**
   - `postgres`: cada folha com `db_type` passa por `postgres_value_problem(db_type, cell_scalar(valor))`;
   - `cassandra`: `cql_by_src` vem de `_cassandra_column_plan(binding.cfg, binding.kinds, list(cast.columns))`, e cada coluna passa por `cassandra_value_problem`;
   - a conferência vale para todas as linhas que a entidade gravaria, depois dos filtros e antes da deduplicação, e a docstring diz isso.

**Referências (decisão 9 do spec).** A comparação usa `cell_scalar` dos valores convertidos e ignora valores nulos, porque FK ou ponta vazia significa que não há relacionamento.
- **PostgreSQL:** para cada relacionamento, quando a partição é `rspec["to"]`, guarda o conjunto dos valores de `references_key`. Quando é `rspec["from"]`, guarda `valor → primeira (arquivo, linha)` de `foreign_key`; os dois nomes são campos de destino, resolvidos para a coluna CSV pelas folhas. Em `close()`, cada valor de FK ausente do conjunto do `to` gera um exemplo, e a contagem é de valores distintos.
- **Neo4j:** quando a partição é uma entidade que aparece como ponta de algum relacionamento, guarda o conjunto das chaves (`is_key` única). Em `inspect_relationship_rows`, cada linha com as duas pontas não nulas e uma delas fora do conjunto da entidade correspondente gera um exemplo por linha. As colunas das pontas são resolvidas como em `Neo4jSink.write_relationships`.

- [ ] **Step 1: Escrever os testes que falham** em `tests/test_data_validation.py`, com CSVs pequenos em `tmp_path` e `plan_import`:

```python
def test_an_unparseable_date_in_a_mapped_column_is_an_error(tmp_path): ...    # rule not_convertible, line == 2 + row index
def test_the_same_bad_date_in_an_unmapped_column_is_not(tmp_path): ...
def test_integer_text_fallback_is_an_error(tmp_path): ...                     # "3.0" in an integer column
def test_empty_key_is_an_error_for_postgres_redis_neo4j_not_mongodb(tmp_path): ...
def test_empty_cassandra_partition_or_cluster_is_an_error(tmp_path): ...
def test_text_in_a_declared_bigint_is_an_error(tmp_path): ...                 # rule db_type, reason present
def test_dangling_postgres_foreign_key_is_an_error(tmp_path): ...             # rule dangling_reference, value listed
def test_fk_to_a_row_the_target_filter_drops_is_dangling(tmp_path): ...      # Review Focus 5
def test_null_foreign_key_is_not_an_error(tmp_path): ...
def test_dangling_neo4j_endpoint_is_an_error(tmp_path): ...
def test_at_most_five_examples_but_every_occurrence_counted(tmp_path):
    report, _ = validate_data(plan_with_12_bad_dates)
    (g,) = report.groups(); assert g.count == 12 and len(g.examples) == 5

def test_line_numbers_on_a_bom_crlf_file(tmp_path): ...                       # Review Focus 3: bad value on data row 3 -> line 4

def test_validation_counts_equal_the_write_counts(tmp_path):
    report, counts = validate_data(plan)
    written = run_stream_import(plan, sink_factories=fakes)
    assert report.ok() and counts.written == written.written

@pytest.mark.parametrize("cfg_name", ["import_config.json", "import_config_combined.json"])
def test_the_ecommerce_examples_pass(cfg_name): ...                           # anti-goal: report.ok()

@pytest.mark.parametrize("mode", ["multi", "combined"])
def test_the_committed_reference_dataset_passes(mode): ...                    # data/benchmark/ with --source overrides

def test_validation_peak_does_not_scale_with_rows(tmp_path):
    # config with no relationships and keys of bounded cardinality;
    # tracemalloc peak at 4x the rows stays within 1.5x of the 1x peak
```

- [ ] **Step 2: Rodar e confirmar que falham.** Run: `.venv/Scripts/python.exe -m pytest tests/test_data_validation.py -v`. Expected: FAIL com `ModuleNotFoundError`.

- [ ] **Step 3: Implementar `data_validation.py`** conforme as interfaces acima.

- [ ] **Step 4: Rodar e confirmar que passam.** Mesmo comando. Expected: PASS. Se um dos testes dos exemplos falhar, siga a anti-meta: pare e reporte o erro exato.

- [ ] **Step 5: Rodar a suíte inteira.** Expected: tudo passa.

- [ ] **Step 6: Commit e push.** Mensagem: `feat(validacao): leitura de validacao com sinks de conferencia, chaves e referencias`.

---

### Task 7: Importação em três leituras na CLI (`--dry-run`, `--chunk-size`, `--batch-size`, métricas)

**Files:**
- Modify: `src/polyglotimportcsv/runner.py`: novo `run_import`; remove `_run`, `_run_stream` e o despacho por `execution`.
- Modify: `src/polyglotimportcsv/cli.py`
- Modify: `src/polyglotimportcsv/metrics.py`
- Modify: `src/polyglotimportcsv/sinks/postgres_sink.py` e `src/polyglotimportcsv/sinks/neo4j_sink.py`
- Modify: `src/polyglotimportcsv/benchmark_runner.py`: só deixa de passar `execution=` ao importador; o eixo é trocado na Task 8.
- Test: `tests/test_cli.py`; `tests/test_runner.py`, que é criado e substitui `tests/test_runner_registry.py`; `tests/test_metrics.py`, `tests/test_benchmark_output.py`, `tests/test_validation_dry_run.py`, `tests/test_benchmark_example.py` e `tests/test_sinks.py`. Em `tests/test_benchmark_runner.py`, retire só as afirmações sobre o argumento `execution` passado ao importador; o eixo muda na Task 8.
- Delete: `tests/test_mode_equivalence.py`, `tests/test_importer_metrics.py` e `tests/test_runner_registry.py`.

**Interfaces:**
- Consumes: `check_source_overrides`, `read_source_headers` e `validate_headers` (Task 2); `plan_import` e `ImportPlan` (Task 3); `run_stream_import` (Task 4); `validate_data`, `print_validation_report` e `DataValidationError` (Task 6).
- Produces:
  - `run_import(config_path, *, dbms_config_path=None, dry_run=False, create_schema=True, only=None, source_overrides=None, show_data=None, sample_size=DEFAULT_SAMPLE_SIZE, collector=None, benchmark=False, chunk_size_mb: float = DEFAULT_CHUNK_MB, batch_size: int = DEFAULT_BATCH_SIZE, sink_factories=None) -> List[str]`. Saem os parâmetros `importers` e `execution`. O retorno são as linhas do resumo.
  - `metrics.PHASES = ("infer", "validate", "write")`. As fases são registradas assim:
    - `("(sources)", "*", "infer", rows=total de linhas dos perfis, seconds)`;
    - `("(all)", "*", "validate", rows=o mesmo total, seconds)`;
    - `(dbms, "*", "write", ...)`, uma por SGBD, vinda de `run_stream_import`.

**Ordem de `run_import`.** Cada passo usa `step()` com estes rótulos:
1. `Load config`;
2. `Check sources`: `check_source_overrides` e `read_source_headers`;
3. `Validate mappings`: `validate_headers` para os SGBDs selecionados;
4. `Check DBMS`: `_require_dbms`, que não roda no `--dry-run`;
5. `Infer types`: `plan_import`;
6. `Validate data`: `validate_data`, com `on_batch` da prévia só no `--dry-run`. Havendo erro, imprime `print_validation_report` e lança `DataValidationError(f"Data validation failed: {report.total()} problem(s) in {len(groups)} group(s); nothing was written.")`;
7. avisos e notas (ver adiante);
8. no `--dry-run`, imprime as linhas `[{dbms}] {partition}: {rows} row(s)` da validação e `success("Finished dry-run — nothing was written")`; se houver `benchmark`, grava os arquivos e retorna;
9. `Write`: `run_stream_import(plan, ..., on_batch=preview.observe, collector=collector)`;
10. **conferência das contagens:** para cada `(dbms, partition)` cuja contagem difere entre validação e gravação, `warn(...)`, sem mudar o código de saída;
11. imprime as linhas do resumo, a `metrics_table` e, com `--benchmark`, os arquivos de benchmark.

O banner continua `mode: import` ou `mode: dry-run`, sem `· execution`.

**Avisos e notas do passo 7:**
- para cada `(dbms, entity)` com `entity_rows == 0`, `logger.warning("entity %s/%s bound to 0 row(s)", ...)`;
- para cada valor de origem de arquivo combinado que nenhuma entidade selecionada usa, `note(f"origin '{name}' ({rows} row(s)) feeds no entity")`.

**CLI:**
- remover `--execution`;
- `--chunk-size`: `type=click.IntRange(MIN_CHUNK_MB, MAX_CHUNK_MB)`, `default=DEFAULT_CHUNK_MB`, `show_default=True`, `metavar="MB"`, com a ajuda "Memory budget of each read chunk, in MB (8-256). Rows per chunk follow each file's row width.";
- `--batch-size`: `type=click.IntRange(MIN_BATCH_SIZE, MAX_BATCH_SIZE)`, `default=DEFAULT_BATCH_SIZE`, `show_default=True`, `metavar="N"`, com a ajuda "Rows per write batch (1024-8192), capped at the rows of one read chunk.";
- a ajuda de `--dry-run` passa a ser "Run every check, on headers and on the data rows, and print the row counts; do not connect to databases.".

**Sinks:**
- `PostgresSink.write_batch` passa `page_size=len(tuples)`;
- `Neo4jSink.write_batch` passa `batch=len(props_list)`;
- com isso, cada `write_batch` vira uma única ida ao SGBD;
- os relacionamentos do Neo4j continuam como estão.

- [ ] **Step 1: Escrever os testes que falham.** Em `tests/test_runner.py` (*sinks* falsos via `sink_factories` e `_require_dbms` com *monkeypatch*):

```python
def test_a_validation_error_stops_before_any_sink_is_built(tmp_path, monkeypatch):
    built = []
    with pytest.raises(DataValidationError, match="nothing was written"):
        run_import(cfg_with_bad_date, sink_factories={"postgres": lambda c: built.append(c) or _FakeSink()})
    assert built == []

def test_steps_run_in_order(tmp_path, monkeypatch): ...      # headers -> check dbms -> infer -> validate -> write (record calls)
def test_header_error_stops_before_the_dbms_check(tmp_path, monkeypatch): ...
def test_dry_run_reads_the_data_and_never_checks_the_dbms(tmp_path, monkeypatch): ...  # bad date -> DataValidationError
def test_dry_run_prints_counts_per_dbms(tmp_path, capsys): ...
def test_zero_row_entity_warns_and_imports(tmp_path, caplog): ...   # Review Focus 1, end to end
def test_unused_origin_is_noted(tmp_path, capsys): ...
def test_count_mismatch_warns_without_failing(tmp_path, monkeypatch): ...  # patch validate_data counts
def test_metrics_have_infer_validate_and_one_write_per_dbms(tmp_path): ...
def test_a_real_import_stops_before_reading_data_when_a_dbms_is_down(tmp_path, monkeypatch): ...  # moved from test_runner_registry
```

Em `tests/test_cli.py`, troque os três testes de `--execution` por:

```python
def test_cli_chunk_and_batch_defaults(monkeypatch): ...      # captured chunk_size_mb == 8, batch_size == 1024
@pytest.mark.parametrize("flag,value", [("--chunk-size", "7"), ("--chunk-size", "257"), ("--batch-size", "1023"), ("--batch-size", "8193")])
def test_cli_rejects_out_of_range_sizes(flag, value): ...    # exit code 2, flag named in output
def test_cli_has_no_execution_option(): ...                   # "--execution stream" -> exit code 2
```

Em `tests/test_sinks.py`, afirme que `PostgresSink` usa `page_size == len(batch)` e que `Neo4jSink` faz um único `UNWIND` por `write_batch`. Converta para o fluxo novo `test_validation_dry_run.py`, `test_benchmark_output.py`, `test_metrics.py` e o teste de *smoke* do `--dry-run` em `test_benchmark_example.py`. Apague os testes de fases e de leitura da materialização (`test_run_import_records_read_and_map_phases`, `test_read_rows_*`, `test_mode_equivalence_entity_counts`) e os arquivos da lista *Delete*.

- [ ] **Step 2: Rodar e confirmar que falham.** Run: `.venv/Scripts/python.exe -m pytest tests/test_runner.py tests/test_cli.py tests/test_sinks.py -v`. Expected: FAIL.

- [ ] **Step 3: Implementar** o fluxo, as opções, as fases e os *sinks* descritos acima.

- [ ] **Step 4: Rodar e confirmar que passam.** Mesmo comando. Expected: PASS.

- [ ] **Step 5: Rodar a suíte inteira.** Expected: tudo passa. A GUI ainda emite `--execution` e é corrigida na Task 10; os testes dela não executam a CLI.

- [ ] **Step 6: Smoke com Docker.** Run:

```bash
.venv/Scripts/python.exe -m polyglotimportcsv.cli --config data/ecommerce/import_config.json --dry-run
.venv/Scripts/python.exe -m polyglotimportcsv.cli --config data/ecommerce/import_config_combined.json
```

Expected: o primeiro termina com "Finished dry-run" e código 0; o segundo, com "Finished import" e código 0, sem aviso de diferença de contagem.

- [ ] **Step 7: Commit e push.** Mensagem: `feat(cli): importacao em tres leituras com validacao completa antes de gravar; --chunk-size e --batch-size`.

---

### Task 8: Ferramentas de campanha com eixo de tamanho de bloco

**Files:**
- Modify: `src/polyglotimportcsv/benchmark_runner.py`, `src/polyglotimportcsv/benchmark_results.py`, `scripts/run_benchmarks.py` e `scripts/benchmark_tracemalloc_ab.py`
- Test: `tests/test_benchmark_runner.py`, `tests/test_benchmark_results.py`, `tests/test_benchmark_resume.py`, `tests/test_benchmark_trace_flag.py` e `tests/test_benchmark_tracemalloc_ab.py`

**Interfaces:**
- Consumes: `run_import(..., chunk_size_mb=...)` (Task 7).
- Produces:
  - `run_matrix(..., chunk_sizes: Iterable[int] = (DEFAULT_CHUNK_MB,), ...)`, que substitui `executions`. Valores fora de `[MIN_CHUNK_MB, MAX_CHUNK_MB]` dão `ValueError`. Cada execução rotulada leva `"chunk_mb"` no lugar de `"execution"`, e a chave da execução é `(size, mode, chunk_mb, repetition)`. O importador é chamado com `chunk_size_mb=chunk_mb`.
  - Em `benchmark_results`, os campos `_RESULT_FIELDS` trocam `"execution"` por `"chunk_mb"`, e o agrupamento das medianas usa `run["chunk_mb"]`.
  - Em `scripts/run_benchmarks.py`, `--chunk-sizes` (padrão `"8"`, lista separada por vírgulas) substitui `--executions`, e `RESUME_KEYS` troca `"executions"` por `"chunk_sizes"`. A ajuda de `--out` lembra que o CSV antigo de `benchmarks/` tem o cabeçalho velho.
  - Em `scripts/benchmark_tracemalloc_ab.py`, a mesma troca: medianas por tamanho de bloco e `--chunk-sizes` com padrão `"8"`.

- [ ] **Step 1: Atualizar os testes**, trocando o eixo de execução pelo de bloco, e acrescentar:

```python
def test_matrix_sweeps_chunk_sizes_and_labels_runs(): ...    # chunk_sizes=(8, 64) -> 2 runs per cell, run["chunk_mb"] in {8, 64}
def test_matrix_rejects_an_out_of_range_chunk_size(): ...     # (4,) -> ValueError
def test_resume_refuses_a_checkpoint_with_other_chunk_sizes(tmp_path): ...
```

- [ ] **Step 2: Rodar e confirmar que falham.** Run: `.venv/Scripts/python.exe -m pytest tests/test_benchmark_runner.py tests/test_benchmark_results.py tests/test_benchmark_resume.py tests/test_benchmark_trace_flag.py tests/test_benchmark_tracemalloc_ab.py -v`. Expected: FAIL.

- [ ] **Step 3: Implementar** a troca de eixo descrita acima.

- [ ] **Step 4: Rodar e confirmar que passam.** Mesmo comando. Expected: PASS.

- [ ] **Step 5: Smoke.** Run: `.venv/Scripts/python.exe scripts/run_benchmarks.py --sizes 1000 --modes multi --repetitions 1 --chunk-sizes 8,64 --out "C:/Users/lbc92/AppData/Local/Temp/claude/D--UFSC-TCC1-polyglot-import-csv/6cae03e8-453e-401e-9eef-4fc41079de44/scratchpad/bench-smoke"`. Expected: código 0, e o CSV consolidado tem a coluna `chunk_mb` com os valores 8 e 64.

- [ ] **Step 6: Rodar a suíte inteira, depois commit e push.** Mensagem: `feat(benchmark): eixo de tamanho de bloco no lugar do modo de execucao`.

---

### Task 9: Remoção da materialização

**Files:**
- Delete:
  - `src/polyglotimportcsv/importers/base.py` e `src/polyglotimportcsv/importers/mongodb_importer.py`;
  - as funções `run_postgres_import`, `run_redis_import`, `run_cassandra_import` e `run_neo4j_import`, junto com os *imports* que só elas usavam;
  - em `importers/__init__.py`, o registro (`default_importer_registry`); fica só a docstring;
  - `sources.load_sources` e `sources._register`. Ficam `SOURCE_COLUMN`, `SourceData` e `_resolve_path`;
  - `mapping_resolver.resolve_backend_entities` e `_binding_cache_key`;
  - `reporting.dump_entity_frame` e `reporting.entity_progress`, se `grep` não achar outro uso;
  - `metrics.timed_phase`, `metrics.EXCLUDED_PHASES` e o código que exclui fases em `reporting.metrics_table` e `benchmark_results`;
  - `csv_reader.read_csv`, se `grep` não achar outro uso.
- Rename: `src/polyglotimportcsv/materialize.py` → `src/polyglotimportcsv/row_shaping.py` com `git mv`. Atualize os *imports* em `sinks/*`, `data_validation.py`, `importers/*` e nos testes.
- Modify: as docstrings que citam a materialização em `dbms_sink.py`, `data_preview.py`, `sinks/*.py`, `stream_binding.py`, `stream_source.py` e `mapping_resolver.py` passam a descrever só o fluxo.
- Tests:
  - apagar `tests/test_postgres_importer_dry_run.py`, `tests/test_doc_kv_importers_dry_run.py`, `tests/test_graph_wide_importers_dry_run.py` e `tests/test_phase_boundaries.py`;
  - `tests/test_importer_write_batching.py`: mantenha apenas os testes de funções auxiliares que continuam existindo (`_write_batched`, `_merge_nodes_batched`, `_merge_rels_batched`, `_dedupe_props`) e apague os que chamam `run_*_import`, inclusive `test_importers_have_no_strategy_and_no_row_at_a_time_writers`;
  - `tests/test_sources.py`: os testes de `--source`, arquivo ausente, origem vazia e colisão migram para `tests/test_stream_source.py` e `tests/test_source_profile.py`, se ainda não estiverem cobertos pelas Tasks 2 e 3;
  - `tests/test_pipeline_logging.py`: fica só `test_cast_frame_warns_on_text_fallback`;
  - `tests/test_row_view.py`: monte os quadros com `pd.read_csv` e `cast_frame` direto, no lugar de `load_sources` e `resolve_backend_entities`;
  - `tests/test_materialize.py` vira `tests/test_row_shaping.py`.

- [ ] **Step 1: Apagar e renomear** conforme a lista acima.

- [ ] **Step 2: Conferir que não sobrou nada.** Run: `rtk grep -n -i "materializ\|execution\|load_sources\|resolve_backend_entities\|ImporterRegistry\|run_postgres_import" src scripts tests`. Expected: nenhuma ocorrência. As exceções são os nomes de teste já convertidos e a palavra "execution" em `ImportExecutionError`, que deve permanecer.

- [ ] **Step 3: Rodar a suíte inteira.** Run: `.venv/Scripts/python.exe -m pytest -q`. Expected: tudo passa.

- [ ] **Step 4: Smoke com Docker.** Run: `.venv/Scripts/python.exe -m polyglotimportcsv.cli --config data/ecommerce/import_config.json`. Expected: "Finished import", código 0.

- [ ] **Step 5: Commit e push.** Mensagem: `refactor: remove a materializacao; fluxo como modo unico`.

---

### Task 10: GUI (bloco e lote; sem "Execução")

**Files:**
- Modify: `src/polyglotimportcsv/gui/state.py`, `gui/command.py`, `gui/widgets/options_panel.py` e `gui/widgets/main_window.py`
- Test: `tests/test_gui_state.py`, `tests/test_gui_command.py`, `tests/test_gui_options_panel.py` e `tests/test_gui_main_window.py`

**Interfaces:**
- Consumes: `DEFAULT_CHUNK_MB`, `MIN_CHUNK_MB` e `MAX_CHUNK_MB` (de `stream_source`); `DEFAULT_BATCH_SIZE`, `MIN_BATCH_SIZE` e `MAX_BATCH_SIZE` (de `import_plan`).
- Produces:
  - **`RunOptions`:** sai `execution`; entram `chunk_size_mb: int = DEFAULT_CHUNK_MB` e `batch_size: int = DEFAULT_BATCH_SIZE`. `EXECUTIONS` sai de `state.py` e do `__all__`.
  - **`validate()`:** fora da faixa, `errors["chunk_size_mb"] = "O bloco deve ter entre 8 e 256 MB."` e `errors["batch_size"] = "O lote deve ter entre 1024 e 8192 linhas."`.
  - **`build_argv`:** depois de `--only`, emite sempre `--chunk-size N` e `--batch-size N`; `--execution` sai.
  - **`OptionsPanel`:**
    - sai a linha "Execução (--execution)", com os botões e as ajudas `stream` e `materialize`;
    - entram dois `QSpinBox`: "Bloco em MB (--chunk-size)", com faixa 8–256 e valor inicial 8, e "Lote (--batch-size)", com faixa 1024–8192, valor inicial 1024 e passo 1024;
    - entram os leitores `chunk_size_mb() -> int` e `batch_size() -> int`;
    - cada campo tem o seu `InfoBadge`, com os textos `HELP["chunk_size"]` e `HELP["batch_size"]` abaixo;
    - `set_errors` passa a mostrar também `chunk_size_mb` e `batch_size`.
  - **Textos de `HELP`:**
    - `chunk_size`: "Memória de cada bloco de leitura, em MB (8 a 256). A ferramenta calcula quantas linhas cabem no bloco pela largura das linhas de cada arquivo. Blocos maiores usam mais memória.";
    - `batch_size`: "Linhas por lote de gravação (1024 a 8192). O lote nunca passa das linhas de um bloco de leitura.";
    - `dry_run`: "Faz todas as verificações, inclusive a leitura dos dados, e mostra quantos registros iriam para cada destino, sem conectar a nenhum SGBD.".
  - **`MainWindow.options()`:** passa `chunk_size_mb` e `batch_size` no lugar de `execution`. Se as configurações salvas (`QSettings`) guardarem `execution`, a chave é ignorada.

- [ ] **Step 1: Atualizar e escrever os testes:**

```python
def test_argv_always_carries_chunk_and_batch():
    argv = build_argv(RunOptions(config_path=CFG))
    assert argv[argv.index("--chunk-size") + 1] == "8" and argv[argv.index("--batch-size") + 1] == "1024"
    assert "--execution" not in argv

def test_validate_rejects_sizes_out_of_range(): ...          # 7 MB and 8193 rows -> both keys present
def test_options_panel_has_no_execution_row_and_two_spins(qtbot): ...  # ranges, defaults, step 1024
def test_main_window_command_shows_the_new_options(qtbot): ...  # "--chunk-size 8 --batch-size 1024" in the panel text
```

Remova das expectativas existentes todas as ocorrências de `--execution` e `execution=`.

- [ ] **Step 2: Rodar e confirmar que falham.** Run: `.venv/Scripts/python.exe -m pytest tests/test_gui_state.py tests/test_gui_command.py tests/test_gui_options_panel.py tests/test_gui_main_window.py -v`. Expected: FAIL.

- [ ] **Step 3: Implementar** os campos, os textos e as validações descritos acima.

- [ ] **Step 4: Rodar e confirmar que passam.** Mesmo comando. Expected: PASS.

- [ ] **Step 5: Rodar a suíte inteira, depois commit e push.** Mensagem: `feat(gui): campos de bloco e lote; remove o controle de execucao`.

---

### Task 11: Documentos de uso, versão 3.0.0 e verificação ponta a ponta

**Files:**
- Modify: `README.md` (inglês e português), `docs/ARCHITECTURE.md`, `benchmarks/README.md` e `data/ecommerce/README.md`.
- `run_example.sh` e `scripts/run_example.completion.bash`: conferir com `grep`; só mudam se citarem `--execution` ou as opções novas.
- Modify: `pyproject.toml`, `src/polyglotimportcsv/__init__.py` e `tests/test_version.py`, que passam a usar `3.0.0` (o nome do teste vira `test_the_delivered_version_is_3_0_0`).
- Create: `docs/releases/v3.0.0.md`, bilíngue e no formato de `docs/releases/v2.0.1.md`.
- Não alterar `docs/releases/v1*.md` e `v2*.md` nem os resultados antigos em `benchmarks/`.

**Conteúdo dos documentos:**
- a validação em três camadas, todas antes de gravar, com a frase "A validação prévia tem três camadas:" no trecho em português do README;
- as três leituras (inferência, validação e gravação);
- `--chunk-size` e `--batch-size`, com faixas e padrões;
- `--dry-run`, que agora lê os dados;
- a saída de `--execution`;
- o eixo `--chunk-sizes` das campanhas, em `benchmarks/README.md`;
- o desenho `DbmsStream` / `CheckingSink`, em `docs/ARCHITECTURE.md`.

Nos trechos em português, sempre "SGBD". As notas de versão não citam o histórico do relatório.

- [ ] **Step 1: Atualizar os documentos e a versão.** Run: `rtk grep -rn -- "--execution\|materializ" README.md docs/ARCHITECTURE.md benchmarks/README.md data/ecommerce/README.md run_example.sh scripts/run_example.completion.bash`. Expected: nenhuma ocorrência.

- [ ] **Step 2: Rodar a suíte inteira.** Run: `.venv/Scripts/python.exe -m pytest -q`. Expected: tudo passa, inclusive `test_version.py`.

- [ ] **Step 3: Verificação ponta a ponta com Docker.** Guarde as saídas em `C:/Users/lbc92/AppData/Local/Temp/claude/D--UFSC-TCC1-polyglot-import-csv/6cae03e8-453e-401e-9eef-4fc41079de44/scratchpad/verificacao-etapa1/`. Os comandos e o resultado esperado:

| # | Comando | Esperado |
|---|---|---|
| 1 | `--config data/ecommerce/import_config.json --dry-run` | código 0 |
| 2 | `--config data/ecommerce/import_config.json` | código 0, contagens iguais às do item 1 |
| 3 | `--config data/ecommerce/import_config_combined.json` | código 0 |
| 4 | `--config data/ecommerce/import_config_invalido.json --dry-run` | código 1 com a mensagem de cabeçalho |
| 5 | uma cópia de `ecommerce_purchase.csv` com uma data inválida, passada com `--source purchase=<cópia>` | código 1, relatório com arquivo, linha, coluna e valor, e nada gravado (conferir com `scripts/inspect_persisted_data.py` que as contagens não mudaram desde o item 2) |
| 6 | base sintética de 100 mil linhas (`data/benchmark/generated/100000/`) em multifonte com `--source`, com `--dry-run` e depois sem ele | código 0 nos dois |
| 7 | `--chunk-size 64 --batch-size 8192` sobre a mesma base | código 0, contagens iguais às do item 6 |

- [ ] **Step 4: Commit e push.** Mensagem: `docs: uso da versao 3.0.0 (fluxo unico, validacao completa, bloco e lote)`.
