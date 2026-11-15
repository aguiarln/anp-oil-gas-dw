-- =============================================================================
-- anp-oil-gas-dw - criação dos bancos do projeto (PostgreSQL 17)
-- Padrão de nomes: st_ = stage/transacional, dw_ = Data Warehouse.
--
-- Executar conectado ao banco "postgres":
--   psql -d postgres -f database/criar_bancos.sql
--
-- Os bancos gêmeos usados pelo motor alternativo (PDI), st_anp_pdi e
-- dw_anp_pdi, só são criados na fase PDI.
-- =============================================================================

CREATE DATABASE st_anp
    ENCODING 'UTF8'
    TEMPLATE template0;
COMMENT ON DATABASE st_anp IS
    'Stage/transacional do projeto anp-oil-gas-dw: dados brutos da ANP (ETL 1)';

CREATE DATABASE dw_anp
    ENCODING 'UTF8'
    TEMPLATE template0;
COMMENT ON DATABASE dw_anp IS
    'Data Warehouse do projeto anp-oil-gas-dw: modelo estrela (ETL 2)';
