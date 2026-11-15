-- =============================================================================
-- anp-oil-gas-dw - Stage/transacional (st_anp) - DDL das 16 tabelas
-- PostgreSQL 17. Modelo aprovado em 01/10/2026, com as tabelas 15 e 16 (coordenadas) aprovadas em
-- 17/10/2026 (docs/modelagem/oltp_diagrama_relacional.png).
--
-- Regra do projeto: a stage guarda o DADO BRUTO da ANP. Nada é corrigido na carga
-- (ETL 1). Só se converte o que o PostgreSQL exige para colunas tipadas (decimal com
-- vírgula, datas). As entidades entram pela grafia EXATA da fonte, e toda correção
-- acontece no ETL 2 (ver docs/etl/tratamentos.md). Única exceção: espaços no início
-- e no fim dos textos são removidos na leitura (C02), porque os arquivos de 2005-2017
-- completam os nomes com espaços até 20 caracteres (formato do arquivo, não dado).
-- A coluna "Nome Poço Operador" da fonte não é carregada (decisão do autor).
--
-- Executar conectado ao banco st_anp:
--   psql -d st_anp -f database/st/criar_tabelas.sql
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. carga: controle de cargas (rastreabilidade e auditoria, C05)
-- -----------------------------------------------------------------------------
CREATE TABLE carga (
    id_carga         serial        PRIMARY KEY,
    nome_arquivo     varchar(300)  NOT NULL,   -- caminho relativo a data/ (ex.: raw/anp/concessionarios/2026-09-30/relacao-concessionarios.csv)
    fonte            varchar(40)   NOT NULL,   -- ex.: producao_por_poco, producao_por_poco_cdp, concessionarios, pais_origem, preco_referencia, preco_minimo
    hash_sha256      char(64)      NOT NULL,   -- impressão digital do conteúdo do arquivo
    data_hora_carga  timestamp     NOT NULL DEFAULT now(),
    situacao         varchar(10)   NOT NULL CHECK (situacao IN ('carregada', 'repetida')),
    qtd_linhas       integer       NOT NULL DEFAULT 0  -- linhas gravadas (0 quando o arquivo é repetido)
);
-- Um mesmo conteúdo só pode ser carregado uma vez; tentativas repetidas ficam registradas.
CREATE UNIQUE INDEX uk_carga_hash_carregada ON carga (hash_sha256) WHERE situacao = 'carregada';
COMMENT ON TABLE carga IS 'Cada arquivo processado pelo ETL 1. Arquivo com hash já carregado é registrado como repetido e não é recarregado';

-- -----------------------------------------------------------------------------
-- 2. grupo_economico e 3. empresa
-- -----------------------------------------------------------------------------
CREATE TABLE grupo_economico (
    id_grupo  serial        PRIMARY KEY,
    nome      varchar(100)  NOT NULL UNIQUE,
    pais      varchar(60)
);
COMMENT ON TABLE grupo_economico IS 'Grupo controlador e país de origem (fonte: relação de país de origem dos concessionários)';

CREATE TABLE empresa (
    id_empresa     serial        PRIMARY KEY,
    nome_fantasia  varchar(100)  NOT NULL UNIQUE,  -- grafia exata da fonte
    razao_social   varchar(200),
    cnpj           varchar(14),                    -- sem UK: a mesma empresa pode vir com grafias diferentes
    id_grupo       integer       REFERENCES grupo_economico (id_grupo)
);
COMMENT ON TABLE empresa IS 'Operadoras e concessionárias. Reúne concessionários, país de origem e os operadores que aparecem na produção';

-- -----------------------------------------------------------------------------
-- 4. bacia, 5. campo, 6. estado
-- -----------------------------------------------------------------------------
CREATE TABLE bacia (
    id_bacia  serial       PRIMARY KEY,
    nome      varchar(60)  NOT NULL UNIQUE
);

CREATE TABLE campo (
    id_campo  serial        PRIMARY KEY,
    nome      varchar(100)  NOT NULL,
    id_bacia  integer       NOT NULL REFERENCES bacia (id_bacia),
    CONSTRAINT uk_campo_nome_bacia UNIQUE (nome, id_bacia)   -- existem dois campos FAZENDA BELEM, em bacias diferentes
);

CREATE TABLE estado (
    id_estado  serial       PRIMARY KEY,
    nome       varchar(40)  NOT NULL UNIQUE,  -- grafia da ANP (ex.: Rio Grande do Norte)
    sigla      char(2),                        -- tabela fixa do IBGE
    regiao     varchar(20)                     -- tabela fixa do IBGE
);

