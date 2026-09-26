# Releases do PolyglotImportCSV no GitHub — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publicar a v1.0.0 com executáveis de Windows e Linux (CLI e GUI) na página de releases do GitHub, gerados por um workflow do GitHub Actions.

**Architecture:** A lógica de montagem dos pacotes fica num script Python testável (`scripts/package_release.py`), e o workflow (`.github/workflows/release.yml`) só orquestra: testes → PyInstaller → script de pacote → teste de fumaça → release. O workflow é validado no branch antes do merge, sem publicar nada; a publicação acontece só com a tag `v1.0.0` em `main`.

**Tech Stack:** GitHub Actions (`windows-latest`, `ubuntu-latest`), Python 3.12, PyInstaller, `softprops/action-gh-release`.

**Spec:** `docs/superpowers/specs/2026-09-26-releases-github-design.md`

## Global Constraints

- Versão **1.0.0**, num único lugar lógico: `pyproject.toml` e `polyglotimportcsv.__version__` iguais, conferidos por teste; o workflow usa o nome da tag nos arquivos.
- Plataformas: `windows-x64` e `linux-x64`. Nada de macOS.
- Artefatos por plataforma: `polyglotimportcsv-<tag>-<so>.zip` (CLI) e `polyglotimportcsv-gui-<tag>-<so>.zip` (GUI). Cada um leva o executável, `data/ecommerce/` **sem** o `.xlsx`, `docker-compose.yml`, `LICENSE` e `LEIAME.txt`.
- Testes no job `test` rodam em `windows-latest`; se falhar, não há release.
- Teste de fumaça do executável da CLI: `--help` e `--dry-run` do cenário de e-commerce. No da GUI: `--cli --help` (o executável da GUI também é a CLI).
- Nada é publicado antes do merge: o workflow é exercitado no branch por um gatilho temporário de `push` em `tcc2-gui`, removido antes do merge.
- Commits em português, `Co-Authored-By` no fim, `git push` a cada commit.

## Review Focus

- **Executável sem os schemas JSON:** o `--dry-run` do teste de fumaça valida as configurações, então falha se o PyInstaller não empacotou `schemas/`.
- **Driver do Cassandra ausente no executável:** o `--dry-run` não importa o driver; o teste de fumaça importa `cassandra.cluster` pelo executável (`--cli` não serve para isso), então o job de build confere o módulo no ambiente e o `.spec` ganha `hiddenimports` se a análise mostrar falta.
- **Zip com caminhos absolutos ou com o `.xlsx`:** coberto por teste do script de pacote.
- **Versão divergente entre `pyproject.toml` e `__version__`:** coberto por teste.
- **Gatilho temporário esquecido no merge:** verificação explícita na Tarefa 4.

---

### Task 1: Versão 1.0.0

- [ ] Teste `tests/test_version.py`: lê `pyproject.toml` com `tomllib` (Python ≥ 3.11; pular com `pytest.importorskip("tomllib")` se ausente) e compara `project.version` com `polyglotimportcsv.__version__`; e confere que ambos são `"1.0.0"`.
- [ ] Rodar: falha (0.1.0).
- [ ] `pyproject.toml` e `src/polyglotimportcsv/__init__.py` para `1.0.0`.
- [ ] Rodar: passa. Commit `chore: versao 1.0.0`.

### Task 2: Script de pacote

- [ ] Teste `tests/test_package_release.py` com um `dist/` falso em `tmp_path` (um arquivo executável qualquer) e um repositório falso mínimo (`data/ecommerce/a.csv`, `data/ecommerce/x.xlsx`, `docker-compose.yml`, `LICENSE`, `packaging/LEIAME.txt`): `build_zip(repo, executable, out_dir, name)` gera `name.zip` contendo `name/<executável>`, `name/data/ecommerce/a.csv`, `name/docker-compose.yml`, `name/LICENSE`, `name/LEIAME.txt`, e **não** contém o `.xlsx` nem caminhos absolutos.
- [ ] Rodar: falha (módulo inexistente).
- [ ] `scripts/package_release.py` com `build_zip(...)` e um `main()` de linha de comando: `--tag`, `--os` (`windows-x64`|`linux-x64`), `--dist` (padrão `dist`), `--out` (padrão `release`); gera os dois zips (CLI: `polyglotimportcsv[.exe]`; GUI: `polyglotimportcsv-gui[.exe]`).
- [ ] `packaging/LEIAME.txt`: como executar a GUI e a CLI, o `--dry-run` do cenário, como subir os SGBDs com `docker compose up -d`, onde fica o log, o aviso do SmartScreen no Windows.
- [ ] Rodar: passa. Commit `feat(release): script que monta os pacotes da release`.

### Task 3: Workflow e notas da release

- [ ] Build local com PyInstaller (`pip install pyinstaller` no venv; `pyinstaller polyglotimportcsv.spec`), teste de fumaça local dos dois executáveis; ajustar `hiddenimports` do `.spec` se faltar algo; conferir `upx=False` (o spec ganha `upx=False`, para não disparar antivírus).
- [ ] `.github/workflows/release.yml` com os jobs `test` (windows), `build` (matriz windows/ubuntu, Python 3.12: instala `.[gui]` e `pyinstaller`, `python -c "import cassandra.cluster"`, PyInstaller, teste de fumaça, `scripts/package_release.py`, `upload-artifact`) e `release` (só em tag `v*`: baixa os artefatos e publica com `softprops/action-gh-release`, corpo `docs/releases/${{ github.ref_name }}.md`). Gatilhos: `push` de tags `v*`, `workflow_dispatch` e, **temporariamente**, `push` em `tcc2-gui`.
- [ ] `docs/releases/v1.0.0.md` em português: capacidades, conteúdo dos pacotes, requisitos (Docker para os SGBDs), limitações (sem macOS, executáveis sem assinatura).
- [ ] Push; acompanhar o run com `gh run watch`; corrigir até verde nos dois sistemas; baixar os artefatos e conferir o conteúdo dos zips.
- [ ] Commit(s) `ci(release): ...`.

### Task 4: Documentação, PDF 2.1 e publicação

- [ ] README (EN e PT): seção de download apontando para a página de releases.
- [ ] Relatório: nota de rodapé da Seção 4.1 acrescenta que os executáveis para Windows e Linux estão na página de releases do projeto (o spec condiciona isso à release existir; ela é publicada nesta mesma tarefa).
- [ ] Remover o gatilho temporário de `push` em `tcc2-gui` do workflow; `grep -n "tcc2-gui" .github/workflows/release.yml` vazio.
- [ ] Suíte completa verde.
- [ ] `cd docs-tcc && latexmk -pdf -interaction=nonstopmode main.tex`; copiar `main.pdf` para `TCC2-PolyglotImportCSV-Report-v2.1.pdf`; apagar `TCC2-PolyglotImportCSV-Report-v2.0.pdf`; manter o v1.0. Commit do v2.1.
- [ ] Merge de `tcc2-gui` em `main`, suíte verde no resultado, push de `main`.
- [ ] Tag `v1.0.0` em `main`, push da tag; acompanhar o workflow até a release publicada; conferir os quatro zips anexados.
