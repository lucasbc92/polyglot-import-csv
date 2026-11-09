# Etapa 1 — Limites, eixo de lote e campanha exploratória — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir os limites do lote (512–8192), dar ao executor de campanhas um eixo de lote e o registro da memória livre, e medir a campanha exploratória que vai definir a regra do tamanho automático.

**Architecture:** O eixo `batch_sizes` entra em `benchmark_runner.run_matrix` ao lado de `chunk_sizes`, e o rótulo de cada execução ganha `batch_lines` e `free_memory_mb`. A consolidação e o CSV passam a ter essas duas colunas, e `--resume` passa a comparar `batch_sizes`. Um módulo novo, `system_memory`, lê a memória livre do sistema; ele também será usado pelo modo automático na etapa 2. A campanha roda em quatro pastas, um eixo de cada vez. Um script de análise descartável tira dela a regra, que fica registrada no spec.

**Tech Stack:** Python 3.14 (`.venv`), click, pytest; Docker Compose para a campanha.

**Spec:** `docs/superpowers/specs/2026-11-08-revisao-ronaldo-v23-design.md` (Parte 1, itens 1–2; Parte 3, 3a; decisões sobre a regra do bloco e do lote).

## Global Constraints

- Branch `revisao-ronaldo-v23`. Push depois de cada commit. Commits em português, com o trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Todo comando git leva o prefixo `rtk`. Preparar só caminhos explícitos.
- Limites: bloco **16–256 MB** (padrão 128, já no código); lote **512–8192 linhas**, padrão **2048** (explícito, e não `MIN*8`).
- A GUI não muda nesta etapa, exceto as mensagens de `gui/state.py`, que repetem os limites. Os sliders e os 8 testes de GUI quebrados desde `6b7becc` são resolvidos na etapa 2, que remove os sliders.
- Os READMEs e as notas de versão são atualizados na etapa 2, junto com o modo automático.
- Testes em dois processos (8 GB de RAM): `.venv/Scripts/python.exe -m pytest -q -rfEs tests --ignore-glob="tests/test_gui_*"` e `.venv/Scripts/python.exe -m pytest -q tests/test_gui_*.py`.
- Docker: o autor autorizou ligar quando for preciso (memória `docker-start-authorized`). Desligar só com OK. Se o motor travar, `docker desktop restart`.
- Campanhas destacadas, com `Start-Process`, nunca com `run_in_background`. Retomar com `--resume`.
- Arquivos descartáveis vão para `.superpowers/scratch/`.

## Review Focus

1. **Checkpoint antigo, sem `batch_lines`, retomado com o código novo.** O esperado é que `resume_runs` o recuse por `batch_sizes` (porque `RESUME_KEYS` muda), em vez de quebrar com `KeyError`. Teste na Task 2.
2. **CSV de uma pasta antiga (cabeçalho sem `batch_lines`).** O esperado é que ele seja recusado antes de a matriz rodar, como hoje. O teste existente de recusa precisa continuar passando com o cabeçalho novo (Task 2).
3. **Memória livre ilegível** (plataforma sem `/proc/meminfo` nem Windows). `available_mb()` devolve `None` e o resultado sai com `free_memory_mb` vazio, sem exceção (Task 2).
4. **Lote maior que as linhas de um bloco pequeno** (bloco de 16 MB). `entity_batch` limita o lote às linhas do bloco. A campanha precisa registrar o lote pedido, e o texto da análise precisa saber que o lote efetivo pode ser menor. A Task 4 calcula as linhas por bloco de cada fonte.
5. **`--batch-size` fora de 512–8192 na CLI.** O click recusa com código 2, e o texto de ajuda mostra o intervalo novo (Task 1).

---

### Task 1: Limites do lote e textos de ajuda

