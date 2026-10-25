# Design — Apresentação de slides da defesa do TCC2

Data: 2026-10-25
Status: aprovado em brainstorming; aguardando revisão do autor.
Branch: `apresentacao-defesa` (a partir de `main`).

## Origem e intenção

Slides para a defesa pública do TCC2 (Ciência da Computação, UFSC). A exposição oral tem
**até 30 minutos**, seguida da arguição. A sessão pode ser **presencial ou remota**: o mesmo
PDF precisa funcionar no projetor e no compartilhamento de tela. Banca: Prof.ª Carina
Friedrich Dorneles e Prof. Jônata Tyska Carvalho; orientador: Prof. Ronaldo dos Santos Mello.

**Mensagem central (palavras do autor):** uma única ferramenta importa dados em CSV para
cinco SGBDs de paradigmas diferentes — basicamente o título do trabalho. Todo slide existe
para sustentar essa ideia.

**Base de conteúdo:** relatório v2.3 (`docs-tcc/TCC2-PolyglotImportCSV-Report-v2.3.pdf`,
fontes em `docs-tcc/chapters/`). O autor avisou que texto e código ainda podem mudar
substancialmente; por isso o conteúdo dos slides deve ser rastreável até a seção do
relatório de onde veio (ver "Roteiro").

**Perfil da banca (para calibrar o nível):**

- Carina Dorneles — banco de dados: extração de dados da web, similaridade, qualidade e
  linhagem de dados, geração de esquema com LLM. Esteve na banca de três monografias
  anteriores do orientador. Deve fazer a arguição mais técnica de BD.
- Jônata Tyska Carvalho — IA/aprendizado de máquina, computação evolutiva, ciência de dados
  sobre dados públicos. Menos voltado a BD: a fundamentação precisa ser acessível, sem
  jargão, e a metodologia da avaliação precisa estar explícita.

## Metas

- Cerca de **25 slides no corpo, ~25 min** de fala (folga de 5 min sobre o limite).
- Seguir a "Organização Usual" das dicas do orientador
  (`C:\Users\lbc92\Downloads\Dicas_trabalhos_apresentaçõesI_2019.pdf`, slide 23): capa →
  introdução (poucos slides) → fundamentação e trabalhos relacionados (poucos, com tabela) →
  núcleo (a maior parte, rico em exemplos) → conclusão (motivação, comparação com os
  relacionados, contribuições, trabalhos futuros) → agradecimentos → perguntas → capa de
  novo.
- Slide de **roteiro** no início e reapresentado a cada bloco, com o bloco atual destacado.
- **Fio condutor** do núcleo: o cenário e-commerce do Capítulo 4, acompanhando o `user1` e o
  `Product2` pelos cinco SGBDs.
- **Cartas na manga** depois do fechamento, para perguntas previsíveis da banca.

## Não-metas

- Detalhar o programa anti-fraude de licitações em que a ferramenta será aplicada. Decisão do
  autor: o cenário sintético do e-commerce basta como motivação; o programa ainda não está
  definido. Citações a trabalhos da banca são opcionais e não devem virar um bloco.
- Alterar a monografia. As lacunas encontradas na v2.3 (tabela comparativa ausente no Cap. 3,
  "Atividades Futuras" como capítulo próprio, avaliação sem comparação com importadores
  nativos, futuro em `ch1introducao.tex:48,75`, artigo SBC como apêndice, e
  `consideracoes.tex:17` falando em "avaliação empírica com dados reais" quando o §5.1 usa
  um gerador sintético) são outra frente, a decidir com o autor depois. Nos slides, vale o
  §5.1: os dados da avaliação são **sintéticos**.
- Demonstração ao vivo. A interface gráfica entra por capturas de tela.
- Versão `.pptx`, notas do apresentador e roteiro de fala.

## Anti-metas (fracasso mesmo que compile)

- Slides poluídos, que obriguem o autor a ler: parágrafos, frases longas, muitos itens.
- Qualquer número que não exista no relatório v2.3, ou que misture campanhas de medição
  diferentes (com e sem instrumentação de memória) na mesma comparação.
