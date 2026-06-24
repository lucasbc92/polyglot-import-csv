---
title: "Polyglot Import CSV: Uma solução para importação de documentos CSV para múltiplos bancos de dados"
author: "Lucas Bueno Cesario"
date: "2026/1"
abstract: |
  A persistência poliglota é essencial na arquitetura contemporânea de bancos de dados, integrando diversas tecnologias de armazenamento em uma mesma aplicação. A ferramenta "Polyglot Import CSV" destaca-se como solução para otimizar a importação de dados CSV em diversos bancos de dados simultaneamente, superando desafios da persistência poliglota. Optou-se pelo formato CSV por ser amplamente utilizado na importação de dados pelos diversos SGBDs e por ser um formato simples e familiar tanto a humanos quanto a sistemas. Por meio de configurações declarativas em arquivos JSON, a ferramenta oferece suporte ao principal representante de código aberto dos bancos de dados relacionais — o PostgreSQL — e aos principais representantes dos bancos de dados NoSQL: Redis (chave-valor), MongoDB (documento), Apache Cassandra (colunar) e Neo4j (grafo). Não foram identificadas ferramentas equivalentes que realizem, a partir de um único arquivo CSV e de regras declarativas, a importação simultânea para múltiplos paradigmas de dados, o que evidencia a originalidade da proposta. A publicação do código aberto da ferramenta impulsiona avanços colaborativos na dinâmica arquitetura moderna de bancos de dados. Como atividade futura, prevê-se a avaliação de desempenho das importações com diferentes volumes de dados CSV e configurações.
tags:
  - Persistência poliglota
  - Ferramenta "Polyglot Import CSV"
  - Importação de dados CSV
  - JSON
  - SQL
  - NoSQL
  - Software Livre
capa: true
folhaderosto: true
toc: true
toc-depth: 3
listoffigures: true
listofabbreviations: true
tagstitle: "Palavras-chave"
institution: "Universidade Federal de Santa Catarina"
department: "Departamento de Informática e Estatística"
course: "Curso de Graduação em Ciência da Computação"
place: "Florianópolis"
orientador: "Profº Ronaldo dos Santos Mello, Dr."
folhaorientadores: true
membrosbanca:
  - nome: "Profº Ronaldo dos Santos Mello, Dr."
    funcao: "Orientador"
    instituicao: "Universidade Federal de Santa Catarina"
  - nome: "Profª Carina Friedrich Dorneles, Dra."
    instituicao: "Universidade Federal de Santa Catarina"
  - nome: "Profº Jônata Tyska Carvalho, Dr."
    instituicao: "Universidade Federal de Santa Catarina"
