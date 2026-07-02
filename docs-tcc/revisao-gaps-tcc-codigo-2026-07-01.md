# Revisão cruzada TCC × Código + Verificação de Referências (2026-07-01)

Auditoria do texto em `docs-tcc/polyglot-tcc-latex-final/` contra o código em
`src/polyglotimportcsv/` (nas duas direções), excluindo o Capítulo 5 (Atividades
Futuras). Todos os itens marcados **[verificado]** foram confirmados executando o
código (dry-run real, pytest, script de checagem de schema/validação).

## O que o texto afirma e o código CONFIRMA

- Contagens da Tabela `tab:dryrun` batem exatamente com a execução real de
  `--dry-run` no cenário e-commerce (32 linhas; 8/8/8/8; 32 no Cassandra; 8/8 Redis;
  8/8 nós + PURCHASED). **[verificado]**
- Suíte `pytest`: 30 passed, 1 skipped. **[verificado]**
- Apêndice A reproduz fielmente os dois JSON Schemas embutidos. **[verificado]**
- `run_example.sh` de fato lê o `sgbd_config.json` e sobe apenas os serviços
  declarados (`SELECTED_SERVICES`). **[verificado]**
- Operador `each`, `csv_column` por índice, `--only`, import tardio do driver
  Cassandra, `BusinessException` abortando antes de conectar: tudo implementado.

## A. Afirmações do texto NÃO implementadas (ou imprecisas) — doc → código

1. **Redis: "chave Redis (prefixada pelo nome da entidade)"** (ch4, §Redis).
   `redis_payload_from_row` retorna o valor bruto da coluna `is_key`, sem prefixo;
   `inspect_persisted_data.py` também varre `*` sem prefixo. **[verificado]**
   Além do erro de documentação, há risco real de colisão entre entidades (ex.:
   `shopping_cart` e `user_session` podem sobrescrever chaves uma da outra).
   *Opções:* implementar prefixo `entidade:valor` (recomendado) ou corrigir o texto.

2. **Cassandra: "A ausência de `cassandra_partition` é detectada na validação
   cruzada quando não há nenhuma coluna marcada com `is_key`"** (ch4, §Cassandra).
   Não existe essa checagem em `validation.validate_import_config`; uma entidade
   sem partição e sem `is_key` passa pela validação e só falha em tempo de
   importação (`ValueError` em `_primary_key_clause`, após conectar). **[verificado]**
   *Opções:* adicionar a checagem na camada 3 (recomendado — reforça o objetivo
   específico "não permitir configurações incorretas") ou corrigir o texto.

3. **Neo4j: o Listing do fragmento de importação mostra `filters` dentro do
   relacionamento `PURCHASED`** (ch4, §Neo4j). O JSON Schema rejeita essa chave
   (`additionalProperties: false` → `BusinessException`). **[verificado]**
   O `import_config.json` real não tem `filters` no relacionamento; no código, as
   arestas herdam os filtros (não-`each`) da **entidade de origem** (`from`).
   *Opções:* corrigir o listing para refletir a configuração real (mínimo) ou
   implementar filtros por relacionamento no schema + importer.

4. **Redis: "cada entidade deve ter exatamente uma coluna `is_key`"** (ch4, §Redis).
   A restrição não é validada previamente (nem no dry-run): config com 0 ou 2
   `is_key` passa e, na importação real, as linhas são **silenciosamente puladas**
   (`except ValueError: continue`) — importa 0 chaves sem erro. **[verificado]**
   *Recomendação:* validar em `validate_import_config` (checagem barata).

5. **"PostgreSQL / Cassandra: `flatten_entity_dataframe` — seleção, renomeação,
   deduplicação por `is_key`"** (ch4, §4.3.1, fase de materialização).
   O importer do Cassandra **não** usa `flatten_entity_dataframe` nem deduplica:
   insere todas as linhas filtradas, uma a uma (coerente com as 32 linhas da
   tabela de dry-run). A deduplicação por `is_key` vale só para PostgreSQL.
   *Recomendação:* ajustar o texto.

6. **"Inferência de kinds ... para validar operadores de filtro"** (ch4, §4.1).
   `validate_import_config` recebe `kinds` mas não os usa (`_ = kinds  # reserved`);
   os kinds servem para **coerção de tipos ao aplicar** os filtros
   (`filter_engine._coerce_compare`). Ajuste fino de redação.

7. **Fragmentos ilustrativos divergem da configuração real do e-commerce**:
   o listing PostgreSQL mostra `products` com filtro `action == stock` e coluna
   `name` renomeada; o listing Redis mostra `shopping_cart` com chave `user_id` e
   coluna `added_at`. No `data/ecommerce/import_config.json`, `products` não tem
   filtro, `shopping_cart` usa `shopping_cart_id`/`cart_*`, e `added_at` não existe
   no CSV. Como a Tabela `tab:dryrun` reflete a configuração real, vale alinhar os
   fragmentos (ou rotulá-los explicitamente como exemplos didáticos).

## B. Comportosamentos do código pouco/não documentados no TCC — código → doc

1. **`--sgbd-config` é opcional**: default `sgbd_config.json` ao lado do
   `--config` (documentado no README, ausente no ch4).
2. **Arquivo de log de sessão** em `logs/` (`console.init_session_log`) — o texto
   menciona apenas "linhas de log".
3. **`ImporterRegistry` / inversão de dependência** (importers injetáveis; base do
   teste sem I/O real; `docs/ARCHITECTURE.md`). É uma decisão de arquitetura
   central da ferramenta e mereceria uma subseção no cap. 4.