- Figura complexa jogada de uma vez, sem revelação gradual.
- Estourar 30 minutos num ensaio em ritmo normal.
- Jargão não definido ou termos vetados pelo orientador (ver "Restrições").
- Visual diferente do aprovado, ou slide mestre mais carregado que o aprovado.
- Texto com "cara de IA": exageros, autoelogio ("inovador", "robusto"), travessões em série.

## Restrições

**Regras do orientador para apresentações (Dicas, 2019):** poucos itens por slide ou
revelados aos poucos; frases curtas que sintetizam a ideia; fonte agradável e de tamanho
adequado, com destaque discreto para palavras-chave; cores discretas; figuras complexas
apresentadas aos poucos; ~1 minuto por slide; slides extras ("cartas na manga") depois do
último; demonstração só do que certamente funciona, senão capturas de tela.

**Preferências do orientador já conhecidas:** nunca "backend" — sempre "SGBD"; definir sigla
ou termo técnico no primeiro uso; trechos de JSON parciais terminam em `...`; tabelas com
título acima, figuras com legenda abaixo, e "Fonte:" quando a figura ou tabela vier de
outro trabalho.

**Vocabulário do relatório (manter idêntico):** estratégia "ingênua (*naive*)" × "em lote
(*batch*)"; modos "multifonte" × "combinado"; modelos de execução "materialização" ×
"fluxo (*streaming*)"; "arquivo de importação" e "arquivo de conexão"; QP1–QP6 com os mesmos
nomes do Capítulo 5.

**Integridade dos números:** todo número vem do `docs-tcc/chapters/ch6avaliacao.tex` (v2.3),
com a campanha declarada no slide quando houver comparação de tempo ou memória. A precisão
de tempo é de ~20%: não tirar conclusões abaixo disso. Números de referência (conferir no
`.tex` antes de usar):

- QP4: estratégia em lote ~9× mais rápida que a ingênua (`tab:naive-optimized`,
  `fig:naive-optimized`; N = 10 000, materialização, campanha sem instrumentação de memória).
- QP1: escrita > 90% do tempo em 100 mil linhas; vazão varia mais de uma ordem de grandeza
  entre SGBDs (`tab:fases-100k`, `tab:escrita-sgbd`, `fig:throughput-sgbd`).
- QP2: multifonte e combinado empatam no tempo total; multifonte lê 2× mais rápido e usa 5–6%
  menos memória (`tab:multi-combined`).
- QP3: tempo cresce aproximadamente proporcional ao volume (`tab:tempo-execucao`,
  `fig:tempo-execucao`).
- QP5/QP6: fluxo reduz o pico de memória em 12,5× em 100 mil linhas, a +10% de tempo, com
  pico constante no tamanho do arquivo (`tab:memoria`, `fig:memoria`,
  `tab:tradeoff-memoria`).
- Ambiente: `tab:ambiente-sgbds`; limitação do Cassandra (heap de 1 GB numa VM de ~3,8 GB) e
  ameaças à validade em `sec:ameacas-validade`.

**Ferramentas:** Beamer com pdflatex/latexmk no MiKTeX local. Verificado presente: `beamer`,
`tikz`, `pgfplots`, `siunitx`, `listings`, `booktabs`.

**Git:** commits em português, coerentes e de tamanho médio, com o trailer
`Co-Authored-By`; `git push` logo após cada commit (política do autor, o disco D: já perdeu
dados).

## Decisões do autor

