#!/usr/bin/env bash
# Regenerate Mermaid diagram PNGs for the TCC report.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGES_ROOT="$(cd "${SCRIPT_DIR}/../images" && pwd)"
CFG="${IMAGES_ROOT}/mermaid-config.json"
MERMAID_CLI="@mermaid-js/mermaid-cli@11.4.0"

render() {
  local input="$1"
  local output="$2"
  local width="$3"
  echo "Gerando ${output} ..."
  (
    cd "${IMAGES_ROOT}"
    npx -y "${MERMAID_CLI}" \
      -c "${CFG}" \
      -b white \
      -w "${width}" \
      -s 2 \
      -i "${input}" \
      -o "${output}"
  )
}

render "figure1-polyglot-ecommerce.mmd" "figure1-polyglot-ecommerce.png" 1400
render "figure3-nosql-data-models.mmd" "figure3-nosql-data-models.png" 1400
render "figure4-import-algorithm.mmd" "figure4-import-algorithm.png" 1600

echo "Diagramas atualizados em ${IMAGES_ROOT}"
