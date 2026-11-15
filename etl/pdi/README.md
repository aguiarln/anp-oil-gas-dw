# ETL 2 no Pentaho Data Integration (PDI)

O PDI reproduz o **ETL 2** (stage → Data Warehouse) do motor principal em Python,
gravando no **Data Warehouse gêmeo `dw_anp_pdi`**, criado com os mesmos
scripts do DW oficial (`database/dw/`). O script `etl/comparacao/comparar.py`
compara os dois bancos e confirma que o resultado é o mesmo. O ETL 1 (arquivos da
ANP → stage) roda em Python.

Este documento explica **cada etapa e cada consulta SQL** do PDI, para que a
carga possa ser auditada sem ler o código. Os tratamentos citados (T01, T02...)
estão descritos, com a evidência nos dados, em `docs/etl/tratamentos.md`. Os
números entre parênteses são os da carga atual (01/2005 a 12/2023).

## Sumário

1. [Visão geral](#1-visão-geral)
2. [Como rodar](#2-como-rodar)
3. [O Job: job_etl2.kjb](#3-o-job-job_etl2kjb)
4. [Área de trabalho e funções de regra](#4-área-de-trabalho-e-funções-de-regra-00_area_de_trabalhosql)
5. [tr_01_extracao](#5-tr_01_extracao-da-stage-para-a-área-de-trabalho)
6. [tr_02_de_para](#6-tr_02_de_para-listas-revisadas)
7. [tr_03_dim_empresa](#7-tr_03_dim_empresa)
8. [tr_04_dim_contrato](#8-tr_04_dim_contrato)
9. [tr_05_dim_campo](#9-tr_05_dim_campo)
10. [tr_06_dim_poco](#10-tr_06_dim_poco)
11. [tr_07_dim_instalacao](#11-tr_07_dim_instalacao)
12. [tr_08_dim_corrente](#12-tr_08_dim_corrente)
13. [tr_09_ft_producao](#13-tr_09_ft_producao)
14. [tr_10_ft_participacao](#14-tr_10_ft_participacao)
15. [Como auditar](#15-como-auditar)
16. [Detalhes técnicos](#16-detalhes-técnicos)

---

## 1. Visão geral

```
stage (st_anp)                      DW gêmeo (dw_anp_pdi)
┌────────────────────┐   tr_01_extracao    ┌──────────────────────────────┐
│ 16 tabelas, dado   │ ──────────────────> │ schema trab (área de trabalho)│
│ bruto e versionado │                     │  + listas de-para (tr_02)     │
└────────────────────┘                     └──────────────┬───────────────┘
                                                          │ tr_03 a tr_08 (SCD2)
                                                          v
                                           ┌──────────────────────────────┐
                                           │ 6 dimensões + etl_depara      │
                                           └──────────────┬───────────────┘
                                                          │ tr_09 e tr_10
                                                          v
                                           ┌──────────────────────────────┐
                                           │ ft_producao e ft_participacao │
                                           └──────────────────────────────┘
```

**Divisão de trabalho entre o PDI e o SQL.** Cada transformação tem dois tipos de
passo:

- **Table input** (entrada de tabela): uma consulta SQL que lê os dados e aplica as
  regras do tratamento. As regras ficam no banco porque são operações sobre
  milhões de linhas (filtros, agrupamentos e junções), que o PostgreSQL resolve em
  segundos; e porque são as mesmas regras do ETL em Python, o que garante o mesmo
  resultado nos dois motores;
- **passos do PDI** que gravam: **Table output** (cópia e fatos), **Dimension
  lookup/update** (SCD2 das dimensões) e **Insert/Update** (dimensão de corrente).
  É o PDI que decide, linha a linha, se uma chave natural é nova, se mudou (nova
  versão) ou se continua igual.

O **Job** orquestra a ordem, e uma etapa com erro interrompe as seguintes.

| Arquivo | O que faz |
| --- | --- |
| `jobs/job_etl2.kjb` | Job que executa tudo, na ordem |
| `sql/00_area_de_trabalho.sql` | Recria a área de trabalho (`trab`) e as funções de regra |
| `etl2/tr_01_extracao.ktr` | Copia a stage para a área de trabalho (13 leituras) |
| `etl2/tr_02_de_para.ktr` | Lê as 3 listas de-para (CSV) |
| `etl2/tr_03_dim_empresa.ktr` a `tr_07_dim_instalacao.ktr` | Uma dimensão cada, com SCD2 e o controle `etl_depara` |
| `etl2/tr_08_dim_corrente.ktr` | Dimensão de corrente (uma versão por período de carga) |
| `etl2/tr_09_ft_producao.ktr` | Fato de produção |
| `etl2/tr_10_ft_participacao.ktr` | Fato de participação |

---

## 2. Como rodar

1. **Uma vez:** crie o banco `dw_anp_pdi` com `database/dw/dim_data.sql` e
   `database/dw/criar_tabelas.sql` (os mesmos scripts do DW oficial).
2. **Uma vez:** informe a senha do PostgreSQL ao PDI. No Spoon, em
   *Edit → Edit the kettle.properties file*, acrescente a variável `PG_SENHA` com a
   senha e reinicie o Spoon. As conexões dos arquivos usam `localhost:5432`, o
   usuário `postgres` e `${PG_SENHA}`; nenhuma senha fica nos arquivos.
3. Abra `jobs/job_etl2.kjb` no Spoon e clique em **Run**. Pela linha de comando:

   ```sh
   C:\Pentaho\data-integration\Kitchen.bat /file:etl\pdi\jobs\job_etl2.kjb /level:Basic
   ```

   A carga completa leva cerca de 8 minutos (a maior parte na fato de produção).
4. Confira o resultado contra o DW do Python (seção 15):

   ```sh
   .venv/Scripts/python -m etl.comparacao.comparar
   ```

---

## 3. O Job: job_etl2.kjb

| # | Entrada | Tipo | O que faz |
| --- | --- | --- | --- |
| 1 | START | início | Ponto de partida |
| 2 | Área de trabalho | SQL (arquivo) | Executa `sql/00_area_de_trabalho.sql` (seção 4) |
| 3 | Limpa o controle de-para | SQL | `TRUNCATE etl_depara`: o controle é refeito a cada carga |
| 4 | tr_01_extracao | transformação | Seção 5 |
| 5 | tr_02_de_para | transformação | Seção 6 |
| 6 | Estatísticas da área de trabalho | SQL | `ANALYZE` (seção 16) |
| 7 a 12 | tr_03 a tr_08 | transformações | As seis dimensões (seções 7 a 12) |
| 13 | Estatísticas das dimensões | SQL | `ANALYZE` antes das fatos (seção 16) |
| 14 e 15 | tr_09 e tr_10 | transformações | As duas fatos (seções 13 e 14) |
| 16 | Sucesso | fim | Fim sem erro |

As ligações entre as entradas só seguem em caso de sucesso: se uma falhar, o Job
para e as seguintes não rodam. A ordem importa: a dimensão de campo usa a de
empresa (para saber o grupo econômico da operadora), e as fatos usam todas as
dimensões.

---

## 4. Área de trabalho e funções de regra (00_area_de_trabalho.sql)

O script recria, a cada carga, o schema **`trab`** dentro do DW gêmeo. É uma área
de trabalho (*staging area* do Data Warehouse): recebe a cópia da stage, porque o
PostgreSQL não junta tabelas de dois bancos diferentes numa mesma consulta. As
tabelas do Data Warehouse (`dim_`, `ft_`, `etl_depara`) não são tocadas aqui.

**Funções de regra.** As regras que se repetem em várias consultas viraram
funções, equivalentes às de `etl/python/etl2/normalizacao.py`:

| Função | Regra | Exemplo |
| --- | --- | --- |
| `trab.chave(nome)` | Chave de comparação de grafias (T14, T20): tira acentos (decompõe o texto em letra + acento e descarta o que não é ASCII), troca `_` por espaço, deixa um espaço só entre as palavras e põe em maiúsculas | `'Cabiúnas  mistura'` → `'CABIUNAS MISTURA'` |
| `trab.chave_contrato(numero)` | Contrato (T15): só os dígitos e, se o número termina numa letra logo após um dígito, essa letra em maiúscula | `'48000.003552/97-11'` → `'480000035529711'`; `'48610.003886/2000a'` → `'486100038862000A'` |
| `trab.ponto_lat` / `ponto_lon` | Latitude e longitude a partir do texto WKT do poço, com 7 casas | `'POINT (-38.12 -12.5)'` → `-12.5`, `-38.12` |
| `trab.centro(wkt)` | Centro do contorno do campo: centroide do anel externo do polígono, pela fórmula da área com sinal | usado no mapa |

Também cria a tabela fixa do IBGE (`trab.ibge`: sigla e região dos 27 estados) e as
tabelas vazias que as transformações seguintes preenchem.

---

## 5. tr_01_extracao: da stage para a área de trabalho

São 13 pares **Table input** (stage) → **Table output** (`trab`), um por tabela,
que rodam em paralelo. Doze são cópias simples, com no máximo uma junção para
trazer um nome; a de produção aplica três tratamentos.

### 5.1 Produção (trab.cons): T17, T16 e T02

A tabela `producao_mensal` da stage guarda o dado como a ANP publicou, com
repetições. Somar tudo inflaria a produção. A consulta entrega **uma linha por
poço, campo e mês**, o grão da fato:

| Etapa | Linhas |
| --- | --- |
| Linhas na stage (todas as versões) | 2.761.294 |
| − versões antigas (T17) | −476.558 |
| − linhas do pré-sal que repetem o mar (T16) | −21.977 |
| − repetições consolidadas no mesmo arquivo (T02, 5.513 chaves) | |
| **= linhas na área de trabalho (grão da fato)** | **2.257.246** |

```sql
WITH ult AS (
    SELECT * FROM (SELECT pm.*, max(id_carga) OVER (PARTITION BY id_poco, id_campo, periodo, arquivo_origem) AS ultima
                   FROM producao_mensal pm) x
    WHERE id_carga = ultima
)
```

**Bloco 1, `ult`: só a versão mais recente (T17).** Cada arquivo carregado é uma
carga numerada (`id_carga`), e cargas mais novas têm números maiores. A ANP
publicou o mesmo poço no mesmo mês mais de uma vez: num arquivo mensal e num anual
(zips de 2010 a 2015) e numa revisão da Consulta de Dados Públicos (12/2023). A
stage guarda cada versão. A **função de janela** `max(id_carga) OVER (PARTITION BY
...)` calcula, para cada poço, campo, mês e arquivo de origem, o maior número de
carga, sem agrupar as linhas; o `WHERE` mantém só as linhas dessa carga.

```sql
WHERE NOT (arquivo_origem = 'presal' AND EXISTS (
           SELECT 1 FROM ult m WHERE m.arquivo_origem = 'mar'
           AND (m.id_poco, m.id_campo, m.periodo) = (u.id_poco, u.id_campo, u.periodo)))
```

**Bloco 2, filtro do pré-sal (T16).** O arquivo do pré-sal é um subconjunto do
arquivo do mar: as mesmas linhas aparecem nos dois. Se a linha veio do pré-sal e
existe uma do mar para o mesmo poço, campo e mês, a do pré-sal sai. O poço continua
marcado como pré-sal na dimensão (seção 10).

```sql
GROUP BY id_poco, id_campo, periodo
-- max(oleo_bbl_dia), max(...): o maior valor de cada medida
-- (array_agg(id_instalacao ORDER BY id_instalacao IS NULL, horas_producao DESC NULLS LAST))[1]
-- count(*) AS linhas_consolidadas
```

**Bloco 3, consolidação (T02).** Algumas chaves ainda aparecem em mais de uma linha
do mesmo arquivo, em geral com os mesmos volumes e só as horas ou a instalação
diferentes. O `GROUP BY` junta essas linhas numa só:
- **medidas:** o maior valor (`max`). Somar contaria o mesmo óleo duas vezes;
- **instalação e tipo de instalação:** a primeira preenchida, da linha com mais
  horas de produção (`array_agg(... ORDER BY ...)[1]` ordena e pega a primeira);
- **demais chaves (estado, operadora, contrato, caracterização):** o maior valor;
- **`linhas_consolidadas`:** quantas linhas foram juntadas, para auditoria.

### 5.2 As outras doze leituras

| Destino | Linhas | Consulta |
| --- | --- | --- |
| `trab.pocos_presal` | 365 | Poços que aparecem no arquivo do pré-sal: marcam o ambiente "Pré-sal" (T16) |
| `trab.empresa` | 170 | Empresas, com o grupo econômico e o país (junção com `grupo_economico`) |
| `trab.contrato` | 1.801 | Contratos, com o nome da bacia (junção com `bacia`) |
| `trab.campo` | 591 | Campos, com o nome da bacia |
| `trab.poco` | 43.571 | Poços (nome ANP) |
| `trab.estado` | 11 | Estados como aparecem na fonte |
| `trab.instalacao` | 696 | Instalações de destino |
| `trab.caracterizacao` | 1.507 | Análise do óleo de cada corrente e período de carga (grau API e destilados, T19), com o nome da corrente |
| `trab.coordenada_poco` | 31.323 | Coordenada **mais recente** de cada poço (`id_carga = max(id_carga)` do poço) |
| `trab.coordenada_campo` | 429 | Contorno **mais recente** de cada campo, com o nome e a bacia como a camada de mapas escreve (T20) |
| `trab.participacao` | 1.102 | Participação de cada sócia em cada contrato, com o nome do arquivo da carga (que traz a data do download) |
| `trab.preco` | 83.341 | Preço do petróleo: a versão mais recente de cada preço (T17) e sem os 16 preços vazios ou com código de erro do Excel (T11, T18) |

---

## 6. tr_02_de_para: listas revisadas

Três passos **CSV file input** → **Table output**. As listas ficam em
`etl/python/etl2/de_para/` e são as mesmas usadas pelo ETL em Python. Elas tratam
os casos que a normalização das grafias não resolve (T21):

| Lista | Linhas | Para quê |
| --- | --- | --- |
| `empresas.csv` → `trab.dp_empresas` | 11 | Mesma empresa com nomes diferentes (T07). Ex.: "Potiguar" e "Potiguar E&P S.A." |
| `grupos_economicos.csv` → `trab.dp_grupos` | 22 | Grupo econômico das empresas que a ANP publica sem grupo (T23), com a evidência de cada linha |
| `campos.csv` → `trab.dp_campos` | 64 | Renomeações (T04, ex.: LULA → TUPI) e unificações (T05, ex.: BALEIA AZUL → JUBARTE) de campos |

---

## 7. tr_03_dim_empresa

**Passos:** "Regras da dim_empresa" (Table input) → "SCD2 dim_empresa" (Dimension
lookup/update); e "De-para da dim_empresa" (Table input) → `etl_depara` (Table output).

**Resultado:** as 170 grafias da stage viram **158 empresas**.

**Consulta "Regras da dim_empresa", por bloco:**

| Bloco | O que faz |
| --- | --- |
| `uso`, `uso_part` | Conta quantas linhas de produção e de participação cada grafia tem; serve para escolher a grafia de exibição |
| `lista` | Lista de-para de empresas (T07), pela chave normalizada |
| `grupos` | Lista de grupos econômicos (T23) |
| `m` | Cada grafia da stage com a sua chave natural: o destino da lista, se houver; senão, a própria chave normalizada (T14). Ex.: "3R Petroleum" e "3R PETROLEUM" → `3R PETROLEUM` |
| `d` | Uma linha por chave natural. **Nome:** a grafia mais usada (no empate, a primeira em ordem alfabética). **Razão social, grupo e país:** o primeiro valor preenchido, na ordem da grafia mais usada |
| `SELECT` final | Se a ANP não publica o grupo econômico, ele vem da lista (22 empresas); se publica, o da ANP prevalece. Sem informação: `N/A` |

**SCD2 (Dimension lookup/update):** chave natural `nk_empresa`; nome, razão
social, grupo e país marcados como *Insert*: se algum mudar numa carga futura, a
versão vigente é fechada e entra uma versão nova.

**Consulta "De-para da dim_empresa" (T22):** uma linha por grafia da stage, com a
chave natural do DW em que ela entrou (170 linhas). É o que permite auditar que
"3R Petroleum" (id 115) e "3R PETROLEUM" (id 151) viraram a mesma empresa.

---

## 8. tr_04_dim_contrato

**Passos:** iguais aos da empresa (consulta → SCD2; consulta de-para → `etl_depara`).

**Resultado:** os 1.801 números de contrato da stage (três formatos diferentes)
viram **1.003 contratos**. Três números sem nenhum dígito ficam de fora.

**Consulta "Regras da dim_contrato":**
- **chave natural:** `trab.chave_contrato(numero)`, com os dígitos e a letra final
  (T15). Os três formatos `480000037939797`, `48000.003552/97-11` e
  `48610009275200571` passam a casar, e BM-S-11 e BM-S-11A continuam contratos
  diferentes;
- **atributos (nome, rodada, fase, ambiente, bacia):** o primeiro valor preenchido,
  dando preferência aos registros da relação de concessionários (os que têm rodada,
  `ORDER BY rodada IS NULL`), que são os mais completos.

**De-para:** 1.798 linhas (uma por número da stage com dígitos).

---

## 9. tr_05_dim_campo

**Passos:** consulta → SCD2; consulta de-para → `etl_depara`.

**Resultado:** as 530 grafias de campo com produção viram **516 campos**, em 11
estados: 328 no Nordeste, 177 no Sudeste, 9 no Norte e 2 no Sul.

É a consulta mais longa, porque reúne cinco regras. Por bloco:

| Bloco | O que faz |
| --- | --- |
| `uso`, `m` | Campos com produção e a chave de cada grafia: nome + bacia normalizados (T14). O nome sozinho não basta: FAZENDA BELEM existe nas bacias Potiguar e Recôncavo |
| `nomes`, `bacias`, `g` | Uma linha por campo (`kn`, `kb`), com o nome e a bacia de exibição: a grafia mais usada |
| `ev`, `ren`, `suc` | Eventos da lista de-para de campos: renomeações (`ren`) e renomeações + unificações (`suc`) |
| `cad_ren`, `cad_suc` | **Consultas recursivas** (`WITH RECURSIVE`) que seguem a cadeia de eventos até o fim. Ex.: Jandaia Sul → JANDAIA → TANGARÁ |
| `atual`, `sucessor` | O último elo de cada cadeia: o **nome atual** (T04, 14 campos renomeados) e o **campo sucessor** (T05, 64 campos com renomeação ou unificação) |
| `unico`, `cont` | **Contorno** do campo (T20): a camada de mapas escreve nomes e bacias do seu jeito. Casa pelo nome + bacia normalizados ou, se o nome for único entre os campos da produção, só pelo nome. 385 campos têm contorno |
| `op_n`, `op_mes` | **Operadora predominante** de cada campo em cada mês: a empresa (já uniformizada pela `dim_empresa`, via `etl_depara`) com mais linhas de produção no mês |
| `grupo` | Grupo econômico de cada empresa, da versão vigente da `dim_empresa` |
| `seq`, `trocas` | **Trocas de operador** (T23): `lag()` compara a operadora de cada mês com a do mês anterior com produção. Troca = a operadora muda; **venda** = o grupo econômico também muda; **reorganização** = troca dentro do mesmo grupo. Guarda o mês da última de cada tipo: 226 campos com troca, 208 com venda e 90 com reorganização |
| `estados`, `siglas`, `pinfo`, `psuf`, `puf` | **Estado de cada poço** (T13), pela mesma regra da `dim_poco`: o sufixo do nome do poço (`-RN`; no mar, `-RJS`) ou, sem sufixo válido, o estado mais informado nas linhas do poço |
| `uf_n`, `uf` | **Estado do campo**: o estado com mais linhas de produção dos seus poços; no empate, a sigla em ordem alfabética. A região vem da tabela do IBGE |
| `SELECT` final | Junta tudo: nome, nome atual, sucessor, bacia, estado e região, contorno, centro do contorno (`trab.centro`) e as três datas |

**SCD2:** chave `nk_campo` (nome + bacia). Nome, nome atual, sucessor, bacia,
estado, região, contorno e centro marcados como *Insert* (mudança gera versão). As
datas da última troca, venda e reorganização marcadas como *Update*: são
atualizadas na versão vigente, sem gerar versão (SCD tipo 1), porque mudam a cada
mês novo de produção.

**De-para:** 530 linhas, com o nome original no formato "nome (bacia)".

---

## 10. tr_06_dim_poco

**Passos:** consulta → SCD2; consulta de-para → `etl_depara`.

**Resultado:** **30.752 poços** com produção: 27.474 em terra, 2.913 no mar e 365 no
pré-sal; 18.504 com coordenada.

| Bloco | O que faz |
| --- | --- |
| `estados`, `siglas` | Siglas válidas: os estados da stage, completados pela tabela fixa do IBGE |
| `info` | Por poço: o arquivo de origem e o estado mais frequentes (`mode()`), e o **primeiro e o último mês com produção** de petróleo ou gás |
| `sufixo`, `uf` | **Estado** (T13): pelo sufixo do nome ANP do poço (`7-ET-994-RN` → RN; no mar, sigla + S: `3-BRSA-1017D-RJS` → RJ). Se o sufixo não for uma sigla, usa o estado mais frequente da produção. Corrige cadastros contraditórios, como poços que aparecem em dois estados |
| `SELECT` final | Nome e região do estado; **ambiente**: Pré-sal se o poço aparece no arquivo do pré-sal (T16), senão Terra ou Mar pelo arquivo de origem; latitude e longitude da coordenada mais recente |

**SCD2:** chave `nk_poco` (nome ANP). Estado, região, ambiente e coordenadas como
*Insert*; primeiro e último mês de produção como *Update* (SCD tipo 1), porque mudam
a cada mês e são a base dos poços parados no dashboard.

---

## 11. tr_07_dim_instalacao

**Passos:** consulta → SCD2; consulta de-para → `etl_depara`.

**Resultado:** as 694 grafias com produção viram **693 instalações**.

- **bloco `i`:** para cada instalação da stage, quantas linhas de produção ela tem e
  o **tipo de instalação mais recente** (T13c: o tipo muda com o tempo; vale o da
  produção mais recente);
- **`SELECT` final:** agrupa pela chave normalizada (T14); nome = a grafia mais
  usada; tipo = o primeiro preenchido, na ordem da grafia mais usada.

**SCD2:** chave `nk_instalacao`; nome e tipo como *Insert*.

---

## 12. tr_08_dim_corrente

**Passos:** "Regras da dim_corrente" (Table input) → "Versões da dim_corrente"
(**Insert/Update**); consulta de-para → `etl_depara`.

**Resultado:** **104 correntes** de petróleo em **214 versões**.

Esta dimensão não usa o Dimension lookup/update, porque a versão não nasce de uma
mudança percebida na carga: a ANP publica uma análise do óleo por **período de
carga**, e cada período é uma versão (T19). A validade de cada versão vai do seu
período até o período seguinte.

| Bloco | O que faz |
| --- | --- |
| `car` | Caracterizações usadas na produção, com a chave da corrente e quantos campos de análise estão preenchidos |
| `nome` | Nome de exibição: a grafia mais frequente |
| `analise` | Para cada corrente e período, a análise mais completa (mais campos preenchidos). Há cadastros divergentes para a mesma corrente e período (T19) |
| `versoes` | Número da versão (`row_number()` por período) e o período seguinte (`lead()`) |
| `SELECT` final | Validade: a versão 1 vale desde 1900-01-01 (cobre a produção anterior à primeira análise); as demais, desde o seu período; todas até o período seguinte ou 2199-12-31 |

**Insert/Update:** chave composta (`nk_corrente`, `dt_periodo_carga`). Se a
corrente e o período já existem, atualiza os valores; senão, insere.

---

## 13. tr_09_ft_producao

**Passos:** "Produção com chaves e preço" (Table input) → `ft_producao` (Table
output, com *Truncate table*: a fato é recarregada por completo a cada execução).

**Resultado:** **2.257.246 linhas** (poço × campo × mês).

| Bloco | O que faz |
| --- | --- |
| `preco` | Preços com a chave do contrato (`chave_contrato`) e do campo (`chave`) |
| `preco_contrato` | **Preço por contrato + campo + mês** (T11, T18): a média dos preços publicados para essa combinação (pode haver mais de uma corrente) |
| `preco_campo` | **Preço só pelo campo + mês**, quando um único contrato publica preço para aquele campo no mês. Cobre os casos em que o contrato da produção e o do preço não casam |
| `campo`, `contrato`, `poco`, `empresa`, `instalacao`, `corrente` | **Chaves substitutas:** id da stage → chave natural (`etl_depara`) → `sk_` da **versão vigente** da dimensão |
| `SELECT` final | `sk_data` = AAAAMM01 (primeiro dia do mês); **volumes do mês** = média diária publicada × dias do mês (T10), vazios como zero; horas; preço = por contrato, senão pelo campo; **receita estimada** = petróleo (bbl) × 0,158987294928 (m³ por barril) × preço (R$/m³). Dimensões que não se aplicam apontam para a **linha 0** (ex.: produção sem instalação de destino) |

Na carga atual, 28.854 linhas ficam sem preço (ex.: 07/2005, mês que a ANP não
publicou); o preço cobre 99,0% do volume de petróleo.

---

## 14. tr_10_ft_participacao

**Passos:** "Participações por foto" (Table input) → `ft_participacao` (Table
output, recarga completa).

**Resultado:** **1.102 participações** em 883 contratos, numa foto da relação de
concessionários.

- **data da foto:** extraída do caminho do arquivo da carga (a pasta tem a data do
  download, `AAAA-MM-DD`), com `regexp_match`;
- **chaves:** empresa e contrato pela versão vigente das dimensões, via `etl_depara`;
- **agrupamento:** se duas grafias da mesma empresa (T07) aparecem no mesmo
  contrato, a participação é somada;
- **`dd_operador`:** `S` se a empresa é a operadora do contrato naquela foto.

---

## 15. Como auditar

**Conferência completa com o Python.** O script compara os dois Data Warehouses
pelas chaves naturais: cada dimensão atributo por atributo e as fatos linha a linha,
com todas as medidas.

```sh
.venv/Scripts/python -m etl.comparacao.comparar
```

Resultado da carga atual:

```
OK   dim_empresa     Python    158 | PDI    158 | iguais    158 | diferentes 0 | só no PDI 0 | só no Python 0
OK   dim_contrato    Python  1,003 | PDI  1,003 | iguais  1,003 | diferentes 0 | só no PDI 0 | só no Python 0
OK   dim_campo       Python    516 | PDI    516 | iguais    516 | diferentes 0 | só no PDI 0 | só no Python 0
OK   dim_poco        Python 30,752 | PDI 30,752 | iguais 30,752 | diferentes 0 | só no PDI 0 | só no Python 0
OK   dim_instalacao  Python    693 | PDI    693 | iguais    693 | diferentes 0 | só no PDI 0 | só no Python 0
OK   dim_corrente    Python    214 | PDI    214 | iguais    214 | diferentes 0 | só no PDI 0 | só no Python 0
OK   ft_producao     Python 2,257,246 | PDI 2,257,246 | diferentes 0 | só no PDI 0 | só no Python 0
OK   ft_participacao Python     1,102 | PDI     1,102 | diferentes 0 | só no PDI 0 | só no Python 0
Conferência aprovada: o PDI reproduz o ETL 2 em Python.
```

**Consultas para conferir à mão** (no banco `dw_anp_pdi`):

```sql
-- 1. De quais grafias da stage veio uma empresa (T07, T14, T22)
SELECT id_stage, nm_original FROM etl_depara
WHERE nm_dimensao = 'dim_empresa' AND nk_dw = '3R PETROLEUM';

-- 2. Linhas consolidadas na extração (T02): chaves que tinham mais de uma linha
SELECT id_poco, id_campo, periodo, linhas_consolidadas FROM trab.cons
WHERE linhas_consolidadas > 1 LIMIT 10;

-- 3. Um campo renomeado e as suas trocas de operador (T04, T23)
SELECT nm_campo, nm_campo_atual, nm_campo_sucessor, dt_ultima_troca_operador, dt_ultima_venda
FROM dim_campo WHERE nk_campo IN ('LULA|SANTOS', 'ESTREITO|POTIGUAR');

-- 4. Versões de uma corrente (T19)
SELECT nk_corrente, dt_periodo_carga, etl_versao, etl_dt_inicio, etl_dt_fim
FROM dim_corrente WHERE nk_corrente = 'MARLIM' ORDER BY etl_versao;

-- 5. A fato tem as mesmas linhas da extração (nenhuma linha perdida no caminho)
SELECT (SELECT count(*) FROM trab.cons) AS linhas_extraidas, (SELECT count(*) FROM ft_producao) AS linhas_na_fato;
```

---

## 16. Detalhes técnicos

- **Fim da versão vigente.** O Dimension lookup/update marca a versão vigente com
  `etl_dt_fim = 2199-12-31 23:59:59.999` (o último instante do ano máximo
  configurado), e o ETL em Python com `2199-12-31 00:00`. Por isso as consultas pegam
  a versão vigente com `etl_dt_fim >= '2199-12-31'`, que vale para os dois.
- **Estatísticas (`ANALYZE`).** O Job atualiza as estatísticas depois da extração e
  antes das fatos. Sem elas, o PostgreSQL acha que as tabelas recém-carregadas estão
  quase vazias (estimou 578 linhas para a produção, que tem 2,26 milhões) e escolhe
  planos que deixam a fato de produção horas mais lenta.
- **Acento no arquivo SQL.** O PDI lê `00_area_de_trabalho.sql` na codificação do
  sistema operacional, que no Windows não é UTF-8. Por isso o arquivo só usa acentos
  nos comentários, nunca em valores.
- **Recarga.** Rodar o Job de novo não cria versões onde nada mudou: o Dimension
  lookup/update compara cada atributo e só grava quando há diferença.
