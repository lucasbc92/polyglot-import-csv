#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  PY=python
fi

"${PY}" -m polyglotimportcsv \
  "data/ecommerce/ecommerce_join.csv" \
  --config "data/ecommerce/import_config.json" \
  --dry-run
