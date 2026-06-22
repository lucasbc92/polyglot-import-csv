#!/usr/bin/env bash
# Gera PDF ABNT (abnTeX2). ODT opcional: ./gerar-tcc1.sh --odt
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCS_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BASE="LucasBuenoCesario-PolyglotImportCSV-Report-TCC1"
MD="${DOCS_ROOT}/${BASE}.md"
PDF="${DOCS_ROOT}/${BASE}.pdf"
ODT="${DOCS_ROOT}/${BASE}.odt"
TMPL="${DOCS_ROOT}/abntex2.latex"
BIB="${DOCS_ROOT}/references.bib"
CSL="${DOCS_ROOT}/associacao-brasileira-de-normas-tecnicas.csl"
REF="${DOCS_ROOT}/abnt-ufsc-reference.odt"

ODT_FLAG=false
if [[ "${1:-}" == "--odt" ]]; then
  ODT_FLAG=true
fi

echo "Gerando PDF (abnTeX2 + ABNT)..."
pandoc "${MD}" \
  "--template=${TMPL}" \
  "--resource-path=${DOCS_ROOT}" \
  --top-level-division=chapter \
  --syntax-highlighting=none \
  --pdf-engine=xelatex \
  --citeproc \
  "--bibliography=${BIB}" \
  "--csl=${CSL}" \
  -V documentclass=abntex2 \
  -V classoption=oneside \
  -V papersize=a4paper \
  -V fontsize=12pt \
  -V listoffigures=true \
  -V listofabbreviations=true \
  -o "${PDF}"

if [[ "${ODT_FLAG}" == true ]]; then
  if [[ ! -f "${REF}" ]]; then
    echo "Criando reference.odt ABNT..."
    python3 "${SCRIPT_DIR}/criar-reference-odt-abnt.py"
  fi
  echo "Gerando ODT..."
  pandoc "${MD}" \
    "--resource-path=${DOCS_ROOT}" \
    "--reference-doc=${REF}" \
    --top-level-division=chapter \
    --syntax-highlighting=none \
    --citeproc \
    "--bibliography=${BIB}" \
    "--csl=${CSL}" \
    -V lang=pt-BR \
    -V toc=true \
    -V toc-depth=3 \
    --number-sections \
    -o "${ODT}"
  echo "Ajustando proporcoes das figuras (A4)..."
  python3 "${SCRIPT_DIR}/ajustar-figuras-odt.py" "${ODT}"
fi

echo "Concluido: ${PDF}"
