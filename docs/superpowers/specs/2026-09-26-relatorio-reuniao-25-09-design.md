# Design — Relatório: mudanças da reunião de 25/09

Data: 2026-09-26
Status: aprovado em brainstorming; aguardando revisão do autor.
Branch: `tcc2-gui`.

Parte 3 de 3. É executada **depois** da parte 1
(`2026-09-26-gui-reuniao-25-09-design.md`), porque a seção da interface gráfica
e as Figuras 12 a 15 precisam descrever a GUI resultante, e as capturas devem
ser feitas uma única vez.

Regras de redação que valem para todo o trabalho (preferências do orientador):
legendas de figura abaixo e de tabela acima; "Fonte:" sempre abaixo; toda
listagem com frase de introdução; nada de "backend", sempre SGBD; **nenhuma
prosa sobre versões anteriores do próprio relatório**. A menção ao TCC1 no
item 5 é sobre a história da **ferramenta**, pedida explicitamente pelo
orientador, e não sobre versões do texto.

## 1. Itens

### 1.1 "CSV por assunto" → "CSV por conjunto de dados"

Ocorrências em `chapters/ch4proposta.tex`, reescritas preservando a concordância:

| Linha (aprox.) | Hoje | Passa a |
|---|---|---|
| 31 | "um arquivo por assunto" | "um arquivo por conjunto de dados" |
| 32 | "carrega todos os assuntos" | "carrega todos os conjuntos de dados" |
| 105 | "corresponde a um assunto do domínio" | "corresponde a um conjunto de dados do domínio" |
| 109 | legenda "(um CSV por assunto)" | "(um CSV por conjunto de dados)" |
| 120 | "assuntos" | "conjuntos de dados" |
| 321 | "cada assunto já vem de uma fonte" | "cada conjunto de dados já vem de uma fonte" |
| 751 | "ao seu assunto" | "ao seu conjunto de dados" |

A busca final `grep -n -i assunto chapters/*.tex` deve voltar vazia.

### 1.2 Referência ao exemplo de e-commerce do Capítulo 2

- Criar `\label{sec:persistencia-poliglota}` na Seção 2.1 (a figura já tem
  `fig:polyglot-ecommerce`).
- Na primeira aparição do cenário no Capítulo 4 (Seção 4.2.1, antes da
  Listagem `lst:sources-multi`), acrescentar uma frase que retoma o exemplo:
  *"o cenário de e-commerce apresentado na Seção~\ref{sec:persistencia-poliglota}
  (Figura~\ref{fig:polyglot-ecommerce})"*, lembrando em uma oração que cada
  categoria de dado ali vai para o SGBD mais adequado.
- Trocar o "seção 2.1" digitado à mão (Seção 4.3.3, "materializando o cenário
  poliglota da seção 2.1") por `Seção~\ref{sec:persistencia-poliglota}`.

### 1.3 Um único domínio de exemplo: e-commerce

A verificação feita em 26/09 não encontrou outro domínio: o Capítulo 4 usa o
e-commerce, e o Capítulo 6 usa um gerador sintético do mesmo domínio. A tarefa
é só **conferir** que nenhum trecho sugere outros cenários (por exemplo "em
diversos cenários de uso", "outros domínios"). Onde houver, o texto é
reformulado para o e-commerce ou o trecho vai para Trabalhos Futuros.

### 1.4 O projeto no GitHub e a origem dos caminhos

- Na visão geral do Capítulo 4 (Seção 4.1), acrescentar que a ferramenta é um
  projeto de código aberto hospedado no GitHub, com a URL
  `https://github.com/lucasbc92/polyglot-import-csv` em nota de rodapé
  (`\footnote{\url{...}}`), e que **todo caminho de arquivo citado no texto é
  relativo à raiz desse repositório**.
- Nos pontos que hoje dizem "do repositório da ferramenta" sem referência
  (`apendiceconfig.tex` linha 5; Capítulo 4 linhas 136, 740, 978, 987, 1035), manter o
  texto, mas garantir que o primeiro deles no capítulo aponte para a nota. Os
  demais podem dizer só "do repositório".
- Se a release v1.0.0 (parte 2) já existir quando o texto for escrito, a
  mesma nota menciona que os executáveis estão na página de releases do
  projeto. Se ainda não existir, a frase fica de fora, porque o texto não
  promete o que ainda não existe.

### 1.5 `naive`: a implementação do TCC1, mantida como linha de base

- Seção 4.5.1 (`sec:estrategias-escrita`): uma frase dizendo que a estratégia
  ingênua corresponde à implementação original da ferramenta, desenvolvida no
  TCC1, e que foi mantida no TCC2 apenas como linha de base de comparação.
  Continua acessível pela CLI (`--strategy naive`), mas não é oferecida na
  interface gráfica, que usa sempre `optimized`.
- Capítulo 6, onde a linha de base é apresentada (linha ~126): meia frase
  remetendo à Seção 4.5.1 com a mesma ideia ("a implementação do TCC1").
- Os números e conclusões do Capítulo 6 **não mudam**.

### 1.6 Exibição de dados e opções da CLI

Reflexo da parte 1 no texto:

- Seção 4.1, bloco de sintaxe (linha ~48) e parágrafo das opções (linhas
  ~74-75): incluir `--sample N` e descrever os três modos (amostra, com N
  padrão 50; todos os dados; nenhum dado).
- Seção 4.4, Observabilidade (linhas ~1068-1069): "materializada até um
  limite de 50 linhas" passa a descrever a amostra das primeiras N linhas,
  válida nos dois modelos de execução.
- A contagem "onze opções" da Seção 4.6 é recontada a partir do `cli.py`
  final.

### 1.7 Seção 4.6, Interface Gráfica

Reescrita dos trechos afetados pela parte 1:

- Controles: sem estratégia e sem *benchmark*. As duas opções continuam na CLI,
  e isso é dito explicitamente, com o motivo (ferramentas de avaliação, não de
  uso cotidiano). Exibição de dados como amostra, todos ou nenhum. Ícones de
  ajuda com *tooltips*.
- Fontes CSV: detecção do tipo de configuração (multifonte/combinada) e como o
  cartão se adapta; arrastar e soltar.
- Validação antes da execução: passa de "restrita ao que pode conferir sem
  abrir os arquivos" para a verificação por JSON Schema, a consistência entre
  os arquivos, os nomes de fonte e o cabeçalho dos CSVs, **com o mesmo código
  da CLI**, deixando claro o limite (nada que exija conexão ou leitura das
  linhas de dados).
- Comando colorido e saída colorida.
- "Salvar log…" e o caminho clicável.
- **Remover** o parágrafo da limitação de apresentação (monocromático no
  Windows), se a parte 1 confirmar a cor. Se não confirmar, o parágrafo fica.
- Figuras 12 a 15 recapturadas com `scripts/capture_gui_figures.py`, depois de
  ajustar o script à GUI nova. A figura de erro (15) passa a mostrar, se
  possível, um erro apanhado **antes** da execução pelo *preflight*, que é
  a novidade, ou continua mostrando um erro de execução. A decisão é tomada ao
  ver as capturas.

## 2. Verificação

- `latexmk -pdf main.tex` sem erros e sem referências indefinidas
  (`grep "undefined" main.log` vazio).
- `grep -n -i assunto chapters/*.tex` vazio.
- Leitura das páginas alteradas no PDF renderizado.
- Contagem de páginas registrada no commit (hoje são 101 mais a epígrafe).

## 3. Fora do escopo

- Alterar números, tabelas ou figuras do Capítulo 6.
- Criar novos cenários ou apêndices.
- A página de releases propriamente dita (parte 2).