1. **Formato:** Beamer, 16:9, PDF.
2. **Visual — "estilo C bicolor em diagonal"** (aprovado sobre mockup):
   - Cabeçalho: faixa azul `#0b3d6e` com o título do slide em branco, à esquerda; a faixa
     termina num **corte diagonal** antes do canto superior direito, que fica **branco** e
     abriga o **brasão colorido** da UFSC (`docs-tcc/brasao_UFSC_vertical_sigla.pdf`).
     **Sem linha** abaixo do cabeçalho: o brasão parece solto no branco do slide.
   - Rodapé: faixa azul com "Lucas Bueno Cesario · Polyglot Import CSV · Ciência da
     Computação · UFSC" à esquerda e o número do slide à direita.
   - Corpo branco; painéis e tabelas com bordas finas azul-acinzentadas; destaque de
     palavras-chave em azul.
   - Capa: brasão grande centralizado; "Universidade Federal de Santa Catarina · Centro
     Tecnológico / Departamento de Informática e Estatística · Ciência da Computação";
     título "Polyglot Import CSV" e o subtítulo "Uma solução para importação de documentos
     CSV para múltiplos bancos de dados"; autor; "Orientador: Prof. Dr. Ronaldo dos Santos
     Mello"; faixa azul inferior "Defesa de Trabalho de Conclusão de Curso · Florianópolis,
     2026".
   - Mockups de referência (HTML) em
     `.superpowers/brainstorm/1709-1792941637/content/roteiro-v1.html` (estilo final no topo)
     e `visual-style-c-brasao.html` (capa).
3. **Roteiro** abaixo, aprovado como está.
4. **Interface gráfica por capturas** (figuras 12–16), sem demonstração ao vivo.
5. **Elasticsearch** (motor de busca, um sexto paradigma) entra como trabalho futuro.
6. Citar trabalhos da banca e o artigo de Araujo, Silva e Mello (2025) é permitido, sem
   desenvolver o cenário de licitações.

## Roteiro aprovado

Tempo total estimado: ~25 min. "Fonte" indica de onde o conteúdo sai no relatório v2.3.

| # | Slide | Conteúdo | Fonte | Min |
|---|---|---|---|---|
| 1 | Capa | conforme "Visual" | — | 0,5 |
| 2 | Roteiro | Introdução · Fundamentação · Proposta · Avaliação · Conclusão | — | 0,5 |
| 3 | Persistência poliglota | um só modelo não atende tudo; figura do e-commerce poliglota | §1.1, §2.1, Fig. 1 | 1 |
| 4 | O problema | hoje, um importador nativo por SGBD, cada um com a sua sintaxe; nenhum atende os cinco | §1.1, Cap. 3 | 1 |
| 5 | Objetivos | objetivo geral + os quatro específicos, em frases curtas | §1.2 | 1 |
| 6 | Cinco paradigmas | relacional, chave-valor, documento, colunar, grafo e o SGBD escolhido para cada um | §2.2, Figs. 2–6 | 1,5 |
| 7 | Trabalhos relacionados | **tabela comparativa** (ver abaixo) | Cap. 3 | 1 |
| 8 | Visão geral | entrada → processamento → saída | §4.1, Fig. 7 | 1 |
| 9 | Arquivo de importação | fontes, entidades e colunas; trecho curto e fiel do arquivo real | §4.2.1 | 1,5 |
| 10 | Conexão e validação prévia | arquivo de conexão; JSON Schema + consistência entre arquivos; nada é gravado se houver erro | §4.2.3, §4.2.4, Fig. 10 | 1 |
| 11 | Cenário e-commerce | os quatro tipos de evento; multifonte × combinado | §4.2, Tab. de eventos, §4.3.2 | 1 |
| 12 | O mesmo cenário em cinco modelos de dados | slide-chave do mockup, revelado SGBD a SGBD | §4.3.3 | 1,5 |
| 13 | Algoritmo de execução | verificação dos SGBDs → leitura → mapeamento → escrita | §4.3, §4.3.1, Fig. 11 | 1 |
| 14 | Exemplo de execução | comando da CLI (partes explicadas) + contagens do `--dry-run` | §4.3.4 | 1 |
| 15 | Escrita e execução | ingênua × em lote; materialização × fluxo (conceitos) | §4.5 | 1 |
| 16 | Interface gráfica | capturas das figuras 12–16 (uma ou duas por vez) | §4.6 | 1 |
| 17 | Metodologia | dados gerados, volumes, protocolo, ambiente; QP1–QP6 | §5.1, §5.2 | 1,5 |
| 18 | Em lote × ingênua (QP4) | ~9× | §5.3.1 | 1 |
| 19 | Onde está o tempo (QP1, QP3) | escrita > 90%; vazão por SGBD; crescimento com o volume | §5.3.2, `tab:tempo-execucao` | 1,5 |
| 20 | Multifonte × combinado (QP2) | empate no tempo total | §5.3.3 | 0,5 |
| 21 | Memória (QP5, QP6) | pico 12,5× menor e constante, a +10% de tempo | §5.3.4 | 1 |
| 22 | Contribuições | objetivos retomados um a um | §1.2, Cap. 7 | 1 |
| 23 | Resolve × em aberto | o que a ferramenta resolve e o que continua aberto (ver abaixo) | Araujo et al. (2025) | 1 |
| 24 | Trabalhos futuros | Elasticsearch como sexto paradigma; edição da configuração na GUI; volumes de milhões de linhas; outros itens do Cap. 6 | Cap. 6 | 0,5 |
| 25 | Obrigado! Perguntas? | volta à arte da capa | — | — |
| B1 | Falha no meio da importação | atomicidade entre SGBDs: o que a ferramenta faz hoje e o que não garante | Cap. 4 (conferir no código) | — |
| B2 | Coerção de tipos | valores malformados e conversão para os tipos nativos | Cap. 4 | — |
| B3 | Por que configurar à mão? | mapeamento declarativo × inferido (por exemplo, por LLM) | §1.1, Cap. 4 | — |
| B4 | Importadores nativos | comparação qualitativa com COPY, `redis-cli --pipe`, `mongoimport`, `cqlsh`/`sstableloader`, `neo4j-admin` | §3.1 | — |
| B5 | Cassandra e o ambiente | heap/VM, por que é o SGBD mais lento, escala | §5.2, §5.4.1 | — |
| B6 | Ameaças à validade | precisão de ~20%, dados sintéticos, máquina única | §5.4.1 | — |
| B7 | Referências | só as obras citadas nos slides, em ABNT | — | — |

