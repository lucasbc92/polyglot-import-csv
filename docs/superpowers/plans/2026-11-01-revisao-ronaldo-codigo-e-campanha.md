# Correções de código da revisão do Prof. Ronaldo e Etapa 2 (campanha) — Plano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** executar as decisões 1 e 2 do design da revisão (remover `--create-schema`/`--no-create-schema`; `target_suffix` como modelo com `{value}` e a coleção `orders` dividida por `state` no cenário exemplo), ajustar o limpador da campanha, as notas da 3.0.0 e os READMEs, e então rodar a campanha de medição da 3.0.0 com o resumo das medianas.

**Architecture:** as mudanças de código são pequenas e localizadas. `create_schema()` dos *sinks* passa a rodar sempre em `stream_runner.run_stream_import`, e a opção some de todas as camadas que a repassavam (CLI, *runner*, `benchmark_runner`, GUI, scripts). O nome das partições do `each` fica em `filter_engine`, que ganha uma função que reconhece esses nomes, usada pelo limpador e pelo inspetor do MongoDB. A campanha usa `scripts/run_benchmarks.py` sem mudanças, em quatro pastas novas de `benchmarks/v3/`.

**Tech Stack:** Python 3.12, pandas, click, jsonschema, PySide6, pytest, Docker (PostgreSQL, MongoDB, Cassandra, Redis, Neo4j).

**Spec:** `docs/superpowers/specs/2026-10-30-revisao-ronaldo-v22-design.md` (decisões 1 e 2, "Achados no código", "Mudanças só de texto no código"), que complementa `docs/superpowers/specs/2026-10-27-fluxo-unico-validacao-previa-design.md` (etapa 2, restrições da campanha).

## Global Constraints

- **Testes:** sempre `.venv/Scripts/python.exe -m pytest` (sem o venv, cerca de 100 testes da GUI são pulados; não passar pelo `rtk pytest`, que esconde os erros). Com 8 GB de RAM, a suíte inteira roda em dois processos:
  1. `.venv/Scripts/python.exe -m pytest -q -rfEs tests --ignore-glob="tests/test_gui_*"`
  2. `.venv/Scripts/python.exe -m pytest -q tests/test_gui_*.py`
- **Git:** prefixo `rtk` em todo comando git; preparar só caminhos explícitos (nunca `git add -A`); commits em português terminando com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; `rtk git push` depois de cada commit; branch `fluxo-unico`. Sem merge, tag ou release.
- **Nunca commitar** `docs-tcc/TCC2-PolyglotImportCSV-Report-v2.2-REVISADO.pdf` nem nada de `docs-tcc/relacionados/EQD2026_Lilian/`. `.claude/session-state.md` é local.
- **Busca:** `grep` pelo shell em `data/` ou no repositório inteiro trava (bases grandes em `data/benchmark/generated`). Usar a ferramenta Grep com caminho e glob.
- **Idioma:** código, mensagens da CLI e logs em inglês; textos da GUI em português; "SGBD" em português, "DBMS" no resto; READMEs bilíngues.
- **Vocabulário dos READMEs:** "camada" → "etapa" e "layer" → "stage" só para as etapas de validação. "Camada" de arquitetura (`README.md:167`, `README.md:443`, `docs/ARCHITECTURE.md`) fica.
- **Modelo de `target_suffix`:** padrão JSON Schema exatamente `^[A-Za-z0-9_]*\{value\}[A-Za-z0-9_]*$`; nome da partição `<entidade>_<modelo com {value} trocado por _slugify(valor)>`; sem `target_suffix`, o sufixo é `_slugify(valor)`, como hoje.
- **Cenário exemplo:** coleção MongoDB `orders`, fonte `purchase`, filtro `{"column": "state", "operator": "each", "target_suffix": "state_{value}"}`, nos dois arquivos `data/ecommerce/import_config.json` e `import_config_combined.json`. As entidades existentes não mudam. Nenhum relacionamento aponta para `orders`.
- **Docker:** o autor ligou o Docker. Nunca iniciar, parar nem reiniciar contêineres; `docker ps` e `docker info` são leitura e podem ser usados.
- **Campanha:** máquina quieta durante cada medição (nada de testes, renderização ou outro processo pesado em paralelo). Memória e tempo vêm de campanhas separadas e nunca se misturam numa tabela.

## Review Focus

1. **Recarga sem limpar sobre FKs de uma carga anterior (PostgreSQL):** é o caso que `--no-create-schema` quebrava. Duas importações seguidas do cenário exemplo, sem limpar entre elas, terminam com código 0. Conferido ao vivo na Task 6.
2. **O exemplo "Seeing the data checks at work" de `data/ecommerce/README.md`:** com a coleção `orders`, o `order_date` inválido pode passar a aparecer também em `mongodb · orders_state_*`. O texto do README tem de bater com a saída real. Conferido na Task 3.
3. **Scripts antigos que ainda passam a opção:** `polyglotimportcsv --no-create-schema` sai com código 2 ("No such option") e `./run_example.sh --no-create-schema` sai com "Unknown option" antes de fazer qualquer coisa. Teste e conferência na Task 1.
4. **`target_suffix` sem `{value}` na GUI:** a pré-verificação mostra o mesmo erro de JSON Schema da CLI, porque usa o mesmo `load_import_config`. Teste na Task 3 (precisa da coleção `orders`).
5. **Limpeza entre repetições:** sem apagar as coleções `orders_state_*`, a segunda repetição acumula documentos no MongoDB e a carga deixa de ser a frio. Teste na Task 4 e conferência ao vivo na Task 6; a conferência das contagens da campanha (Task 7) pega um limpador que falhe.

## Mapa de arquivos