**Files:**
- Modify: `src/polyglotimportcsv/import_plan.py:20-23`, `src/polyglotimportcsv/cli.py:82-100`, `src/polyglotimportcsv/gui/state.py:70-75`, `scripts/run_benchmarks.py:110-113`
- Modify (testes que fixam os limites e padrões antigos): os que falham na linha de base de 2026-11-09 por causa dos limites (lista no ledger)
- Test: `tests/test_import_plan.py`, `tests/test_cli_limits.py` (novo)

**Interfaces:**
- Produces: `MIN_BATCH_LINES = 512`, `MAX_BATCH_LINES = 8192`, `DEFAULT_BATCH_LINES = 2048` em `import_plan`.

- [ ] **Step 1: Teste dos limites**

`tests/test_cli_limits.py`:
```python
from click.testing import CliRunner
from polyglotimportcsv.cli import main
from polyglotimportcsv import import_plan, stream_source

def test_batch_limits_are_512_to_8192_default_2048():
    assert (import_plan.MIN_BATCH_LINES, import_plan.DEFAULT_BATCH_LINES, import_plan.MAX_BATCH_LINES) == (512, 2048, 8192)

def test_chunk_limits_are_16_to_256_default_128():
    assert (stream_source.MIN_CHUNK_MB, stream_source.DEFAULT_CHUNK_MB, stream_source.MAX_CHUNK_MB) == (16, 128, 256)

def test_help_shows_the_current_ranges():
    out = CliRunner().invoke(main, ["--help"]).output
    assert "(16-256)" in out and "(512-8192)" in out

def test_batch_below_512_is_refused():
    r = CliRunner().invoke(main, ["--config", "x.json", "--batch-size", "256"])
    assert r.exit_code == 2 and "512" in r.output
```
Use o nome real do comando click exportado por `cli.py`, que pode não ser `main`.

- [ ] **Step 2: Rodar.** Expected: FAIL (MIN 256 e a ajuda antiga).
- [ ] **Step 3: Implementar.**
  - `import_plan`: `MIN_BATCH_LINES = 512`, `MAX_BATCH_LINES = 8192`, `DEFAULT_BATCH_LINES = 2048`.
  - Ajuda da CLI: "(16-256)" e "(512-8192)".
  - `gui/state.py`: as mensagens usam as constantes (f-string) em vez de números fixos.
  - Ajuda de `--chunk-sizes` no `run_benchmarks.py`: "Use '16,64,256'".
- [ ] **Step 4: Testes que fixam os valores antigos.** Na suíte fora da GUI, atualizar cada teste cuja falha na linha de base vem dos limites ou padrões antigos (8/1024 → 128/2048; 8–256 → 16–256; 1024–8192 → 512–8192). Falhas de outra natureza ficam registradas no ledger e não são mexidas.
- [ ] **Step 5: Suíte fora da GUI.** Expected: só falham os testes que já falhavam na linha de base por outro motivo (lista no ledger).
- [ ] **Step 6: Commit** "fix: limites do lote 512-8192 (padrao 2048) e textos de ajuda coerentes".

---

### Task 2: Eixo de lote, memória livre e colunas novas no executor

**Files:**
- Create: `src/polyglotimportcsv/system_memory.py`
- Modify: `src/polyglotimportcsv/benchmark_runner.py` (`run_matrix`, `_run_key`), `src/polyglotimportcsv/benchmark_results.py` (`_RESULT_FIELDS`, `median_results`), `scripts/run_benchmarks.py` (`--batch-sizes`, `RESUME_KEYS`, metadados)
- Modify: os importadores falsos dos testes do executor, que passam a aceitar `batch_size`
- Test: `tests/test_system_memory.py` (novo), `tests/test_benchmark_batch_flag.py` (novo), `tests/test_benchmark_resume.py`, `tests/test_benchmark_results.py`

