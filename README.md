# anp-oil-gas-dw

**Português** | [English](README.en.md)

## O que é este projeto

Um **pipeline de BI reutilizável** sobre os dados públicos da ANP:

```
arquivos baixados da ANP → ETL 1 → stage (st_anp) → ETL 2 → Data Warehouse (dw_anp) → painel web (Streamlit)
```

O pipeline é sempre o mesmo. O que muda são os dados: qualquer pessoa pode
baixar arquivos novos no site da ANP, salvá-los em `data/raw/anp/`, rodar o
pipeline e ver os dados novos no dashboard. O passo a passo está em
[Como atualizar os dados](#como-atualizar-os-dados-extração-manual).

## Começo rápido

Para reproduzir tudo a partir dos dados publicados pela ANP (comandos do Windows; em
Linux ou macOS, troque `.venv/Scripts/` por `.venv/bin/` e `copy` por `cp`):

1. Instale o **PostgreSQL 17** e o **Python 3.11** ou mais novo.
2. Crie o ambiente e copie o modelo de configuração. Depois, preencha a senha do
   PostgreSQL (`PGPASSWORD`) no `.env`:

```sh
py -3 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
copy .env.exemplo .env
```

3. Crie os bancos e as tabelas:

```sh
psql -U postgres -d postgres -f database/criar_bancos.sql
psql -U postgres -d st_anp -f database/st/criar_tabelas.sql
psql -U postgres -d dw_anp -f database/dw/dim_data.sql
psql -U postgres -d dw_anp -f database/dw/criar_tabelas.sql
```

4. Carregue a stage, de um dos dois jeitos:
   - pelos **16 CSVs da base origem**, anexados às Releases (seção
     [Base origem](#base-origem-as-16-tabelas-da-stage-em-csv)), sem baixar os
     arquivos da ANP;
   - pelos **arquivos brutos da ANP** (seção
     [Como atualizar os dados](#como-atualizar-os-dados-extração-manual)).
5. Rode o pipeline (ETL 1 → ETL 2 → validação) e abra o painel em
   <http://localhost:8765>:

```sh
.venv/Scripts/python pipeline.py
.venv/Scripts/python -m painel_web
```

## Perguntas que o painel responde

Cada pergunta tem os seus dados no Data Warehouse e uma tela no painel. Os códigos
(RQ-01 a RQ-09) aparecem no código, nos testes e nos títulos das telas.

| Código | Pergunta | Tela |
| --- | --- | --- |
| RQ-01 | Como evolui a produção de cada campo (óleo, condensado, gás e água), mês a mês e ano a ano, desde 2005? | Ficha do campo |
| RQ-02 | Qual o declínio anual da produção de petróleo e de gás do campo, comparado ao da sua bacia? | Ficha do campo e Campos candidatos |
| RQ-03 | Quão maduro está o campo (BSW e RGO)? | Ficha do campo e Campos candidatos |
| RQ-04 | Quantos poços produzem e quais estão parados, com quanto produziam antes de parar? | Ficha do campo |
| RQ-05 | Qual a receita estimada do campo (produção × preço do petróleo publicado pela ANP)? | Ficha do campo |
| RQ-06 | Quem opera cada campo (operadora, grupo econômico e país) e quem são os prováveis vendedores? | Vendedores e sócios |
| RQ-07 | Os campos melhoraram depois da troca de operador (venda ou reorganização no mesmo grupo)? | Trocas de operador |
| RQ-08 | Quem são os sócios de cada contrato, com o percentual de cada um? | Vendedores e sócios |
| RQ-09 | Quais campos merecem atenção, comparados lado a lado e no mapa dos contornos? | Campos candidatos |

## Base origem: as 16 tabelas da stage em CSV

Para **facilitar a revisão e a auditoria**, a stage também é publicada já pronta,
como **16 arquivos CSV, um por tabela**, mais um `manifesto.csv`. Assim, dá
para recriar o banco transacional direto, sem baixar os ~110 MB de arquivos
brutos da ANP e sem rodar o ETL 1.

**De onde vêm os 16 CSVs:** eles **não substituem os arquivos da ANP**. São
gerados **a partir deles**: os 375 arquivos brutos (zips, CSVs e o CSV extraído
dos PDFs de 2005–2008) foram carregados na stage pelo ETL 1, e cada uma das 16
tabelas resultantes foi exportada para um CSV.

```
378 arquivos da ANP → ETL 1 → st_anp (16 tabelas) → exportação → 16 CSVs + manifesto.csv
```

- **Conteúdo:** as tabelas exatamente como o ETL 1 as gravou, com os mesmos IDs.
  É uma **carga estrutural**: os dados da ANP são só reorganizados nas tabelas,
  sem nenhuma correção. Duplicatas, nomes antigos de campos e unidades ficam
  como a ANP publicou. As correções são feitas no ETL 2 e registradas, com a
  justificativa, em [`docs/etl/tratamentos.md`](docs/etl/tratamentos.md).
- **Rastreabilidade:** cada linha aponta para a sua carga (`id_carga`), e a
  tabela `carga` traz o nome e o SHA-256 do arquivo bruto de onde ela veio. Os
  links de download de cada fonte estão na seção [Dados](#dados).
- **Onde fica:** como anexo das **Releases** deste repositório no GitHub.
- **Continua atualizável:** a stage recriada pelos CSVs aceita cargas novas do
  ETL 1 normalmente. Arquivos já carregados são reconhecidos pelo hash e
  ignorados, revisões da ANP entram como nova versão e os IDs novos continuam a
  numeração.

**Recriar a stage a partir dos 16 CSVs**

```sh
psql -U postgres -d postgres -f database/criar_bancos.sql
psql -U postgres -d st_anp -f database/st/criar_tabelas.sql
cd <pasta dos 16 CSVs>
psql -U postgres -d st_anp -f <projeto>/database/st/carregar_base.sql
```

**Auditar o ETL 1 (conferir que os brutos geram exatamente esses CSVs)**

Com os brutos em `data/raw/anp/` e `data/interim/anp/`, crie um banco vazio,
aplique `database/st/criar_tabelas.sql`, rode o ETL 1 nele e confira o
resultado contra o manifesto:

```sh
.venv/Scripts/python -m etl.python.etl1 --ate 2026-10-17 --banco <banco_vazio>
.venv/Scripts/python -m etl.python.etl1.exportar <pasta dos 16 CSVs> --conferir --banco <banco_vazio>
```

A conferência compara, tabela por tabela, a quantidade de linhas e um SHA-256 do
conteúdo, que ignora só o horário de cada carga (`carga.data_hora_carga`). Se
todas as tabelas baterem, o ETL 1 gerou exatamente a base publicada.

**Gerar os 16 CSVs de novo** (depois de uma carga nova do ETL 1):

```sh
.venv/Scripts/python -m etl.python.etl1.exportar dist/base-origem
```

## Testes automatizados

Os testes ficam em `tests/` e usam o **pytest**. A configuração está no
`pyproject.toml`. Cada teste diz qual premissa do projeto ele verifica.

```sh
.venv/Scripts/python -m pytest                 # todos, menos a auditoria completa (~1 min)
.venv/Scripts/python -m pytest -m unidade      # só as funções isoladas (segundos)
.venv/Scripts/python -m pytest -m lento        # auditoria completa com todos os brutos (~10 min)
```

| Grupo | O que verifica | Precisa de |
| --- | --- | --- |
| `unidade` | conversões (decimais, `%`, códigos de erro do Excel, datas seriais, espaços), os 5 layouts de produção, codificações, origem terra/mar/pré-sal, ordem dos arquivos | só as amostras de `tests/dados/amostras/` |
| `integracao` | DDL da stage (16 tabelas, PKs e FKs); ETL 1 sobre as amostras: arquivo repetido, mês publicado duas vezes, revisão da ANP como versão nova, erro desfeito por inteiro, grafia exata, determinismo; base origem (exportar → `carregar_base.sql` → conferir) e carga nova sobre a stage recriada; `dim_data`; ETL 2 e o pipeline completo | PostgreSQL. Os testes criam e apagam bancos temporários `st_teste_pytest_*` e não alteram a stage oficial |
| `dados` | a stage e o DW batem com os números documentados e com a base origem publicada; preços mínimo e de referência; as telas do painel batem com o DW; o PDI reproduz o ETL 2 | `st_anp` e `dw_anp` carregados (pulados se não existirem) |
| `lento` | o ETL 1 sobre todos os brutos gera exatamente a base origem; a stage recriada pelos CSVs aceita a amostra da CDP (34 versões novas) | brutos em `data/raw/anp/` e `dist/base-origem/` |
| `regras` | nenhuma senha versionada; arquivos locais fora do git; tratamentos e fontes documentados; os dois READMEs sincronizados | git |

**Amostras:** `tests/dados/amostras/` guarda trechos dos arquivos reais da ANP
(o cabeçalho original e as primeiras linhas de cada layout, na codificação
original). Assim, os testes de unidade e de integração rodam em segundos, sem os
brutos.

## Diagramas

As figuras de `docs/modelagem/` (o modelo relacional da stage, em pé de galinha,
o modelo dimensional com as duas estrelas e o croqui do processo de BI) são
geradas por `tools/diagramas/`. Os dois diagramas de tabelas são desenhados a
partir do **catálogo dos bancos** do `.env` (colunas, tipos, chaves e
relacionamentos), então ficam sempre iguais ao DDL. Depois de mudar uma tabela,
gere as figuras de novo:

```sh
.venv/Scripts/python tools/diagramas/gerar.py
```

## Painel web (Streamlit)

O dashboard é um **painel web em Python** (`painel_web/`), com 4 telas, lendo
somente o Data Warehouse. Não exige licença nem Windows: abre no navegador.

```sh
.venv/Scripts/python -m painel_web
```

O painel abre em <http://localhost:8765>. As telas são **Campos candidatos**
(comparação dos campos e mapa dos contornos), **Ficha do campo** (produção,
declínio, BSW, RGO, poços, receita, mapa e sócios), **Vendedores e sócios** e
**Trocas de operador**. Os filtros de região, estado, ano e meses de poço
parado valem para todas as telas, e o glossário de siglas e unidades fica na
barra lateral. O botão **🌐 PT | EN**, no topo da barra lateral, troca o idioma do
painel (textos, legendas e formato dos números); os nomes publicados pela ANP não
são traduzidos. O idioma vai junto no link: <http://localhost:8765/?lang=en>.

## Como atualizar os dados (extração manual)

O pipeline é sempre o mesmo. O que muda são os dados carregados. A ANP não tem
API, então a extração é **manual**. Siga os passos abaixo sempre que quiser
trazer dados novos.

**Regras gerais:**
- salve cada download em `data/raw/anp/<fonte>/AAAA-MM-DD/`, usando a **data do
  dia do download**;
- **não renomeie, não edite e não apague** arquivos, inclusive os de downloads
  anteriores;
- baixar de novo algo que já foi carregado não causa problema. O pipeline ignora
  arquivos idênticos e só cria versão nova para as linhas que mudaram de verdade.

### Passo 1: produção por poço (todo mês)

A produção de um mês é publicada **cerca de dois meses depois**. Exemplo: a de
janeiro sai em março.

1. Abra a
   [Consulta de Dados Públicos — Produção por Poço](https://cdp.anp.gov.br/ords/r/cdp_apex/consulta-dados-publicos-cdp/consulta-produ%C3%A7%C3%A3o-por-po%C3%A7o).
2. Para **cada mês novo**, faça **três exportações**, uma para cada ambiente:
   **Terra**, **Mar** e **Pré-Sal**.
   1. Escolha o **mês/ano** e o **ambiente**.
   2. Rode a consulta.
   3. Clique em **"Exportar p/ csv"**. Se o botão não aparecer, ele fica no
      **menu de ações** da tabela de resultados.
3. Salve os arquivos, com o nome que o site der (ex.:
   `2024_01_producao_Terra.csv`), em
   `data/raw/anp/producao-por-poco-cdp/AAAA-MM-DD/`.

### Passo 2: relação de concessionários e país de origem (a cada atualização)

São uma foto das sociedades vigentes no dia do download. Baixar a cada
atualização faz o histórico de participação se acumular ao longo do tempo.

1. Baixe os dois arquivos da página
   [Relação de concessionários](https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/relacao-de-concessionarios):
   - [`relacao-concessionarios.csv`](https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/rc/relacao-concessionarios.csv)
   - [`relacao-pais-origem-concessionarios.csv`](https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/rc/relacao-pais-origem-concessionarios.csv)
2. Salve em `data/raw/anp/concessionarios/AAAA-MM-DD/`.

### Passo 3: preço de referência do petróleo (quando houver ano novo)

1. Abra a página
   [Participações governamentais](https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/participacoes-governamentais)
   e localize **"Preço de referência do petróleo"**.
2. Baixe o CSV de cada ano que ainda não foi carregado e também o do ano
   corrente, que a ANP atualiza durante o ano. O nome do arquivo muda de padrão
   entre anos (ex.: `precorefpetro_2019.csv`, `preco-referencia-petroleo-2023.csv`),
   então confira na página.
3. Salve em `data/raw/anp/preco-referencia-petroleo/AAAA-MM-DD/`.

### Passo 3a: coordenadas dos poços e dos campos (a cada atualização)

A ANP atualiza as camadas georreferenciadas todo mês. Cada link abaixo baixa o
arquivo direto, sem passar por uma página.

1. Baixe os dois arquivos:
   - poços: [`POCOS_SIRGAS.csv`](https://gishub.anp.gov.br/geoserver/BD_ANP/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=BD_ANP:POCOS_SIRGAS&maxFeatures=40000&outputFormat=csv)
   - contornos dos campos: [`CAMPOS_PRODUCAO_SIRGAS.csv`](https://gishub.anp.gov.br/geoserver/BD_ANP/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=BD_ANP:CAMPOS_PRODUCAO_SIRGAS&outputFormat=csv)
2. Salve em `data/raw/anp/pocos-georreferenciados/AAAA-MM-DD/` e
   `data/raw/anp/campos-georreferenciados/AAAA-MM-DD/`, com o nome original.
3. **Atenção:** o link dos poços tem o limite `maxFeatures=40000`. Em 17/10/2026
   eram 31.323 poços. Se o arquivo vier com exatamente 40.000 linhas, aumente o
   número no link e baixe de novo.

### Passo 4: rodar o pipeline

Um único comando roda as etapas em sequência: ETL 1 → ETL 2 → validação. Uma
etapa com erro interrompe as seguintes, e o DW só muda quando o ETL 2 termina
(uma transação só). O resumo de cada execução vai para `logs/pipeline.log`
(fora do git).

```sh
.venv/Scripts/python pipeline.py                    # arquivos novos da ANP -> stage -> DW -> validação
.venv/Scripts/python pipeline.py --exportar-base    # ... e gera de novo os CSVs da base origem
.venv/Scripts/python pipeline.py --ate 2026-10-17   # só as pastas de download até essa data
pipeline.bat                                        # o mesmo, com duplo clique no Windows
```

O motor vem de `MOTOR_PRINCIPAL` no `.env` (ou `--motor python|pdi`); o
pipeline roda o motor em Python. O ETL 2 no Pentaho PDI roda pelo Spoon ou pelo
Kitchen (item 3 abaixo). Não há agendamento: a extração da ANP é
manual (Passos 1 a 3a), então o pipeline roda depois de cada download. Quem
quiser agendar pode chamar o `pipeline.bat` pelo Agendador de Tarefas do Windows.

As etapas também podem ser rodadas separadamente:

1. **ETL 1 (carga do transacional):** registra cada arquivo na tabela `carga`,
   ignora arquivos repetidos e grava as linhas novas ou alteradas como novas
   versões. Funciona tanto sobre a stage montada pelos brutos quanto sobre a
   recriada pelos 16 CSVs da base origem:

   ```sh
   .venv/Scripts/python -m etl.python.etl1            # carrega tudo o que ainda não foi carregado
   .venv/Scripts/python -m etl.python.etl1 --listar   # só mostra os arquivos e a ordem, sem gravar
   ```

2. **ETL 2 (transacional → Data Warehouse):** aplica os tratamentos
   (`docs/etl/tratamentos.md`), carrega as dimensões com histórico (SCD2) e
   recarrega as duas tabelas fato. Depois, a validação confere o DW contra a
   stage:

   ```sh
   .venv/Scripts/python -m etl.python.etl2              # stage -> DW (cerca de 4,5 min)
   .venv/Scripts/python -m etl.python.etl2.validacao    # grão, somas e listas de-para
   ```

   O DW é criado uma vez com `database/dw/dim_data.sql` e
   `database/dw/criar_tabelas.sql`. As listas de-para revisadas (empresas,
   campos e grupos econômicos) ficam em `etl/python/etl2/de_para/`.

3. **ETL 2 no Pentaho PDI (motor alternativo):** o mesmo ETL 2, em
   transformações do PDI 9.4 orquestradas por um Job, gravando no DW gêmeo
   `dw_anp_pdi`. Cada etapa e cada consulta estão explicadas em
   `etl/pdi/README.md`. A conferência compara os dois Data Warehouses pelas
   chaves naturais, tabela a tabela:

   ```sh
   C:\Pentaho\data-integration\Kitchen.bat /file:etl\pdi\jobs\job_etl2.kjb /level:Basic
   .venv/Scripts/python -m etl.comparacao.comparar      # DW do Python x DW do PDI
   ```

### Passo 5: atualizar o dashboard

O painel web guarda as consultas ao DW em cache por uma hora. Depois de rodar o
pipeline, feche e abra o painel de novo (`python -m painel_web`) para ver os dados
novos na hora.

### Fora da extração recorrente

- **Preço mínimo do petróleo:** a série terminou em 2017 e não recebe dados
  novos.
- **PDFs de preço mínimo de 2005–2008:** a extração foi feita uma única vez (ver
  [Dados derivados](#dados-derivados)).
- **Produção por poço de 2005–2023:** já está nos arquivos da carga inicial. A
  CDP só cobre de 01/2023 em diante.

## Dados

Os dados brutos ficam em `data/raw/`, que **não é versionado** (está no `.gitignore`).

**Organização:** cada download vai para uma subpasta com a **data do download**,
`data/raw/anp/<fonte>/AAAA-MM-DD/`, mantendo o nome original do arquivo. A ANP
republica arquivos com o mesmo nome. Separar por data garante que nenhum arquivo
bruto seja sobrescrito.

Fonte de todos os dados: **ANP — Agência Nacional do Petróleo, Gás Natural e Biocombustíveis**
(dados abertos). A carga inicial foi baixada em 30/09/2026, na subpasta `2026-09-30/`.
Para baixar dados novos, siga a seção [Como atualizar os dados](#como-atualizar-os-dados-extração-manual).

### Produção de petróleo e gás natural por poço

- **Página:** <https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/producao-de-petroleo-e-gas-natural-por-poco>
- **Metadados:** <https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/arquivos-producao-de-petroleo-e-gas-natural-por-poco/metadados-dados-producao-poco.pdf>
- **Período baixado:** 01/2005 a 12/2023 (52 arquivos `.zip`, ~92 MB)
- **Pasta local:** `data/raw/anp/producao-por-poco/2026-09-30/`

Os arquivos seguem a base
`https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/arquivos-producao-de-petroleo-e-gas-natural-por-poco/`,
acrescida do nome do arquivo:

| Período | Arquivos | Nome local |
| --- | --- | --- |
| 2005–2020 (anual) | `producao-por-poco-AAAA.zip` | igual ao original |
| 2021 (mensal) | `2021_MM_producao.zip` (jan–jul) e `2021-MM-producao.zip` (ago–dez) | igual ao original |
| 2022 (mensal) | `2022/producao-2022-MM.zip` (maio, nov e dez: `2022/2022_MM_producao.zip`) | `/` trocada por `_` |
| 2023 (mensal) | `2023/producao-MM.zip` | `/` trocada por `_` |

A partir de 2024, a ANP não publica mais arquivos para download. Os dados ficam
disponíveis só pela
[Consulta de Dados Públicos — Produção por Poço](https://cdp.anp.gov.br/ords/r/cdp_apex/consulta-dados-publicos-cdp/consulta-produ%C3%A7%C3%A3o-por-po%C3%A7o)
(CDP), que cobre de 01/2023 em diante.

- **Pasta local:** `data/raw/anp/producao-por-poco-cdp/AAAA-MM-DD/`.
- **Formato:** o CSV exportado tem o mesmo layout dos arquivos mensais de
  2021–2023: 48 colunas, ISO-8859-1, separador `;`, nome
  `AAAA_MM_producao_<Ambiente>.csv`.
- **Diferença:** a coluna "Data de atualização" traz a data da exportação.
- **Amostra:** 12/2023 (terra), exportada em 01/10/2026, em
  `producao-por-poco-cdp/2026-10-01/`.

### Relação de concessionários

- **Página:** <https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/relacao-de-concessionarios>
- **Pasta local:** `data/raw/anp/concessionarios/2026-09-30/`

| Arquivo | Link |
| --- | --- |
| `relacao-concessionarios.csv` | <https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/rc/relacao-concessionarios.csv> |
| `relacao-pais-origem-concessionarios.csv` | <https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/rc/relacao-pais-origem-concessionarios.csv> |

Os dois arquivos são uma fotografia dos contratos **vigentes** na data do download,
sem histórico.

### Preço de referência do petróleo

- **Página:** <https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/participacoes-governamentais>
- **Período baixado:** 2018 a 2023. A série de preço de referência começa em 2018.
- **Pasta local:** `data/raw/anp/preco-referencia-petroleo/2026-09-30/`

Os arquivos seguem a base
`https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/pg/preco-referencia-petroleo/`,
acrescida do nome do arquivo:

| Ano | Arquivo |
| --- | --- |
| 2018 | `precorefpetro_2018.csv` |
| 2019 | `precorefpetro_2019.csv` |
| 2020 | `precoref-petro-2020-1.csv` |
| 2021–2023 | `preco-referencia-petroleo-AAAA.csv` |

### Preço mínimo do petróleo

É o antecessor do preço de referência. Usava outra metodologia e foi extinto pela
Resolução ANP nº 703/2017.

- **Página:** <https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/participacoes-governamentais>
- **Período baixado:** 2009 a 2017. Não há arquivo de dados para 2005–2008; nesses
  anos, a ANP publicou só PDFs mensais em
  <https://www.gov.br/anp/pt-br/assuntos/royalties-e-outras-participacoes/preco-minimo-do-petroleo>.
- **Pasta local:** `data/raw/anp/preco-minimo-petroleo/2026-09-30/`

Arquivos: `precominpetro_AAAA.csv`, na base
`https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/pg/preco-minimo-petroleo/`.

#### 2005 a 2008: PDFs mensais

- **Pasta local:** `data/raw/anp/preco-minimo-petroleo/2026-09-30/pdf/` (52 PDFs)

Os arquivos seguem a base
`https://www.gov.br/anp/pt-br/assuntos/royalties-e-outras-participacoes/arq-royalties/arquivos-preco-minimo-petroleo/pmp-mes-ano/`,
acrescida do nome do arquivo:

| Período | Arquivo |
| --- | --- |
| 2005 | `2005/preco-minimo-2005MM.pdf`. **Julho de 2005 não foi publicado.** |
| 2006–2007 | `AAAA/AAAAMM-preco-minimo.pdf` |
| 2008 | `2008/preco-minimo-<mês>-2008.pdf` (`jan`, `fev`, `mar`, ..., `dez`) |
| Revisões | `revisao/revisao_anexos_ii_iii_2005.pdf`, `revisao/revisao-2006.pdf`, `revisao/revisao-2007.pdf`, `revisao/revisao-2008.pdf` e `revisao/revisao-complementar-2008.pdf` |

As revisões **não alteram preços**. São despachos da ANP que atualizam a lista de
tipos de petróleo (correntes) e a associação campo → corrente, a partir de um mês.

### Coordenadas dos poços e contornos dos campos

Camadas georreferenciadas da ANP, servidas pelo GeoServer da ANP (WFS) e
atualizadas mensalmente, segundo os metadados (Superintendência de Dados
Técnicos). O projeto carrega só o nome e a geometria (texto WKT, SIRGAS 2000).

| Arquivo | Conteúdo | Link direto |
| --- | --- | --- |
| `POCOS_SIRGAS.csv` | um ponto por poço (31.323 poços em 17/10/2026) | [download](https://gishub.anp.gov.br/geoserver/BD_ANP/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=BD_ANP:POCOS_SIRGAS&maxFeatures=40000&outputFormat=csv) |
| `CAMPOS_PRODUCAO_SIRGAS.csv` | o contorno (polígono) de cada campo de produção (429 campos) | [download](https://gishub.anp.gov.br/geoserver/BD_ANP/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=BD_ANP:CAMPOS_PRODUCAO_SIRGAS&outputFormat=csv) |

- **Metadados:** [poços](https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/arquivos-dados-georreferenciados-das-bacias-sedimentares-brasileiras/metadados-cgu-shapefile-pocos.pdf/@@download/file)
  e [campos](https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/arquivos-dados-georreferenciados-das-bacias-sedimentares-brasileiras/metadados-shapefile-campos-de-producao.pdf/@@download/file).
- **Pastas locais:** `data/raw/anp/pocos-georreferenciados/2026-10-17/` e
  `data/raw/anp/campos-georreferenciados/2026-10-17/`.

### Divisão regional do Brasil (IBGE)

A sigla e a região de cada estado vêm de uma tabela fixa no código do ETL 1
(`etl/python/etl1/cadastros.py`), conforme a
[Divisão Regional do Brasil do IBGE](https://www.ibge.gov.br/geociencias/organizacao-do-territorio/divisao-regional/15778-divisoes-regionais-do-brasil.html). Não há arquivo a baixar.

## Dados derivados

Os dados derivados ficam em `data/interim/`, que também está **fora do git**. São
arquivos gerados por nós a partir dos dados brutos.

### `data/interim/anp/preco-minimo-petroleo-2005-2008.csv`

Contém os preços mínimos de 2005 a 2008, extraídos dos 47 PDFs mensais: 12.753
linhas, de 01/2005 a 12/2008, sem julho de 2005.

Colunas, separadas por `;` e em UTF-8:
- `periodo`
- `n_linha_pdf`
- `contrato`
- `campo`
- `corrente`
- `preco_rs_m3`
- `observacao`

**Método de extração:**

1. Cada PDF foi convertido para Markdown com o
   [markitdown](https://github.com/microsoft/markitdown):
   `.venv/Scripts/markitdown <pdf> -o <md>`.
2. As tabelas saem com formatação irregular. Cada linha da tabela foi
   reconhecida pelo padrão `nº da linha, contrato, campo, corrente, preço`,
   com as seguintes variações tratadas:
   - pipes de tabela e linhas separadoras `---`;
   - número da linha isolado numa linha própria;
   - colunas separadas por um único espaço, caso em que a corrente foi
     separada do nome do campo usando a lista de correntes conhecidas;
   - preços acima de 1.000 sem separador de milhar;
   - contratos em cinco formatos: `48000.003629/97-43`, `48610.07984/2004`,
     `48610009229/2002`, `480000038359735` e `48610.010735/2001-IBU`.
3. **Validação:** em cada mês, a numeração das linhas deve ser contínua de 1 a
   N. Sobraram 3 lacunas, linhas que não aparecem na saída do markitdown:
   - 07/2008: linhas 62 e 78. A linha 78 era "CORREGO CEDRO SUL (retirar)" em
     06/2008, então provavelmente foi retirada da lista;
   - 12/2008: linha 284.
4. **Nomes quebrados em duas linhas no PDF:**
   - 10 nomes foram recuperados pelo contrato, quando o contrato aponta para um
     único campo nos outros meses; a coluna `observacao` marca esses casos;
   - 41 linhas sem nome de campo recuperável foram **descartadas**.
5. **101 linhas não têm corrente.** A coluna já vem vazia no PDF (ex.:
   "BT-REC-10 LAGOA DO PAULO").

## Licença

O código e a documentação estão sob a [licença MIT](LICENSE). Duas exceções:

- os **dados da ANP**, e a base origem gerada a partir deles, seguem os termos de uso
  dos dados abertos da ANP;
- o script de calendário `database/dw/dim_data.sql` é adaptado de um script de
  terceiros, com o crédito ao autor original no próprio arquivo.
