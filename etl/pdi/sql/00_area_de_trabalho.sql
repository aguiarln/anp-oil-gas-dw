-- =============================================================================
-- ETL 2 no Pentaho PDI: área de trabalho no Data Warehouse gêmeo (dw_anp_pdi)
-- -----------------------------------------------------------------------------
-- Executado pelo Job (jobs/job_etl2.kjb) antes das transformações. Recria o
-- schema "trab", que recebe a cópia da stage (tr_01_extracao) e as listas
-- de-para (tr_02_de_para), e as funções com as regras de uniformização do
-- ETL 2, equivalentes às de etl/python/etl2/normalizacao.py:
--   trab.chave           grafias (T14, T20)
--   trab.chave_contrato  contrato com os dígitos e a letra final (T15)
--   trab.ponto_lat/lon   coordenada do poço a partir do WKT
--   trab.centro          centro do contorno do campo (centroide do anel externo)
-- As tabelas do Data Warehouse (dim_, ft_, etl_depara) não são tocadas aqui.
-- =============================================================================

DROP SCHEMA IF EXISTS trab CASCADE;
CREATE SCHEMA trab;

-- ------------------------------------------------------------ regras (funções)
-- Chave de comparação de grafias: sem acento (decomposição NFKD e remoção do que
-- não é ASCII), "_" como espaço, um espaço só entre as palavras, maiúsculas.
CREATE FUNCTION trab.chave(nome text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT nullif(upper(btrim(regexp_replace(
        regexp_replace(normalize(replace(replace(nome, chr(173), ''), '_', ' '), NFKD), '[^\x01-\x7F]', '', 'g'),
        '\s+', ' ', 'g'))), '')
$$;

-- Contrato: só os dígitos e, se o número termina numa única letra após um dígito,
-- essa letra em maiúscula (BM-S-11 e BM-S-11A são contratos diferentes).
CREATE FUNCTION trab.chave_contrato(numero text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN regexp_replace(numero, '\D', '', 'g') = '' THEN NULL
                ELSE regexp_replace(numero, '\D', '', 'g')
                     || coalesce(upper(substring(btrim(numero) FROM '\d([A-Za-z])$')), '')
           END
$$;

-- 'POINT (lon lat)' -> latitude e longitude, com 7 casas
CREATE FUNCTION trab.ponto_lat(wkt text) RETURNS numeric LANGUAGE sql IMMUTABLE AS $$
    SELECT round((regexp_match(wkt, '^\s*POINT\s*\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)', 'i'))[2]::numeric, 7)
$$;
CREATE FUNCTION trab.ponto_lon(wkt text) RETURNS numeric LANGUAGE sql IMMUTABLE AS $$
    SELECT round((regexp_match(wkt, '^\s*POINT\s*\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)', 'i'))[1]::numeric, 7)
$$;

-- Centro do contorno: centroide do anel externo de um POLYGON (fórmula da área com
-- sinal); polígono degenerado usa a média dos vértices. Devolve {latitude, longitude}.
CREATE FUNCTION trab.centro(wkt text) RETURNS numeric[] LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    anel text := (regexp_match(wkt, '^\s*POLYGON\s*\(\(([^)]+)\)', 'i'))[1];
    xs double precision[] := '{}';
    ys double precision[] := '{}';
    par text[];
    n int; j int;
    area double precision := 0; cx double precision := 0; cy double precision := 0; f double precision;
BEGIN
    IF anel IS NULL THEN RETURN NULL; END IF;
    FOR par IN SELECT regexp_split_to_array(btrim(p), '\s+') FROM regexp_split_to_table(anel, ',') p LOOP
        xs := xs || par[1]::double precision;
        ys := ys || par[2]::double precision;
    END LOOP;
    n := array_length(xs, 1);
    FOR i IN 1..n LOOP
        j := CASE WHEN i = n THEN 1 ELSE i + 1 END;
        f := xs[i] * ys[j] - xs[j] * ys[i];
        area := area + f; cx := cx + (xs[i] + xs[j]) * f; cy := cy + (ys[i] + ys[j]) * f;
    END LOOP;
    IF abs(area) < 1e-12 THEN
        RETURN ARRAY[round((SELECT avg(y) FROM unnest(ys) y)::numeric, 7), round((SELECT avg(x) FROM unnest(xs) x)::numeric, 7)];
    END IF;
    area := area / 2;
    RETURN ARRAY[round((cy / (6 * area))::numeric, 7), round((cx / (6 * area))::numeric, 7)];
END
$$;

-- Tabela fixa do IBGE (etl/python/etl1/cadastros.py): completa os estados sem cadastro na stage
CREATE TABLE trab.ibge (nome text, sigla char(2), regiao text);
INSERT INTO trab.ibge VALUES
    ('ACRE', 'AC', 'Norte'), ('ALAGOAS', 'AL', 'Nordeste'), ('AMAPA', 'AP', 'Norte'), ('AMAZONAS', 'AM', 'Norte'),
    ('BAHIA', 'BA', 'Nordeste'), ('CEARA', 'CE', 'Nordeste'), ('DISTRITO FEDERAL', 'DF', 'Centro-Oeste'),
    ('ESPIRITO SANTO', 'ES', 'Sudeste'), ('GOIAS', 'GO', 'Centro-Oeste'), ('MARANHAO', 'MA', 'Nordeste'),
    ('MATO GROSSO', 'MT', 'Centro-Oeste'), ('MATO GROSSO DO SUL', 'MS', 'Centro-Oeste'), ('MINAS GERAIS', 'MG', 'Sudeste'),
    ('PARA', 'PA', 'Norte'), ('PARAIBA', 'PB', 'Nordeste'), ('PARANA', 'PR', 'Sul'), ('PERNAMBUCO', 'PE', 'Nordeste'),
    ('PIAUI', 'PI', 'Nordeste'), ('RIO DE JANEIRO', 'RJ', 'Sudeste'), ('RIO GRANDE DO NORTE', 'RN', 'Nordeste'),
    ('RIO GRANDE DO SUL', 'RS', 'Sul'), ('RONDONIA', 'RO', 'Norte'), ('RORAIMA', 'RR', 'Norte'),
    ('SANTA CATARINA', 'SC', 'Sul'), ('SAO PAULO', 'SP', 'Sudeste'), ('SERGIPE', 'SE', 'Nordeste'), ('TOCANTINS', 'TO', 'Norte');

-- ------------------------------------------------------------ cópia da stage (tr_01_extracao)
-- Produção no grão da fato (poço × campo × mês): versão mais recente (T17), sem o
-- pré-sal repetido (T16) e com as repetições consolidadas no maior valor (T02).
CREATE TABLE trab.cons (
    id_poco int, id_campo int, periodo date, arquivo_origem text, id_estado int, id_empresa int, id_contrato int,
    id_caracterizacao int, id_instalacao int, tipo_instalacao text, linhas_consolidadas int,
    oleo_bbl_dia numeric, condensado_bbl_dia numeric, petroleo_bbl_dia numeric, gas_assoc_mm3_dia numeric,
    gas_nao_assoc_mm3_dia numeric, gas_total_mm3_dia numeric, agua_bbl_dia numeric, horas_producao int
);
CREATE TABLE trab.pocos_presal (id_poco int);
CREATE TABLE trab.empresa (id_empresa int, nome_fantasia text, razao_social text, grupo text, pais text);
CREATE TABLE trab.contrato (id_contrato int, numero text, nome text, rodada text, fase text, ambiente text, bacia text);
CREATE TABLE trab.campo (id_campo int, nome text, bacia text);
CREATE TABLE trab.poco (id_poco int, nome_anp text);
CREATE TABLE trab.estado (id_estado int, nome text, sigla char(2), regiao text);
CREATE TABLE trab.instalacao (id_instalacao int, nome text);
CREATE TABLE trab.caracterizacao (
    id_caracterizacao int, id_corrente int, corrente text, periodo_carga date, grau_api numeric,
    dest_leve_corte text, dest_leve_pct numeric, dest_medio_corte text, dest_medio_pct numeric,
    dest_pesado_corte text, dest_pesado_pct numeric
);
CREATE TABLE trab.coordenada_poco (id_poco int, geometria_wkt text);
CREATE TABLE trab.coordenada_campo (id_campo int, nome text, bacia text, geometria_wkt text);
CREATE TABLE trab.participacao (id_empresa int, id_contrato int, nome_arquivo text, percentual numeric, operador boolean);
CREATE TABLE trab.preco (numero text, campo_nome text, periodo date, valor_rs_m3 numeric);

-- ------------------------------------------------------------ listas de-para (tr_02_de_para)
CREATE TABLE trab.dp_empresas (empresa_origem text, empresa_destino text, motivo text);
CREATE TABLE trab.dp_grupos (empresa text, grupo_economico text, pais text, evidencia text, fonte text);
CREATE TABLE trab.dp_campos (campo_origem text, bacia_origem text, campo_destino text, bacia_destino text, mes text, tipo text, motivo text);