tipotrabalho: "Trabalho de Conclusão de Curso"
preamble: "Trabalho de conclusão de curso apresentado como parte dos requisitos para obtenção do título de Bacharel, do Curso de Graduação em Ciência da Computação na Universidade Federal de Santa Catarina."
bibliography: references.bib
csl: associacao-brasileira-de-normas-tecnicas.csl
header-includes: |
  \providecommand{\pandocbounded}[1]{#1}
---

<!--
=======================================================================
  COMPILAÇÃO (a partir da raiz do repositório)
=======================================================================

  Bash (Git Bash / macOS / Linux, from repo root):
    ./docs-tcc/scripts/gerar-tcc1.sh             # PDF ABNT (oficial)
    ./docs-tcc/scripts/gerar-tcc1.sh --odt       # PDF + ODT para revisão (LibreOffice / Google Docs)

  Gera PDF (abnTeX2) e, com --odt, versão editável estilizada em docs-tcc/.
  Assets: abntex2.latex, abnt-ufsc-reference.odt, references.bib, CSL ABNT e images/.

=======================================================================
  CITAÇÕES (Pandoc / citeproc)
=======================================================================

  - [@chave]             → (AUTOR, ANO)
  - [@chave, p. 10]      → (AUTOR, ANO, p. 10)
  - @chave               → AUTOR (ANO)  — citação narrativa

=======================================================================
-->

# 1 INTRODUÇÃO

## 1.1 Visão Geral

Nas esferas industrial e acadêmica de bancos de dados, a concepção de que um único modelo de dados não atende a todas as necessidades tem conquistado aceitação, apontando para a perspectiva de persistência poliglota no futuro. Embora os sistemas de banco de dados relacionais devam manter sua predominância, espera-se uma convivência com diversas formas de sistemas, como os NoSQL [@sadalage2013nosql].

Algumas pesquisas têm sido feitas na área de persistência poliglota, como sugestões de modelos de dados unificados [@chillon2023propagating], comparação de desempenho de bancos de dados multi-modelos contra abordagens de persistência poliglota [@ye2023benchmark], revisões sistemáticas sobre modelagem poliglota de dados [@silva2024modelagem], tutoriais sobre o estado da arte e desafios abertos [@kiehn2022polyglot], e a adoção da persistência poliglota em Big Data [@khine2019review].

Dada essa necessidade crescente da adoção de persistência poliglota pelas aplicações, percebe-se a falta de uma ferramenta única de importação simultânea de dados para diversos SGBDs que tratem modelos de dados diferentes. Até onde se investigou (Capítulo 3), não foram identificadas ferramentas equivalentes: os importadores nativos atendem a um único SGBD por vez, e as soluções de migração ou de modelagem poliglota não realizam a materialização simultânea de um mesmo CSV em múltiplos paradigmas de dados — o que ressalta a originalidade desta proposta.

Assim sendo, a intenção deste trabalho é desenvolver a ferramenta *Polyglot Import CSV*, que importa dados armazenados em CSV para SGBDs relacionais e NoSQL. A configuração da ferramenta será baseada em dois arquivos JSON: um de importação, mapeando entidades e relacionamentos em cada SGBD, considerado seu modelo de dados; outro de configuração de conexão dos SGBDs envolvidos. A escolha pelo formato JSON deve-se à sua simplicidade e ampla adoção; sua finalidade é detalhar, de forma declarativa, o mapeamento das colunas do CSV para os modelos de dados de cada SGBD, permitindo a validação prévia da importação.

CSV (Comma-Separated Values) é um arquivo de valores separados por vírgulas, frequentemente visualizado em Excel e outras planilhas eletrônicas. Pode haver outros tipos de valores como delimitadores, mas o mais comum é a vírgula. Muitos sistemas e processos hoje convertem seus dados para o formato CSV para saídas de arquivo para outros sistemas, relatórios amigáveis para humanos, disponibilização de dados públicos, e outras necessidades. É um formato de arquivo padrão com o qual humanos e sistemas já estão familiarizados ao usar e manipular.

## 1.2 Objetivos

### 1.2.1 Objetivo Geral

Desenvolver a ferramenta *Polyglot Import CSV* que possibilitará a importação de dados em arquivos CSV para múltiplos SGBDs: PostgreSQL, Redis, MongoDB, Cassandra ou Neo4j.

### 1.2.2 Objetivos Específicos

- Projetar os arquivos de configuração JSON para que eles sigam sintaxes específicas, e flexíveis para lidar com vários modelos de dados, além de adicionar opções como filtros, escolha de chave primária e escolha do nome da coluna no banco de dados;
- Não permitir configurações incorretas, ou seja, se houver erro em algum lugar dos arquivos de configuração, a importação não deve começar até que sejam corrigidos (validação prévia da configuração);
- Avaliar o desempenho da ferramenta para diferentes volumes e modelos de dados destino;
- Disponibilizar a ferramenta de forma acessível ao usuário: inicialmente por meio de uma interface de linha de comando (CLI), com possibilidade de evolução para uma interface gráfica em trabalhos futuros.

## 1.3 Metodologia

O desenvolvimento deste trabalho segue uma metodologia de pesquisa aplicada, adotando as seguintes etapas:

1. Estudo sobre persistência poliglota e seu estado da arte;
2. Estudo sobre os paradigmas não-relacionais que serão abrangidos pela solução: chave-valor, documento, grafo e colunar;
3. Estudo de decisão de linguagem de implementação que demonstra melhor produtividade para codificar a solução;
4. Projeto dos arquivos de configuração JSON;
5. Projeto da instrução principal de importação que utiliza os arquivos de configuração;
6. Implementação da solução "Polyglot Import CSV";
7. Testes da solução "Polyglot Import CSV" implementada.

Na primeira etapa, foi estudado o que é a persistência poliglota, e a sua relevância no cenário atual.

Na segunda etapa, foram estudados os diversos modelos de dados não-relacionais: como cada modelo representa suas entidades; se há relacionamentos entre entidades no modelo; se é possível a existência de entidades aninhadas e multivaloradas; as limitações de cada modelo.

Na terceira etapa, foram estudadas as formas de implementar a solução usando as linguagens Java e Python e, pela simplicidade e produtividade, a linguagem Python foi escolhida.

Na quarta e quinta etapas, foram projetados os dois arquivos de configuração JSON — um para o mapeamento da importação (entidades, relacionamentos e colunas) e outro para a conexão dos SGBDs — bem como a instrução principal de importação que os utiliza.

As últimas etapas, que estão em andamento, tratam da implementação da solução proposta, "Polyglot Import CSV", e dos testes da mesma com diferentes volumes de dados CSV e importações simples e complexas para diferentes modelos de dados destino.

## 1.4 Estrutura do Trabalho

Este trabalho está estruturado em cinco capítulos principais. O primeiro aborda os objetivos, a metodologia e o contexto que levaram à elaboração deste TCC. O capítulo 2 revisa fundamentos teóricos. O capítulo 3 apresenta trabalhos relacionados. O capítulo 4 descreve a proposta da ferramenta *Polyglot Import CSV* e o capítulo 5 as atividades futuras (TCC II).

# 2 FUNDAMENTAÇÃO TEÓRICA

## 2.1 Persistência Poliglota

Neal Ford introduziu o conceito de “programação poliglota” para expressar a ideia de que aplicativos devem ser desenvolvidos utilizando uma combinação de linguagens, aproveitando o fato de que diferentes linguagens são mais adequadas para lidar com diferentes problemas [@ford2008productive]. Uma das consequências notáveis da programação poliglota é a transição para a “persistência poliglota”, usando a mesma analogia: pode-se dizer que múltiplas tecnologias de bancos de dados podem ser utilizadas como armazenamento persistente para diferentes tipos de casos de uso. Embora ainda exista uma quantidade considerável de dados gerenciados por sistemas relacionais, a abordagem predominante passa a ser a reflexão sobre como se deseja manipular os dados antes de determinar qual tecnologia é a mais adequada para essa manipulação [@fowler2011polyglot].

A persistência poliglota abrange uma variedade de formatos de dados, incluindo estruturados, semi-estruturados e não estruturados. Dados estruturados geralmente englobam formatos como relacional, objeto-relacional, e grafos de propriedades. Dados semi-estruturados incluem principalmente documentos JSON e XML. Por fim, dados não estruturados são representados por arquivos de texto, imagens e áudios, dentre outros [@ye2023benchmark].

Um domínio em que a persistência poliglota pode ser aplicada é o de um e-commerce. Nesse cenário, diferentes categorias de dados possuem características e padrões de acesso distintos — volume de escrita, frequência de leitura, necessidade de consistência, estrutura dos registros — o que torna mais adequado o uso de um SGBD específico para cada uma delas. A Figura 1 ilustra esse cenário, mapeando cada categoria de dado do e-commerce ao SGBD mais adequado, conforme sugerido a seguir:

- **Dados Financeiros/Transacionais de Pagamento e Inventário de Produtos:** Pedidos, pagamentos e estoques exigem garantias transacionais fortes (ACID) para evitar inconsistências — por exemplo, debitar um pagamento sem registrar o pedido correspondente. Além disso, consultas analíticas sobre esses dados frequentemente combinam várias entidades por meio de junções. Bancos de dados relacionais como o PostgreSQL são a escolha natural para esse perfil, pois oferecem suporte nativo a transações com consistência forte, integridade referencial e uma linguagem de consulta expressiva (SQL).
- **Dados do Catálogo de Produtos:** O catálogo de um e-commerce tende a ter esquema variável: diferentes produtos possuem atributos distintos (um livro físico com ISBN e editora; um eletrodoméstico com voltagem e garantia). Além disso, o catálogo é lido com muito maior frequência do que escrito, e cada consulta normalmente recupera o produto completo de uma vez. Bancos de dados orientados a documentos como o MongoDB são otimizados exatamente para esse perfil: armazenam cada produto como um documento autocontido (favorecendo leituras de agregados complexos), suportam esquemas flexíveis e oferecem índices secundários e pipelines de agregação para fins de consulta.
- **Dados da Sessão e do Carrinho de Compras do Usuário:** Dados de sessão e carrinho são acessados a cada interação do usuário durante a navegação, exigindo latência mínima, e são também inerentemente temporários — um carrinho abandonado não precisa persistir indefinidamente. Bancos de dados chave-valor em memória como o Redis oferecem latência de microssegundos, expiração automática de chaves  e são horizontalmente escaláveis para absorver picos de tráfego, tornando-se a escolha ideal para dados de natureza efêmera e de acesso intenso.
- **Dados de Atividade do Usuário:** Eventos de navegação (clickstream), visualizações de produto e histórico de ações são gerados em alto volume e alta velocidade. Consultas típicas percorrem o histórico de um usuário em um intervalo de tempo, ou agregam eventos por tipo de ação. Bancos de dados colunares como o Apache Cassandra são projetados para ingestão massiva com particionamento por chave primária composta (por exemplo, (user_id, timestamp)), garantindo escritas rápidas e leituras eficientes por usuário ou período — padrão ideal para séries temporais de atividade.
- **Dados de Recomendação:** Sistemas de recomendação dependem de relacionamentos entre entidades: usuários que compraram os mesmos produtos, produtos frequentemente adquiridos em conjunto ou usuários com perfis semelhantes. Esses padrões são naturalmente modelados como grafos, onde nós representam usuários e produtos, e arestas representam interações (comprou, avaliou, visualizou, etc). Bancos de dados orientados a grafos como o Neo4j permitem percorrer esses relacionamentos com eficiência por meio de consultas Cypher, tarefa que em um banco de dados relacional exigiria múltiplas junções e difícil otimização.

![Exemplo de aplicação da Persistência Poliglota em um e-commerce.](images/figure1-polyglot-ecommerce.png){width=15cm}

**Fonte:** Elaborado pelo autor (2026).

## 2.2 Bancos de Dados NoSQL

Os bancos de dados NoSQL podem ser divididos em subcategorias com base em seus modelos de dados. Este trabalho utiliza a classificação de Hecht e Jablonski [@hecht2011nosql], que categoriza os bancos de dados NoSQL em quatro tipos: chave-valor, colunares, documentos e grafos.

A Figura 2 ilustra esses modelos de dados, que são detalhados a seguir. 

![Diferentes tipos de modelos de dados NoSQL.](images/figure3-nosql-data-models.png){width=15cm}

**Fonte:** Elaborado pelo autor (2026).

### 2.2.1 Chave-valor

Os bancos de dados de chave-valor têm um modelo de dados simples baseado justamente em pares chave-valor, semelhante a um mapa associativo ou dicionário. A chave identifica exclusivamente o valor e é usada para armazenar e recuperar o valor no banco de dados, funcionando como uma chave primária. O valor pode ser usado para armazenar qualquer dado arbitrário, incluindo um número inteiro, uma string, um array ou um objeto, proporcionando uma representação de dados sem esquema conhecido.

Além disso, os bancos de dados de chave-valor são muito eficientes no armazenamento de dados distribuídos, mas não são adequados para cenários que requerem a definição de relacionamentos entre dados ou esquemas fortemente estruturados. Qualquer funcionalidade que necessite desses requisitos deve ser implementada na aplicação cliente que interage com o banco de dados chave-valor.

Como os valores são opacos para os bancos de dados, esses não podem lidar com consultas e indexações a nível de dados, podendo realizar consultas apenas por meio de chaves. Um exemplo de SGBD chave-valor é o Redis, que mantém os dados tanto na memória como no disco.

### 2.2.2 Colunar

Em bancos de dados colunares, o conjunto de dados consiste em várias linhas, cada uma identificada por uma chave de linha única, semelhante a uma chave primária. Cada linha é composta por uma família (ou conjunto) de colunas, e diferentes linhas podem ter diferentes famílias de colunas. Semelhante aos bancos de dados de chave-valor, a chave de linha funciona como a chave, e o conjunto de famílias de colunas atua como o valor representado pela chave de linha. No entanto, colunas em uma família de colunas consistem em pares atributo-valor que podem ser indexadas. O SGBD Cassandra oferece a funcionalidade adicional de supercolunas, que são criadas agrupando várias colunas.

Normalmente, os dados pertencentes a uma linha são armazenados juntos no mesmo nó do servidor. No entanto, o Cassandra pode distribuir uma única linha por vários nós de servidor usando chaves de partição compostas.
Nos bancos de dados colunares, a configuração das famílias de colunas é tipicamente feita durante a inicialização. No entanto, a definição prévia de colunas não é necessária, oferecendo grande flexibilidade no armazenamento de qualquer tipo de dado.

De forma semelhante aos bancos de dados de chave-valor, qualquer lógica que exija relações deve ser implementada na aplicação cliente, ou seja, essa categoria de banco de dados também não têm ciência de relacionamentos entre dados e controle de integridade referencial.

### 2.2.3 Documento

Bancos de dados orientados a documento armazenam dados como documentos autocontidos, em geral em formato JSON ou BSON. Cada documento possui um identificador e um conjunto de campos que podem variar entre documentos de uma mesma coleção, favorecendo esquemas flexíveis e agregados de leitura (read-optimized). O SGBD MongoDB é um exemplo popular nesta categoria. Ele define coleções de documentos, índices secundários e pipelines de agregação, permitindo consultas ricas sem exigir junções (joins) no servidor.

### 2.2.4 Grafo

Bancos de dados em grafo representam dados como **nós** (entidades) e **arestas** (relacionamentos tipados), com propriedades em ambos. Consultas exploram caminhos e vizinhanças de forma natural, o que é útil para recomendação, detecção de fraude e redes sociais. O Neo4j utiliza a linguagem Cypher para ``MERGE``/``CREATE`` de nós e relacionamentos.

Na ferramenta proposta, o destino grafo exige que o usuário declare explicitamente quais colunas do CSV identificam cada rótulo de nó e quais colunas alimentam propriedades do relacionamento (por exemplo, comprador $\rightarrow$ vendedor com atributos do pedido).

## 2.3 Bancos de Dados Multimodelo e Arquiteturas de Persistência Poliglota

SGBDs multimodelo integram mais de um paradigma de dados no mesmo motor de gerência de dados (por exemplo, documento + chave-valor + grafo), oferecendo em geral uma interface de acesso unificada — como a linguagem AQL do SGBD ArangoDB, que combina filtros sobre estruturas de documento similares à JSON e travessias em grafos em uma única abstração de modelo de dados que combina ambos modelos NoSQL.

A persistência poliglota, por outro lado, combina vários SGBDs heterogêneos, cada um escolhido pela adequação a um caso de uso da aplicação [@sadalage2013nosql]. Na literatura recente, essa ideia materializa-se como um SGPD (Sistema de Gerenciamento Poliglota de Dados): coordenação transparente entre tecnologias distintas, com requisitos de modelagem e expressividade de acesso (diferentes padrões de consulta) e capacidade de adaptação quando o workload evolui [@kiehn2022polyglot; @glake2022towards].

@tan2017query apresentam uma taxonomia útil para distinguir arquiteturas relacionadas: BD federado (fontes homogêneas, interface única), BD multistore (fontes heterogêneas, modelo canônico de consulta), BD polystore (fontes heterogêneas, múltiplas interfaces de acesso — exemplificadas por sistemas como o BigDAWG) e abordagens multimodelo (vários modelos no mesmo motor).

A escolha entre essas arquiteturas não é trivial. O trabalho de @royhubara2022selecting propõem critérios para selecionar quais modelos de dados usar em aplicações de persistência poliglota, destacando o trade-off entre especialização por SGBD e simplicidade operacional de um motor multimodelo.

O Polyglot Import CSV adota explicitamente a linha da persistência poliglota ao invés de multimodelo, conforme detalhado no capítulo 4. O usuário direciona entidades e filtros para PostgreSQL, Redis, MongoDB, Cassandra e Neo4j conforme o padrão de representação e acesso desejados.

# 3 TRABALHOS RELACIONADOS

Este capítulo apresenta e discute ferramentas oferecidas na indústria por SGBDs e também propostas na literatura acadêmica relacionadas com a importação de dados por SGBDs heterogêneos. A preferência está em dados no formato CSV que devem ser importados por alguma tecnologia de banco de dados, que é o foco deste trabalho.

## 3.1 Importação de arquivo CSV para um único SGBD

Esta seção investiga mecanismos de importação de dados presentes em SGBDs populares na indústria que são considerados neste trabalho.

### 3.1.1 PostgreSQL

No SGBD PostgreSQL você utiliza o comando `COPY` para realizar importações de dados CSV. É necessário especificar a tabela com os nomes das colunas após a cláusula `COPY`. A ordem das colunas deve ser a mesma que aquelas no arquivo CSV, conforme ilustra o exemplo a seguir:

```sql
COPY nome_da_tabela(col1, col2, col3)
FROM 'C:/caminho_do_arquivo/dados_de_amostra.csv'
DELIMITER ','
CSV HEADER;
```

Caso o arquivo CSV contenha todas as colunas da tabela, você não precisa especificá-las explicitamente:

```sql
COPY nome_da_tabela
FROM 'C:/caminho_do_arquivo/dados_de_amostra.csv'
DELIMITER ','
CSV HEADER;
```

Você também deve inserir o caminho do arquivo CSV após a palavra-chave `FROM`. Como o formato do arquivo é CSV, você precisa especificar `DELIMITER`, bem como as cláusulas `CSV`. A cláusula `HEADER` deve ser especificada para indicar que o arquivo CSV contém um cabeçalho. Quando o comando `COPY` importa dados, ele ignora o cabeçalho do arquivo.

O arquivo CSV deve ser lido diretamente pelo servidor PostgreSQL, não pela aplicação cliente. Portanto, ele deve ser acessível pela máquina do servidor PostgreSQL. Além disso, é necessário ter permissão de superusuário para executar com sucesso o comando `COPY`.

### 3.1.2 Redis

A maneira preferida de importar uma massa de dados para o Redis é gerar um arquivo de texto contendo o protocolo Redis, em formato bruto, para chamar os comandos necessários para inserir os dados requeridos.

Por exemplo, se é necessário gerar um grande conjunto de dados com bilhões de chaves no formato "chaveN -> ValorN", deve ser criado um arquivo contendo os seguintes comandos:

```text
SET Chave0 Valor0
SET Chave1 Valor1
...
SET ChaveN ValorN
```

Uma vez criado esse arquivo, a ação restante é alimentá-lo no Redis. No passado, a maneira de fazer isso era usar o netcat com o seguinte comando:

```bash
(cat dados.txt; sleep 10) | nc localhost 6379
```

Nas versões 2.6 ou posteriores do Redis, o utilitário `redis-cli` suporta um novo modo chamado modo pipe que foi projetado para realizar o carregamento em massa. O comando a ser executado neste caso é o seguinte:

```bash
cat dados.txt | redis-cli --pipe
```

O utilitário `redis-cli` imprime um pequeno resumo. A saída típica é semelhante a esta:

```text
All data transferred. Waiting for the last reply...
Last reply received from server.
errors: 0, replies: 1000000
```

A linha de contagem ao final é a informação mais importante do resumo: `errors` indica quantos comandos foram rejeitados pelo servidor, e `replies` indica o total de respostas recebidas. Se `errors: 0`, todos os comandos foram processados com sucesso. Um valor maior que zero em `errors` significa que ao menos um comando falhou — seja por sintaxe inválida no arquivo, por tipo de dado incompatível com a chave existente, ou por qualquer outra razão que o Redis tenha rejeitado.

Vale notar que o `--pipe` não exibe cada resposta individualmente (como um `+OK` por `SET`), o que é intencional: imprimir bilhões de respostas destruiria o ganho de performance do modo pipe e inundaria o terminal. Em vez disso, o `redis-cli` lê e contabiliza todas as respostas silenciosamente conforme chegam, entregando apenas o agregado final.

Por fim, uma verificação útil: o valor de `replies` deve ser igual ao número de comandos enviados. Uma divergência entre os dois pode indicar que o arquivo de entrada estava truncado ou malformado, mesmo que `errors` apareça como zero.

### 3.1.3 MongoDB

No SGBD MongoDB, o processo de importação de dados em formato CSV é realizado através do utilitário `mongoimport`. Sua sintaxe básica exige que se informe o banco de dados de destino através do parâmetro `--db`, seguido do nome da coleção que receberá os dados, especificado em `--collection`. Caso esse último parâmetro seja omitido, o nome da coleção será automaticamente inferido a partir do nome do arquivo CSV fornecido.

```bash
mongoimport --db nome_do_db --collection nome_da_colecao \
  --type csv --headerline --ignoreBlanks \
  --file caminho/do/arquivo.csv
```

O tipo do arquivo de entrada deve ser declarado explicitamente através do parâmetro `--type`, que neste caso recebe o valor `csv`. Para que o `mongoimport` reconheça os nomes dos campos a partir do próprio arquivo, utiliza-se o parâmetro `--headerline`, que instrui o utilitário a tratar o conteúdo da primeira linha do CSV como o cabeçalho dos campos. Opcionalmente, o parâmetro `--ignoreBlanks` pode ser utilizado para que valores em branco presentes no arquivo sejam ignorados durante a importação, evitando que campos vazios sejam persistidos na coleção. Por fim, o caminho do arquivo CSV a ser importado é fornecido através do parâmetro `--file`.

### 3.1.4 Cassandra

A importação de dados CSV para o Cassandra utiliza o comando `sstableloader` e envolve vários passos. Inicialmente, é necessário se certificar que o arquivo CSV está no formato adequado para o Cassandra. Isso geralmente envolve garantir que os tipos de dados e as colunas correspondem ao esquema da tabela no Cassandra.

O `sstableloader` requer que os dados estejam em um formato específico chamado SSTable. Para converter o CSV em SSTables, você pode usar o comando `cqlsh` fornecido pelo Cassandra. Um exemplo de uso é o seguinte:

```bash
cqlsh -e "COPY keyspace_name.table_name TO 'output_directory';"
```

Na sequência, é possível usar o `sstableloader` para carregar os dados. A sintaxe do comando é a seguinte:

```bash
sstableloader -d <hostname> -u <username> -pw <password> \
  output_directory/keyspace_name/table_name
```

- `<hostname>`: O endereço do nó Cassandra.
- `<username>`: O nome de usuário, se a autenticação estiver habilitada.
- `<password>`: A senha correspondente.

Este comando move os dados do diretório de saída para o Cassandra.

### 3.1.5 Neo4j

Usar `neo4j-admin` para importar grandes conjuntos de dados no Neo4j envolve alguns passos. Esta ferramenta de linha de comando é projetada para importações em massa eficientes.

Certifique-se de que seus arquivos CSV estejam estruturados corretamente e sigam o formato necessário para nós e relacionamentos.

Crie um banco de dados não povoado:

```bash
neo4j-admin create-db --database=nome_do_seu_banco_de_dados \
  --from=diretorio_com_arquivos_csv
```

Substitua `nome_do_seu_banco_de_dados` pelo nome desejado para o novo banco de dados. A opção `--from` especifica o diretório onde estão localizados seus arquivos CSV.

Execute o comando de importação com `neo4j-admin`. O comando exato depende do seu modelo de dados, mas pode se parecer com isto:

```bash
neo4j-admin import --database=nome_do_seu_banco_de_dados \
  --mode=csv \
  --nodes:Rotulo1 nos.csv \
  --nodes:Rotulo2 nos2.csv \
  --relationships:TIPO_RELACIONAMENTO relacionamentos.csv
```

Substitua *Rotulo1*, *Rotulo2*, *nos.csv*, *nos2.csv*, *TIPO_RELACIONAMENTO* e *relacionamentos.csv* pelos seus rótulos específicos e nomes de arquivo.

## 3.2 Importação de arquivo CSV para SGBD multimodelo

Ferramentas comerciais e de código aberto tratam de **migração** ou **modelagem** entre tecnologias heterogêneas, embora raramente com o foco deste TCC (um único CSV largo + regras declarativas + cinco paradigmas).

- **ArangoDB** é um SGBD multimodelo nativo (documento/chave-valor/grafo) com ``arangoimport`` para CSV; a importação é para **um** motor multimodelo, não para cinco backends independentes.
- **``mongoimport`` / ``COPY`` / ``redis-cli --pipe`` / ``cqlsh`` / ``neo4j-admin``** (seção 3.1) cobrem importação **para um único** produto por vez.
- **dbcrossbar** [@dbcrossbar2024] copia dados tabulares entre PostgreSQL, BigQuery, armazenamento em nuvem e CSV, incluindo conversão de esquemas; a ênfase é *pipeline* de migração, não mapeamento semântico de entidades aninhadas com filtros por valor.
- **Hackolade** [@hackolade2024polyglot] oferece *polyglot data modeling* com engenharia de esquema para dezenas de alvos; trata-se de **modelagem visual** e geração de artefatos, e não de um utilitário CLI único para importar um CSV operacional com validação prévia de filtros.

## 3.3 Considerações sobre os trabalhos relacionados

A literatura sobre **metamodelos unificados** para SQL e NoSQL (por exemplo, U-Schema [@berlanga2021unified]) e sobre **evolução de esquema** em ambientes heterogêneos [@chillon2023propagating] informa decisões de validação e de representação de entidades no JSON de configuração, mas não substitui uma ferramenta de *bulk import* orientada a CSV.

Surveys recentes convergem em desafios abertos da gestão poliglota de dados: migração automatizada entre stores quando o *workload* muda, planejamento de consultas entre sistemas, gestão de esquemas multi-modelo e preservação das propriedades não funcionais de cada SGBD [@kiehn2022polyglot; @glake2022towards]. @royhubara2022selecting tratam da **seleção de SGBDs** por fragmento de aplicação; @silva2024modelagem mapeiam o estado da arte em **modelagem poliglota**. Nenhum desses trabalhos implementa, contudo, um utilitário declarativo que receba um CSV operacional único e o materialize simultaneamente em cinco paradigmas distintos com validação estática prévia.

Sistemas **polystore** como o BigDAWG [@duggan2017bigdawg] e middlewares de portabilidade em nuvem [@wang2020cmc] tratam de **consultas federadas** e movimentação de dados em ecossistemas complexos. @tan2017query classificam essas soluções (federado, multistore, polystore, poliglota) e avaliam transparência, autonomia e heterogeneidade — eixos nos quais importadores nativos (seção 3.1) e ferramentas de migração (seção 3.2) também divergem, mas sem convergir para um pipeline único de ingestão.

Ferramentas como **dbcrossbar** [@dbcrossbar2024] e **Hackolade** [@hackolade2024polyglot] aproximam-se do domínio de integração de dados, porém com foco em *pipelines* de migração ou modelagem visual, respectivamente — não em regras declarativas sobre entidades aninhadas, filtros por valor (`each`) e validação por JSON Schema antes de qualquer conexão com SGBDs.

**Lacuna identificada:** a combinação de (i) um CSV largo como fonte operacional, (ii) configuração JSON validada estaticamente, (iii) materialização distinta por paradigma (relacional, chave-valor, documento, colunar, grafo) e (iv) modo *dry-run* para revisão prévia. O *Polyglot Import CSV* ocupa essa lacuna como ferramenta de **bootstrap de persistência poliglota** — carga inicial e reprodutível de dados — enquanto middlewares e polystores assumem dados já residentes ou consultas em tempo de execução. Trabalhos futuros podem integrar a ferramenta a mecanismos de migração adaptativa descritos por @kiehn2022polyglot e @glake2022towards.

# 4 A PROPOSTA DA FERRAMENTA PolyglotImportCSV

## 4.1 Visão geral

A ferramenta **PolyglotImportCSV** (pacote Python ``polyglot-import-csv``) lê um arquivo CSV e **dois arquivos de configuração JSON** — um de importação (mapeamento) e um de conexão dos SGBDs — cada um validado por um **JSON Schema** embutido. A CLI executa, em sequência:

1. Carregamento do CSV (como texto, para evitar erros de *parse* em campos com ``+`` em timestamps).
2. Inferência de *kinds* de coluna (inteiro, *float*, data/hora, texto) para validar operadores de filtro.
3. Validação cruzada: colunas referenciadas existem no CSV; relacionamentos PostgreSQL e Neo4j referenciam entidades conhecidas; chaves de partição Cassandra estão declaradas quando necessário.
4. Para cada backend configurado: aplicação de filtros (incluindo o operador ``each`` para particionar por valor distinto), materialização de entidades e importação (ou apenas resumo em ``--dry-run``).

Comando principal:

```bash
python -m polyglotimportcsv caminho/dados.csv \
  --config caminho/import_config.json \
  --sgbd-config caminho/sgbd_config.json \
  [--dry-run] \
  [--create-schema / --no-create-schema] \
  [--only postgres,redis]
```

## 4.2 Formato de configuração (JSON Schema)

A configuração é dividida em **dois arquivos JSON**, cada um validado estaticamente por um **JSON Schema** próprio embutido em ``src/polyglotimportcsv/schemas/`` (rascunho 2020-12):

- ``import_config.json`` — o **mapeamento** de entidades, relacionamentos e colunas do CSV para cada SGBD (schema ``import_config.schema.json``);
- ``sgbd_config.json`` — a **configuração de conexão** de cada SGBD, isto é, quais bancos estão disponíveis e como alcançá-los (schema ``sgbd_config.schema.json``).

Essa separação atende a duas preocupações distintas: o *mapeamento* (modelo de dados) muda conforme o domínio dos dados, enquanto a *conexão* muda conforme o ambiente de execução (desenvolvimento, testes, produção). A validação ocorre em ``config_parser.load_config`` antes de qualquer leitura do CSV ou conexão com SGBDs; os exemplos de referência do cenário e-commerce estão em ``data/ecommerce/import_config.json`` e ``data/ecommerce/sgbd_config.json``, alinhados ao CSV ``data/ecommerce/ecommerce_join.csv``.

Um SGBD só pode ser referenciado no arquivo de importação se estiver **declarado** no arquivo de conexão; caso contrário, a execução é abortada (ver seção 4.2.5). O schema de importação também passou por uma **reforma de simplificação** (seção 4.2.6) cujo objetivo foi reduzir o vocabulário do comando ao mínimo necessário, eliminando campos redundantes ou depreciados. A representação completa de ambos os schemas, na forma universal de *JSON Schema*, e o diagrama de estrutura resultante são apresentados na seção 4.2.6.

### 4.2.1 Estrutura raiz

Ambos os arquivos compartilham a mesma raiz: um campo ``version`` obrigatório e um bloco opcional por backend. No **arquivo de importação**, cada bloco contém o mapeamento (``entities`` e, quando aplicável, ``relationships``):

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| ``version`` | inteiro ($\geq 1$) | sim | Versão do formato de configuração (atualmente ``1``). |
| ``postgres`` | objeto | não | Bloco de mapeamento relacional. |
| ``mongodb`` | objeto | não | Bloco de mapeamento documental. |
| ``cassandra`` | objeto | não | Bloco de mapeamento colunar. |
| ``redis`` | objeto | não | Bloco de mapeamento chave-valor. |
| ``neo4j`` | objeto | não | Bloco de mapeamento em grafo. |

No **arquivo de conexão**, cada bloco de backend contém um objeto ``connection`` (e, para o PostgreSQL, o ``schema`` de destino). Em ambos os arquivos, propriedades adicionais na raiz e nos blocos são **rejeitadas** (``additionalProperties: false``), o que impede erros de digitação como ``postgress`` passarem despercebidos.

### 4.2.2 Mapeamento de colunas (`columnSpec`)

Cada **folha** do mapa ``columns`` descreve como um valor do CSV alimenta um atributo no destino. A chave JSON no mapa ``columns`` identifica o campo por omissão; quando o cabeçalho CSV ou o nome no schema diferem dessa chave, usam-se os campos explícitos abaixo.

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| ``csv_column`` | *string* ou inteiro ($\geq 0$) | não | Nome do cabeçalho CSV **ou** índice da coluna (base 0). Se omitido, a chave JSON é o cabeçalho CSV. |
| ``schema_column`` | *string* | não | Nome do atributo no SGBD destino. Se omitido, usa-se a chave JSON. |
| ``is_key`` | booleano | não | Marca chave primária, chave de ``MERGE`` (Neo4j) ou chave Redis. |
| ``db_type`` | *string* | não | Tipo SQL/CQL para geração de DDL (PostgreSQL, Cassandra). |

Propriedades adicionais em um ``columnSpec`` são rejeitadas (``additionalProperties: false``). Apenas estes quatro campos — ``csv_column``, ``schema_column``, ``is_key`` e ``db_type`` — compõem o mapeamento de uma folha, resultado da reforma de simplificação descrita na seção 4.2.6.

**Forma mínima** — coluna CSV e destino com o mesmo nome:

```json
"product_id": {}
```

**Renomeação explícita** — cabeçalho CSV distinto do atributo no schema:

```json
"timestamp": { "schema_column": "event_time" }
```

**Índice numérico** — útil quando o CSV não possui cabeçalho ou o nome é ambíguo:

```json
"logical_key": { "csv_column": 0, "is_key": true }
```

**Chave lógica distinta do CSV e do schema:**

```json
"redis_key": { "csv_column": "user_id", "schema_column": "session_id", "is_key": true }
```

### 4.2.3 Entidade (`entity`)

Uma **entidade** representa um alvo lógico: tabela (PostgreSQL/Cassandra), coleção (MongoDB), rótulo de nó (Neo4j) ou entidade Redis.

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| ``columns`` | objeto recursivo | sim | Mapa de mapeamentos; ver abaixo. |
| ``filters`` | lista | não | Predicados sobre o CSV completo antes da materialização. |
| ``cassandra_partition`` | lista de *strings* | não | Colunas CSV que formam a chave de partição. |
| ``cassandra_cluster`` | lista de *strings* | não | Colunas de agrupamento (*clustering*). |

**Aninhamento MongoDB via chaves JSON:** objetos aninhados em ``columns`` produzem subdocumentos BSON, espelhando a estrutura de um documento JSON. Após a reforma de simplificação (seção 4.2.6), o aninhamento é expresso **exclusivamente** por chaves aninhadas dentro de ``columns`` — não há mais um bloco ``nested`` separado:

```json
"columns": {
  "product_id": {},
  "category": {
    "category_id": {},
    "category_name": {}
  },
  "stock": {
    "quantity_available": {},
    "last_restock_date": {}
  }
}
```

Backends **planos** (PostgreSQL, Redis, Cassandra, Neo4j) aceitam apenas folhas em ``columns``; aninhamento é rejeitado na validação cruzada.

**Filtros** — cada item exige ``column`` e ``operator``:

| Operador | ``value`` | Efeito |
|----------|-----------|--------|
| ``==``, ``!=``, ``>``, ``<``, ``>=``, ``<=`` | escalar | Comparação sobre a coluna CSV. |
| ``in``, ``not_in`` | lista | Pertinência ao conjunto. |
| ``each`` | escalar (opcional) | Particiona a entidade por valores distintos da coluna; sufixo opcional em ``target_suffix``. |

Exemplo do e-commerce — apenas linhas de estoque alimentam o inventário:

```json
"filters": [{ "column": "action", "operator": "==", "value": "stock" }]
```

### 4.2.4 Blocos por backend

No **arquivo de importação**, cada backend opcional contém ``entities``; PostgreSQL e Neo4j admitem ainda ``relationships``. As credenciais de acesso (``connection`` e, no PostgreSQL, ``schema``) ficam no **arquivo de conexão** (``sgbd_config.json``) e são mescladas a cada backend em tempo de execução. A seguir, os campos de conexão de cada SGBD aparecem entre parênteses por referência.

**PostgreSQL** — conexão (host, port, database, user, password) e ``schema`` (padrão ``public``) no arquivo de conexão; entidades planas com ``db_type`` e ``relationships`` para chaves estrangeiras no arquivo de importação:

```json
"relationships": {
  "product_category": {
    "from": "products",
    "to": "categories",
    "foreign_key": "category_id",
    "references_key": "category_id"
  }
}
```

**MongoDB** — conexão (``uri``, ``database``); entidades com ``columns`` recursivos para subdocumentos.

**Cassandra** — conexão (``hosts``, ``keyspace``); entidades com ``cassandra_partition`` / ``cassandra_cluster`` e renomeação via ``schema_column``:

```json
"timestamp": { "schema_column": "event_time" },
"cassandra_partition": ["user_id"],
"cassandra_cluster": ["timestamp"]
```

**Redis** — exatamente uma coluna ``is_key`` por entidade; demais campos compõem o valor JSON.

**Neo4j** — nós em ``entities`` (um ``is_key`` cada); ``relationships`` declaram arestas tipadas com propriedades opcionais:

```json
"relationships": {
  "PURCHASED": {
    "from": "User",
    "to": "Product",
    "type": "PURCHASED",
    "columns": { "order_number": { "is_key": true }, "quantity": {} }
  }
}
```

### 4.2.5 Validação estática e cruzada

A validação ocorre em **três camadas**:

1. **JSON Schema** — cada arquivo é validado contra o seu schema (`config_parser.validate_import_config_schema` e `config_parser.validate_sgbd_config`): sintaxe, tipos e propriedades permitidas.
2. **Consistência entre arquivos** (`config_parser.merge_configs`) — todo backend referenciado no arquivo de importação deve estar **declarado** no arquivo de conexão; caso contrário, a execução é abortada antes de qualquer leitura do CSV.
3. **Validação cruzada CSV** (`validation.validate_import_config`) — colunas referenciadas existem no CSV; filtros coerentes; FKs PostgreSQL e arestas Neo4j referenciam entidades válidas; backends planos não usam ``columns`` aninhados; índices ``csv_column`` dentro do intervalo.

Qualquer falha levanta ``BusinessException`` e **impede** o início da importação, conforme o objetivo específico do TCC.

### 4.2.6 Reforma de simplificação e representação na forma universal

O *JSON Schema* de configuração passou por uma **reforma** orientada pelo princípio de manter o comando o mais simples possível: cada conceito deve ter **uma única** forma de ser expresso. Versões anteriores acumulavam campos redundantes, mantidos por retrocompatibilidade, que duplicavam funcionalidades já cobertas por ``csv_column``, ``schema_column`` e pelo mapa recursivo ``columns``. Esses campos foram removidos, conforme a Tabela a seguir.

| Campo removido | Substituto canônico | Justificativa |
|----------------|---------------------|---------------|
| ``db_column`` | ``schema_column`` | Sinônimo de renomeação no destino; redundante. |
| ``alias_db`` | ``schema_column`` | Segundo sinônimo da mesma operação de renomeação. |
| ``nested`` (em ``entity``) | chaves aninhadas em ``columns`` | O aninhamento de subdocumentos MongoDB já é expresso recursivamente pelo próprio mapa ``columns`` (``columnEntry``), tornando o bloco separado desnecessário. |

Com a reforma, o vocabulário de uma folha (``columnSpec``) reduz-se a quatro campos opcionais (``csv_column``, ``schema_column``, ``is_key``, ``db_type``) e o aninhamento documental fica concentrado em um único mecanismo. A motivação prática para manter ``csv_column`` e ``schema_column`` é que **nem sempre o nome da coluna no CSV coincide com o nome do atributo no banco de destino**: ``csv_column`` indica o nome — ou o índice numérico (base 0) — da coluna de origem no CSV, enquanto ``schema_column`` indica o nome do atributo correspondente no SGBD. Quando ambos coincidem com a chave JSON, nenhum dos dois é necessário (forma mínima ``"campo": {}``).

A reforma preserva a propriedade de *fechamento* do schema: em todos os níveis vale ``additionalProperties: false``, de modo que qualquer campo legado remanescente em configurações antigas é detectado na validação, em vez de ser silenciosamente ignorado.

**Separação em dois schemas.** Além da reforma de simplificação, a configuração foi **dividida em dois arquivos**, cada um com o seu próprio *JSON Schema*: ``import_config.schema.json`` (mapeamento) e ``sgbd_config.schema.json`` (conexão). A separação isola o que muda por **domínio de dados** (entidades, relacionamentos, colunas) do que muda por **ambiente de execução** (credenciais e endereços), permitindo, por exemplo, reaproveitar o mesmo mapeamento com diferentes ambientes apenas trocando o arquivo de conexão. O bloco ``connection`` (antes aninhado em cada backend do arquivo único) passou para o arquivo de conexão, e a função ``merge_configs`` recompõe, em tempo de execução, a estrutura por backend exigida pelos importadores — exigindo que todo SGBD do arquivo de importação esteja declarado no de conexão (seção 4.2.5).

**Diagrama de estrutura.** A Figura 4 apresenta a árvore de estrutura dos dois schemas reformados — o de importação, da raiz aos blocos por backend, à definição reutilizável ``entity`` e à recursão ``columns → columnEntry → columnSpec`` que sustenta os subdocumentos MongoDB; e o de conexão, com o bloco ``connection`` por backend. O diagrama-fonte Mermaid encontra-se em ``docs-tcc/images/figure4-config-schema.mmd`` (campos obrigatórios marcados com ``*``).

![Estrutura dos JSON Schemas de configuração do PolyglotImportCSV (importação e conexão).](images/figure4-config-schema.png){width=15cm}

**Fonte:** Elaborado pelo autor (2026).

**Representação na forma universal.** A seguir reproduzem-se os dois documentos *JSON Schema* completos na sua forma serializada canônica (rascunho 2020-12), tal como embutidos em ``src/polyglotimportcsv/schemas/``. Essa é a representação **universal** e portável do contrato de configuração: pode ser consumida por qualquer validador compatível com a especificação, independentemente de linguagem de programação. Primeiro, o schema de **importação** (``import_config.schema.json``):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://polyglot-import-csv.local/schemas/import_config.schema.json",
  "title": "PolyglotImportCSV import configuration",
  "description": "Declarative mapping from a wide CSV file to entities and relationships of one or more database backends. Connection settings live in the separate SGBD configuration.",
  "type": "object",
  "required": ["version"],
  "properties": {
    "version": {
      "type": "integer",
      "minimum": 1,
      "description": "Configuration format version."
    },
    "postgres": { "$ref": "#/$defs/postgresMapping" },
    "mongodb": { "$ref": "#/$defs/mongoMapping" },
    "cassandra": { "$ref": "#/$defs/cassandraMapping" },
    "redis": { "$ref": "#/$defs/redisMapping" },
    "neo4j": { "$ref": "#/$defs/neo4jMapping" }
  },
  "additionalProperties": false,
  "$defs": {
    "columnSpec": {
      "type": "object",
      "description": "Leaf mapping from a CSV column to a destination field.",
      "properties": {
        "is_key": {
          "type": "boolean",
          "description": "Primary or merge key for the entity."
        },
        "csv_column": {
          "description": "CSV header name or 0-based column index when it differs from the JSON key.",
          "oneOf": [
            { "type": "string", "minLength": 1 },
            { "type": "integer", "minimum": 0 }
          ]
        },
        "schema_column": {
          "type": "string",
          "minLength": 1,
          "description": "Destination field name when it differs from the JSON key."
        },
        "db_type": {
          "type": "string",
          "description": "SQL/CQL type for DDL generation (PostgreSQL, Cassandra)."
        }
      },
      "additionalProperties": false
    },
    "columnEntry": {
      "description": "Either a leaf columnSpec or a nested object (MongoDB subdocuments).",
      "oneOf": [
        { "$ref": "#/$defs/columnSpec" },
        {
          "type": "object",
          "minProperties": 1,
          "additionalProperties": { "$ref": "#/$defs/columnEntry" }
        }
      ]
    },
    "filter": {
      "type": "object",
      "description": "Row predicate applied to the full CSV before materialization.",
      "required": ["column", "operator"],
      "properties": {
        "column": { "type": "string", "minLength": 1 },
        "operator": {
          "type": "string",
          "enum": ["==", "!=", ">", "<", ">=", "<=", "in", "not_in", "each"]
        },
        "value": {},
        "target_suffix": {
          "type": "string",
          "description": "With operator 'each', optional template; default is sanitized distinct value"
        }
      },
      "additionalProperties": false
    },
    "entity": {
      "type": "object",
      "description": "One logical target (table, collection, label, or Redis entity).",
      "required": ["columns"],
      "properties": {
        "columns": {
          "type": "object",
          "minProperties": 1,
          "additionalProperties": { "$ref": "#/$defs/columnEntry" }
        },
        "filters": {
          "type": "array",
          "items": { "$ref": "#/$defs/filter" }
        },
        "cassandra_partition": {
          "type": "array",
          "items": { "type": "string" },
          "description": "CSV/source column names forming the partition key (compound supported)"
        },
        "cassandra_cluster": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Clustering columns (optional)"
        }
      },
      "additionalProperties": false
    },
    "postgresMapping": {
      "type": "object",
      "required": ["entities"],
      "properties": {
        "entities": {
          "type": "object",
          "additionalProperties": { "$ref": "#/$defs/entity" }
        },
        "relationships": {
          "type": "object",
          "additionalProperties": {
            "type": "object",
            "required": ["from", "to", "foreign_key"],
            "properties": {
              "from": { "type": "string" },
              "to": { "type": "string" },
              "foreign_key": { "type": "string" },
              "references_key": { "type": "string" }
            },
            "additionalProperties": false
          }
        }
      },
      "additionalProperties": false
    },
    "mongoMapping": {
      "type": "object",
      "required": ["entities"],
      "properties": {
        "entities": {
          "type": "object",
          "additionalProperties": { "$ref": "#/$defs/entity" }
        }
      },
      "additionalProperties": false
    },
    "cassandraMapping": {
      "type": "object",
      "required": ["entities"],
      "properties": {
        "entities": {
          "type": "object",
          "additionalProperties": { "$ref": "#/$defs/entity" }
        }
      },
      "additionalProperties": false
    },
    "redisMapping": {
      "type": "object",
      "required": ["entities"],
      "properties": {
        "entities": {
          "type": "object",
          "additionalProperties": { "$ref": "#/$defs/entity" }
        }
      },
      "additionalProperties": false
    },
    "neo4jMapping": {
      "type": "object",
      "required": ["entities"],
      "properties": {
        "entities": {
          "type": "object",
          "additionalProperties": { "$ref": "#/$defs/entity" }
        },
        "relationships": {
          "type": "object",
          "additionalProperties": {
            "type": "object",
            "required": ["from", "to", "type"],
            "properties": {
              "from": { "type": "string" },
              "to": { "type": "string" },
              "type": { "type": "string" },
              "columns": {
                "type": "object",
                "additionalProperties": { "$ref": "#/$defs/columnSpec" }
              }
            },
            "additionalProperties": false
          }
        }
      },
      "additionalProperties": false
    }
  }
}
```

E, em seguida, o schema de **conexão** (``sgbd_config.schema.json``):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://polyglot-import-csv.local/schemas/sgbd_config.schema.json",
  "title": "PolyglotImportCSV SGBD connection configuration",
  "description": "Connection settings for each database backend. Lists which SGBDs are available; the import configuration may only target backends declared here.",
  "type": "object",
  "required": ["version"],
  "properties": {
    "version": {
      "type": "integer",
      "minimum": 1,
      "description": "Configuration format version."
    },
    "postgres": { "$ref": "#/$defs/postgresConnection" },
    "mongodb": { "$ref": "#/$defs/mongoConnection" },
    "cassandra": { "$ref": "#/$defs/cassandraConnection" },
    "redis": { "$ref": "#/$defs/redisConnection" },
    "neo4j": { "$ref": "#/$defs/neo4jConnection" }
  },
  "additionalProperties": false,
  "$defs": {
    "postgresConnection": {
      "type": "object",
      "properties": {
        "connection": {
          "type": "object",
          "properties": {
            "host": { "type": "string" },
            "port": { "type": "integer" },
            "database": { "type": "string" },
            "user": { "type": "string" },
            "password": { "type": "string" }
          },
          "additionalProperties": false
        },
        "schema": {
          "type": "string",
          "default": "public",
          "description": "Target schema for created tables."
        }
      },
      "additionalProperties": false
    },
    "mongoConnection": {
      "type": "object",
      "properties": {
        "connection": {
          "type": "object",
          "properties": {
            "uri": { "type": "string" },
            "database": { "type": "string" }
          },
          "required": ["uri", "database"],
          "additionalProperties": false
        }
      },
      "additionalProperties": false
    },
    "cassandraConnection": {
      "type": "object",
      "properties": {
        "connection": {
          "type": "object",
          "properties": {
            "hosts": { "type": "array", "items": { "type": "string" } },
            "port": { "type": "integer" },
            "keyspace": { "type": "string" },
            "protocol_version": { "type": "integer" }
          },
          "required": ["hosts", "keyspace"],
          "additionalProperties": false
        }
      },
      "additionalProperties": false
    },
    "redisConnection": {
      "type": "object",
      "properties": {
        "connection": {
          "type": "object",
          "properties": {
            "host": { "type": "string" },
            "port": { "type": "integer" },
            "db": { "type": "integer" },
            "password": { "type": "string" }
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false
    },
    "neo4jConnection": {
      "type": "object",
      "properties": {
        "connection": {
          "type": "object",
          "properties": {
            "uri": { "type": "string" },
            "user": { "type": "string" },
            "password": { "type": "string" },
            "database": { "type": "string" }
          },
          "required": ["uri", "user", "password"],
          "additionalProperties": false
        }
      },
      "additionalProperties": false
    }
  }
}
```

