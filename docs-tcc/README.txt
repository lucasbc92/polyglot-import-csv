Toda a cadeia Pandoc + abnTeX2 vive nesta pasta (docs-tcc/).

Relatorio principal (TCC1):
  LucasBuenoCesario-PolyglotImportCSV-Report-TCC1.md

Gerar PDF ABNT (versao oficial):
  A partir da raiz do repositorio:
    .\docs-tcc\scripts\gerar-tcc1.ps1

Gerar PDF + ODT para revisao (LibreOffice / Google Docs):
    .\docs-tcc\scripts\gerar-tcc1.ps1 -Odt

  Saidas:
    LucasBuenoCesario-PolyglotImportCSV-Report-TCC1.pdf  — ABNT completo (abnTeX2)
    LucasBuenoCesario-PolyglotImportCSV-Report-TCC1.odt  — conteudo editavel (opcional)

  O PDF e a unica saida fiel a ABNT (capa, folha de rosto, folha de orientadores,
  listas pre-textuais). O ODT usa abnt-ufsc-reference.odt (margens NBR 14724,
  Times 12 pt, espacamento 1,5, titulos) e serve para revisao de texto.

  Google Docs: envie o .odt ao Drive e use "Abrir com" -> Google Docs.

  Recriar estilos do reference.odt:
    python docs-tcc/scripts/criar-reference-odt-abnt.py

  Figuras no ODT sao redimensionadas automaticamente para A4 (ate 16cm de largura)
  pelo script ajustar-figuras-odt.py apos o Pandoc.

Running example (codigo + Docker):
  .\run_example.ps1   (na raiz do repositorio)

Figuras em docs-tcc/images/:
  figure1-polyglot-ecommerce.png — e-commerce poliglota
  figure2-polyglot-persistence-azure.png — Azure (referencia externa)
  figure3-nosql-data-models.png — modelos NoSQL
  figure4-import-algorithm.png — algoritmo de importacao
  figure*.mmd — fontes Mermaid (regenerar com gerar-diagramas.ps1)
