-- =============================================================================
-- anp-oil-gas-dw - Data Warehouse (dw_anp) - DDL do modelo dimensional
-- PostgreSQL 17. Modelo aprovado em 18/10/2026 (docs/modelagem/modelo_dimensional.md
-- e docs/modelagem/dw_diagrama_estrela.png).
--
-- Duas estrelas (constelação de fatos): ft_producao e ft_participacao, com as
-- dimensões conformadas dim_data, dim_empresa e dim_contrato.
--
-- Convenções: dim_ dimensão, ft_ fato, md_ medida,
-- sk_ surrogate key, nk_ natural key, nm_ nome, dt_ data, dd_ dimensão degenerada;
-- nr_ número e desc_ descrição, como na dim_data; sg_ sigla.
--
-- Chave natural (nk_): a chave de negócio da entidade depois dos tratamentos do
-- ETL 2 (ex.: nome ANP do poço, número do contrato só com dígitos), e não o id da
-- stage, que é uma chave substituta do OLTP e pode juntar várias grafias numa só.
--
-- Versionamento (SCD2): etl_dt_inicio, etl_dt_fim (2199-12-31 na versão
-- vigente) e etl_versao, o mesmo padrão do script dim_data.
--
-- DNQ (dimensão não qualificada): cada dimensão tem a linha 0 (textos 'N/A', char(1) 'N', números -1,
-- datas 1900-01-01). As FKs vazias da stage apontam para ela, e o painel a filtra.
-- O -1 é só da linha 0: atributo que falta numa entidade real (ex.: poço sem coordenada)
-- fica vazio (NULL), para não virar um ponto falso no mapa.
--
-- Ordem de execução, conectado ao banco dw_anp:
--   psql -d dw_anp -f database/dw/dim_data.sql       (calendário)
--   psql -d dw_anp -f database/dw/criar_tabelas.sql  (este arquivo)
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- dim_data: a tabela vem de database/dw/dim_data.sql; aqui só entra a linha 0 (DNQ)
-- -----------------------------------------------------------------------------
INSERT INTO dim_data VALUES
    (0, '1900-01-01', 'N/A', -1, 'N/A', 'N/A', -1, 'N/A', 'N/A', -1, 'N/A', -1, -1, 'N/A', 'N/A', 'N/A', 'N/A',
     '1900-01-01', '2199-12-31', 1)
ON CONFLICT (sk_data) DO NOTHING;

-- -----------------------------------------------------------------------------
-- dim_poco: um poço (estado, região, ambiente, coordenadas)
-- -----------------------------------------------------------------------------
CREATE TABLE dim_poco (
    sk_poco               serial         PRIMARY KEY,
    nk_poco               varchar(40)    NOT NULL,   -- nome ANP do poço
    nm_poco               varchar(40)    NOT NULL,
    nm_estado             varchar(40)    NOT NULL,
    sg_estado             char(2)        NOT NULL,
    nm_regiao             varchar(20)    NOT NULL,
    nm_ambiente           varchar(10)    NOT NULL,   -- Terra, Mar ou Pré-sal
    nr_latitude           numeric(10,7),             -- do WKT de coordenada_poco (SIRGAS 2000); vazia sem coordenada
    nr_longitude          numeric(10,7),
    dt_primeira_producao  date,                      -- SCD1; vazia se o poço só aparece com produção zero
    dt_ultima_producao    date,                      -- SCD1: base dos poços parados (RQ-04)
    etl_dt_inicio         timestamp      NOT NULL,
    etl_dt_fim            timestamp      NOT NULL,
    etl_versao            integer        NOT NULL,
    CONSTRAINT uk_dim_poco_versao UNIQUE (nk_poco, etl_versao)
);
INSERT INTO dim_poco VALUES (0, 'N/A', 'N/A', 'N/A', 'NA', 'N/A', 'N/A', -1, -1, '1900-01-01', '1900-01-01',
                             '1900-01-01', '2199-12-31', 1);