**Fonte:** Elaborado pelo autor (2026).

## 4.3 Algoritmo de execução da importação

O núcleo da ferramenta está em ``runner.run_import``. A seguir descreve-se o fluxo de alto nível desde a linha de comando até a persistência em cada SGBD.

### 4.3.1 Fases do algoritmo

1. **Entrada** — caminho do CSV, caminhos dos dois JSON de configuração (importação e conexão) e flags: ``--dry-run``, ``--create-schema`` / ``--no-create-schema``, ``--only`` (lista de backends).
2. **Carregar configuração** — ``load_config``: parse dos dois JSON + ``jsonschema.validate`` de cada um contra o seu schema embutido + verificação de consistência entre arquivos (backends declarados) e mesclagem das conexões.
3. **Carregar CSV** — ``load_csv_with_inference``: leitura com ``dtype=str`` (evita erros de *parse* em timestamps com ``+``) e inferência de *kind* por coluna (``integer``, ``float``, ``datetime``, ``string``, ``empty``).
4. **Validar config × CSV** — ``validate_import_config``: checagens semânticas descritas na seção 4.2.5.
5. **Para cada backend** presente na configuração e não filtrado por ``--only``:
   - **Para cada entidade** declarada em ``entities``:
     - Aplicar filtros (exceto operador ``each``) sobre o DataFrame completo.
     - Expandir partições ``each`` (opcional) — uma entidade lógica pode gerar várias tabelas/coleções com sufixo.
     - **Materializar** registros conforme o paradigma do backend:
       - PostgreSQL / Cassandra: ``flatten_entity_dataframe`` — seleção, renomeação, deduplicação por ``is_key``.
       - MongoDB: ``mongo_document_from_row`` — documento recursivo a partir de ``columns`` aninhados.
       - Redis: ``redis_payload_from_row`` — par (chave, valor JSON).
       - Neo4j: propriedades de nós; depois ``MERGE`` de arestas a partir de ``relationships``.
     - Conectar ao SGBD (omitido em ``--dry-run``).
     - Criar schema se ``--create-schema`` (DDL PostgreSQL/Cassandra).
     - Persistir (``INSERT``, ``insert_many``, ``SET``, ``MERGE`` Cypher, etc.).