-- -----------------------------------------------------------------------------
-- 7. contrato e 8. participacao_contrato (N:N contrato x empresa)
-- -----------------------------------------------------------------------------
CREATE TABLE contrato (
    id_contrato  serial       PRIMARY KEY,
    numero       varchar(40)  NOT NULL UNIQUE,  -- como veio na fonte, com ou sem pontuação (unificação no ETL 2, T15)
    nome         varchar(100),
    rodada       varchar(30),
    fase         varchar(30),
    ambiente     varchar(20),
    id_bacia     integer      REFERENCES bacia (id_bacia)
);

CREATE TABLE participacao_contrato (
    id_empresa   integer       NOT NULL REFERENCES empresa (id_empresa),
    id_contrato  integer       NOT NULL REFERENCES contrato (id_contrato),
    id_carga     integer       NOT NULL REFERENCES carga (id_carga),
    percentual   numeric(5,2)  NOT NULL,
    operador     boolean       NOT NULL DEFAULT false,  -- o nome vem como "(Operador) - <empresa>" na fonte
    CONSTRAINT pk_participacao_contrato PRIMARY KEY (id_empresa, id_contrato, id_carga)
);
COMMENT ON TABLE participacao_contrato IS 'Sócias de cada contrato. Cada carga da relação de concessionários é uma foto; a sequência de fotos forma o histórico';

-- -----------------------------------------------------------------------------
-- 9. poco, 10. instalacao, 11. corrente, 12. caracterizacao_petroleo
-- -----------------------------------------------------------------------------
CREATE TABLE poco (
    id_poco   serial       PRIMARY KEY,
    nome_anp  varchar(40)  NOT NULL UNIQUE   -- identificador oficial da ANP; campo, estado e pré-sal ficam na produção
);

CREATE TABLE instalacao (
    id_instalacao  serial        PRIMARY KEY,
    nome           varchar(100)  NOT NULL UNIQUE   -- o tipo da instalação fica na produção (T13)
);

CREATE TABLE corrente (
    id_corrente  serial        PRIMARY KEY,
    nome         varchar(100)  NOT NULL UNIQUE
);

CREATE TABLE caracterizacao_petroleo (
    id_caracterizacao      serial       PRIMARY KEY,
    id_corrente            integer      REFERENCES corrente (id_corrente),   -- opcional: ~38 mil linhas (2018+) trazem só a análise do gás, sem corrente
    periodo_carga          date,          -- a fonte usa AAAA/MM, AAAAMM ou MM/AAAA; guardado como o 1º dia do mês
    grau_api               numeric,
    dest_leve_corte        varchar(30),   -- ex.: "< 290ºC" (texto, como publicado)
    dest_leve_pct          numeric,
    dest_medio_corte       varchar(30),
    dest_medio_pct         numeric,
    dest_pesado_corte      varchar(30),
    dest_pesado_pct        numeric,
    pct_metano             numeric,
    pct_etano              numeric,
    pct_propano            numeric,
    pct_isobutano          numeric,
    pct_butano             numeric,
    pct_isopentano         numeric,
    pct_n_pentano          numeric,
    pct_hexanos            numeric,
    pct_heptanos           numeric,
    pct_octanos            numeric,
    pct_nonanos            numeric,
    pct_decanos            numeric,
    pct_undecanos          numeric,
    pct_oxigenio           numeric,
    pct_nitrogenio         numeric,
    pct_gas_carbonico      numeric,
    densidade_glp_gas      numeric,
    densidade_glp_liquido  numeric,
    pcs_kj_m3              numeric
);
COMMENT ON TABLE caracterizacao_petroleo IS 'Cada combinação distinta de análise de óleo e gás (só a partir de 2018). Sem chave única (corrente, período): 153 de 606 combinações têm valores diferentes (T19)';

-- -----------------------------------------------------------------------------
-- 13. producao_mensal: um poço num campo num mês, tal como publicado
-- -----------------------------------------------------------------------------
CREATE TABLE producao_mensal (
    id_producao            bigserial    PRIMARY KEY,
    id_carga               integer      NOT NULL REFERENCES carga (id_carga),
    arquivo_origem         varchar(6)   NOT NULL CHECK (arquivo_origem IN ('terra', 'mar', 'presal')),
    periodo                date         NOT NULL,   -- AAAA/MM da fonte, guardado como o 1º dia do mês
    id_estado              integer      REFERENCES estado (id_estado),       -- opcional: há linha com estado em branco
    id_poco                integer      NOT NULL REFERENCES poco (id_poco),
    id_campo               integer      NOT NULL REFERENCES campo (id_campo),
    id_empresa             integer      NOT NULL REFERENCES empresa (id_empresa),  -- operador no mês
    id_contrato            integer      NOT NULL REFERENCES contrato (id_contrato),
    id_instalacao          integer      REFERENCES instalacao (id_instalacao),     -- opcional: vazia em ~60% das linhas
    tipo_instalacao        varchar(40),
    id_caracterizacao      integer      REFERENCES caracterizacao_petroleo (id_caracterizacao),  -- só a partir de 2018
    oleo_bbl_dia           numeric,
    condensado_bbl_dia     numeric,
    petroleo_bbl_dia       numeric,     -- publicado pela ANP (óleo + condensado); conferido no ETL 2 (T09)
    gas_assoc_mm3_dia      numeric,
    gas_nao_assoc_mm3_dia  numeric,
    gas_total_mm3_dia      numeric,     -- publicado pela ANP (associado + não associado); conferido no ETL 2 (T09)
    gas_royalties          numeric,     -- unidade muda na fonte: Mm³/dia até 2017, m³/mês depois (T08)
    agua_bbl_dia           numeric,
    horas_producao         integer,
    data_atualizacao       timestamp   -- a fonte traz 'dd/mm/aaaa' ou 'dd/mm/aaaa hh:mm'; timestamp guarda os dois sem perder a hora
);
COMMENT ON TABLE producao_mensal IS 'Produção como a ANP publica: mantém duplicatas, grafias variadas e conflitos de cadastro. Cada carga com dado novo cria nova versão (id_carga)';

