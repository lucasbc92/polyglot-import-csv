#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# build-docx.sh — gera um DOCX editável (compatível com Google Docs) a partir
# das fontes LaTeX do TCC, usando Pandoc.
#
# Por que Pandoc (e não htlatex/tex4ht):
#   - emite DOCX diretamente (htlatex só chega a ODT; aqui não há LibreOffice);
#   - converte os capítulos (LaTeX padrão) com fidelidade e rapidez;
#   - dispensa o preâmbulo abntex2 (capa/folha de aprovação), que trava o
#     leitor LaTeX do Pandoc e que, de todo modo, é burocracia ABNT não
#     editável em texto corrido.
#
# O que o DOCX inclui: Resumo, Abstract, todos os capítulos, o Apêndice A
# (schemas), figuras embutidas, tabelas, blocos de código e a seção de
# Referências (geradas via citeproc a partir de references.bib).
# Capa, ficha catalográfica e folha de aprovação ABNT NÃO são incluídas
# (recupere-as do PDF se necessário).
#
# O formato de saída é inferido pela extensão do arquivo (.docx ou .odt). O Pandoc
# gera ODT de forma instantânea e limpa — preferível ao tex4ht/htlatex, que é
# impraticavelmente lento com a classe abntex2 (memoir).
#
# Uso:  ./build-docx.sh [saida.docx|saida.odt]
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")"

OUT="${1:-v3.2-TCC1-PolyglotImportCSV-Report.docx}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
COMBINED="$TMP/combined.tex"

# Extrai o conteúdo do N-ésimo ambiente \begin{resumo}...\end{resumo} de main.tex
extract_resumo() {
  awk -v want="$1" '
    /\\begin\{resumo\}/      { c++; if (c==want) { inblk=1; next } }
    /\\end\{resumo\}/        { if (inblk) { inblk=0 } ; next }
    inblk                    { print }
  ' main.tex
}

{
  echo '\section*{Resumo}'
  extract_resumo 1
  echo
  echo '\section*{Abstract}'
  extract_resumo 2
  echo
  # Capítulos + apêndice, na ordem do documento.
  for ch in ch1introducao ch2fundamentacao ch3relacionados ch4proposta \
            ch5futuros consideracoes apendiceschemas; do
    cat "chapters/$ch.tex"
    echo
  done
} \
  | sed -E 's/\\citeonline/\\citet/g' \
  | sed -E 's/(\\includegraphics(\[[^]]*\])?\{images\/[^}.]*)\}/\1.png}/g' \
  > "$COMBINED"

pandoc "$COMBINED" \
  -f latex \
  --resource-path=.:images \
  --citeproc --bibliography=references.bib \
  --metadata reference-section-title=Referências \
  --toc --toc-depth=3 \
  -o "$OUT"

echo "OK -> $OUT"
