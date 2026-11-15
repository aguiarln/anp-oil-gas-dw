"""ETL 2 de ponta a ponta: ETL 1 sobre as amostras (stage temporária) -> ETL 2 -> DW temporário.

Premissas: [autor] modelo de duas estrelas; fatos recarregadas por completo; SCD2 nas dimensões; T02, T13,
T14, T15, T16, T17, T19, T22 (docs/etl/tratamentos.md).
"""

import psycopg
import pytest

from etl.python.etl1.config import conninfo
from etl.python.etl2 import __main__ as etl2_main
from etl.python.etl2 import validacao

from .conftest import RAIZ, consultar, rodar_etl1, valor

pytestmark = pytest.mark.integracao

DW = RAIZ / "database" / "dw"


@pytest.fixture
def bancos(novo_banco, dados_teste):
    st = novo_banco()
    rodar_etl1(st)
    dw = novo_banco(ddl=None)
    with psycopg.connect(conninfo(dw)) as c:
        c.execute((DW / "dim_data.sql").read_text(encoding="utf-8"))
        c.execute((DW / "criar_tabelas.sql").read_text(encoding="utf-8"))
    assert etl2_main.main(["--stage", st, "--dw", dw]) == 0
    return st, dw


def test_grao_da_fato(bancos):
    st, dw = bancos
    # 6 (2005) + 6 (2010 anual) + 6 (02/2010) + 5 (pré-sal sem linha de mar na amostra) + 5 (2019) + 6 (12/2023);
    # o mensal 01/2010 é igual ao anual e não chegou à stage (C05)
    assert valor(dw, "SELECT count(*) FROM ft_producao") == 34


def test_validacao_stage_dw(bancos):
    st, dw = bancos
    with psycopg.connect(conninfo(st)) as cst, psycopg.connect(conninfo(dw)) as cdw:
        erros, _ = validacao.validar(cst, cdw)
    # as listas de-para citam campos e empresas reais que não estão nas amostras
    assert [e for e in erros if not e.startswith("listas de-para")] == []


def test_volume_do_mes_e_media_diaria_vezes_dias(bancos):
    st, dw = bancos
    # 7-ET-994-RN, 12/2023: 3,6158 bbl/dia x 31 dias
    assert float(valor(dw, """SELECT f.md_petroleo_bbl FROM ft_producao f JOIN dim_poco p USING (sk_poco)
                              WHERE p.nk_poco = '7-ET-994-RN' AND f.sk_data = 20231201""")) == pytest.approx(3.6158 * 31)


def test_presal_sem_repeticao_do_mar_e_mantido_e_marca_o_ambiente(bancos):
    st, dw = bancos
    assert valor(dw, "SELECT count(*) FROM dim_poco WHERE nm_ambiente = 'Pré-sal'") == 5
    assert valor(dw, """SELECT count(*) FROM ft_producao f JOIN dim_poco p USING (sk_poco) WHERE p.nm_ambiente = 'Pré-sal'""") == 5


def test_dimensoes_uniformizadas(bancos):
    st, dw = bancos
    # T15: o contrato do preço com pontuação e o da produção sem pontuação viram um só
    assert valor(dw, "SELECT count(*) FROM dim_contrato WHERE nk_contrato = '480000036389734'") == 1
    # T14: as duas grafias de "Baiano Mistura" (preço) não geram correntes de produção duplicadas
    assert valor(dw, "SELECT count(*) - count(DISTINCT nk_corrente || dt_periodo_carga) FROM dim_corrente") == 0
    # T13: estado pelo sufixo do poço também no formato sem a coluna Estado (02/2010)
    assert consultar(dw, "SELECT sg_estado, nm_regiao FROM dim_poco WHERE nk_poco = '7-C-10-BA'") == [("BA", "Nordeste")]
    # estado e região do campo (T13: o estado dos seus poços) e contorno do campo (camada da ANP)
    assert consultar(dw, """SELECT sg_estado, nm_regiao, desc_contorno_wkt LIKE 'POLYGON%%' FROM dim_campo
                            WHERE nk_campo = 'ESTREITO|POTIGUAR'""") == [("RN", "Nordeste", True)]
    assert valor(dw, "SELECT nr_latitude IS NOT NULL FROM dim_poco WHERE nk_poco = '7-ET-994-RN'")


def test_linhas_nao_qualificadas_quando_a_dimensao_nao_se_aplica(bancos):
    st, dw = bancos
    # antes de 2018 não há caracterização do petróleo: a fato aponta para a linha 0 da dim_corrente
    assert valor(dw, "SELECT count(*) FROM ft_producao WHERE sk_data < 20180101 AND sk_corrente <> 0") == 0
    assert valor(dw, "SELECT count(*) FROM ft_producao WHERE sk_data >= 20180101 AND sk_corrente = 0") == 1  # 1-ALV-8D-BA, sem análise


def test_participacao_e_de_para(bancos):
    st, dw = bancos
    assert valor(dw, "SELECT count(*) FROM ft_participacao") == 8
    assert valor(dw, "SELECT count(*) FROM ft_participacao WHERE dd_operador = 'S'") == 8
    # T22: cada linha da stage usada no DW está na etl_depara
    assert valor(dw, "SELECT count(*) FROM etl_depara WHERE nm_dimensao = 'dim_poco'") == valor(dw, "SELECT count(*) FROM dim_poco WHERE sk_poco <> 0")


def test_scd2_nova_versao_quando_o_atributo_muda(bancos):
    st, dw = bancos
    # segunda execução sem mudança na stage: nenhuma versão nova e a fato recarregada igual
    assert etl2_main.main(["--stage", st, "--dw", dw]) == 0
    assert valor(dw, "SELECT max(etl_versao) FROM dim_poco") == 1
    assert valor(dw, "SELECT count(*) FROM ft_producao") == 34
    # a ANP move a coordenada de um poço: nova carga na stage -> nova versão na dim_poco
    id_carga = valor(st, """INSERT INTO carga (nome_arquivo, fonte, hash_sha256, situacao)
                            VALUES ('teste', 'coordenada_poco', repeat('f', 64), 'carregada') RETURNING id_carga""")
    consultar(st, """INSERT INTO coordenada_poco SELECT id_poco, %s, 'POINT (-36.5 -5.5)' FROM poco
                     WHERE nome_anp = '7-ET-994-RN' RETURNING 1""", [id_carga])
    assert etl2_main.main(["--stage", st, "--dw", dw]) == 0
    versoes = consultar(dw, """SELECT etl_versao, nr_latitude, etl_dt_fim < '2199-12-31' FROM dim_poco
                               WHERE nk_poco = '7-ET-994-RN' ORDER BY etl_versao""")
    assert [(v, fechada) for v, _, fechada in versoes] == [(1, True), (2, False)]
    assert float(versoes[1][1]) == -5.5
    # a fato aponta para a versão vigente
    assert valor(dw, """SELECT p.etl_versao FROM ft_producao f JOIN dim_poco p USING (sk_poco)
                        WHERE p.nk_poco = '7-ET-994-RN' AND f.sk_data = 20231201""") == 2