| Arquivo | Responsabilidade | Tarefas |
|---|---|---|
| `src/polyglotimportcsv/{cli,runner,stream_runner,benchmark_runner}.py` | opção removida; `create_schema()` sempre | 1 |
| `src/polyglotimportcsv/gui/{state,command}.py`, `gui/widgets/{options_panel,main_window}.py` | caixa "Criar esquema" removida | 1 |
| `run_example.sh`, `scripts/run_example.completion.bash` | opção removida | 1 |
| `src/polyglotimportcsv/filter_engine.py` | modelo `{value}`; `each_partition_pattern` | 2 |
| `src/polyglotimportcsv/schemas/import_config.schema.json` | padrão e descrição de `target_suffix` | 2 |
| `data/ecommerce/import_config.json`, `import_config_combined.json` | coleção `orders` | 3 |
| `scripts/inspect_persisted_data.py` | `mongo_collections`; limpador e inspetor do MongoDB | 4 |
| `docs/releases/v3.0.0.md`, `README.md`, `data/ecommerce/README.md`, `business_exception.py`, design | textos | 1, 3, 5 |
| `benchmarks/v3/{memory,timings,chunks-memory,chunks-timings}/`, `benchmarks/README.md` | campanha e resumo | 7, 8 |

---

### Task 1: Remover `--create-schema`/`--no-create-schema`

**Files:**
- Modify: `src/polyglotimportcsv/cli.py:77-82` (opção), `:147` (parâmetro), `:182` (repasse)
- Modify: `src/polyglotimportcsv/runner.py:256` (parâmetro), `:348-351` (as duas notas, sem substituto), `:356` (repasse)
- Modify: `src/polyglotimportcsv/stream_runner.py:299` (parâmetro), `:306` (docstring: "then ``create_schema()``", sem "(when asked)"), `:324-325` (chamada incondicional)
- Modify: `src/polyglotimportcsv/benchmark_runner.py:201`
- Modify: `src/polyglotimportcsv/gui/state.py:43`; `gui/command.py:5-7` (docstring: o exemplo passa a ser só o *spin box* de tamanho) e `:41`; `gui/widgets/options_panel.py:59-61` (ajuda), `:105-110` (a linha de modificadores fica só com `dry_run_box`), `:150-151`; `gui/widgets/main_window.py:174`
- Modify: `run_example.sh:4` ("import with schema creation" → "import"), `:11`, `:21-22`, `:52`, `:97-104`, `:430-434` (o `elif`/`else` some; resta `if dry_run → --dry-run`)
- Modify: `scripts/run_example.completion.bash:21`
- Modify: `README.md:95` e `README.md:370` (as linhas da opção saem)
- Test: `tests/test_cli.py`, `tests/test_runner.py:381-392` (teste removido) e `:512` (fake), `tests/test_validation_dry_run.py:15`, `tests/test_benchmark_runner.py` (7 fakes), `tests/test_benchmark_resume.py:31`, `tests/test_benchmark_tracemalloc_ab.py:92,114`, `tests/test_gui_command.py`, `tests/test_gui_state.py:16`, `tests/test_gui_options_panel.py:21,143`, `tests/test_gui_main_window.py:63`
- Ficam como estão: o método `create_schema()` de `dbms_sink.py`, dos `sinks/*.py` e de `data_validation.py`; os testes desses métodos em `tests/test_sinks.py`; os métodos `create_schema(self)` dos *sinks* falsos (`test_stream_memory.py:37`, `test_runner.py:85`, `test_data_validation.py:508`, `test_stream_runner.py:35`); a asserção (d) de `test_stream_runner.py:120` (passa a provar a chamada incondicional); `docs/ARCHITECTURE.md:23`.

**Interfaces:**
- Produces: `run_import(...)` e `run_stream_import(plan, *, sink_factories, on_batch=None, collector=None)` sem `create_schema`; `RunOptions` sem o campo `create_schema`; `OptionsPanel` sem `create_schema_box` nem `create_schema()`.

- [ ] **Step 1: Escrever os testes que falham**

Em `tests/test_cli.py`, junto de `test_cli_has_no_execution_option`:

```python
@pytest.mark.parametrize("flag", ["--create-schema", "--no-create-schema"])
def test_cli_has_no_create_schema_option(flag, monkeypatch):
    monkeypatch.setattr("polyglotimportcsv.cli.run_import", _no_run)
    res = CliRunner().invoke(main, ["--config", str(ECOMMERCE / "import_config.json"), flag])
    assert res.exit_code == 2
    assert "No such option" in res.output and flag in res.output


def test_the_import_and_the_write_take_no_create_schema():
    import inspect
    from polyglotimportcsv.runner import run_import
    from polyglotimportcsv.stream_runner import run_stream_import
    assert "create_schema" not in inspect.signature(run_import).parameters
    assert "create_schema" not in inspect.signature(run_stream_import).parameters
```

