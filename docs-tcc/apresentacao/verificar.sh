#!/usr/bin/env bash
# Compila a apresentação e confere as regras da defesa.
# Uso: bash verificar.sh <corpo> <cartas> [página ...]
#   <corpo>   número esperado do frame de fechamento ("Obrigado! Perguntas?")
#   <cartas>  número esperado de \begin{frame} em secoes/6-cartas.tex
#   [página]  páginas do PDF a renderizar em render/pagina-<P>.png (80 dpi)
set -euo pipefail
cd "$(dirname "$0")"

falha() { echo "FALHA: $*" >&2; exit 1; }

[ $# -ge 2 ] || falha "uso: bash verificar.sh <corpo> <cartas> [página ...]"
corpo=$1
cartas=$2
shift 2

if ! latexmk -pdf -interaction=nonstopmode -halt-on-error apresentacao.tex > /dev/null 2>&1; then
  grep -A 3 '^!' apresentacao.log >&2 2>/dev/null || true
  falha "a compilação falhou (ver apresentacao.log)"
fi

numero=$(grep -o 'FECHAMENTO-NUMERO=[0-9]*' apresentacao.log | tail -n 1 | cut -d= -f2 || true)
[ "$numero" = "$corpo" ] || falha "o fechamento é o frame ${numero:-?}; esperado: $corpo"

n_cartas=$(grep -o '\\begin{frame}' secoes/6-cartas.tex | wc -l || true)
[ "$n_cartas" -eq "$cartas" ] || falha "secoes/6-cartas.tex tem $n_cartas frames; esperado: $cartas"

fontes=(apresentacao.tex beamerthemeufsc.sty secoes/*.tex)
if grep -n -i 'backend' "${fontes[@]}"; then
  falha "termo vetado (use \"SGBD\")"
fi
if grep -n -F -e '\tiny' -e '\trans' -e '\movie' -e '\sound' "${fontes[@]}"; then
  falha "comando proibido (\\tiny, \\trans, \\movie ou \\sound)"
fi

if grep -E 'Overfull \\[hv]box' apresentacao.log; then
  falha "caixa estourada (Overfull) no apresentacao.log"
fi

if [ $# -gt 0 ]; then
  mkdir -p render
  for p in "$@"; do
    pdftoppm -png -r 80 -f "$p" -l "$p" -singlefile apresentacao.pdf "render/pagina-$p" \
      || falha "não foi possível renderizar a página $p"
  done
fi

echo "OK corpo=$corpo cartas=$cartas"