### Slide 12 — conteúdo fiel ao §4.3.3

O mockup aprovado vale pelo **layout** (faixa de origem em cima, cinco painéis lado a lado),
não pelo conteúdo, que simplificou demais. No slide:

- Usar os nomes reais dos campos do §4.3.3 (`quantity_available`, `product_name`,
  `stock.quantity_available` etc.), abreviando com `...` em vez de renomear.
- Não sugerir que uma única linha alimenta os cinco SGBDs. Pela `tab:exemplo-ecommerce`, a
  linha de `stock` do `Product2` alimenta PostgreSQL, MongoDB, Cassandra e Neo4j, mas **não**
  o Redis, que recebe os eventos `add_to_cart` e `select_product` do `user1`. Cada painel
  indica a fonte de onde veio (`stock`, `purchase`, `add_to_cart`, as quatro fontes no
  Cassandra), e a faixa de cima apresenta o fio condutor (`user1` e `Product2`) em vez de uma
  linha só.

### Slide 7 — tabela comparativa

Conteúdo novo (não existe na v2.3), montado **só com o que o Capítulo 3 afirma**. Linhas
sugeridas: importadores nativos (§3.1); ArangoDB/`arangoimport` (§3.2); dbcrossbar;
Hackolade; frameworks de acesso poliglota (Pereira et al., 2025; Sachdeva et al., 2024);
*polystores* (BigDAWG); e a Polyglot Import CSV. Critérios sugeridos, derivados da "Lacuna
identificada" do §3.3: entrada CSV; vários SGBDs de paradigmas diferentes na mesma execução;
mapeamento declarativo; validação prévia da configuração; revisão sem gravar (`--dry-run`).
Célula sem respaldo no texto do Cap. 3 fica "—"; nada é inventado.

### Slide 23 — resolve × em aberto

Ligação com Araujo, Silva e Mello, "Uma Revisão Sistemática Simplificada e Análise de
Estudos sobre Evolução de Esquemas em Aplicações de Persistência Poliglota", ERBD 2025,
DOI 10.5753/erbd.2025.7322 (PDF em `docs-tcc/relacionados/`). A conclusão do artigo aponta
como problemas em aberto: gerar instruções adequadas a cada SGBD; garantir atomicidade;
estimar o efeito das modificações antes de executá-las. No contexto de **importação** (o
artigo trata de evolução de esquemas, e o slide precisa deixar essa diferença clara): a
ferramenta gera a escrita específica de cada SGBD (resolve); valida antes e oferece
`--dry-run` (resolve); não garante atomicidade entre SGBDs (em aberto).