Ajustar os testes existentes:
- Os *fakes* de importador em `test_benchmark_runner.py`, `test_benchmark_resume.py` e `test_benchmark_tracemalloc_ab.py` perdem o parâmetro `create_schema` da assinatura. Como as assinaturas são explícitas, o `run_matrix` atual quebra com `TypeError` (argumento inesperado), e esse é o teste de que o `benchmark_runner` não repassa mais a opção.
- `test_runner.py`: apagar `test_create_schema_reaches_the_write`; tirar `create_schema` da assinatura de `fake_stream` (`:512`).
- `test_validation_dry_run.py:15`: tirar `create_schema=False`.
- `test_gui_state.py:16` → `assert not hasattr(options, "create_schema")`.
- `test_gui_options_panel.py:21` → `assert not hasattr(panel, "create_schema_box")`; `:143`: tirar `"create_schema"` do conjunto de *badges*.
- `test_gui_command.py`: tirar `"--create-schema"` das listas esperadas (`:23`, `:177`) e `"--no-create-schema"` de `:139`; tirar `create_schema=False` de `:61`, `:127` e `:158`; `test_boolean_flags` fica só com `--dry-run`; apagar `test_create_schema_emits_one_of_its_two_forms`; tirar o caso `create_schema=False` da varredura de `test_every_option_changes_the_command_when_toggled`; no docstring de `:15`, trocar o exemplo "Criar esquema" pelo *spin box* de tamanho.
- `test_gui_main_window.py:63` → `"polyglotimportcsv --chunk-size 8 --batch-size 1024 --log-level INFO --sample 50"`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_cli.py tests/test_runner.py tests/test_validation_dry_run.py tests/test_benchmark_runner.py tests/test_benchmark_resume.py tests/test_benchmark_tracemalloc_ab.py`
Expected: FAIL — exit code 0 em vez de 2 para as duas opções, `create_schema` presente nas assinaturas e `TypeError ... unexpected keyword argument 'create_schema'` nos *fakes*.

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_gui_command.py tests/test_gui_state.py tests/test_gui_options_panel.py tests/test_gui_main_window.py`
Expected: FAIL nas listas de argv e nos `hasattr`.

- [ ] **Step 3: Remover a opção em todos os arquivos listados**

`stream_runner.run_stream_import` chama `sink.create_schema()` sempre, logo depois de criar o *sink*. Em `runner.py`, o passo "Write" fica sem nota sobre esquema.

- [ ] **Step 4: Rodar e ver passar**

Run: os dois comandos do Step 2, mais `.venv/Scripts/python.exe -m pytest -q tests/test_stream_runner.py tests/test_sinks.py tests/test_stream_memory.py tests/test_data_validation.py`
Expected: PASS.

- [ ] **Step 5: Conferir que nada mais cita a opção**

Ferramenta Grep, padrão `create.schema`, em `src`, `scripts`, `tests`, `run_example.sh`, `README.md`, `packaging`, `.github`.
Expected: só o método `create_schema` (definições em `dbms_sink.py`, `sinks/*.py`, `data_validation.py`; a chamada e o docstring de `run_single_pass` em `stream_runner.py`; `docs/ARCHITECTURE.md:23`; os *fakes* e `test_sinks.py`). Nenhum `--create-schema`, `--no-create-schema`, `CREATE_SCHEMA` ou "Criar esquema".

Run: `bash run_example.sh --no-create-schema`
Expected: código de saída 1 e "Unknown option: --no-create-schema", sem iniciar Docker nem importar.

- [ ] **Step 6: Commit**

```bash
rtk git add src/polyglotimportcsv/cli.py src/polyglotimportcsv/runner.py src/polyglotimportcsv/stream_runner.py src/polyglotimportcsv/benchmark_runner.py src/polyglotimportcsv/gui/state.py src/polyglotimportcsv/gui/command.py src/polyglotimportcsv/gui/widgets/options_panel.py src/polyglotimportcsv/gui/widgets/main_window.py run_example.sh scripts/run_example.completion.bash README.md tests/test_cli.py tests/test_runner.py tests/test_validation_dry_run.py tests/test_benchmark_runner.py tests/test_benchmark_resume.py tests/test_benchmark_tracemalloc_ab.py tests/test_gui_command.py tests/test_gui_state.py tests/test_gui_options_panel.py tests/test_gui_main_window.py
rtk git commit -m "fix: remove --create-schema; a preparacao dos SGBDs roda sempre" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
rtk git push
```

---

### Task 2: `target_suffix` como modelo com `{value}`

**Files:**
- Modify: `src/polyglotimportcsv/filter_engine.py:100-122` (`expand_each`) e função nova no mesmo arquivo
- Modify: `src/polyglotimportcsv/schemas/import_config.schema.json:85-88`
- Test: `tests/test_filter_engine.py`, `tests/test_config_parser.py`, `tests/test_gui_preflight.py`

**Interfaces:**
- Produces: `each_partition_pattern(base_entity_name: str, filters: Optional[List[Dict[str, Any]]]) -> Optional[re.Pattern[str]]` em `filter_engine`. Devolve `None` quando `filters` não tem filtro `each`. Senão, um padrão cujo `fullmatch` aceita exatamente os nomes que `expand_each` pode gerar para essa entidade: `<base>_<prefixo><slug><sufixo>`, com o slug formado por um ou mais `[A-Za-z0-9_]` e o prefixo e o sufixo tirados do modelo (vazios sem `target_suffix`). O formato do nome fica num lugar só, usado por `expand_each` e por essa função.

- [ ] **Step 1: Escrever os testes que falham**

Em `tests/test_filter_engine.py` (importar também `each_partition_pattern`):

```python
def test_expand_each_applies_the_target_suffix_template():
    df = pd.DataFrame({"region": ["South", "North", "South", ""], "v": [1, 2, 3, 4]})
    flt = [{"column": "region", "operator": "each", "target_suffix": "r_{value}"}]
    assert sorted(n for n, _ in expand_each(df, flt, "sales")) == ["sales_r_North", "sales_r_South"]


def test_expand_each_template_takes_the_sanitized_value():
    df = pd.DataFrame({"city": ["São Paulo"]})
    flt = [{"column": "city", "operator": "each", "target_suffix": "c_{value}_x"}]
    assert [n for n, _ in expand_each(df, flt, "t")] == ["t_c_S_o_Paulo_x"]


def test_each_partition_pattern_matches_only_the_names_expand_each_gives():
    pat = each_partition_pattern(
        "orders", [{"column": "state", "operator": "each", "target_suffix": "state_{value}"}]
    )
    assert pat.fullmatch("orders_state_SP") and pat.fullmatch("orders_state_S_o_Paulo")
    for other in ("orders", "orders_state_", "orders_SP", "product_catalog", "xorders_state_SP"):
        assert not pat.fullmatch(other)
    default = each_partition_pattern("orders", [{"column": "state", "operator": "each"}])
    assert default.fullmatch("orders_SP") and not default.fullmatch("orders")
    assert each_partition_pattern("orders", [{"column": "state", "operator": "==", "value": "SP"}]) is None
    assert each_partition_pattern("orders", None) is None
```

