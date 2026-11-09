# Etapa 2 — Tamanho automático, saída dos sliders e GUI em inglês — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer a ferramenta escolher sozinha o bloco de leitura e o lote de gravação (com `--chunk-size`/`--batch-size` como ajuste manual), tirar os sliders da GUI, traduzir a GUI para o inglês e registrar o commit nos metadados das campanhas.

**Architecture:** Um módulo novo, `auto_size`, guarda a regra do spec como uma função pura (`choose_chunk_mb`) e uma função que mede as fontes da importação (`auto_chunk_mb`). A estimativa de memória de uma fonte inteira (`source_memory_mb`) fica em `stream_source`, ao lado de `chunk_rows`, porque usa a mesma sondagem das primeiras mil linhas. `run_import` resolve os dois tamanhos quando não vêm da CLI, registra o valor e o motivo no console e no log da sessão e os grava nos metadados de `--benchmark`. O executor de campanhas ganha um modo `auto`, que resolve o bloco uma vez por célula (tamanho, modo) no início, com uma só leitura da memória livre, e guarda a escolha no checkpoint, para que `--resume` a reaproveite. A GUI perde os dois sliders e os campos correspondentes de `RunOptions`, e todo texto visível passa para o inglês, conforme a tabela da Task 5.

**Tech Stack:** Python 3.14 (`.venv`), click, pandas, PySide6, pytest/pytest-qt.

**Spec:** `docs/superpowers/specs/2026-11-08-revisao-ronaldo-v23-design.md`: Parte 1, itens 3 e 4; Parte 2; a seção "Resultado da campanha exploratória (2026-11-09)", cuja **regra adotada** prevalece sobre a Parte 1, item 3; e a Parte 3b, sobre resolver o automático uma vez por campanha.

## Global Constraints

- **Branch e commits:**
  - branch `revisao-ronaldo-v23`, com push depois de cada commit;
  - commits em português, com o trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`;
  - todo comando git leva o prefixo `rtk`, e só caminhos explícitos são preparados;
  - nunca commitar `docs-tcc/TCC2-PolyglotImportCSV-Report-v2.3_REVISADO.pdf`, `docs-tcc/main-v2.*.tex`, `docs-tcc/notas-reuniao-2026-11-09.md` nem `docs-tcc/relacionados/`.
- **Limites (não mudam):** bloco de 16 a 256 MB (`MIN_CHUNK_MB`, `MAX_CHUNK_MB`); lote de 512 a 8192 linhas; **lote automático = `DEFAULT_BATCH_LINES` = 2048**.
- **Constantes da regra:** ficam em `auto_size`, com estes nomes e valores: `PEAK_BASE_MB = 22.2`, `PEAK_BASE_PER_DISK_MB = 2.31`, `PEAK_MB_PER_CHUNK_MB = 1.078`, `FREE_MEMORY_FRACTION = 0.25`.
- **Regra:**
  - bloco = mín(256; MB da maior fonte lida inteira; limite de segurança), preso a [16, 256] e arredondado para baixo a um inteiro;
  - limite de segurança = (0,25 × livre − (22,2 + 2,31 × MiB em disco das fontes lidas)) / 1,078;
  - com a memória livre ilegível (`None`), o limite não se aplica.
- **Idiomas:** as mensagens da CLI continuam em inglês. Na GUI, **todo** texto visível passa para o inglês. Use "DBMS"/"DBMSs" e nunca o termo barrado por `tests/test_naming_dbms.py`.
- **Testes, em dois processos** (a máquina tem 8 GB, e o `python` sem venv pula ~100 testes de GUI):
  - `.venv/Scripts/python.exe -m pytest -q -rfEs tests --ignore-glob="tests/test_gui_*"`;
  - `.venv/Scripts/python.exe -m pytest -q tests/test_gui_*.py`.
- **Docker:** pode ser ligado quando for preciso; desligar só com OK.
- **Arquivos descartáveis** vão para `.superpowers/scratch/`.

## Review Focus

1. **Memória livre ilegível.** `available_mb()` devolve `None`. O bloco esperado é o da maior fonte inteira, preso a [16, 256], e o motivo diz "free memory unknown", sem exceção, tanto na CLI quanto no executor. Testes na Task 1 e na Task 3.
2. **Memória quase esgotada.** O limite de segurança fica negativo ou abaixo de 16. O esperado é um bloco de 16 MB e um motivo que diz que a memória limitou, nunca um erro nem um bloco ≤ 0. Teste na Task 1.
3. **Fonte vazia ou minúscula** (só o cabeçalho, ou poucos KB). `source_memory_mb` devolve 0,0 ou quase isso, e o bloco é 16. Teste na Task 1.
4. **`--source` apontando para um arquivo maior que o da configuração, ou fonte combinada (`{"file": ...}`).** O automático mede o arquivo que será de fato lido: o do override, e o arquivo combinado inteiro. Teste na Task 1.
5. **`--resume` de uma campanha automática depois que a memória livre mudou.** O esperado é reaproveitar o bloco salvo no checkpoint, sem medir nada de novo nem misturar blocos diferentes na mesma célula. Teste na Task 3.

---

### Task 1: Regra do tamanho automático (`auto_size`)

**Files:**
- Create: `src/polyglotimportcsv/auto_size.py`
- Modify: `src/polyglotimportcsv/stream_source.py` (nova função depois de `chunk_rows`)
- Test: `tests/test_auto_size.py` (novo) e `tests/test_stream_source.py`

**Interfaces:**
- Produces:
  - `stream_source.source_memory_mb(name: str, path: Path) -> float`: MB em memória para ler o arquivo inteiro, estimados como `tamanho do arquivo × (bytes em memória das primeiras PROBE_ROWS linhas, deep, sem índice / bytes em disco dessas mesmas linhas)`. Os bytes em disco são a soma dos comprimentos das linhas 2 a PROBE_ROWS+1, lidas em binário (o cabeçalho fica fora). Um arquivo sem linhas de dados dá `0.0`. Essa é a estimativa "sem segunda leitura" que o spec permite; a docstring diz isso.
  - `auto_size.AutoChunk`: `@dataclass(frozen=True)` com `mb: int` e `reason: str`.
  - `auto_size.choose_chunk_mb(largest_source_mb: float, sources_disk_mb: float, free_mb: Optional[float]) -> AutoChunk`: a regra pura.
  - `auto_size.auto_chunk_mb(config: Dict[str, Any], base_dir: Path, dbms_names: Sequence[str], overrides: Optional[Dict[str, str]], free_mb: Optional[float]) -> AutoChunk`. As fontes são `import_plan.dbms_sources(config, dbms_names)`, e cada caminho vem de `stream_source.source_path(name, decl, base_dir, overrides or {})`. Os MiB em disco são a soma de `path.stat().st_size / 2**20`, e a maior fonte é o máximo de `source_memory_mb`.
  - O texto exato de `reason` sai da Step 3 e é usado pelas Tasks 2 e 3.

- [ ] **Step 1: Testes da regra pura**, em `tests/test_auto_size.py`, com os números do spec:

```python
from polyglotimportcsv.auto_size import choose_chunk_mb

