#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCS_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MD="${DOCS_ROOT}/polyglot-import-csv.md"
TEX="${DOCS_ROOT}/polyglot-import-csv.tex"
TMPL="${DOCS_ROOT}/abntex2.latex"
BIB="${DOCS_ROOT}/references.bib"
CSL="${DOCS_ROOT}/associacao-brasileira-de-normas-tecnicas.csl"

pandoc "${MD}" \
  "--template=${TMPL}" \
  "--resource-path=${DOCS_ROOT}" \
  --syntax-highlighting=none \
  --citeproc \
  "--bibliography=${BIB}" \
  "--csl=${CSL}" \
  -V documentclass=abntex2 \
  -V papersize=a4paper \
  -V fontsize=12pt \
  -o "${TEX}"

(
  cd "${DOCS_ROOT}"
  xelatex "$(basename "${TEX}")"
)
