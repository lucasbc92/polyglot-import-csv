$ErrorActionPreference = "Stop"
$DocsRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Md = Join-Path $DocsRoot "polyglot-import-csv.md"
$Out = Join-Path $DocsRoot "polyglot-import-csv.tex"
$Tmpl = Join-Path $DocsRoot "abntex2.latex"
$Bib = Join-Path $DocsRoot "references.bib"
$Csl = Join-Path $DocsRoot "associacao-brasileira-de-normas-tecnicas.csl"

pandoc $Md `
  "--template=$Tmpl" `
  "--resource-path=$DocsRoot" `
  --syntax-highlighting=none `
  --citeproc `
  "--bibliography=$Bib" `
  "--csl=$Csl" `
  -V documentclass=abntex2 `
  -V papersize=a4paper `
  -V fontsize=12pt `
  -o $Out
