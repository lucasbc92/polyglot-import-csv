# Design — Releases do PolyglotImportCSV no GitHub

Data: 2026-09-26
Status: aprovado em brainstorming; aguardando revisão do autor.

Parte 2 de 3 das mudanças da reunião de 25/09. É executada **por último**,
depois de as partes 1 (GUI/CLI) e 3 (relatório) estarem em `tcc2-gui` e de
`tcc2-gui` ser mesclado em `main`, para que a primeira release contenha a
interface descrita no relatório.

## 1. Objetivo

Publicar executáveis prontos para uso na página de releases de
`github.com/lucasbc92/polyglot-import-csv`, de modo que a ferramenta possa ser
usada sem instalar Python. Há duas variantes:

- **CLI** (`polyglotimportcsv`): todas as opções, inclusive as que a GUI não
  expõe (`--benchmark`, `--strategy naive`).
- **GUI** (`polyglotimportcsv-gui`): a interface. O mesmo executável também
  funciona como CLI completa quando chamado com `--cli` (é assim que a GUI roda
  a importação, `gui/launcher.py`), então nenhuma opção fica inacessível.

## 2. Plataformas

Windows (`windows-latest`) e Linux (`ubuntu-latest`), nos *runners* gratuitos
do GitHub Actions. O macOS fica de fora: executável sem assinatura bloqueado
pelo Gatekeeper e extensão C do `cassandra-driver` em Apple Silicon. Fica
registrado como possibilidade futura.

## 3. Workflow `.github/workflows/release.yml`

Disparo: `push` de tag `v*` e, para testar sem publicar, `workflow_dispatch`
(gera os artefatos no *run* sem criar release).

Jobs:

1. **`test`** (windows-latest): instala `.[dev,gui]` e roda
   `pytest tests -q`. Roda no Windows, a plataforma contra a qual os testes da
   GUI foram escritos. No Linux sem tela, o `QT_QPA_PLATFORM=offscreen` não tem
   fontes e distorce os tamanhos, o que pode falhar testes de layout sem haver
   defeito real. Falhou, não há release.
2. **`build`** (matriz windows/ubuntu, depende de `test`): instala o pacote com
   `PySide6` e `pyinstaller`, roda `pyinstaller polyglotimportcsv.spec` e monta
   dois zips por plataforma:
   - `polyglotimportcsv-<versão>-<so>.zip`: executável da CLI;
   - `polyglotimportcsv-gui-<versão>-<so>.zip`: executável da GUI.

   Os dois zips levam também `data/ecommerce/` (sem o `.xlsx`),
   `docker-compose.yml`, `LICENSE` e um `LEIAME.txt` curto: como subir os SGBDs
   com Docker, o comando de *dry-run* do cenário e onde fica o log.
   `<so>` é `windows-x64` ou `linux-x64`.
3. **`release`** (depende de `build`, só em tag): cria a release com
   `softprops/action-gh-release` (ou `gh release create`), anexa os quatro
   zips e usa como corpo as notas de `docs/releases/<tag>.md`.

Um *smoke test* no job `build`, antes de zipar: `polyglotimportcsv --help` e
um `--dry-run` do cenário de e-commerce com o executável gerado, para garantir
que o PyInstaller empacotou os schemas e as dependências (o `--dry-run` não
conecta aos SGBDs). No Linux, a GUI só é verificada quanto à importação do
módulo, sem abrir janela.

## 4. Versão

- Primeira release: **v1.0.0**, a versão entregue no TCC2.
- `pyproject.toml` passa de `0.1.0` para `1.0.0`. A versão fica em um único
  lugar: o workflow a lê da tag, e o nome dos zips usa a tag.
- As notas da v1.0.0 (`docs/releases/v1.0.0.md`, em português) resumem as
  capacidades: cinco SGBDs, modos multifonte e combinado, `stream` e
  `materialize`, GUI, onde está o cenário de exemplo, e as limitações
  conhecidas (sem macOS; Cassandra exige o *driver* nativo, embutido nos
  executáveis).

## 5. Riscos

- **PyInstaller e o `cassandra-driver`:** a extensão C e os *hidden imports*
  podem faltar no executável. O *smoke test* com `--dry-run` não importa o
  *driver* (o *dry-run* não conecta), então é acrescentado um passo
  `python -c "import cassandra.cluster"` no ambiente de build e, no
  executável, uma verificação do módulo empacotado. Se o `.spec` precisar de
  `hiddenimports`, eles são adicionados.
- **UPX:** `upx=True` no `.spec` pode gerar executáveis marcados por
  antivírus no Windows. Os *runners* não têm UPX instalado, então na prática
  ele não é aplicado. Se for instalado no futuro, deve ser desligado.
- **Tamanho:** PySide6 deixa o executável da GUI com ~100 MB ou mais. É
  aceitável para um anexo de release e fica registrado nas notas.
- **Executável sem assinatura no Windows:** o SmartScreen avisa na primeira
  execução. O LEIAME explica como prosseguir.

## 6. Fora do escopo

- Publicação no PyPI.
- Instaladores (MSI, .deb) e atualização automática.
- macOS.
