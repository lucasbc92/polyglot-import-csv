---
name: tcc-google-scholar
description: Pesquisa trabalhos acadêmicos no Google Scholar sobre persistência poliglota e bancos de dados NoSQL/SQL, extrai citações e adiciona ao references.bib. Use quando o usuário pedir para pesquisar referências, literatura, ou trabalhos relacionados para o TCC.
---

# Pesquisa Acadêmica no Google Scholar para o TCC

## Sobre a Skill
Inspirada nos agentes de "Deep Research", esta skill orienta o assistente (Gemini) a atuar como um pesquisador autônomo focado no seu TCC. Ela usa as ferramentas nativas de busca na web do assistente para consultar bases acadêmicas (como o Google Scholar), ler resumos e extrair citações prontas para o seu documento.

## Instruções de Execução

Sempre que o usuário pedir para pesquisar artigos, siga estes passos rigorosamente:

### 1. Pesquisa Direcionada (WebSearch)
Utilize a ferramenta `WebSearch` para buscar artigos. Para restringir a resultados acadêmicos, use operadores de busca como:
- `site:scholar.google.com.br "persistência poliglota"`
- `site:scholar.google.com "polyglot persistence" AND "data import"`
- `site:scholar.google.com "CSV" AND ("Neo4j" OR "Cassandra" OR "MongoDB")`

### 2. Leitura e Filtro (WebFetch)
- Obtenha os links dos resultados mais promissores.
- Priorize trabalhos recentes (últimos 5-7 anos).
- (Opcional) Use `WebFetch` no link do artigo para ler o resumo (Abstract) e confirmar se tem aderência com a proposta da *Polyglot Import CSV* (importação automatizada, arquivos de configuração JSON, múltiplos SGBDs).

### 3. Extração e Formatação BibTeX
Para os artigos selecionados, crie a entrada BibTeX correspondente. Use chaves no formato `sobrenomeANO` (ex: `silva2023`).

Exemplo de formato esperado:
```bibtex
@article{chave2024,
  title={Título do Artigo sobre Persistência Poliglota},
  author={Sobrenome, Nome and Sobrenome2, Nome2},
  journal={Nome da Revista ou Conferência},
  year={2024},
  publisher={Editora}
}
```

### 4. Atualização Automática do TCC
- Verifique o conteúdo atual de `_docs/references.bib`.
- Adicione as novas entradas geradas ao final do arquivo.
- Se o usuário solicitar, escreva uma proposta de texto para a Seção **"3. TRABALHOS RELACIONADOS"** no arquivo `_docs/polyglot-import-csv.md`, citando os novos artigos no padrão Pandoc (ex: `Conforme demonstrado por Silva et al. [@silva2023]...`).

## Exemplo de Interação
**Usuário:** "Ache 3 artigos recentes sobre importação de dados para bancos em grafo e adicione ao meu TCC."
**Ação do Assistente:** 
1. Realiza buscas no Google Scholar usando `WebSearch`.
2. Lê os resumos dos artigos via `WebFetch`.
3. Escreve as entradas BibTeX no `_docs/references.bib`.
4. Sugere parágrafos para o `_docs/polyglot-import-csv.md` descrevendo como os artigos comparam com a ferramenta *Polyglot Import CSV*.