Em `tests/test_config_parser.py`:

```python
def _each_config(suffix):
    return {
        "sources": {"s": "s.csv"},
        "mongodb": {"entities": {"orders": {
            "columns": {"a": {}},
            "filters": [{"column": "state", "operator": "each", "target_suffix": suffix}],
        }}},
    }


@pytest.mark.parametrize("suffix", ["r", "r_{value}_{value}", "", "state-{value}", "{VALUE}"])
def test_import_schema_rejects_a_target_suffix_that_is_not_a_template(suffix):
    with pytest.raises(BusinessException):
        validate_import_config_schema(_each_config(suffix))


@pytest.mark.parametrize("suffix", ["{value}", "state_{value}", "r_{value}_x"])
def test_import_schema_accepts_a_target_suffix_template(suffix):
    validate_import_config_schema(_each_config(suffix))
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_filter_engine.py tests/test_config_parser.py`
Expected: FAIL — `sales_r`/`sales_r` em vez de `sales_r_North`/`sales_r_South`, `ImportError` de `each_partition_pattern`, e os modelos inválidos aceitos pelo *schema*.

- [ ] **Step 3: Implementar**

- `expand_each`: com `target_suffix`, o sufixo é o modelo com `{value}` trocado por `_slugify(val)`; sem ele, `_slugify(val)`.
- `each_partition_pattern` conforme o bloco Interfaces, com `re.escape` no nome da entidade, no prefixo e no sufixo.
- No *schema*, `target_suffix` ganha `"pattern": "^[A-Za-z0-9_]*\\{value\\}[A-Za-z0-9_]*$"` e a descrição: `"With operator 'each', template for the suffix of each part's name: '{value}' (exactly once, with only letters, digits and '_' around it) is replaced by the sanitized distinct value, and the part is named <entity>_<suffix>. Default: the sanitized value itself."`

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_filter_engine.py tests/test_config_parser.py tests/test_stream_runner.py tests/test_validation.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add src/polyglotimportcsv/filter_engine.py src/polyglotimportcsv/schemas/import_config.schema.json tests/test_filter_engine.py tests/test_config_parser.py
rtk git commit -m "fix: target_suffix do each vira modelo com {value}" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
rtk git push
```

---

### Task 3: Coleção `orders` dividida por estado no cenário exemplo

**Files:**
- Modify: `data/ecommerce/import_config.json` e `data/ecommerce/import_config_combined.json` (bloco `mongodb.entities`, depois de `product_catalog`, no estilo de indentação de cada arquivo)
- Modify: `data/ecommerce/README.md` (parágrafo "Seeing the data checks at work" e o equivalente em português), só se a saída real mudar
- Test: `tests/test_validation_dry_run.py`, `tests/test_benchmark_example.py`, `tests/test_gui_preflight.py`

**Interfaces:**
- Consumes: o modelo `{value}` de `expand_each` (Task 2).

- [ ] **Step 1: Escrever os testes que falham**

Em `test_validation_dry_run.py::test_dry_run_counts_every_dbms`, entre `"[postgres] products: 8 row(s)"` e `"[mongodb] product_catalog: 8 row(s)"`:

```python
        "[mongodb] orders_state_CA: 1 row(s)",
        "[mongodb] orders_state_RJ: 1 row(s)",
        "[mongodb] orders_state_RS: 1 row(s)",
        "[mongodb] orders_state_SC: 1 row(s)",
        "[mongodb] orders_state_SE: 1 row(s)",
        "[mongodb] orders_state_SP: 2 row(s)",
        "[mongodb] orders_state_TO: 1 row(s)",
```

Em `test_benchmark_example.py::test_dry_run_smoke_on_reference` (base sintética, quatro estados):

```python
    states = {line.split(":")[0] for line in lines if line.startswith("[mongodb] orders_state_")}
    assert states == {f"[mongodb] orders_state_{s}" for s in ("CA", "NY", "SC", "TX")}
```

Em `tests/test_gui_preflight.py` (Review Focus 4; a fixture `ecommerce` copia `data/ecommerce/`):

```python
def test_a_target_suffix_without_value_is_refused_with_the_cli_message(ecommerce):
    path = ecommerce / "import_config.json"
    cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg["mongodb"]["entities"]["orders"]["filters"][0]["target_suffix"] = "state"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    result = _check(ecommerce)
    assert result.errors["config_path"].startswith("Invalid import configuration JSON")
    assert "{value}" in result.errors["config_path"]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_validation_dry_run.py tests/test_benchmark_example.py`
Expected: FAIL — faltam as linhas `orders_state_*`.

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_gui_preflight.py -k target_suffix`
Expected: FAIL com `KeyError: 'orders'`.

- [ ] **Step 3: Acrescentar a entidade aos dois arquivos**

```json
      "orders": {
        "source": "purchase",
        "columns": {
          "order_number": {},
          "user_id": {},
          "order_date": {},
          "order_status": {},
          "payment_method": {},
          "quantity": {},
          "product_id": {},
          "price": {},
          "comment": {},
          "rating": {}
        },
        "filters": [
          { "column": "state", "operator": "each", "target_suffix": "state_{value}" }
        ]
      }
```