**Interfaces:**
- Produces:
  - `system_memory.available_mb() -> Optional[float]`: memória física disponível em MiB (Windows: `GlobalMemoryStatusEx.ullAvailPhys` via `ctypes`; Linux: `MemAvailable` de `/proc/meminfo`; outras plataformas ou erro: `None`).
  - `run_matrix(..., batch_sizes: Iterable[int] = (DEFAULT_BATCH_LINES,), ...)` chama `importer(..., chunk_size_mb=c, batch_size=b)`.
  - Cada execução rotulada ganha `"batch_lines": b` e `"free_memory_mb": available_mb()`, lido antes da limpeza dos SGBDs.
  - `_run_key` passa a ser `(size, mode, chunk_mb, batch_lines, repetition)`.
  - `_RESULT_FIELDS = ("timestamp","size","mode","chunk_mb","batch_lines","dbms","entity","phase","rows","median_seconds","rows_per_second","peak_memory_mb","free_memory_mb")`.
  - `median_results` agrupa também por `batch_lines`; `free_memory_mb` é a mediana dos valores não nulos, ou `None`.
  - `run_benchmarks.py`: `--batch-sizes` (padrão `str(DEFAULT_BATCH_LINES)`); `RESUME_KEYS` inclui `"batch_sizes"`; os metadados levam `batch_sizes`.

- [ ] **Step 1: Testes.**
  - `test_system_memory.py`: `available_mb()` devolve um `float > 0` nesta máquina; com `sys.platform` forçado a `"darwin"` (monkeypatch), devolve `None`.
  - `test_benchmark_batch_flag.py`, no molde de `test_benchmark_chunk_flag.py`:
    - o padrão `[2048]` chega a `run_matrix` e aos metadados;
    - `--batch-sizes 512,8192` vira `[512, 8192]`;
    - `run_matrix` aceita 512 e 8192, recusa 256 e 8193 com `ValueError` que cita "batch size", e não roda nada ao recusar;
    - a matriz percorre bloco × lote e passa `batch_size` ao importador, e o rótulo traz `batch_lines` e `free_memory_mb`.
  - `test_benchmark_resume.py`: um checkpoint sem `batch_sizes` nos metadados é recusado com uma mensagem que cita `batch_sizes`.
  - `test_benchmark_results.py`: duas execuções que só diferem em `batch_lines` viram duas linhas, e `free_memory_mb` é a mediana.
- [ ] **Step 2: Rodar.** Expected: FAIL (`system_memory` inexistente; `batch_sizes` desconhecido).
- [ ] **Step 3: Implementar** conforme as Interfaces. A faixa de lote vem de `import_plan.MIN_BATCH_LINES`/`MAX_BATCH_LINES`. O laço fica `for chunk_mb in chunk_sizes: for batch in batch_sizes:` dentro do laço das células, e a ordem das repetições continua por fora.
- [ ] **Step 4: Importadores falsos.** Os fakes de `tests/test_benchmark_runner.py`, `test_benchmark_resume.py`, `test_benchmark_chunk_flag.py`, `test_benchmark_trace_flag.py` e `test_benchmark_tracemalloc_ab.py` (se chamar `run_matrix`) passam a aceitar `batch_size`. Asserções sobre o cabeçalho do CSV recebem as duas colunas novas.
- [ ] **Step 5: Suíte fora da GUI.** Expected: verde, salvo as falhas da linha de base de outra natureza.
- [ ] **Step 6: Commit** "feat(bench): eixo --batch-sizes e memoria livre por execucao no executor de campanhas".

---

### Task 3: Campanha exploratória (`benchmarks/v4-explore/`)

**Files:**
- Create: `benchmarks/v4-explore/{chunks-timings,chunks-memory,batches-timings,batches-memory}/{benchmark_results.csv,benchmark_run_*.json}`
- Modify (não versionado): `.superpowers/scratch/check_campaign.py`, que passa a receber os volumes e os eixos esperados por parâmetro

- [ ] **Step 1: Pré-condições.** Tasks 1–2 commitadas e enviadas; Docker no ar (`docker compose up -d --wait`, ligado sem perguntar); memória livre anotada.
- [ ] **Step 2: As quatro campanhas, uma de cada vez, destacadas.**

