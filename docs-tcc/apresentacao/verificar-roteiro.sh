#!/usr/bin/env bash
# Compila o roteiro de estudo e confere as regras dele.
# Uso: bash verificar-roteiro.sh [página ...]
#   [página]  páginas do PDF do roteiro a renderizar em render/roteiro-<P>.png (60 dpi)
# Confere: 22 seções (abertura, 20 slides de conteúdo e fechamento); soma dos tempos-alvo dos
# 20 slides entre 840 e 870 s; nenhuma referência indefinida (as miniaturas vêm dos rótulos
# do deck, lidos de apresentacao.aux).
set -euo pipefail
cd "$(dirname "$0")"

falha() { echo "FALHA: $*" >&2; exit 1; }

n=$(grep -c '^\\slideroteiro{' roteiro-estudo.tex || true)
[ "$n" -eq 22 ] || falha "22 seções esperadas, $n encontradas"

# \slideroteiro{rótulo}{revelação}{segundos}{título}: campos 2 e 6 ao separar por { e }.
soma=$(grep '^\\slideroteiro{' roteiro-estudo.tex \
  | awk -F'[{}]' '$2 != "roteiro" && $2 != "fechamento" { s += $6 } END { print s + 0 }')
[ "$soma" -ge 840 ] && [ "$soma" -le 870 ] \
  || falha "soma dos 20 slides de conteúdo: $soma s; esperado entre 840 e 870"

# O roteiro lê apresentacao.aux e apresentacao.pdf: recompila o deck se alguma fonte for
# mais nova que o PDF.
if [ ! -f apresentacao.aux ] || [ ! -f apresentacao.pdf ] \
   || [ -n "$(find apresentacao.tex beamerthemeufsc.sty secoes -newer apresentacao.pdf -print -quit)" ]; then
  latexmk -pdf -interaction=nonstopmode -halt-on-error apresentacao.tex > /dev/null 2>&1 \
    || falha "o deck não compila (ver apresentacao.log)"
fi

if ! latexmk -pdf -interaction=nonstopmode -halt-on-error roteiro-estudo.tex > /dev/null 2>&1; then
  grep -A 3 '^!' roteiro-estudo.log >&2 2>/dev/null || true
  falha "o roteiro não compila (ver roteiro-estudo.log)"
fi

if grep -E "Reference .* undefined" roteiro-estudo.log; then
  falha "referência indefinida no roteiro"
fi

if [ $# -gt 0 ]; then
  mkdir -p render
  for p in "$@"; do
    pdftoppm -png -r 60 -f "$p" -l "$p" -singlefile roteiro-estudo.pdf "render/roteiro-$p" \
      || falha "não foi possível renderizar a página $p"
  done
fi

echo "OK seções=$n soma=${soma}s"