São as colunas do `orders` do PostgreSQL, sem `db_type` (o MongoDB não usa) e sem `is_key` (o MongoDB não deduplica; cada compra é um pedido).

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_validation_dry_run.py tests/test_benchmark_example.py tests/test_config_parser.py tests/test_row_view.py tests/test_stream_runner.py tests/test_cli.py`
Expected: PASS.

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_gui_preflight.py`
Expected: PASS.

- [ ] **Step 5: Conferir numa execução real**

Run: `.venv/Scripts/python.exe -m polyglotimportcsv --config data/ecommerce/import_config.json --dry-run --no-data` e o mesmo com `import_config_combined.json`
Expected: código 0; as sete linhas `[mongodb] orders_state_*` acima nos dois. Guardar a saída do multifonte no `.claude/session-state.md` (Task 9); a etapa 3 usa esses nomes no item 10 do mapa.

- [ ] **Step 6: Conferir o exemplo de erro do README (Review Focus 2)**

Copiar `data/ecommerce/ecommerce_purchase.csv` para `<scratchpad>/purchase_bad.csv`, trocar o `order_date` de uma linha por `2023-13-45 99:99:99` e rodar:
`.venv/Scripts/python.exe -m polyglotimportcsv --config data/ecommerce/import_config.json --source purchase=<scratchpad>/purchase_bad.csv --dry-run`
Expected: código 1 e a tabela com `not_convertible`. Se a tabela listar mais lugares do que `postgres · orders` (por exemplo `mongodb · orders_state_SP`), reescrever a frase do README, em inglês e em português, com os lugares que a saída mostrou. Se não mudar, o README fica como está.

- [ ] **Step 7: Commit**

```bash
rtk git add data/ecommerce/import_config.json data/ecommerce/import_config_combined.json tests/test_validation_dry_run.py tests/test_benchmark_example.py tests/test_gui_preflight.py
# acrescentar data/ecommerce/README.md se o Step 6 o mudou
rtk git commit -m "feat: colecao orders dividida por estado no cenario exemplo" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
rtk git push
```

---

### Task 4: Limpador e inspetor do MongoDB enxergam as partições do `each`

**Files:**
- Modify: `scripts/inspect_persisted_data.py:86-105` (`inspect_mongodb`), `:261-277` (`clean_mongodb`) e função nova no mesmo arquivo
- Create: `tests/test_inspect_persisted_data.py`

**Interfaces:**
- Consumes: `filter_engine.each_partition_pattern` (Task 2).
- Produces: `mongo_collections(db: Any, entities: Dict[str, Dict[str, Any]]) -> List[str]` em `scripts/inspect_persisted_data.py`. Na ordem das entidades: uma entidade sem `each` dá o próprio nome; uma com `each` dá, em ordem alfabética, os nomes de `db.list_collection_names()` que o padrão aceita. `inspect_mongodb` e `clean_mongodb` percorrem essa lista em vez de `entities`.

Escopo: só o MongoDB. O cenário exemplo não usa `each` no PostgreSQL nem no Cassandra; o Redis (`flushdb`) e o Neo4j (`DETACH DELETE` de tudo) já apagam tudo.

- [ ] **Step 1: Escrever os testes que falham**

```python
"""Cleaner and inspector of the campaign: MongoDB collections split by `each`."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import inspect_persisted_data as ipd  # noqa: E402

from polyglotimportcsv.config_parser import load_config  # noqa: E402

ECOMMERCE = Path(__file__).resolve().parents[1] / "data" / "ecommerce"


class _Collection:
    def __init__(self, db, name):
        self.db, self.name = db, name

    def delete_many(self, query):
        self.db.emptied.append(self.name)
        return SimpleNamespace(deleted_count=self.db.docs.get(self.name, 0))


class _Db:
    def __init__(self, docs):
        self.docs, self.emptied = docs, []

    def list_collection_names(self):
        return list(self.docs)

    def __getitem__(self, name):
        return _Collection(self, name)


class _Client:
    def __init__(self, db):
        self.db = db

    def __getitem__(self, name):
        return self.db

    def close(self):
        pass


def _mongodb_block():
    return load_config(ECOMMERCE / "import_config.json")["mongodb"]


def test_mongo_collections_lists_each_entity_by_its_partitions():
    db = _Db({"orders_state_SP": 2, "orders_state_RJ": 1, "unrelated": 5})
    assert ipd.mongo_collections(db, _mongodb_block()["entities"]) == [
        "product_catalog", "orders_state_RJ", "orders_state_SP",
    ]


def test_clean_mongodb_empties_every_partition_and_nothing_else(monkeypatch):
    db = _Db({"orders_state_SP": 2, "orders_state_RJ": 1, "product_catalog": 8, "unrelated": 5})
    monkeypatch.setattr("pymongo.MongoClient", lambda *a, **k: _Client(db))
    ipd.clean_mongodb(_mongodb_block())
    assert sorted(db.emptied) == ["orders_state_RJ", "orders_state_SP", "product_catalog"]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_inspect_persisted_data.py`
Expected: FAIL — `AttributeError: ... no attribute 'mongo_collections'` e `emptied` com `orders` em vez das partições.

