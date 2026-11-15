# Modelo dimensional do Data Warehouse (`dw_anp`)

**Aprovado em 18/10/2026.** Diagrama: [`dw_diagrama_estrela.png`](dw_diagrama_estrela.png).
Referências: Kimball e Ross (2013), para o modelo dimensional, os tipos de
métrica e o versionamento das dimensões; Machado (2010), para a arquitetura e
a granularidade do DW.

## Visão geral: duas estrelas (constelação de fatos)

O DW tem **duas tabelas fato**, cada uma no centro do seu **modelo estrela**, que
compartilham as dimensões em comum:

- **`ft_producao`**: a produção de cada poço, em cada campo, em cada mês;
- **`ft_participacao`**: a participação de cada empresa sócia em cada contrato,
  em cada foto da ANP.

As dimensões `dim_data`, `dim_empresa` e `dim_contrato` são **conformadas**: a
mesma tabela, com o mesmo significado, nas duas estrelas. Esse arranjo se chama
**constelação de fatos** (*galaxy schema*). **Não é floco de neve**: nenhuma
dimensão é normalizada em subdimensões. A bacia, o estado, a região
e o grupo econômico ficam **dentro** das dimensões, desnormalizados, como pede o
modelo estrela.

## Por que duas tabelas fato

A participação das sócias e a produção têm **grãos diferentes**:

| Fato | Uma linha é... | Dimensões |
| --- | --- | --- |
| `ft_producao` | um poço, num campo, num mês | data, poço, campo, empresa (operadora), contrato, instalação, corrente |
| `ft_participacao` | uma empresa, num contrato, numa foto da ANP | data (da foto), empresa (sócia), contrato |

Juntar as duas numa fato só não funciona:

1. **Pôr as sócias na `ft_producao`** obrigaria a repetir cada linha de produção
   uma vez por sócia. Num contrato com duas sócias de 50%, a produção do mês
   apareceria **duas vezes**, e toda soma sairia em dobro. Evitar a duplicação
   exigiria ratear a produção pelos percentuais, o que está fora do escopo
   (RQ-08: só os sócios e os percentuais).
2. **Pôr a participação como atributo da `dim_contrato`** não cabe: um contrato
   tem várias sócias (relação N:N), e uma dimensão guarda um valor por linha.
   Seria preciso criar colunas "sócia 1, sócia 2, sócia 3...", sem limite fixo.

A **matriz dimensão-indicador** (seção 2) mostra isso: o percentual de
participação usa só data, empresa e contrato, enquanto os indicadores de
produção usam sete dimensões. Indicadores com dimensões e grãos diferentes vão
para fatos diferentes. As dimensões compartilhadas
permitem cruzar, no painel, "quanto o campo produz" com "quem são os sócios do
contrato" sem duplicar números.

## 1. Pontos cardeais

| | `ft_producao` | `ft_participacao` |
| --- | --- | --- |
| **Quem?** | a empresa operadora no mês (`dim_empresa`) | a empresa sócia (`dim_empresa`) |
| **Quando?** | o mês de produção (`dim_data`) | a data da foto da ANP (`dim_data`) |
| **Onde?** | o poço (estado, região, coordenadas), o campo (bacia, estado, região, contorno) e a instalação | por meio do contrato (bacia) |
| **O quê?** | o tipo de petróleo (`dim_corrente`) e o contrato | o contrato |

## 2. Matriz dimensão-indicador

| Indicador (requisito) | Data | Poço | Campo | Empresa | Contrato | Instalação | Corrente |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| Volumes de óleo, gás e água (RQ-01) | ✓ | ✓ | ✓ | ✓ operadora | ✓ | ✓ | ✓ |
| Declínio, BSW e RGO (RQ-02, RQ-03) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Poços produtores e parados (RQ-04) | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| Preço e receita estimada (RQ-05) | ✓ | ✓ | ✓ | ✓ | ✓ | | ✓ |
| Campos por operadora (RQ-06), trocas de operador (RQ-07) | ✓ | | ✓ | ✓ operadora | ✓ | | |
| **Percentual de participação (RQ-08)** | ✓ foto | | | ✓ **sócia** | ✓ | | |