CREATE INDEX ix_producao_periodo    ON producao_mensal (periodo);
CREATE INDEX ix_producao_poco       ON producao_mensal (id_poco);
CREATE INDEX ix_producao_campo      ON producao_mensal (id_campo);
CREATE INDEX ix_producao_empresa    ON producao_mensal (id_empresa);
CREATE INDEX ix_producao_contrato   ON producao_mensal (id_contrato);
CREATE INDEX ix_producao_carga      ON producao_mensal (id_carga);

-- -----------------------------------------------------------------------------
-- 14. preco_petroleo: preço mínimo (até 2017) e de referência (2018 em diante)
-- -----------------------------------------------------------------------------
CREATE TABLE preco_petroleo (
    id_preco     serial        PRIMARY KEY,
    id_carga     integer       NOT NULL REFERENCES carga (id_carga),
    periodo      date          NOT NULL,   -- a fonte usa data serial do Excel (ex.: 44927 = 01/01/2023)
    id_contrato  integer       NOT NULL REFERENCES contrato (id_contrato),
    campo_nome   varchar(100)  NOT NULL,   -- texto, sem FK: o arquivo de preço não traz a bacia (T18)
    id_corrente  integer       REFERENCES corrente (id_corrente),   -- opcional: há linhas sem corrente
    tipo_preco   varchar(10)   NOT NULL CHECK (tipo_preco IN ('minimo', 'referencia')),
    valor_rs_m3  numeric       -- opcional: 2 linhas da fonte vêm com o preço em branco (2013 e 2018)
);
CREATE INDEX ix_preco_periodo  ON preco_petroleo (periodo);
CREATE INDEX ix_preco_contrato ON preco_petroleo (id_contrato);

-- -----------------------------------------------------------------------------
-- 15. coordenada_poco: localização de cada poço (camada POCOS_SIRGAS da ANP)
-- -----------------------------------------------------------------------------
-- Uma linha é a coordenada de um poço numa carga. Só entra versão nova quando a
-- coordenada muda (C05). A geometria fica como a ANP publica: texto WKT em
-- SIRGAS 2000 (ex.: POINT (-35.9147941666 -9.614755)); o banco não usa PostGIS.
CREATE TABLE coordenada_poco (
    id_poco        integer  NOT NULL REFERENCES poco (id_poco),
    id_carga       integer  NOT NULL REFERENCES carga (id_carga),
    geometria_wkt  text     NOT NULL,
    PRIMARY KEY (id_poco, id_carga)
);
COMMENT ON TABLE coordenada_poco IS 'Ponto (WKT, SIRGAS 2000) de cada poço, por carga. Fonte: camada POCOS_SIRGAS da ANP';

-- -----------------------------------------------------------------------------
-- 16. coordenada_campo: contorno de cada campo (camada CAMPOS_PRODUCAO_SIRGAS da ANP)
-- -----------------------------------------------------------------------------
-- Uma linha é o contorno de um campo numa carga. O campo é identificado pelo nome e
-- pela bacia da camada, na grafia exata (C01). Geometria em texto WKT (POLYGON).
CREATE TABLE coordenada_campo (
    id_campo       integer  NOT NULL REFERENCES campo (id_campo),
    id_carga       integer  NOT NULL REFERENCES carga (id_carga),
    geometria_wkt  text     NOT NULL,
    PRIMARY KEY (id_campo, id_carga)
);
COMMENT ON TABLE coordenada_campo IS 'Contorno (WKT, SIRGAS 2000) de cada campo, por carga. Fonte: camada CAMPOS_PRODUCAO_SIRGAS da ANP';

COMMIT;