- [ ] **Step 3: Implementar `mongo_collections` e usá-la nas duas funções**

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_inspect_persisted_data.py tests/test_benchmark_resume.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add scripts/inspect_persisted_data.py tests/test_inspect_persisted_data.py
rtk git commit -m "fix: limpador e inspetor do MongoDB enxergam as particoes do each" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
rtk git push
```

---

### Task 5: Notas da 3.0.0, "etapa"/"stage" nos READMEs, docstring e correção do design

**Files:**
- Modify: `docs/releases/v3.0.0.md` (dois itens novos em "Breaking changes" e um em "Changes", nas duas línguas)
- Modify: `README.md:100,106,110` (inglês) e `:375,381,385` (português)
- Modify: `data/ecommerce/README.md:13` e `:71`
- Modify: `src/polyglotimportcsv/business_exception.py:21`
- Modify: `docs/superpowers/specs/2026-10-30-revisao-ronaldo-v22-design.md` (correção sobre o Neo4j)

**Correção do design (achado ao escrever este plano).** O design diz que `--no-create-schema` desligava "as restrições de unicidade do Neo4j" e "a remoção e recriação das FKs do PostgreSQL". O código diz outra coisa, em todas as tags (`v1.0.0` a `v2.0.1`) e no HEAD: `Neo4jSink.create_schema` é vazio, e as restrições são criadas em `ensure_partition`, com ou sem a opção; `PostgresSink.close()` recria as FKs sempre, e a opção só pulava a remoção antes da carga. Só a carga integral (`--execution materialize`) respeitava a opção (`v2.0.1:src/polyglotimportcsv/importers/postgres_importer.py:89`, `neo4j_importer.py:171`). As notas abaixo seguem o código.

- [ ] **Step 1: Notas da 3.0.0, "Breaking changes" (inglês), depois do item de `--execution`**

```markdown
- **`--create-schema` and `--no-create-schema` were removed.** Before writing,
  the tool now always prepares each DBMS: it creates the Cassandra keyspace, the
  PostgreSQL and Cassandra tables and the Neo4j uniqueness constraints that do not
  exist yet, and reuses the ones that do; it drops the PostgreSQL foreign keys of
  the mapping before writing and adds them back at the end. MongoDB and Redis need
  nothing created. The option never did what its name said: in streaming, the
  default of every earlier release, `CREATE TABLE IF NOT EXISTS` ran in PostgreSQL
  and Cassandra, and the Neo4j constraints were created, with or without it.
  `--no-create-schema` skipped only two things: creating the Cassandra keyspace,
  without which the write failed, and dropping the PostgreSQL foreign keys before
  writing, so a new load over the foreign keys of an earlier one could violate a
  foreign key in the middle of the write. Only the whole-file load
  (`--execution materialize`) honored the option. Remove it from your scripts; a
  command that still passes it is rejected.
- **`target_suffix` of an `each` filter is now a template.** It must hold
  `{value}` exactly once, with only letters, digits and `_` around it, and
  `{value}` is replaced by the value of each part: `"target_suffix": "state_{value}"`
  on the entity `orders` writes `orders_state_SP`, `orders_state_RJ` and so on.
  Before, the text was used as it was, so every part got the same name. A
  configuration whose `target_suffix` lacks `{value}` is refused by the JSON Schema
  check, with exit code 1.
```

E em "Changes", por último:

```markdown
- **The e-commerce example** has a new MongoDB collection, `orders`, split by the
  buyer's state with `each` and `"target_suffix": "state_{value}"`:
  `orders_state_CA`, `orders_state_SP` and so on.
```

- [ ] **Step 2: Notas da 3.0.0, "Mudanças incompatíveis" e "Mudanças" (português), nas mesmas posições**

```markdown
- **As opções `--create-schema` e `--no-create-schema` foram removidas.** Antes de
  gravar, a ferramenta agora sempre prepara cada SGBD: cria o *keyspace* do
  Cassandra, as tabelas do PostgreSQL e do Cassandra e as restrições de unicidade do
  Neo4j que ainda não existirem, e reaproveita as que existem; remove as chaves
  estrangeiras do mapeamento no PostgreSQL antes de gravar e as recria no fim.
  MongoDB e Redis não precisam de nada criado. A opção nunca fez o que o nome dizia:
  na transmissão em blocos, o padrão de todas as versões anteriores, o
  `CREATE TABLE IF NOT EXISTS` rodava no PostgreSQL e no Cassandra, e as restrições
  do Neo4j eram criadas, com ou sem ela. A `--no-create-schema` só deixava de fazer
  duas coisas: criar o *keyspace* do Cassandra, sem o qual a gravação falhava, e
  remover as chaves estrangeiras do PostgreSQL antes de gravar. Por isso uma nova
  carga sobre as chaves estrangeiras de uma carga anterior podia violar uma chave
  estrangeira no meio da gravação. Só a carga integral (`--execution materialize`)
  respeitava a opção. Retire-a dos seus scripts; um comando que ainda a passe é
  recusado.
- **O `target_suffix` de um filtro `each` agora é um modelo.** Ele deve conter
  `{value}` exatamente uma vez, só com letras, dígitos e `_` em volta, e `{value}` é
  trocado pelo valor de cada parte: `"target_suffix": "state_{value}"` na entidade
  `orders` grava `orders_state_SP`, `orders_state_RJ` e assim por diante. Antes, o
  texto era usado como estava, e todas as partes recebiam o mesmo nome. Uma
  configuração cujo `target_suffix` não tenha `{value}` é recusada pela conferência
  do JSON Schema, com código de saída 1.
```

```markdown
- **O cenário de exemplo** tem uma coleção nova no MongoDB, `orders`, dividida pelo
  estado do comprador com `each` e `"target_suffix": "state_{value}"`:
  `orders_state_CA`, `orders_state_SP` e assim por diante.