6. **Saída** — linhas de log com contagens por entidade/backend.

### 4.3.2 Pseudocódigo

```
função run_import(csv_path, config_path, sgbd_config_path, dry_run, create_schema, only):
    config ← load_config(config_path, sgbd_config_path)
    df, kinds ← load_csv_with_inference(csv_path)
    validate_import_config(config, df, kinds)

    para cada backend em (postgres, mongodb, cassandra, redis, neo4j):
        se backend nao esta em config ou nao esta em only: continuar
        linhas ← run_{backend}_import(config[backend], df, kinds,
                                       dry_run, create_schema)
        registrar linhas no log
```

Dentro de cada ``run_*_import``, para cada entidade:

```
    df_filtrado ← apply_filters(df, filtros_sem_each)
    para cada (nome_partição, df_parte) em expand_each(...):
        registros ← materializar(df_parte, entidade, backend)
        se não dry_run: conectar, DDL se necessário, gravar registros
```

### 4.3.3 Diagrama do fluxo

A Figura 5 resume o pipeline de execução descrito acima. O diagrama-fonte Mermaid encontra-se em ``docs-tcc/images/figure5-import-algorithm.mmd`` para futuras revisões.

![Algoritmo de execução da importação Polyglot Import CSV.](images/figure5-import-algorithm.png){width=12cm}

