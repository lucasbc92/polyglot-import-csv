---
name: TCC I — Polimento Relatório + Running Example
overview: Corrigir todos os problemas P0/P1 do relatório TCC I para entrega em 1/jul e criar um running example Docker reprodutível com `ecommerce_join.csv`, adicionando evidência real de execução ao §4.4.
todos:
  - id: run-example-script
    content: Criar run_example.ps1 na raiz (docker up, wait Cassandra, dry-run, import real com --create-schema)
    status: completed
  - id: report-p0
    content: "Corrigir P0 no relatório: remover bloco SEÇÕES PENDENTES, corrigir paths docs/, linha 119 metodologia, linha 605 'ficheiro'"
    status: completed
  - id: report-evidence
    content: Adicionar ao §4.4 parágrafo/tabela com contagens reais do dry-run gerado pelo run_example.ps1
    status: completed
  - id: report-conclusion
    content: Adicionar seção 'Considerações Finais' entre §5 e \postextual (contribuições, limitações, ponte TCC II)
    status: completed
  - id: report-ford-citation
    content: Adicionar citação [@ford2008productive] na linha 129 do relatório
    status: completed
  - id: bibtex-updates
    content: Adicionar entrada Neal Ford e urldate aos @misc em references.bib
    status: completed
  - id: siglas-sgpd
    content: Adicionar SGPD à lista de siglas em abntex2.latex
    status: completed
  - id: readme-update
    content: "Atualizar README.md: referências docs/ → docs-tcc/ e instruções do run_example.ps1"
    status: completed
  - id: generate-pdf
    content: Rodar gerar-tcc1.ps1 e verificar o PDF final gerado
    status: completed
isProject: false
---

# TCC I — Polimento Relatório + Running Example

## Escopo confirmado
- Entrega TCC I: 1/jul/2026 (entregável = PDF ABNT em `docs-tcc/`)
- Defesa TCC II: ~1/dez/2026 (com apresentação + banca)
- Foco: relatório polido + running example com `ecommerce_join.csv` funcionando no Docker local
- Abordagem B: relatório + exemplo executável (sem apêndice de configuração completo)

---

## 1. Correções P0 no Relatório

Arquivo: [`docs-tcc/LucasBuenoCesario-PolyglotImportCSV-Report-TCC1.md`](docs-tcc/LucasBuenoCesario-PolyglotImportCSV-Report-TCC1.md)

- **Remover bloco de comentários obsoleto** (linhas 65–77): seção "SEÇÕES PENDENTES" — todas já estão preenchidas. Manter apenas o bloco de compilação e o de citações.
- **Corrigir paths do comentário de build** (linhas 49–51): `.\docs\scripts\...` → `.\docs-tcc\scripts\...`
- **Linha 119** — metodologia: substituir `"As últimas etapas, que estão em andamento, se tratam da implementação..."` por linguagem no passado: *"As etapas de implementação e testes foram concluídas durante a elaboração deste TCC I, resultando no protótipo funcional descrito no Capítulo 4."*
- **Linha 605** — lusitanismo: `"O ficheiro"` → `"O arquivo"`

---

## 2. Correções P1 no Relatório

Ainda em [`docs-tcc/LucasBuenoCesario-PolyglotImportCSV-Report-TCC1.md`](docs-tcc/LucasBuenoCesario-PolyglotImportCSV-Report-TCC1.md):

- **Linha 129** — adicionar citação Neal Ford: `[@ford2008productive]`
- **§4.4** — adicionar parágrafo com evidência de execução dry-run (tabela com contagens por entidade/backend, gerada após rodar o script de exemplo)
- **Seção "Considerações Finais"** — nova seção (½–1 pág.) inserida entre §5 e o bloco `\postextual`, cobrindo: contribuições do TCC I, limitações do protótipo e ponte para o TCC II

---

## 3. Template LaTeX — Lista de Siglas

Arquivo: [`docs-tcc/abntex2.latex`](docs-tcc/abntex2.latex)

Inserir após `\item[SGBD]`:
```latex
\item[SGPD] Sistema de Gerenciamento Poliglota de Dados
```

---

## 4. BibTeX

Arquivo: [`docs-tcc/references.bib`](docs-tcc/references.bib)

- Adicionar entrada para Neal Ford (livro *The Productive Programmer*, 2008, O'Reilly):
```bibtex
@book{ford2008productive,
  author    = {Ford, Neal},
  title     = {The Productive Programmer},
  publisher = {O'Reilly Media},
  year      = {2008}
}
```
- Adicionar `urldate = {2026-05-27}` às entradas `@misc` existentes: `fowler2011polyglot`, `dbcrossbar2024`, `hackolade2024polyglot`

---

## 5. Running Example — `run_example.ps1`

Novo arquivo na raiz: `run_example.ps1`

Fluxo do script:
1. `docker compose up -d` (sobe os 5 serviços)
2. Aguarda Cassandra ficar pronto (health-check por `nc` ou loop de tentativas CQL; Cassandra leva ~90 s)
3. Executa dry-run e imprime saída:
   ```
   python -m polyglotimportcsv data/ecommerce/ecommerce_join.csv --config data/ecommerce/import_config.json --dry-run
   ```
4. Executa import real com `--create-schema`:
   ```
   python -m polyglotimportcsv data/ecommerce/ecommerce_join.csv --config data/ecommerce/import_config.json --create-schema
   ```
5. Imprime resumo de contagens

Credenciais do `import_config.json` já coincidem com o `docker-compose.yml` (verificado):
- Postgres: `postgres/postgres`, db `ecommerce`
- MongoDB: `mongodb://127.0.0.1:27017`, db `ecommerce`
- Cassandra: `127.0.0.1:9042`, keyspace `ecommerce` (criado automaticamente pelo importer)
- Redis: `127.0.0.1:6379`
- Neo4j: `neo4j/password`

---

## 6. README update

Arquivo: [`README.md`](README.md) (raiz)

- Atualizar seção "Running example" para referenciar `run_example.ps1` e os pré-requisitos (Docker Desktop, Python 3.10+)
- Corrigir referências `docs/` → `docs-tcc/` onde existirem

---

## Ordem de execução sugerida

```
5 → Running example (valida o código end-to-end e gera números reais)
2 (§4.4) → Inserir evidência real no relatório
1 + 2 restante → Correções textuais
3 → Siglas
4 → BibTeX
6 → README
→ Gerar PDF final com gerar-tcc1.ps1
```