O painel de campos candidatos (RQ-09) reúne indicadores das duas fatos.

## 3. Grão e medidas

### `ft_producao`

**Grão:** um poço, num campo, num mês, depois dos tratamentos do ETL 2 (T01/T02
duplicatas, T16 pré-sal repetido, T17 versão mais recente).

| Coluna | Tipo de métrica | Descrição |
| --- | --- | --- |
| `sk_data`, `sk_poco`, `sk_campo` | chave (PK composta) | o grão |
| `sk_empresa` | chave estrangeira | a empresa **operadora** no mês |
| `sk_contrato`, `sk_instalacao`, `sk_corrente` | chaves estrangeiras | contrato, instalação de destino, tipo de petróleo |
| `md_oleo_bbl`, `md_condensado_bbl`, `md_petroleo_bbl`, `md_agua_bbl` | aditiva | **volume do mês**, em barris: a média diária da fonte vezes os dias do mês (T10). A média diária não pode ser somada entre meses |
| `md_gas_assoc_mil_m3`, `md_gas_nao_assoc_mil_m3`, `md_gas_total_mil_m3` | aditiva | volume do mês, em mil m³ |
| `md_horas_producao` | aditiva | horas no mês (a média é calculada no painel) |
| `md_preco_rs_m3` | **não aditiva** | preço do petróleo do campo no mês, em R$/m³ (T11, T18) |
| `md_receita_estimada_rs` | derivada (aditiva) | petróleo do mês (m³) × preço, calculada no ETL |

**Calculados no painel, e não guardados:** BSW (água ÷ (petróleo + água)), RGO
(gás associado ÷ óleo), declínio (variação anual), poços produtores (poços com
produção no mês) e médias diárias. São métricas derivadas e **não aditivas**.

**Tipo de preço:** não é coluna na fato (seria dimensão degenerada). Ele é
derivado do mês: até 12/2017, preço mínimo; a partir de 2018, preço de
referência. O marcador da troca de metodologia vem da `dim_data`.

### `ft_participacao`

**Grão:** uma empresa, num contrato, numa foto da relação de concessionários.

| Coluna | Tipo de métrica | Descrição |
| --- | --- | --- |
| `sk_data`, `sk_empresa`, `sk_contrato` | chave (PK composta) | o grão (`sk_data` = data da foto) |
| `md_percentual` | **semiaditiva** | soma 100% num contrato numa data, mas não se soma entre datas |
| `dd_operador` | **dimensão degenerada** | `S` se a empresa é a operadora do contrato naquela foto, `N` se é só sócia. É um atributo da própria participação (a mesma empresa é operadora num contrato e sócia em outro), sem relevância para virar dimensão: o caso típico de dimensão degenerada: um atributo do evento guardado na própria fato |

## 4. Dimensões

Todas têm surrogate key (`sk_`), chave natural (`nk_`) e a **linha 0 (DNQ)**:
textos `N/A`, números `-1`, datas `1900-01-01`.

- **Chave natural (`nk_`):** é a **chave de negócio
  uniformizada** da entidade (ex.: o nome ANP do poço; o contrato com os
  dígitos e a letra final; o nome normalizado da empresa, como `3R PETROLEUM`), e não o id da
  stage. O id da stage (`id_empresa`, `id_poco`...) é a surrogate key do
  transacional, e há uma por grafia: a 3R Petroleum tem dois (115 "3R Petroleum"
  e 151 "3R PETROLEUM"), que o ETL 2 junta numa linha só da `dim_empresa` (T07,
  T14). O nome para exibição fica em `nm_`.
- **Atributo ausente numa entidade real** (ex.: poço sem coordenada, campo sem
  contorno): fica vazio (NULL). O −1 é só da linha 0, para não virar um ponto
  falso no mapa.
- **Surrogate keys** numeradas a partir de 1; a linha 0 fica reservada à DNQ. As dimensões
versionadas usam o mesmo padrão da `dim_data` (`database/dw/dim_data.sql`):
`etl_dt_inicio`, `etl_dt_fim` (`2199-12-31` na versão vigente) e `etl_versao`.