**Fonte:** Elaborado pelo autor (2026).

### 4.3.4 Exemplo: uma linha `action=stock` no e-commerce

Considere uma linha do ``ecommerce_join.csv`` com ``action = stock``, contendo ``product_id``, ``category_id``, ``quantity_available``, ``timestamp``, etc.

| Backend | Entidade | Filtro aplicado | Saída materializada |
|---------|----------|-----------------|---------------------|
| PostgreSQL | ``inventory`` | ``action == stock`` | Linha plana: ``product_id``, ``quantity_available``, ``last_restock_date``, ``price``. |
| MongoDB | ``product_catalog`` | ``action == stock`` | Documento com campos de produto e subobjetos ``category`` e ``stock`` aninhados. |
| Cassandra | ``user_activity_log`` | nenhum (todas as linhas) | Registro com ``timestamp`` renomeado para ``event_time``, ``action`` para ``event_type``; PK composta ``(user_id, timestamp)``. |
| Redis | — | — | Entidades Redis usam outros filtros (``add_to_cart``, ``select_product``); esta linha não alimenta Redis. |
| Neo4j | ``Product`` | ``action == stock`` | Nó ``:Product`` com ``product_id`` como chave de ``MERGE``. |

Assim, um **único CSV largo** alimenta destinos heterogéneos: tabelas relacionais filtradas por tipo de evento, documentos aninhados, log colunar com renomeação de colunas e nós de grafo — materializando a persistência poliglota descrita no capítulo 2.