## Decisões minhas (o autor pode vetar)

- **Local e build:** fontes em `docs-tcc/apresentacao/` (`apresentacao.tex` e o que mais for
  preciso), compiladas com `latexmk -pdf`. As figuras existentes são reaproveitadas de
  `docs-tcc/images/` via `\graphicspath`, sem cópia; o brasão entra como PDF vetorial. O PDF
  de entrega é versionado como `docs-tcc/TCC2-PolyglotImportCSV-Apresentacao-v1.0.pdf`,
  seguindo o padrão dos relatórios. O `.gitignore` de `docs-tcc/` passa a ignorar também os
  artefatos do Beamer (`*.nav`, `*.snm`, `*.vrb`) e o PDF de build
  `apresentacao/apresentacao.pdf` (só a cópia versionada de entrega vai para o git).
- **Figuras 10 e 11 redesenhadas:** os PNGs do relatório são retratos muito altos
  (1700×2744 e 2308×4272) e não cabem legíveis em 16:9. Os slides 10 e 13 redesenham esses
  fluxos em TikZ, na horizontal, com revelação passo a passo. As demais figuras do relatório
  podem ser reaproveitadas se ficarem legíveis.
- **Gráficos da avaliação:** refeitos em pgfplots com **os mesmos dados** do `ch6avaliacao.tex`
  (copiar as coordenadas), mas legíveis a distância: fontes maiores, menos rótulos, uma
  mensagem por gráfico. Valem as mesmas armadilhas do relatório: em `ymode=log`,
  `nodes near coords` mostra o logaritmo, então usar `point meta=explicit symbolic` com o
  rótulo explícito.
- **Revelação gradual:** obrigatória no slide 12 (um SGBD por vez) e em qualquer figura com
  muitas partes; o PDF terá páginas extras por causa das sobreposições, o que é normal.
- **Cartas na manga** numeradas B1–B7, depois do slide 25, fora da contagem do corpo
  (`\appendix` + `appendixnumberbeamer`, presente no MiKTeX local); o rodapé mostra "B1",
  "B2"… nesses slides.
- **Referências:** um slide final (B7), escrito à mão em ABNT, só com o que aparece citado nos
  slides, no formato autor-data do relatório (por exemplo, "(ARAUJO; SILVA; MELLO, 2025)").
  Não depende do `references.bib` do relatório.
- **Branch:** `apresentacao-defesa`.

## Deixado para o construtor

- A redação exata de cada slide (frases curtas, no presente).
- O código TikZ do cabeçalho e do rodapé, a fonte e os tamanhos, desde que o resultado bata
  com o mockup aprovado.
- O desenho de cada slide: quais figuras do relatório reaproveitar, quais refazer em TikZ e
  quais trechos de JSON mostrar.
- A forma do slide de roteiro reapresentado (slide inteiro ou faixa).
- Para B1 e B2, descobrir no código (`src/polyglotimportcsv/`) o comportamento real em caso
  de falha parcial e de valor malformado; se não houver resposta clara, registrar a dúvida
  no plano em vez de supor.

## Critérios de pronto

1. `latexmk -pdf` compila sem erros; o PDF é 16:9.
2. 25 slides no corpo (sem contar as páginas de sobreposição) e as cartas na manga depois.
3. Os slides 1 e 12, renderizados em PNG (`pdftoppm`), conferem visualmente com o mockup
   aprovado: corte diagonal, brasão no canto branco sem linha embaixo, rodapé azul.
4. Todos os números conferidos um a um contra o `ch6avaliacao.tex` da v2.3.
5. Nenhuma ocorrência de "backend"; nenhuma frase longa (o construtor revisa slide a slide).
6. O PDF de entrega versionado e enviado ao remoto.
7. O ensaio de tempo (≤ 30 min, alvo 25) é responsabilidade do autor.