| Dimensão | Colunas | Histórico |
| --- | --- | --- |
| `dim_data` | gerada por script de calendário (`database/dw/dim_data.sql`), de 2005 a 2035; a fato liga pelo 1º dia do mês (`sk_data` = AAAAMM01) | estática |
| `dim_poco` | `nm_poco`; `nm_estado`, `sg_estado`, `nm_regiao`; `nm_ambiente` (terra, mar ou pré-sal); `nr_latitude`, `nr_longitude` (do WKT de `coordenada_poco`); `dt_primeira_producao`, `dt_ultima_producao` | SCD2 (coordenadas); datas de produção em SCD1 |
| `dim_campo` | `nm_campo`; `nm_campo_atual` (T04), `nm_campo_sucessor` (T05); `nm_bacia`; `nm_estado`, `sg_estado`, `nm_regiao` (o estado com mais produção dos poços do campo, T13); `desc_contorno_wkt` (de `coordenada_campo`, T20), `nr_latitude_centro`, `nr_longitude_centro`; `dt_ultima_troca_operador`, `dt_ultima_venda` (T23: a troca em que o grupo econômico muda) e `dt_ultima_reorganizacao` (troca no mesmo grupo) | SCD2; trocas em SCD1 |
| `dim_empresa` | `nm_empresa` (uniformizado, T07 e T14), `nm_razao_social`, `nm_grupo_economico`, `nm_pais` | SCD2 |
| `dim_contrato` | `nr_contrato` (dígitos e letra final, T15), `nm_contrato`, `nm_rodada`, `nm_fase`, `nm_ambiente`, `nm_bacia` | SCD2 |
| `dim_instalacao` | `nm_instalacao`, `nm_tipo_instalacao` (T13) | SCD2 |
| `dim_corrente` | `nm_corrente`; `dt_periodo_carga`; `nr_grau_api`; cortes e percentuais dos destilados leves, médios e pesados. **Só a análise do óleo**: a composição do gás fica fora do DW (T19) | SCD2: uma versão por período de carga |

**Por que `dim_empresa`, e não `dim_operador`:** a mesma dimensão representa a
operadora na `ft_producao` e a sócia na `ft_participacao`.

## 5. Convenções

Nomenclatura padronizada, em minúsculas:
`dim_` dimensão, `ft_` fato, `md_` medida, `sk_` surrogate key, `nk_` natural key,
`nm_` nome, `dt_` data. Também são usados `nr_` (número) e `desc_` (descrição),
como na `dim_data`, e `sg_` (sigla). Dimensão degenerada
(`dd_`): o contrato não é degenerada, porque é a `dim_contrato` (decisão de modelagem); os
demais casos são decididos um a um.

## 6. Rastreabilidade

Cada pergunta que o painel responde (RQ-01 a RQ-09, listadas no README, em "Perguntas que o painel responde")
tem os seus dados neste modelo. O painel de campos candidatos (RQ-09) e o mapa usam os atributos geográficos de
`dim_poco` e `dim_campo`.

## 7. Arquitetura

- **Um Data Warehouse único** (arquitetura global, construção *top-down*): há um só processo de análise, a
  avaliação de campos de produção, e um só modelo, sem Data Marts. Os tratamentos T01–T23 ficam num só ETL.
- **Execução local** (*on-premises*): PostgreSQL 17, com a stage (`st_anp`) e o DW (`dw_anp`) em bancos separados.
  Os dados são públicos e podem ser recarregados a qualquer momento pelo pipeline, a partir dos arquivos brutos da
  ANP ou da base origem em CSV.
- **Três camadas:** servidor de dados (PostgreSQL: `st_anp` e `dw_anp`), processamento (ETL em Python, com o
  Pentaho PDI como alternativa no ETL 2, gravando em `dw_anp_pdi`) e visualização (painel web em Streamlit).

## Referências

- KIMBALL, Ralph; ROSS, Margy. **The data warehouse toolkit**: the definitive guide to
  dimensional modeling. 3. ed. Indianapolis: Wiley, 2013.
- MACHADO, Felipe Nery Rodrigues. **Tecnologia e projeto de data warehouse**: uma visão
  multidimensional. 5. ed. São Paulo: Érica, 2010.