## 4.4 Validação e execução

Erros de configuração levantam ``BusinessException`` antes de qualquer conexão. O modo ``--dry-run`` lista contagens por entidade sem contatar os SGBDs. O *driver* Apache Cassandra é importado de forma tardia para permitir ``--dry-run`` em ambientes onde a extensão C do *driver* não está disponível (por exemplo, versões recentes do Python).

Testes automatizados (``pytest``) cobrem validação de schema, separação e mesclagem dos dois arquivos de configuração, mapeamento de colunas (``csv_column``, ``schema_column``, aninhamento), filtros e *smoke tests* de validação + *dry-run*. O arquivo ``docker-compose.yml`` na raiz define os contêineres de PostgreSQL, Redis, MongoDB, Cassandra e Neo4j para testes de integração manuais; o script ``run_example.sh`` lê o ``sgbd_config.json`` e **sobe apenas os SGBDs ali declarados**, em seguida orquestra um *dry-run* e a importação real com ``--create-schema``.

### 4.4.1 Evidência de execução (cenário e-commerce)

O arquivo ``data/ecommerce/ecommerce_join.csv`` contém 32 linhas de eventos (``stock``, ``purchase``, ``add_to_cart``, ``select_product``). Com ``import_config.json``, ``sgbd_config.json`` e a flag ``--dry-run``, a ferramenta reporta as contagens abaixo sem abrir conexões com os SGBDs — útil para revisar o mapeamento antes da carga:

