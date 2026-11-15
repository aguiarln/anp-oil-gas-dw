-- =============================================================================
-- anp-oil-gas-dw - carga da base origem na stage (PostgreSQL 17)
--
-- Recria o st_anp a partir dos 16 CSVs da base origem (um por tabela),
-- gerados por "python -m etl.python.etl1.exportar". Resultado: o mesmo banco
-- que o ETL 1 produziu a partir dos arquivos brutos da ANP, com os mesmos IDs.
--
-- Pré-requisitos: database/criar_bancos.sql e database/st/criar_tabelas.sql já
-- executados (banco criado e tabelas vazias).
--
-- Executar com o psql, DE DENTRO DA PASTA DOS CSVs (o \copy lê caminhos
-- relativos à pasta atual):
--   cd <pasta dos CSVs>
--   psql -U postgres -d st_anp -f <caminho>/database/st/carregar_base.sql
--
-- Tudo roda numa transação: ou a base entra inteira, ou não entra nada.
-- =============================================================================

\set ON_ERROR_STOP on
\encoding UTF8

BEGIN;

-- Ordem das chaves estrangeiras: cada tabela vem depois das que ela referencia.
\copy carga                   FROM 'carga.csv'                   WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy grupo_economico         FROM 'grupo_economico.csv'         WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy empresa                 FROM 'empresa.csv'                 WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy bacia                   FROM 'bacia.csv'                   WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy estado                  FROM 'estado.csv'                  WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy contrato                FROM 'contrato.csv'                WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy participacao_contrato   FROM 'participacao_contrato.csv'   WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy campo                   FROM 'campo.csv'                   WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy poco                    FROM 'poco.csv'                    WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy instalacao              FROM 'instalacao.csv'              WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy corrente                FROM 'corrente.csv'                WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy caracterizacao_petroleo FROM 'caracterizacao_petroleo.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy producao_mensal         FROM 'producao_mensal.csv'         WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy preco_petroleo          FROM 'preco_petroleo.csv'          WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy coordenada_poco         FROM 'coordenada_poco.csv'         WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy coordenada_campo        FROM 'coordenada_campo.csv'        WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')

-- Os IDs vieram nos CSVs; as sequências avançam para o próximo ID livre, para
-- que uma carga nova do ETL 1 continue a numeração sem conflito.
SELECT setval(pg_get_serial_sequence('carga', 'id_carga'),                                 (SELECT max(id_carga)          FROM carga));
SELECT setval(pg_get_serial_sequence('grupo_economico', 'id_grupo'),                       (SELECT max(id_grupo)          FROM grupo_economico));
SELECT setval(pg_get_serial_sequence('empresa', 'id_empresa'),                             (SELECT max(id_empresa)        FROM empresa));
SELECT setval(pg_get_serial_sequence('bacia', 'id_bacia'),                                 (SELECT max(id_bacia)          FROM bacia));
SELECT setval(pg_get_serial_sequence('estado', 'id_estado'),                               (SELECT max(id_estado)         FROM estado));
SELECT setval(pg_get_serial_sequence('contrato', 'id_contrato'),                           (SELECT max(id_contrato)       FROM contrato));
SELECT setval(pg_get_serial_sequence('campo', 'id_campo'),                                 (SELECT max(id_campo)          FROM campo));
SELECT setval(pg_get_serial_sequence('poco', 'id_poco'),                                   (SELECT max(id_poco)           FROM poco));
SELECT setval(pg_get_serial_sequence('instalacao', 'id_instalacao'),                       (SELECT max(id_instalacao)     FROM instalacao));
SELECT setval(pg_get_serial_sequence('corrente', 'id_corrente'),                           (SELECT max(id_corrente)       FROM corrente));
SELECT setval(pg_get_serial_sequence('caracterizacao_petroleo', 'id_caracterizacao'),      (SELECT max(id_caracterizacao) FROM caracterizacao_petroleo));
SELECT setval(pg_get_serial_sequence('producao_mensal', 'id_producao'),                    (SELECT max(id_producao)       FROM producao_mensal));
SELECT setval(pg_get_serial_sequence('preco_petroleo', 'id_preco'),                        (SELECT max(id_preco)          FROM preco_petroleo));

COMMIT;

ANALYZE;