```
--sizes 131072 --modes multi --chunk-sizes 16,32,64,128,256 --batch-sizes 2048 --repetitions 3 --no-trace-memory --out benchmarks/v4-explore/chunks-timings
--sizes 131072 --modes multi --chunk-sizes 16,32,64,128,256 --batch-sizes 2048 --repetitions 1 --out benchmarks/v4-explore/chunks-memory
--sizes 131072 --modes multi --chunk-sizes 128 --batch-sizes 512,1024,2048,4096,8192 --repetitions 3 --no-trace-memory --out benchmarks/v4-explore/batches-timings
--sizes 131072 --modes multi --chunk-sizes 128 --batch-sizes 512,1024,2048,4096,8192 --repetitions 1 --out benchmarks/v4-explore/batches-memory
```

Cerca de 70 min por campanha de tempo e 60 min por campanha de memória. Cada uma é acompanhada por um monitor com detecção de parada (20 min sem saída no log). Se o motor do Docker travar: encerrar o Python da campanha, `docker desktop restart`, subir o compose e retomar com `--resume`.
- [ ] **Step 3: Conferência de cada pasta.** Com o `check_campaign.py` adaptado: um só *timestamp*; nenhuma chave `(size, mode, chunk_mb, batch_lines, dbms, entity, phase)` repetida; as 5 células do eixo; picos preenchidos/vazios conforme o tipo; `infer`/`validate` com `rows == size`; `free_memory_mb` preenchido; e, entre as pastas pares, `rows` idêntico.
- [ ] **Step 4: Commit e push de cada pasta conferida** ("bench: campanha exploratoria, <eixo> <tempo|memoria>").

---

### Task 4: Análise e regra

**Files:**
- Create (não versionado): `.superpowers/scratch/explore_numbers.py` e a sua saída `explore_numbers.txt`
- Modify: `docs/superpowers/specs/2026-11-08-revisao-ronaldo-v23-design.md` (nova seção "Resultado da campanha exploratória")
- Modify: `benchmarks/README.md` (seção curta EN/PT sobre `v4-explore/`)

- [ ] **Step 1: Script.** Para cada eixo, imprimir:
  - o tempo total (soma das medianas das fases), inferência, validação e escrita por SGBD;
  - o pico de memória e a memória livre;
  - as linhas por bloco de cada fonte (`stream_source.chunk_rows`) e o lote efetivo de cada entidade (`min(lote, linhas do bloco)`).

  A variação entre campanhas sai da célula comum (128 MB, 2048), medida em `chunks-timings` e em `batches-timings`.
- [ ] **Step 2: Regra do bloco** (decisão do spec):
  - **teto** = o menor bloco cujo tempo total fica dentro da variação entre campanhas, ou de 3% se ela for menor, do melhor tempo;
  - **ajuste do pico:** `pico ≈ base + k × bloco`, por mínimos quadrados sobre `chunks-memory`;
  - **limite de segurança:** o maior bloco cujo pico previsto cabe em 25% da memória livre;
  - **bloco automático** = mín(teto, limite, o necessário para ler a maior fonte inteira), preso a [16, 256].
- [ ] **Step 3: Regra do lote.** O menor lote cujo tempo total fica dentro da mesma tolerância do melhor. Se algum SGBD tiver o seu melhor tempo de escrita em outro lote, isso é registrado como atividade futura.
- [ ] **Step 4: Registrar** no spec os números das tabelas, a tolerância, `base`, `k`, o teto e o lote escolhidos, e o bloco que a regra daria nesta máquina com a memória livre medida. Também uma frase sobre o que muda se as regras de corte forem outras. No README, a mesma seção curta, em EN e PT.
- [ ] **Step 5: Commit** "docs: resultado da campanha exploratoria e regra do tamanho automatico".