| Backend | Destino | Registros (após filtros / deduplicação) |
|---------|---------|----------------------------------------|
| PostgreSQL | ``categories`` | 8 |
| PostgreSQL | ``products`` | 8 |
| PostgreSQL | ``inventory`` | 8 |
| PostgreSQL | ``orders`` | 8 |
| MongoDB | ``product_catalog`` | 8 documentos |
| Cassandra | ``user_activity_log`` | 32 linhas (todas as ações) |
| Redis | ``shopping_cart`` | 8 |
| Redis | ``user_session`` | 8 |
| Neo4j | nó ``User`` | 8 |
| Neo4j | nó ``Product`` | 8 |
| Neo4j | aresta ``PURCHASED`` | conforme linhas ``purchase`` |

Com ``docker compose up -d`` e ``run_example.sh`` (ou importação sem ``--dry-run``), os mesmos volumes são persistidos nos cinco backends configurados, materializando o cenário poliglota da seção 2.1.

# 5 ATIVIDADES FUTURAS

- **Avaliação de desempenho** das importações com diferentes volumes de dados CSV e configurações, comparando importações simples e complexas para os diferentes modelos de dados destino.
- **Interface gráfica desktop** (semestre seguinte) que monte o comando CLI e visualize os arquivos JSON de configuração.
- **Suporte a TSV/Excel** e a *chunked* processing para CSV maiores que a RAM.
- **Operadores de filtro adicionais** e políticas de coerção de tipos configuráveis.
- **Testes de integração** contra ``docker compose`` em CI.
- **Generalização** do núcleo de importação para novos conectores (mensageria, *data lakes*, outros SGBDs).