-- -----------------------------------------------------------------------------
-- dim_campo: um campo (nome atual, sucessor, bacia, estado, região, contorno)
-- -----------------------------------------------------------------------------
CREATE TABLE dim_campo (
    sk_campo                  serial         PRIMARY KEY,
    nk_campo                  varchar(150)   NOT NULL,   -- nome normalizado + bacia (T14, T20)
    nm_campo                  varchar(100)   NOT NULL,
    nm_campo_atual            varchar(100)   NOT NULL,   -- renomeações (T04)
    nm_campo_sucessor         varchar(100)   NOT NULL,   -- unificações (T05); o próprio nome se não houver
    nm_bacia                  varchar(60)    NOT NULL,
    nm_estado                 varchar(40)    NOT NULL,   -- estado com mais produção dos poços do campo (T13)
    sg_estado                 char(2)        NOT NULL,
    nm_regiao                 varchar(20)    NOT NULL,   -- grande região do IBGE
    desc_contorno_wkt         text,                      -- de coordenada_campo (T20); vazio sem contorno
    nr_latitude_centro        numeric(10,7),
    nr_longitude_centro       numeric(10,7),
    dt_ultima_troca_operador  date,                      -- SCD1 (RQ-07, RQ-09); vazia se nunca trocou
    dt_ultima_venda           date,                      -- SCD1 (T23): última troca em que o grupo econômico muda
    dt_ultima_reorganizacao   date,                      -- SCD1 (T23): última troca dentro do mesmo grupo econômico
    etl_dt_inicio             timestamp      NOT NULL,
    etl_dt_fim                timestamp      NOT NULL,
    etl_versao                integer        NOT NULL,
    CONSTRAINT uk_dim_campo_versao UNIQUE (nk_campo, etl_versao)
);
INSERT INTO dim_campo VALUES (0, 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'NA', 'N/A', 'N/A', -1, -1, '1900-01-01', '1900-01-01', '1900-01-01',
                              '1900-01-01', '2199-12-31', 1);