```

- [ ] **Step 3: READMEs e docstring**

- `README.md:100` "three layers:" → "three stages:"; `:106` "If any layer fails" → "If any stage fails"; `:110` "1. Layers 1 and 2," → "1. Stages 1 and 2,".
- `README.md:375` "três camadas:" → "três etapas:"; `:381` "Se qualquer camada falhar" → "Se qualquer etapa falhar"; `:385` "1. As camadas 1 e 2," → "1. As etapas 1 e 2,".
- `data/ecommerce/README.md:13` "the JSON Schema layer refuses it" → "the JSON Schema check (validation stage 1) refuses it"; `:71` "a camada de JSON Schema a recusa" → "a conferência do JSON Schema (etapa 1 da validação) a recusa".
- `business_exception.py:21` "(validation layer 3)" → "(validation stage 3)".

- [ ] **Step 4: Corrigir o design**

Em "Achados no código", trocar `- **Neo4j:** cria as restrições de unicidade.` por `- **Neo4j:** nada. As restrições de unicidade são criadas por \`ensure_partition\`, com ou sem a opção.` Na decisão 1, item das notas, trocar "o *keyspace* do Cassandra, as restrições de unicidade do Neo4j e a remoção e recriação das FKs do PostgreSQL em volta da carga" por "o *keyspace* do Cassandra e a remoção das FKs do PostgreSQL antes da carga (a recriação no fim rodava sempre)".

- [ ] **Step 5: Conferir**

Ferramenta Grep, padrão `(?i)\blayers?\b|camadas?\b`, em `README.md`, `data/ecommerce/README.md`, `src`.
Expected: só `README.md:167` e `README.md:443` (arquitetura), `row_view.py:22`, `benchmark_runner.py:3` e `gui/process.py:4` (camadas de software).

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_package_release.py tests/test_exceptions.py tests/test_version.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
rtk git add docs/releases/v3.0.0.md README.md data/ecommerce/README.md src/polyglotimportcsv/business_exception.py docs/superpowers/specs/2026-10-30-revisao-ronaldo-v22-design.md
rtk git commit -m "docs: notas da 3.0.0, etapas de validacao nos READMEs e correcao do design" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
rtk git push
```

---

### Task 6: Suíte completa e conferência ao vivo

Nada é commitado nesta tarefa, a não ser correções; uma falha leva a `superpowers:systematic-debugging` e a correção vira commit próprio.

- [ ] **Step 1: Suíte fora da GUI**

Run: `.venv/Scripts/python.exe -m pytest -q -rfEs tests --ignore-glob="tests/test_gui_*"`
Expected: tudo passa (a última suíte verde, no `7005831`, tinha 1.804 testes; o número muda com os testes novos e removidos).

- [ ] **Step 2: Suíte da GUI**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_gui_*.py`
Expected: tudo passa (313 no `7005831`, menos os removidos e mais o novo).

- [ ] **Step 3: SGBDs e ambiente (só leitura)**

Run: `docker ps --format "table {{.Names}}\t{{.Status}}"`
Expected: os cinco contêineres de `docker-compose.yml` com "(healthy)". Se algum não estiver, parar e avisar o autor.

Run: `docker info --format "{{.MemTotal}}"`
Expected: cerca de 3,8 GB (`tab:ambiente-sgbds`). Anotar o valor para o `benchmarks/README.md`.

- [ ] **Step 4: Recarga sem limpar, limpeza e modo combinado (Review Focus 1 e 5)**

```bash
.venv/Scripts/python.exe scripts/inspect_persisted_data.py clean
.venv/Scripts/python.exe -m polyglotimportcsv --config data/ecommerce/import_config.json --no-data
.venv/Scripts/python.exe -m polyglotimportcsv --config data/ecommerce/import_config.json --no-data
.venv/Scripts/python.exe scripts/inspect_persisted_data.py inspect --only mongodb
.venv/Scripts/python.exe scripts/inspect_persisted_data.py clean
.venv/Scripts/python.exe scripts/inspect_persisted_data.py inspect --only mongodb
.venv/Scripts/python.exe -m polyglotimportcsv --config data/ecommerce/import_config_combined.json --no-data
.venv/Scripts/python.exe scripts/inspect_persisted_data.py clean --config data/ecommerce/import_config_combined.json
```

Expected:
- as duas importações seguidas terminam com código 0 (a segunda, sobre as FKs da primeira, é o caso que `--no-create-schema` quebrava);
- o primeiro `inspect` mostra as sete coleções `orders_state_*` com o dobro dos documentos do *dry-run* (o MongoDB não deduplica);
- o `clean` lista as sete coleções, e o segundo `inspect` as mostra vazias;
- a importação combinada termina com código 0.

---

### Task 7: Campanha da 3.0.0

**Files:**
- Create: `benchmarks/v3/memory/`, `benchmarks/v3/timings/`, `benchmarks/v3/chunks-memory/`, `benchmarks/v3/chunks-timings/` (cada uma com `benchmark_results.csv` e `benchmark_run_<timestamp>.json`)

Eixos (sessão de 2026-10-31 e spec do fluxo único): tamanhos 1.000, 10.000 e 100.000 × multifonte e combinado × 3 repetições, bloco de 8 MB; e blocos de 8, 64 e 256 MB em 100.000. **Escolha do plano:** os blocos rodam só no multifonte (como o exemplo do `benchmarks/README.md`) e repetem o bloco de 8 MB dentro da própria campanha, para que a comparação entre blocos não atravesse campanhas. O bloco de 8 MB em 100.000 multifonte medido nas duas campanhas de tempo dá, de quebra, a variação do tempo entre campanhas na 3.0.0.

- [ ] **Step 1: Pré-condições**

Task 6 verde; `rtk git status` limpo (salvo o PDF não versionado); HEAD enviado. Anotar `git rev-parse --short HEAD` para o README. Nenhum outro processo pesado aberto. Durante cada campanha, nada de testes, renderização ou edição pesada.

- [ ] **Step 2: Quatro campanhas, uma de cada vez, em segundo plano**