# CONSIDERAÇÕES FINAIS

Este TCC I apresentou a fundamentação teórica da persistência poliglota, o estado da arte em importação e modelagem de dados heterogêneos, e a proposta da ferramenta *Polyglot Import CSV* como utilitário de *bootstrap* declarativo a partir de CSV.

As principais contribuições desta etapa são: (i) um formato de configuração JSON validado estaticamente por JSON Schema, separado em mapeamento e conexão, com mapeamento recursivo de colunas e filtros por valor; (ii) um protótipo em Python que materializa o mesmo CSV operacional em PostgreSQL, MongoDB, Cassandra, Redis e Neo4j; (iii) o modo ``--dry-run`` para revisão prévia de contagens; e (iv) o cenário e-commerce reprodutível com ``ecommerce_join.csv``, ``import_config.json``, ``sgbd_config.json`` e ``docker-compose.yml``.

As limitações reconhecidas incluem: testes automatizados predominantemente unitários (sem suíte de integração contínua contra Docker); processamento em memória do CSV inteiro; e dependência do *driver* Cassandra em ambientes Python recentes. Itens como interface gráfica, suporte a TSV/Excel, *chunked* processing e novos conectores permanecem no escopo do TCC II (Capítulo 5).

O trabalho de conclusão de curso em dezembro de 2026 poderá aprofundar a avaliação experimental (desempenho, consistência entre stores) e a interface de uso, consolidando a ferramenta como artefato de pesquisa e de código aberto alinhado à literatura sobre SGPD e modelagem poliglota de dados.

```{=latex}
\postextual
```