def test_whole_source_wins_when_memory_allows():          # 131072 linhas nesta máquina
    c = choose_chunk_mb(95.5, 29.9, 890.0)
    assert c.mb == 95 and "largest source read whole (95.5 MB)" in c.reason and "890 MB free" in c.reason

def test_free_memory_limits_the_block():                   # 262144 linhas nesta máquina
    c = choose_chunk_mb(191.0, 60.3, 890.0)
    assert c.mb == 56 and "limited by free memory" in c.reason

def test_more_memory_reads_the_larger_source_whole():
    assert choose_chunk_mb(191.0, 60.3, 2048.0).mb == 191

def test_source_larger_than_the_maximum_gets_256():
    c = choose_chunk_mb(400.0, 10.0, 16000.0)
    assert c.mb == 256 and "exceeds the 256 MB maximum" in c.reason

def test_unknown_free_memory_skips_the_limit():
    c = choose_chunk_mb(191.0, 60.3, None)
    assert c.mb == 191 and "free memory unknown" in c.reason

def test_starved_memory_still_gives_the_minimum():
    c = choose_chunk_mb(191.0, 60.3, 100.0)                # limite negativo
    assert c.mb == 16 and "limited by free memory" in c.reason and "16 MB minimum" in c.reason

def test_tiny_source_gets_the_minimum_block():
    assert choose_chunk_mb(0.0, 0.0, 890.0).mb == 16