```bash
.venv/Scripts/python.exe scripts/run_benchmarks.py --sizes 1000,10000,100000 --modes multi,combined --chunk-sizes 8 --repetitions 3 --out benchmarks/v3/memory
.venv/Scripts/python.exe scripts/run_benchmarks.py --sizes 1000,10000,100000 --modes multi,combined --chunk-sizes 8 --repetitions 3 --no-trace-memory --out benchmarks/v3/timings
.venv/Scripts/python.exe scripts/run_benchmarks.py --sizes 100000 --modes multi --chunk-sizes 8,64,256 --repetitions 3 --out benchmarks/v3/chunks-memory
.venv/Scripts/python.exe scripts/run_benchmarks.py --sizes 100000 --modes multi --chunk-sizes 8,64,256 --repetitions 3 --no-trace-memory --out benchmarks/v3/chunks-timings
```

Cada comando roda com `run_in_background` e o executor espera a notificação, sem consultar a saída a toda hora. Se uma campanha for interrompida (o Cassandra já caiu assim em 2026-08-01), repetir o mesmo comando com `--resume`. Expected: cada uma termina com código 0 e imprime `benchmark JSON:` e `benchmark CSV:`.

- [ ] **Step 3: Conferir cada pasta antes de começar a próxima**

Um script descartável no *scratchpad* (não versionado) confere:
- um só `benchmark_results.csv`, um só `benchmark_run_*.json` e nenhum `benchmark_checkpoint.json`;
- um só `timestamp` no CSV, e o número de linhas do CSV igual ao de `results` no JSON;
- nenhuma chave `(size, mode, chunk_mb, backend, entity, phase)` repetida;
- `peak_memory_mb` preenchido em todas as linhas de `memory` e `chunks-memory`, e vazio em todas as de `timings` e `chunks-timings`;
- as linhas `infer` e `validate` com `rows` igual a `size`;
- a soma de `rows` das linhas `write` do `mongodb` igual a `stock + purchase` de `benchmark_data._split_rows(size, 42)` (o `product_catalog` mais o `orders`). Isso prova que a coleção nova entrou na carga medida e que o limpador deixou cada repetição a frio;
- ao fim do par, `rows` idêntico entre as pastas pareadas em toda chave comum.

- [ ] **Step 4: Commit de cada pasta conferida, entre uma campanha e a seguinte**

```bash
rtk git add benchmarks/v3/memory/benchmark_results.csv benchmarks/v3/memory/benchmark_run_*.json
rtk git commit -m "bench: campanha 3.0.0 de memoria (1k a 100k, multi e combinado)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
rtk git push
```

O mesmo para `timings` ("de tempo"), `chunks-memory` ("de memoria por bloco, 8/64/256 MB em 100k") e `chunks-timings` ("de tempo por bloco, 8/64/256 MB em 100k").

---

### Task 8: Resumo das medianas no `benchmarks/README.md`

**Files:**
- Modify: `benchmarks/README.md` (inglês e português)

- [ ] **Step 1: Situar as campanhas antigas**

A abertura ("Four campaigns are current…") passa a dizer que as quatro campanhas da raiz, `timings/`, `naive/` e `timings-naive/` são as da 2.x, válidas para o histórico (carga integral × fluxo; ingênua × em lote), e que as atuais estão em `v3/`. O resto do texto antigo fica.

- [ ] **Step 2: Reescrever "Campaigns of the current version" / "Campanhas da versão atual"**

Com os números das quatro pastas, nas duas línguas:
- tabela das pastas (eixos, tracemalloc, uso), o *commit* medido e o ambiente (memória do Docker do Step 3 da Task 6, *heap* de 1 GB do Cassandra);
- a conferência feita (os itens do Step 3 da Task 7, com os números);
- **tempo por fase**, 100.000, multifonte e combinado, bloco de 8 MB (`v3/timings`): `infer`, `validate`, `write` por SGBD e total (soma das medianas das fases), e a fração de `infer` + `validate` no total;
- **crescimento**: total em segundos (`v3/timings`) e pico em MB (`v3/memory`) para 1.000, 10.000 e 100.000 × multifonte e combinado;
- **tamanho do bloco**, 100.000 multifonte (`v3/chunks-memory` e `v3/chunks-timings`): pico, total, `infer` e `validate` para 8, 64 e 256 MB;
- **vazão de escrita por SGBD**, 100.000 multifonte (`v3/timings`): linhas, segundos, linhas/s;
- **ressalvas:** nunca misturar campanhas com e sem tracemalloc; a variação de tempo entre campanhas medida no bloco de 8 MB em 100.000 multifonte (`v3/timings` × `v3/chunks-timings`); a carga medida inclui a coleção `orders` (cerca de `purchase` linhas a mais no MongoDB), então os totais não se comparam aos da 2.x como se a carga fosse a mesma; a fração do Cassandra na escrita.
- O comando de exemplo da seção passa a ser o da campanha `chunks-memory`.

- [ ] **Step 3: Conferir cada número contra os CSVs**

Um script descartável no *scratchpad* recalcula cada célula das tabelas a partir dos `benchmark_results.csv`. Expected: todos os números do README batem.

- [ ] **Step 4: Commit**

```bash
rtk git add benchmarks/README.md
rtk git commit -m "docs: resumo das medianas da campanha 3.0.0 no benchmarks/README" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
rtk git push
```

---

### Task 9: Estado da sessão (local, sem commit)

- [ ] **Step 1:** atualizar `.claude/session-state.md`: etapa 2 concluída, *commits*, pastas da campanha, a saída do *dry-run* com as partições `orders_state_*` (Task 3, Step 5) e o que a etapa 3 herda deste plano:
  - as capturas da GUI na §4.6 mostram a caixa "Criar esquema", que não existe mais, e precisam ser refeitas;
  - o apêndice A reproduz as configurações com a coleção `orders`;
  - o texto sobre o que a ferramenta cria em cada SGBD segue a correção do Neo4j (Task 5).
- [ ] **Step 2:** atualizar a memória `tcc2-roadmap-and-workflow.md` com o mesmo resumo, em uma linha no `MEMORY.md`.
