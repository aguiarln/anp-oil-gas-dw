"""Extração da stage para o ETL 2. Tudo roda numa conexão com a stage, em tabelas temporárias:

1. `ult`: a versão mais recente de cada poço × campo × mês × arquivo de origem (T17);
2. `cons`: o grão da fato, poço × campo × mês, sem as linhas do pré-sal que repetem uma linha do mar (T16) e
   com as repetições consolidadas no maior valor de cada medida (T02);
3. `pocos_presal`: os poços que aparecem no arquivo do pré-sal (marcam o ambiente "Pré-sal", T16).
"""

MEDIDAS = ["oleo_bbl_dia", "condensado_bbl_dia", "petroleo_bbl_dia", "gas_assoc_mm3_dia", "gas_nao_assoc_mm3_dia",
           "gas_total_mm3_dia", "agua_bbl_dia", "horas_producao"]


def preparar(st):
    st.execute("""
        CREATE TEMP TABLE ult AS
        SELECT * FROM (SELECT pm.*, max(id_carga) OVER (PARTITION BY id_poco, id_campo, periodo, arquivo_origem) AS ultima
                       FROM producao_mensal pm) x
        WHERE id_carga = ultima""")
    st.execute("CREATE INDEX ON ult (id_poco, id_campo, periodo, arquivo_origem)")
    medidas = ",\n               ".join(f"max({m}) AS {m}" for m in MEDIDAS)
    st.execute(f"""
        CREATE TEMP TABLE cons AS
        SELECT id_poco, id_campo, periodo,
               max(arquivo_origem) AS arquivo_origem, max(id_estado) AS id_estado, max(id_empresa) AS id_empresa,
               max(id_contrato) AS id_contrato, max(id_caracterizacao) AS id_caracterizacao,
               (array_agg(id_instalacao ORDER BY id_instalacao IS NULL, horas_producao DESC NULLS LAST))[1] AS id_instalacao,
               (array_agg(tipo_instalacao ORDER BY tipo_instalacao IS NULL, horas_producao DESC NULLS LAST))[1] AS tipo_instalacao,
               count(*) AS linhas_consolidadas,
               {medidas}
        FROM ult u
        WHERE NOT (arquivo_origem = 'presal' AND EXISTS (  -- T16: só sai a linha do pré-sal que repete uma do mar
                   SELECT 1 FROM ult m WHERE m.arquivo_origem = 'mar'
                   AND (m.id_poco, m.id_campo, m.periodo) = (u.id_poco, u.id_campo, u.periodo)))
        GROUP BY id_poco, id_campo, periodo""")
    st.execute("CREATE TEMP TABLE pocos_presal AS SELECT DISTINCT id_poco FROM ult WHERE arquivo_origem = 'presal'")
    st.execute("ANALYZE cons")


def todos(st, sql, params=None):
    return st.execute(sql, params).fetchall()


def contagens(st) -> dict:
    return {
        "linhas_producao": todos(st, "SELECT count(*) FROM producao_mensal")[0][0],
        "linhas_ultima_versao": todos(st, "SELECT count(*) FROM ult")[0][0],
        "linhas_presal": todos(st, "SELECT count(*) FROM ult WHERE arquivo_origem = 'presal'")[0][0],
        "presal_mantidas": todos(st, "SELECT count(*) FROM cons WHERE arquivo_origem = 'presal'")[0][0],
        "chaves_consolidadas": todos(st, "SELECT count(*) FROM cons WHERE linhas_consolidadas > 1")[0][0],
        "grao": todos(st, "SELECT count(*) FROM cons")[0][0],
    }