```

- [ ] **Step 2: Rodar e ver falhar.** Comando: `.venv/Scripts/python.exe -m pytest tests/test_auto_size.py -q`. Esperado: ImportError (`auto_size` não existe).

- [ ] **Step 3: Implementar `choose_chunk_mb`** com as constantes das Global Constraints, `MIN_CHUNK_MB`/`MAX_CHUNK_MB` importados de `stream_source` e a docstring do módulo citando a origem dos coeficientes: campanha `benchmarks/v4-explore` e `v4-preview`, uma máquina, modo multifonte; a fração de 25% é uma margem escolhida.
  - O termo que manda é o menor entre `MAX_CHUNK_MB`, a fonte inteira e o limite; num empate entre a fonte inteira e outro termo, vence a fonte inteira.
  - O motivo é o núcleo seguido do sufixo:
    - núcleos: `auto: largest source read whole ({largest:.1f} MB)`, `auto: limited by free memory` ou `auto: largest source ({largest:.1f} MB) exceeds the {MAX_CHUNK_MB} MB maximum`;
    - sufixo `; {free:.0f} MB free`, ou `; free memory unknown`;
    - quando o valor bruto fica abaixo de 16, acrescenta-se ` (raised to the 16 MB minimum)` antes do sufixo.

- [ ] **Step 4: Testes de `source_memory_mb` e `auto_chunk_mb`.**
  - Em `tests/test_stream_source.py`:
    - `test_source_memory_mb_matches_the_rows_per_mb_estimate`: um CSV de 5000 linhas uniformes em `tmp_path`, com o resultado a até 3% de `5000 / chunk_rows(name, path, 1)`;
    - `test_source_memory_mb_of_a_header_only_file_is_zero`.
  - Em `tests/test_auto_size.py` (Review Focus 4):
    - `test_auto_chunk_measures_the_override_file`: a configuração declara `small.csv` (10 linhas), e `overrides={"src": big.csv}` (20000 linhas). O motivo cita o tamanho de `big.csv`, o mesmo de `source_memory_mb("src", big)`, com uma casa decimal;
    - `test_auto_chunk_reads_the_combined_file`: a fonte é `{"file": "join.csv"}`. A maior fonte é o arquivo combinado inteiro.

- [ ] **Step 5: Implementar `source_memory_mb` e `auto_chunk_mb`.** Rodar `.venv/Scripts/python.exe -m pytest tests/test_auto_size.py tests/test_stream_source.py -q`. Esperado: tudo PASS.

- [ ] **Step 6: Conferência com os dados reais** (não vira teste; os dados ficam fora do git). Em `.superpowers/scratch/check_auto.py`, para `data/benchmark/generated/{131072,262144}/ecommerce_purchase.csv`, imprimir `source_memory_mb` e `linhas / chunk_rows(..., 1)`. Esperado: cerca de 95,5 e 191 MB, com até 5% de diferença entre as duas estimativas. Se passar de 5%, parar e relatar antes de seguir.

- [ ] **Step 7: Commit** de `src/polyglotimportcsv/auto_size.py`, `src/polyglotimportcsv/stream_source.py`, `tests/test_auto_size.py` e `tests/test_stream_source.py`, com a mensagem `feat: regra do tamanho automatico do bloco (auto_size)`. Depois, push.

### Task 2: Automático na CLI e em `run_import`, com registro

**Files:**
- Modify: `src/polyglotimportcsv/cli.py:82-100`, `src/polyglotimportcsv/runner.py` (`run_import`, `_print_summary`)
- Test: `tests/test_cli.py`, `tests/test_runner.py`

**Interfaces:**
- Consumes: `auto_chunk_mb`, `AutoChunk` (Task 1); `system_memory.available_mb()`.
- Produces: `run_import(..., chunk_size_mb: Optional[float] = None, batch_size: Optional[int] = None, ...)`, onde `None` quer dizer automático.
  - As opções `--chunk-size` e `--batch-size` passam a ter `default=None` e `show_default=False`; o resto não muda.
  - Novos textos de ajuda:
    - `"Memory budget of each read chunk, in MB (16-256). Default: chosen for each run from the largest source and the free memory. Rows per chunk follow each file's row width."`
    - `"Rows per write batch (512-8192), capped at the rows of one read chunk. Default: 2048."`

- [ ] **Step 1: Atualizar e escrever os testes.**
  - Em `tests/test_cli.py`:
    - `test_cli_chunk_and_batch_defaults` passa a verificar `captured["chunk_size_mb"] is None and captured["batch_size"] is None`;
    - `test_cli_option_help_and_metadata` passa a verificar `(chunk.metavar, chunk.show_default, chunk.default) == ("MB", False, None)`, o mesmo para o lote com `"N"`, e os dois textos de ajuda acima.
  - Em `tests/test_runner.py`:
    - os padrões de `run_import` passam a ser `None`;
    - `test_auto_sizes_are_resolved_logged_and_reach_the_plan`: com `available_mb` substituído por `lambda: 890.0` e `auto_chunk_mb` (no namespace do `runner`) substituído por um stub que devolve `AutoChunk(95, "auto: largest source read whole (95.5 MB); 890 MB free")`, um `run_import(cfg, dry_run=True)` passa `chunk_mb=95, batch_size=2048` ao `plan_import`, e a saída capturada contém `Read block: 95 MB (auto: largest source read whole (95.5 MB); 890 MB free)` e `Write batch: 2048 rows (auto)`;
    - `test_manual_sizes_skip_the_auto_rule`: com `chunk_size_mb=64, batch_size=4096`, o stub nunca é chamado, e a saída tem `Read block: 64 MB (--chunk-size)` e `Write batch: 4096 rows (--batch-size)`;
    - `test_benchmark_metadata_records_the_sizes`: em `--benchmark`, os metadados gravados incluem `chunk_mb`, `chunk_reason`, `batch_lines` e `free_memory_mb`.

- [ ] **Step 2: Rodar e ver falhar.** Comando: `.venv/Scripts/python.exe -m pytest tests/test_cli.py tests/test_runner.py -q`.

- [ ] **Step 3: Implementar.**
  - Em `run_import`, logo antes de `step("Infer types")`:
    - se `chunk_size_mb` for `None`, ler `free = available_mb()` e chamar `auto_chunk_mb(config, config_path.parent, dbms_names, source_overrides, free)`;
    - imprimir `kv("Read block", f"{mb} MB ({reason})")` e `kv("Write batch", f"{n} rows ({'auto' or '--batch-size'})")`. `kv` já vai para o console e para o log da sessão.
  - A memória livre é lida só no modo automático. Com o bloco manual, os metadados levam `free_memory_mb = None`.
  - `_print_summary` recebe esses valores e os acrescenta aos metadados de `--benchmark`.

- [ ] **Step 4: Rodar** a suíte fora da GUI (comando das Global Constraints). Esperado: tudo PASS.

- [ ] **Step 5: Conferência real.**
  - Rodar `.venv/Scripts/python.exe -m polyglotimportcsv --config data/ecommerce/import_config.json --dry-run --no-data`, com `--source` para os quatro arquivos de `data/benchmark/generated/131072/`, e depois de novo com os de 262144.
  - Esperado: `Read block` com cerca de 95 MB (fonte inteira) em 131072, e o bloco limitado pela memória em 262144, se a memória livre estiver perto de 890 MB.
  - Anotar no ledger as duas linhas e a memória livre.

- [ ] **Step 6: Commit** de `src/polyglotimportcsv/cli.py`, `src/polyglotimportcsv/runner.py`, `tests/test_cli.py` e `tests/test_runner.py`, com a mensagem `feat: bloco e lote automaticos por padrao na CLI, com o motivo no log`. Depois, push.

### Task 3: Modo automático no executor de campanhas e commit nos metadados

**Files:**
- Modify: `src/polyglotimportcsv/benchmark_runner.py` (`run_matrix`), `scripts/run_benchmarks.py` (`--chunk-sizes`, `resume_runs`, metadados), `src/polyglotimportcsv/metrics.py` (`environment_metadata`)
- Test: `tests/test_benchmark_runner.py`, `tests/test_benchmark_resume.py`, `tests/test_benchmark_output.py`

**Interfaces:**
- Consumes: `auto_chunk_mb`, `AutoChunk` (Task 1).
- Produces: `run_matrix(..., chunk_sizes: Optional[Iterable[int]] = (DEFAULT_CHUNK_MB,), ..., auto_chunks: Optional[Dict[str, Dict[str, object]]] = None, auto_chunk: Callable[..., AutoChunk] = auto_chunk_mb)`.
  - `chunk_sizes=None` liga o modo automático. Antes da primeira importação, para cada célula cuja chave `f"{size}/{mode}"` falta em `auto_chunks`, o executor chama `auto_chunk(merged, config_path.parent, selected, overrides, free)` e grava `{"chunk_mb": c.mb, "reason": c.reason, "free_memory_mb": free}` **no próprio dicionário recebido**. `free` vem de **uma** chamada a `available_mb()`, feita só se faltar alguma célula. Cada célula usa então `[auto_chunks[key]["chunk_mb"]]` como lista de blocos.
  - `scripts/run_benchmarks.py`:
    - `--chunk-sizes` passa a ter o padrão `"auto"`, que vira `None`;
    - `meta["chunk_sizes"]` vira `"auto"` ou a lista;
    - `meta["auto_chunks"]` é o dicionário passado ao `run_matrix`, de modo que o checkpoint e o JSON final o levam;
    - quando os metadados salvos têm `auto_chunks`, `resume_runs` faz `meta["auto_chunks"].update(saved["auto_chunks"])`.
  - `metrics.environment_metadata` ganha `"git_commit"`: o hash de `git rev-parse HEAD`, com o sufixo `-dirty` se `git status --porcelain -- src` não for vazio, ou `None` se o git falhar (`subprocess.run` com `capture_output`, `check=False` e `cwd` na raiz do pacote, com qualquer `OSError` capturado). Isso fecha a pendência "`git_commit` None": os JSONs de campanha nunca registraram o commit.

- [ ] **Step 1: Testes.**
  - Em `tests/test_benchmark_runner.py`:
    - `test_auto_mode_resolves_each_cell_once_with_one_memory_reading`: com 2 tamanhos e 2 repetições, um stub `auto_chunk` que devolve 40 MB e 70 MB por tamanho, e `benchmark_runner.available_mb` substituído por um contador. Esperado: chamadas = número de execuções + 1 (a leitura por execução que já existe, mais uma só do automático); o stub chamado uma vez por célula; o `chunk_size_mb` do importador igual ao valor da célula; `auto_chunks` preenchido;
    - `test_auto_mode_reuses_saved_chunks`: com `auto_chunks` já preenchido para todas as células, o stub nunca é chamado (Review Focus 5);
    - `test_auto_mode_with_unreadable_memory`: com `available_mb` devolvendo `None`, o stub recebe `free=None` e a matriz roda (Review Focus 1, e o menor adiado da etapa 1).
    - Corrigir também a docstring de `run_matrix`, onde está "(size, mode, chunk size) matrix", para "(size, mode, chunk size, batch size) matrix".
  - Em `tests/test_benchmark_resume.py`, `test_resume_restores_the_auto_chunks`: um checkpoint com `chunk_sizes="auto"` e `auto_chunks={"131072/multi": {...}}` preenche o `meta["auto_chunks"]` passado.
  - Em `tests/test_benchmark_output.py`, `test_environment_metadata_records_the_git_commit`: o valor casa com `^[0-9a-f]{40}(-dirty)?$`, ou é `None` com `subprocess.run` forçado a levantar `OSError`.

- [ ] **Step 2: Rodar e ver falhar**, depois **implementar** e rodar a suíte fora da GUI. Esperado: tudo PASS.

- [ ] **Step 3: Conferência rápida** com uma matriz pequena e real, com o Docker no ar: `--sizes 1024 --modes multi --repetitions 1 --out .superpowers/scratch/auto-smoke`. O JSON final precisa ter `chunk_sizes: "auto"`, `auto_chunks["1024/multi"]` com motivo e memória livre, e `git_commit` preenchido. Apagar a pasta depois.

- [ ] **Step 4: Commit** de `src/polyglotimportcsv/benchmark_runner.py`, `src/polyglotimportcsv/metrics.py`, `scripts/run_benchmarks.py` e dos três arquivos de teste, com a mensagem `feat(bench): modo automatico resolvido uma vez por celula, reaproveitado no --resume, e commit nos metadados`. Depois, push.

### Task 4: Sliders fora da GUI

**Files:**
- Modify:
  - `src/polyglotimportcsv/gui/state.py`: sai `chunk_size_mb`/`batch_size` de `RunOptions` e as duas validações;
  - `src/polyglotimportcsv/gui/command.py`: `build_argv` deixa de emitir `--chunk-size`/`--batch-size`, e a docstring do módulo deixa de citar a "size spin box";
  - `src/polyglotimportcsv/gui/widgets/options_panel.py`: saem os sliders, os leitores `chunk_size_mb()`/`batch_size()`, `_build_slider_row`, as entradas de `HELP` e as chaves de `set_errors`, e os imports órfãos;
  - `src/polyglotimportcsv/gui/widgets/main_window.py:171-172`.
- Test: `tests/test_gui_options_panel.py`, `tests/test_gui_main_window.py`, `tests/test_gui_command.py`, `tests/test_gui_state.py`

**Interfaces:**
- Produces: `RunOptions` sem `chunk_size_mb` e `batch_size`. O `argv` padrão fica `["--config", CFG, "--log-level", "INFO", "--sample", "<DEFAULT_SAMPLE_SIZE>"]`, mais `--only`, `--dry-run`, `--show-data`/`--no-data` e `--source` quando marcados, na ordem atual.

- [ ] **Step 1: Atualizar os testes** que hoje falham (12: 6 do painel de opções, 2 da janela e 4 do comando).
  - Os testes de sliders e spin boxes saem.
  - `test_options_panel_has_two_size_spins_and_only_the_data_radios` passa a ser `test_options_panel_has_no_size_controls`: nenhum `QSlider` nem `QSpinBox` além de `sample_spin`, e nenhum atributo `chunk_slider`/`batch_slider`.
  - Novo `test_command_never_carries_chunk_or_batch`: nem `--chunk-size` nem `--batch-size` no `build_argv` de um `RunOptions` qualquer.
  - Os testes de ordem e de "every option toggled" perdem os dois pares.
  - Em `test_gui_state.py`, saem os casos de limites do bloco e do lote.

- [ ] **Step 2: Implementar e rodar** os dois processos de teste. Esperado: tudo PASS, inclusive as 12 falhas de antes.

- [ ] **Step 3: Commit** dos arquivos de código e de teste listados acima, com a mensagem `feat(gui): bloco e lote saem da GUI (automaticos)`. Depois, push.

### Task 5: GUI em inglês

**Files:**
- Modify:
  - `src/polyglotimportcsv/gui/state.py` e `src/polyglotimportcsv/gui/preflight.py`;
  - `src/polyglotimportcsv/gui/widgets/{options_panel,config_panel,sources_panel,console_panel,main_window,info_badge}.py`.
- Test: os `tests/test_gui_*.py` que conferem textos, e um novo `tests/test_gui_english.py`.

**Interfaces:** só textos; nenhum nome de atributo ou sinal muda.

- [ ] **Step 1: Teste-guarda** em `tests/test_gui_english.py`, `test_gui_shows_no_portuguese_text`:
  - percorre com `ast` todos os `.py` de `src/polyglotimportcsv/gui/`, ignorando docstrings e `style.py`;
  - falha se alguma constante de texto tiver caractere acentuado do português (`áéíóúâêôãõç` e maiúsculas) ou alguma destas palavras inteiras: `de, da, do, para, não, nenhum, Selecione, Arquivo, linhas, Fonte, fonte, Pronto, Executar, Copiar, Salvar, Verificar, Editar, Opções, Escolher, Remover, Adicionar, Procurar, Todos, Amostra, Concluído, Falhou, Interromper, Ajuda, Bloco, Lote`;
  - a mensagem lista arquivo, linha e texto.

  Rodar: hoje falha com cerca de 90 ocorrências.

- [ ] **Step 2: Traduzir** com esta tabela, que é o texto exato. Ela lista os padrões de formatação (`{0}` etc.) e as formas plurais.

| Onde | Português atual | Inglês |
|---|---|---|
| options_panel | Opções de execução / Bancos de dados (--only) / Modificadores / Simulação (--dry-run) / Nível de log (--log-level) / Exibição de dados | Run options / Databases (--only) / Modifiers / Dry run (--dry-run) / Log level (--log-level) / Data display |
| options_panel | Amostra (--sample) / Todos os dados (--show-data) / Nenhum dado (--no-data) / Linhas mostradas por entidade (--sample N) | Sample (--sample) / All rows (--show-data) / No data (--no-data) / Rows shown per entity (--sample N) |
| options_panel HELP | dry_run / log_level / show_data | "Runs every check, including the read of the data rows, and shows how many records would go to each target, without connecting to any DBMS." / "How much detail the console shows. The session log file always records everything (DEBUG)." / "Sample: the first N rows of each entity. All rows: every row; slow on large files. No data: only the counts." |
| config_panel | Arquivos de configuração / Configuração de importação (--config) / Configuração de SGBDs (--dbms-config) / Procurar… / Escolher a configuração de importação / Escolher a configuração de SGBDs / JSON (*.json);;Todos (*) | Configuration files / Import configuration (--config) / DBMS configuration (--dbms-config) / Browse… / Choose the import configuration / Choose the DBMS configuration / JSON (*.json);;All files (*) |
| config_panel HINT | Ambos os arquivos… | "Both files are validated against a JSON Schema before the run. The import configuration may only refer to DBMSs declared in the connection configuration." |
| sources_panel | Fontes CSV — sobrescrita de caminhos (--source) / Nome da fonte / Arquivo CSV | CSV files (--source) / Source name / CSV file |
| sources_panel HINT | Deixe a tabela vazia… | "Leave the table empty to use the paths declared in the \"sources\" block of the import configuration. Each file chosen here replaces the path of the source with the same name; the name is taken from the file and can be corrected in the table." |
| sources_panel | NO_CONFIG_TEXT / MULTI_TEXT / COMBINED_TEXT / ONE_FILE_ERROR / FOLDER_COMBINED_TIP / PLACEHOLDER | "Choose the import configuration to attach CSV files." / "Multi-source configuration: one CSV per data set." / "Combined configuration: a single CSV." / "The combined configuration takes a single CSV file." / "A combined configuration reads a single file; choose it with the button beside." / "Drop CSV files here or use the buttons above" |
| sources_panel | + Adicionar arquivos / + Adicionar arquivo / + Adicionar pasta / − Remover | + Add files / + Add file / + Add folder / − Remove |
| sources_panel (dicas e diálogos) | Escolher um ou mais arquivos CSV / Anexar de uma vez todos os arquivos .csv de uma pasta / Escolher o arquivo CSV combinado / Escolher arquivos CSV / Escolher a pasta com os arquivos CSV / Escolher o arquivo CSV / CSV (*.csv);;Todos (*) | Choose one or more CSV files / Attach every .csv file of a folder at once / Choose the combined CSV file / Choose CSV files / Choose the folder with the CSV files / Choose the CSV file / CSV (*.csv);;All files (*) |
| sources_panel (ignorados) | {0} arquivo ignorado (não é CSV) / {0} arquivos ignorados (não são CSV) / {0} pasta ignorada (…) / {0} pastas ignoradas (…) | {0} file ignored (not a CSV) / {0} files ignored (not CSVs) / {0} folder ignored (the combined configuration takes a single file) / {0} folders ignored (the combined configuration takes a single file) |
| console_panel | somente leitura / modo de edição / em execução / Editar comando / Voltar ao formulário / Copiar / ▶  Executar / ■  Interromper / Verificar SGBDs / Salvar log… / Descartar o comando editado | read-only / editing / running / Edit command / Back to the form / Copy / ▶  Run / ■  Stop / Check DBMSs / Save log… / Discard the edited command |
| console_panel | DISCARD_QUESTION | "The command was edited by hand. Going back to the form disregards the typed text and replaces it with the command the form represents. Go back anyway?" |
| console_panel | LAUNCHER_TOOLTIP | "The command shown starts with «{program}», which is what one would type in a terminal. The process actually started uses the prefix resolved for this installation:\n\n{prefix}\n\nThe remaining arguments are identical to the ones shown." |
| console_panel (dicas) | Testa se os SGBDs… / Salvar uma cópia… | "Tests whether the target DBMSs answer, without importing anything (--check-dbms). For those that do not, the console shows the command that starts them, to be copied into a terminal." / "Save a copy of this run's log file (DEBUG level, no colours)" |
| main_window | Pronto — nenhuma importação em execução / Comando inválido: aspas não fechadas / Todos os SGBDs estão respondendo / Verificação não passou — veja o console | Ready — no import running / Invalid command: unclosed quotes / All DBMSs are answering / Check failed — see the console |
| main_window | Concluído — {0:.2f} s / Falhou — código de saída {0} / Falhou — {0} / Executando: {0} …\n / Verificando: {0}\n / Executando, Verificando / {0} — {1:02d}:{2:02d} decorridos | Finished — {0:.2f} s / Failed — exit code {0} / Failed — {0} / Running: {0} …\n / Checking: {0}\n / Running, Checking / {0} — {1:02d}:{2:02d} elapsed |
| main_window | Abrir a pasta do log / Interromper a importação / A importação pode parar pela metade… / Salvar log / Não foi possível salvar o log: {0} / Log salvo em {0} / Log (*.log);;Todos (*) | Open the log folder / Stop the import / "The import may stop halfway and leave data partly written. Stop anyway?" / Save log / Could not save the log: {0} / Log saved to {0} / Log (*.log);;All files (*) |
| info_badge | Ajuda | Help |
| state | Arquivo não encontrado: {0} / Selecione a configuração de importação. / SGBD desconhecido: {0} / O tamanho da amostra deve estar entre 1 e {0}. / O nome da fonte não pode ficar vazio. / O nome da fonte não pode conter '=': {0} / Nome de fonte repetido: {0} | File not found: {0} / Choose the import configuration. / Unknown DBMS: {0} / The sample size must be between 1 and {0}. / The source name cannot be empty. / The source name cannot contain '=': {0} / Repeated source name: {0} |
| preflight | Não foi possível ler {0}: {1} / Configuração de SGBDs não informada e {0} não encontrado ao lado da configuração de importação. / A configuração combinada aceita um único arquivo CSV. / Fonte não declarada na configuração de importação: {0} / Fonte '{0}': arquivo CSV não encontrado: {1} / Fonte '{0}': não foi possível ler o cabeçalho de {1}: {2} | Could not read {0}: {1} / DBMS configuration not given and {0} not found next to the import configuration. / The combined configuration takes a single CSV file. / Source not declared in the import configuration: {0} / Source '{0}': CSV file not found: {1} / Source '{0}': could not read the header of {1}: {2} |

  Os comentários de código que citam rótulos antigos, como "Verificar SGBDs" em `command.py`, passam para o rótulo novo.

- [ ] **Step 3: Atualizar os testes que conferem textos.** São cerca de 70 linhas em `test_gui_{config_panel,console_panel,info_badge,main_window,options_panel,preflight,sources_panel,state,style}.py`, cada uma trocada pelo texto da tabela. Os testes de comportamento não mudam. Conferir também `scripts/capture_gui_figures.py`: se ele procura algum rótulo em português, trocar pelo da tabela.

- [ ] **Step 4: Rodar** os dois processos de teste. Esperado: tudo PASS, com o teste-guarda incluído.

- [ ] **Step 5: Conferência visual.** Com `QT_QPA_PLATFORM=offscreen`, abrir a `MainWindow` num script de `.superpowers/scratch/` e salvar um `grab()` em PNG. Olhar a imagem: nenhum texto em português, sem rótulos cortados e sem a linha dos sliders.

- [ ] **Step 6: Commit** dos arquivos de código e de teste listados, com a mensagem `feat(gui): interface em ingles`. Depois, push.

### Task 6: Documentação do código (READMEs, ARCHITECTURE, notas de versão)

**Files:**
- Modify:
  - `README.md`: seções EN e PT da GUI (linhas ~52 e ~326), das opções da CLI (~89–90 e ~363–364) e do executor de campanhas (~216–263 e ~490–538);
  - `docs/ARCHITECTURE.md:19-20` e `:56-57`.
- Create: `docs/releases/v3.2.0.md`

- [ ] **Step 1: README (EN e PT).**
  - A GUI não tem mais controles de tamanho: bloco e lote são automáticos. Os rótulos citados ficam em inglês.
  - `--chunk-size MB`: padrão automático, com a regra numa frase, os limites de 16 a 256 e o motivo registrado no log.
  - `--batch-size N`: padrão 2048 e limites de 512 a 8192.
  - O executor de campanhas:
    - `--chunk-sizes` com padrão `auto`, resolvido uma vez por célula e salvo nos metadados;
    - `--batch-sizes`;
    - o exemplo `16,64,256` no lugar de `8,64,256`.

- [ ] **Step 2: `docs/ARCHITECTURE.md` (EN e PT):** uma frase sobre `auto_size` na descrição do pipeline de fontes.

- [ ] **Step 3: `docs/releases/v3.2.0.md`**, no formato de `v3.0.0.md`:
  - tamanho automático;
  - GUI em inglês, sem os controles de tamanho;
  - limites do lote de 512 a 8192;
  - eixo `--batch-sizes` e memória livre nas campanhas;
  - commit nos metadados;
  - um parágrafo dizendo que as tags `v3.1.0` e `v3.1.1` existem, mas não têm release publicada, porque o CI falhou, e que o que elas mudaram (limites e sliders) está incorporado aqui.

  A versão do `pyproject.toml` só muda na release, com o OK do autor.

- [ ] **Step 4: Conferências.** Rodar `.venv/Scripts/python.exe -m pytest tests/test_naming_dbms.py -q` (PASS). Depois, procurar em `README.md` e em `docs/ARCHITECTURE.md` por `8 MB`, `default 8`, `padrão 8`, `1024` e `Bloco em MB`: nenhuma ocorrência pode sobrar fora de contexto histórico.

- [ ] **Step 5: Commit** de `README.md`, `docs/ARCHITECTURE.md` e `docs/releases/v3.2.0.md`, com a mensagem `docs: tamanho automatico e GUI em ingles nos READMEs; notas da 3.2.0`. Depois, push.

### Fechamento

- [ ] Rodar a suíte completa nos dois processos e registrar as contagens no ledger.
- [ ] Revisão final do branch desde `4f950f7`, feita por um subagente opus com `code-reviewer.md`. Corrigir os itens Critical e Important e registrar os menores.
- [ ] Atualizar a memória `tcc2-roadmap-and-workflow.md`: etapa 2 concluída; a próxima é a campanha final `benchmarks/v4/` com `--chunk-sizes auto`.