-- -----------------------------------------------------------------------------
-- dim_empresa: uma empresa (operadora na produção, sócia na participação)
-- -----------------------------------------------------------------------------
CREATE TABLE dim_empresa (
    sk_empresa          serial         PRIMARY KEY,
    nk_empresa          varchar(100)   NOT NULL,   -- nome uniformizado (T07, T14)
    nm_empresa          varchar(100)   NOT NULL,
    nm_razao_social     varchar(200)   NOT NULL,
    nm_grupo_economico  varchar(100)   NOT NULL,
    nm_pais             varchar(60)    NOT NULL,
    etl_dt_inicio       timestamp      NOT NULL,
    etl_dt_fim          timestamp      NOT NULL,
    etl_versao          integer        NOT NULL,
    CONSTRAINT uk_dim_empresa_versao UNIQUE (nk_empresa, etl_versao)
);
INSERT INTO dim_empresa VALUES (0, 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', '1900-01-01', '2199-12-31', 1);

-- -----------------------------------------------------------------------------
-- dim_contrato: um contrato de concessão
-- -----------------------------------------------------------------------------
CREATE TABLE dim_contrato (
    sk_contrato    serial        PRIMARY KEY,
    nk_contrato    varchar(40)   NOT NULL,   -- número só com dígitos (T15)
    nr_contrato    varchar(40)   NOT NULL,
    nm_contrato    varchar(100)  NOT NULL,
    nm_rodada      varchar(30)   NOT NULL,
    nm_fase        varchar(30)   NOT NULL,
    nm_ambiente    varchar(20)   NOT NULL,
    nm_bacia       varchar(60)   NOT NULL,
    etl_dt_inicio  timestamp     NOT NULL,
    etl_dt_fim     timestamp     NOT NULL,
    etl_versao     integer       NOT NULL,
    CONSTRAINT uk_dim_contrato_versao UNIQUE (nk_contrato, etl_versao)
);
INSERT INTO dim_contrato VALUES (0, 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', '1900-01-01', '2199-12-31', 1);

-- -----------------------------------------------------------------------------
-- dim_instalacao: uma instalação de destino da produção
-- -----------------------------------------------------------------------------
CREATE TABLE dim_instalacao (
    sk_instalacao       serial        PRIMARY KEY,
    nk_instalacao       varchar(100)  NOT NULL,   -- nome normalizado (T14)
    nm_instalacao       varchar(100)  NOT NULL,
    nm_tipo_instalacao  varchar(40)   NOT NULL,   -- tipo predominante (T13)
    etl_dt_inicio       timestamp     NOT NULL,
    etl_dt_fim          timestamp     NOT NULL,
    etl_versao          integer       NOT NULL,
    CONSTRAINT uk_dim_instalacao_versao UNIQUE (nk_instalacao, etl_versao)
);
INSERT INTO dim_instalacao VALUES (0, 'N/A', 'N/A', 'N/A', '1900-01-01', '2199-12-31', 1);

-- -----------------------------------------------------------------------------
-- dim_corrente: um tipo de petróleo, com a análise do óleo de cada período de carga
-- (T19: a composição do gás fica fora do DW)
-- -----------------------------------------------------------------------------
CREATE TABLE dim_corrente (
    sk_corrente         serial        PRIMARY KEY,
    nk_corrente         varchar(100)  NOT NULL,   -- nome normalizado (T14)
    nm_corrente         varchar(100)  NOT NULL,
    dt_periodo_carga    date          NOT NULL,   -- cada período de carga é uma versão (SCD2)
    nr_grau_api          numeric,                -- análise do óleo; vazia quando a ANP não publica
    nm_dest_leve_corte   varchar(30),
    nr_dest_leve_pct     numeric,
    nm_dest_medio_corte  varchar(30),
    nr_dest_medio_pct    numeric,
    nm_dest_pesado_corte varchar(30),
    nr_dest_pesado_pct   numeric,
    etl_dt_inicio       timestamp     NOT NULL,
    etl_dt_fim          timestamp     NOT NULL,
    etl_versao          integer       NOT NULL,
    CONSTRAINT uk_dim_corrente_versao UNIQUE (nk_corrente, etl_versao)
);
INSERT INTO dim_corrente VALUES (0, 'N/A', 'N/A', '1900-01-01', -1, 'N/A', -1, 'N/A', -1, 'N/A', -1,
                                 '1900-01-01', '2199-12-31', 1);

-- -----------------------------------------------------------------------------
-- ft_producao: um poço, num campo, num mês (depois de T01, T02, T16 e T17)
-- -----------------------------------------------------------------------------
CREATE TABLE ft_producao (
    sk_data                  integer  NOT NULL REFERENCES dim_data (sk_data),   -- 1º dia do mês (AAAAMM01)
    sk_poco                  integer  NOT NULL REFERENCES dim_poco (sk_poco),
    sk_campo                 integer  NOT NULL REFERENCES dim_campo (sk_campo),
    sk_empresa               integer  NOT NULL REFERENCES dim_empresa (sk_empresa),       -- operadora no mês
    sk_contrato              integer  NOT NULL REFERENCES dim_contrato (sk_contrato),
    sk_instalacao            integer  NOT NULL REFERENCES dim_instalacao (sk_instalacao), -- 0 quando vazia
    sk_corrente              integer  NOT NULL REFERENCES dim_corrente (sk_corrente),     -- 0 antes de 2018
    md_oleo_bbl              numeric  NOT NULL,   -- volume do mês (média diária × dias, T10)
    md_condensado_bbl        numeric  NOT NULL,
    md_petroleo_bbl          numeric  NOT NULL,
    md_agua_bbl              numeric  NOT NULL,
    md_gas_assoc_mil_m3      numeric  NOT NULL,
    md_gas_nao_assoc_mil_m3  numeric  NOT NULL,
    md_gas_total_mil_m3      numeric  NOT NULL,
    md_horas_producao        integer,             -- vazia em ~15% das linhas da fonte
    md_preco_rs_m3           numeric,             -- não aditiva; vazia sem preço publicado (ex.: 07/2005)
    md_receita_estimada_rs   numeric,             -- derivada: petróleo do mês (m³) × preço
    CONSTRAINT pk_ft_producao PRIMARY KEY (sk_data, sk_poco, sk_campo)
);
CREATE INDEX ix_ft_producao_campo    ON ft_producao (sk_campo);
CREATE INDEX ix_ft_producao_empresa  ON ft_producao (sk_empresa);
CREATE INDEX ix_ft_producao_contrato ON ft_producao (sk_contrato);

-- -----------------------------------------------------------------------------
-- ft_participacao: uma empresa, num contrato, numa foto da relação de concessionários
-- -----------------------------------------------------------------------------
CREATE TABLE ft_participacao (
    sk_data        integer       NOT NULL REFERENCES dim_data (sk_data),        -- data da foto
    sk_empresa     integer       NOT NULL REFERENCES dim_empresa (sk_empresa),  -- sócia
    sk_contrato    integer       NOT NULL REFERENCES dim_contrato (sk_contrato),
    md_percentual  numeric(5,2)  NOT NULL,   -- semiaditiva: soma 100 num contrato numa data
    dd_operador    char(1)       NOT NULL CHECK (dd_operador IN ('S', 'N')),   -- dimensão degenerada
    CONSTRAINT pk_ft_participacao PRIMARY KEY (sk_data, sk_empresa, sk_contrato)
);

-- -----------------------------------------------------------------------------
-- etl_depara: tabela de controle do ETL 2 (fora das estrelas). Registra de quais
-- linhas da stage veio cada entidade do DW, para auditar as junções de grafias (T22).
-- Ex.: empresa 115 "3R Petroleum" e 151 "3R PETROLEUM" -> nk_dw "3R PETROLEUM".
-- -----------------------------------------------------------------------------
CREATE TABLE etl_depara (
    nm_dimensao   varchar(30)   NOT NULL,   -- dim_empresa, dim_campo, dim_contrato...
    id_stage      integer       NOT NULL,   -- chave primária da tabela da stage
    nm_original   varchar(300)  NOT NULL,   -- grafia como veio da fonte
    nk_dw         varchar(150)  NOT NULL,   -- chave natural da entidade no DW
    CONSTRAINT pk_etl_depara PRIMARY KEY (nm_dimensao, id_stage)
);

COMMIT;