4. **Semântica de idempotência por backend**: PostgreSQL `ON CONFLICT DO NOTHING`
   + dedupe `keep="last"`; Neo4j `MERGE`; Redis `SET` (sobrescreve); MongoDB
   `insert_many` **duplica documentos** em reexecução. Excelente material de
   discussão poliglota que o texto não cobre.
5. **Ordem de inserção PostgreSQL é fixa no código**
   (`_DEFAULT_INSERT_ORDER = ("categories", "products", "inventory")` + ordem
   alfabética) — a ordem NÃO é derivada de `relationships`; configs arbitrárias
   podem violar FK. Limitação não documentada (e candidata a melhoria: ordenação
   topológica das FKs).
6. **`each`: apenas um por entidade** (`BusinessException`), `target_suffix` e
   slugify do valor. O texto menciona só "sufixo opcional". O exemplo e-commerce
   não exercita `each`, embora o cap. 3 o cite como diferencial.
7. **Coerção nos filtros**: `""` vira `NA` antes de comparar; coerção
   numérica/datetime com `errors="coerce"`; fallback string.
8. **Linhas com chave nula no Redis são puladas silenciosamente** (perda de dados
   silenciosa — vale documentar e/ou logar aviso).
9. **Neo4j**: dedupe de nós por chave (`seen`), sanitização de labels/tipos por
   regex, arestas usam as colunas `is_key` das entidades `from`/`to` e herdam os
   filtros da entidade `from`.
10. **`run_example.sh`** também faz `clean`/`inspect`/`--fresh-start`/completion;
    `scripts/inspect_persisted_data.py` gera a evidência de persistência — o §4.4
    menciona só dry-run + importação.
11. **Leitura CSV**: `utf-8-sig` (BOM) e `keep_default_na=False`.
12. **DDL reexecutável**: `CREATE ... IF NOT EXISTS` + `DROP CONSTRAINT IF EXISTS`
    antes de `ADD CONSTRAINT`.

## C. Verificação de referências (log)

Todas as 25 entradas do `references.bib` foram verificadas (Crossref/DOI, arXiv ou
URL ao vivo). `bibtex` roda com **0 warnings** e não há citações órfãs nem entradas
não citadas.

### Correções aplicadas ao `references.bib` (+ citações em `ch3relacionados.tex`)

| Entrada | Problema | Correção |
|---|---|---|
| `berlanga2021unified` → **`fernandezcandel2022unified`** | Autores incorretos ("Berlanga, Romero, Pedotti" — não existem nesse paper) | Autores reais: Fernández Candel; Sevilla Ruiz; García-Molina. Trocado preprint pela versão de periódico: *Information Systems* 104:101898 (2022), DOI 10.1016/j.is.2021.101898 |
| `wang2020cmc` → **`kaur2020middleware`** | Autores errados ("Wang, L.") e páginas erradas (1399–1416) | Kaur; Sharma; Kahlon, CMC 65(2):1625–1647 (2020), DOI 10.32604/cmc.2020.011535 |
| `duggan2017bigdawg` → **`duggan2015bigdawg`** | Veículo/ano inexistentes (não há paper BigDAWG de Duggan em ICDEW 2017) | Versão canônica: *ACM SIGMOD Record* 44(2):11–16 (2015), DOI 10.1145/2814710.2814713 |
| `royhubara2022selecting` | Primeiro nome errado ("Naama") | **Noa** Roy-Hubara; + DOI 10.1016/j.datak.2021.101950 |
| `tan2017query` | Primeiro nome errado ("Rui") | **Ran** Tan; Mattson, Timothy G.; + DOI 10.1109/BigData.2017.8258302 |
| `chillon2023propagating` | Entrada incompleta (sem veículo, "and others") | Autores completos + CoMoNoS @ EDBT/ICDT 2023, CEUR-WS Vol-3379 + URL |
| `ye2023benchmark` | "and others" | Autores completos + DOI 10.4018/jdm.321756 |
| `hecht2011nosql` | — | + DOI 10.1109/CSC.2011.6138544; nomes por extenso |
| `khine2019review` | — | + DOI 10.3390/info10040141 |
| `kiehn2022polyglot` | — | verificado (DOI 10.14778/3554821.3554891 — pode ser adicionado) |
| `silva2024modelagem` | — | verificado (DOI 10.5753/erbd.2024.238848 — pode ser adicionado) |
| `glake2022towards` | — | verificado no arXiv (2204.05779) |
| `pereira2025transparent`, `chillon2024schema`, `sachdeva2024plugging` | — | DOIs conferem no Crossref |
| 8 entradas `@misc` (docs oficiais, Fowler, dbcrossbar, Hackolade) | — | URLs respondem 200 |

### Observação (não alterado)

- `sadalage2013nosql`: o livro *NoSQL Distilled* foi publicado em ago/2012
  (Addison-Wesley); a página de copyright diz ©2013 Pearson Education — a entrada
  atual (2013, Pearson) é defensável, mas a forma mais citada é 2012/Addison-Wesley.
  Decisão do autor.

## Prioridades sugeridas (antes da banca)

1. Corrigir o listing Neo4j (A3) — hoje o exemplo do texto é **rejeitado** pela
   própria ferramenta.
2. Decidir A1/A2/A4: implementar as 2 validações + prefixo Redis (pequenas,
   alinham código ao texto e ao objetivo específico 2) OU ajustar o texto.
3. Ajustar A5/A6 (redação).
4. Considerar B3/B4/B5 como material novo para o cap. 4 (arquitetura e
   idempotência são pontos fortes não contados).
