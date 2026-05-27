param(
    [switch]$Odt
)

$ErrorActionPreference = "Stop"
$DocsRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Base = "LucasBuenoCesario-PolyglotImportCSV-Report-TCC1"
$Md = Join-Path $DocsRoot "$Base.md"
$Pdf = Join-Path $DocsRoot "$Base.pdf"
$OdtOut = Join-Path $DocsRoot "$Base.odt"
$Tmpl = Join-Path $DocsRoot "abntex2.latex"
$Bib = Join-Path $DocsRoot "references.bib"
$Csl = Join-Path $DocsRoot "associacao-brasileira-de-normas-tecnicas.csl"
$RefOdt = Join-Path $DocsRoot "abnt-ufsc-reference.odt"

if (-not (Test-Path $Md)) {
    throw "Arquivo não encontrado: $Md"
}

Write-Host "Gerando PDF (abnTeX2 + ABNT)..."
& pandoc $Md `
  "--template=$Tmpl" `
  "--resource-path=$DocsRoot" `
  --syntax-highlighting=none `
  --pdf-engine=xelatex `
  --citeproc `
  "--bibliography=$Bib" `
  "--csl=$Csl" `
  -V documentclass=abntex2 `
  -V classoption=oneside `
  -V papersize=a4paper `
  -V fontsize=12pt `
  -V listoffigures=true `
  -V listofabbreviations=true `
  -o $Pdf
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar PDF (pandoc/xelatex)." }

Write-Host "  PDF -> $Pdf"

if ($Odt) {
    if (-not (Test-Path $RefOdt)) {
        Write-Host "Criando reference.odt ABNT (primeira execução)..."
        python (Join-Path $PSScriptRoot "criar-reference-odt-abnt.py")
        if ($LASTEXITCODE -ne 0) { throw "Falha ao criar abnt-ufsc-reference.odt." }
    }

    Write-Host "Gerando ODT (estilos ABNT via reference.odt)..."
    & pandoc $Md `
        "--resource-path=$DocsRoot" `
        "--reference-doc=$RefOdt" `
        --syntax-highlighting=none `
        --citeproc `
        "--bibliography=$Bib" `
        "--csl=$Csl" `
        -V lang=pt-BR `
        -V toc=true `
        -V toc-depth=3 `
        --number-sections `
        -o $OdtOut
    if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar ODT." }

    Write-Host "Ajustando proporcoes das figuras (A4)..."
    python (Join-Path $PSScriptRoot "ajustar-figuras-odt.py") $OdtOut
    if ($LASTEXITCODE -ne 0) { throw "Falha ao ajustar figuras no ODT." }

    Write-Host "  ODT -> $OdtOut"
    Write-Host ""
    Write-Host "Nota: capa, folha de rosto e folha de orientadores existem apenas no PDF (abnTeX2)."
    Write-Host "      O ODT replica margens, fonte e espacamento ABNT para revisao de conteudo."
}

Write-Host ""
Write-Host "Concluido."
