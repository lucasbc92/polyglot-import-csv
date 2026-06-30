---
name: tcc-referencias-verificadas
description: Pesquisa, VERIFICA e adiciona referências acadêmicas reais ao TCC (persistência poliglota, importação CSV, NoSQL/SQL, multimodelo), atualizando references.bib e inserindo citações no .tex (abntex2cite). Combina busca tipo Google Scholar com verificação obrigatória por DOI/Crossref e as regras de integridade da academic-writing. Use SEMPRE que o usuário pedir para pesquisar referências/literatura/trabalhos relacionados, reforçar afirmações sem citação, expandir Trabalhos Relacionados, atualizar o estado da arte, ou adicionar/checar entradas BibTeX — mesmo que ele não diga explicitamente "verifique".
---

# Referências verificadas para o TCC PolyglotImportCSV

## Por que esta skill existe (leia antes de tudo)

O risco número um ao usar um LLM em escrita acadêmica é a **citação fabricada**:
DOIs, páginas e até combinações autor/título plausíveis, porém inexistentes — hoje
uma das maiores causas de retratação (ver `academic-writing`). A skill antiga
`tcc-google-scholar` mandava "criar a entrada BibTeX" a partir do que o modelo
leu, sem checagem — exatamente o caminho da fabricação.

Esta skill inverte a lógica: **o modelo nunca escreve os metadados de uma
referência de cabeça**. Ele descobre candidatos reais, confirma a existência do
trabalho no Crossref e obtém o BibTeX **canônico a partir do DOI**. Se não há DOI
verificável, a referência não entra — é reportada como não-verificada.

Princípio inegociável: **nenhuma entrada vai para o `references.bib` sem um DOI/URL
confirmado por uma fonte autoritativa.** Em caso de dúvida, não adicione; relate.

## O que é (e não é) possível aqui

- ✅ Buscar trabalhos reais (WebSearch), confirmar metadados no Crossref/DOI,
  ler **abstracts públicos** (WebFetch em páginas de editora/arXiv/DOAJ).
- ✅ Gerar BibTeX canônico e citações no padrão do trabalho.
- ❌ **Não** há acesso a texto completo de periódicos pagos (não estamos em VPN;
  o WebFetch falha em URLs autenticadas). Trabalhe com abstract + metadados.
- ❌ **Não** invente abstract, página, volume ou DOI. O script é a fonte.

## Fluxo de trabalho

Crie um item de TODO por etapa. A etapa 3 (verificação) é obrigatória.

### 1. Definir o alvo
Identifique o que precisa de suporte bibliográfico:
- uma **afirmação sem citação** no texto (cite o arquivo:linha); ou
- um **tópico** a expandir nos Trabalhos Relacionados; ou
- uma lacuna de **estado da arte** (últimos ~3 anos).

Formule 2–4 consultas com vocabulário do domínio (em inglês rende mais no Crossref):
persistência poliglota, *polyglot persistence*, *multi-model database*, *data
import/loading*, *CSV ingestion*, *schema mapping*, NoSQL, *ETL to NoSQL*.

### 2. Buscar candidatos reais
Duas frentes complementares:

- **Crossref (estruturado, preferencial):**
  ```bash
  python .claude/skills/tcc-referencias-verificadas/scripts/crossref_verify.py \
      search "polyglot persistence data import" --rows 6 --from-year 2023
  ```
- **WebSearch (descoberta ampla / Google Scholar):** consultas como
  `"polyglot persistence" "data import" site:scholar.google.com`,
  ou busca livre por título/autor para então localizar o DOI.

Priorize: aderência ao tema da PolyglotImportCSV (importação automatizada, config
declarativa, múltiplos SGBDs), recência, e veículos sérios (periódicos/conferências
indexados).

### 3. VERIFICAR (obrigatório)
Para cada candidato que pretende usar:

1. Confirme a aderência lendo o **abstract público** (WebFetch na landing page do
   DOI, arXiv ou DOAJ). Se for só relevância superficial, descarte.
2. Obtenha o BibTeX **canônico** pelo DOI:
   ```bash
   python .claude/skills/tcc-referencias-verificadas/scripts/crossref_verify.py \
       bibtex 10.XXXX/YYYY
   ```
3. Se o DOI não retorna BibTeX (ou o trabalho não existe no Crossref), **não
   adicione**. Anote em um "log de verificação" como não-verificado e siga.

Itens sem DOI (alguns relatórios técnicos, sites de fornecedor) podem ser citados
como `@misc`/`@online` **somente** com URL real que você acabou de acessar e
confirmar — nunca de memória.

### 4. Higienizar e inserir no `references.bib`
- **Rechaveie** para o padrão do trabalho: `sobrenomeprimeiroautorANO` em minúsculas
  (ex.: `royhubara2022`). Veja as chaves existentes para o estilo e **evite
  duplicatas** (cheque se o DOI/título já está no arquivo antes de inserir).
- Mantenha os campos como vieram do Crossref; pode remover `url` se houver `doi`.
- Cuide de acentuação/caixa: proteja siglas com chaves quando necessário
  (`title = {{NoSQL} ...}`) para o BibTeX não rebaixar a capitalização.
- Acrescente ao final do `references.bib` (não reordene o arquivo todo).

### 5. Citar no texto (.tex, abntex2cite)
O trabalho usa `abntex2cite` (estilo `alf`). Convenções observadas no projeto:
- **Citação textual** (autor na frase): `\citeonline{chave}` →
  *"Conforme \citeonline{royhubara2022}, a seleção de bancos…"*.
- **Citação parentética**: `\cite{chave}` → *"… (\cite{royhubara2022})."*.

Insira a citação **junto de uma frase que explique a relação** com a
PolyglotImportCSV (comparação, contraste, fundamento) — não solte a citação sem
contexto. Em Trabalhos Relacionados, deixe explícito o diferencial da ferramenta.

### 6. Reportar
Entregue um **log de verificação** curto: para cada referência, DOI + veículo +
ano + onde foi citada; e a lista do que foi descartado por não-verificável ou
pouco aderente. Transparência > volume.

## Disclosure (academic-writing)
Uso de LLM para apoiar a pesquisa/redação deve ser divulgado conforme as normas da
UFSC/orientador. Sugira ao usuário uma nota de divulgação se ainda não houver, e
lembre que a responsabilidade final pelas citações é do autor.

## Exemplo
**Pedido:** "Acha 2 trabalhos recentes sobre seleção de bancos para persistência
poliglota e cita no Cap. 3."

**Ação:**
1. `crossref_verify.py search "selecting databases polyglot persistence" --from-year 2022`
2. WebFetch no abstract do candidato mais aderente → confirma relevância.
3. `crossref_verify.py bibtex 10.1016/j.datak.2021.101950` → BibTeX canônico.
4. Rechaveia para `royhubara2022`, checa duplicata, adiciona ao `references.bib`.
5. No `ch3relacionados.tex`: *"\citeonline{royhubara2022} propõem um método de
   seleção de SGBDs para aplicações poliglotas; diferentemente, a PolyglotImportCSV
   não seleciona o banco, mas materializa o mesmo CSV em vários paradigmas."*
6. Log: 1 adicionada (DOI ✓, citada em ch3:linha), 1 descartada (sem DOI).

## Arquivos da skill
- `scripts/crossref_verify.py` — núcleo de verificação (search por tema; bibtex por
  DOI). Sem dependências além de Python 3 + rede. É a fonte da verdade dos
  metadados; o modelo não deve substituí-lo escrevendo BibTeX "na mão".
