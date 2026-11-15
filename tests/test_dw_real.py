"""DW oficial (dw_anp) carregado pelo ETL 2 a partir da stage oficial: só leitura.

Premissas: grão poço × campo × mês; volumes do DW iguais aos da stage; listas de-para válidas; os requisitos
têm dados (RQ-05 preço, RQ-09 mapa). Pulado se o DW ainda não foi carregado.
"""

import os

import psycopg
import pytest

from etl.python.etl1.config import conninfo
from etl.python.etl2 import validacao

pytestmark = pytest.mark.dados


@pytest.fixture(scope="module")
def bancos():
    try:
        dw = psycopg.connect(conninfo(os.environ.get("DW_DB", "dw_anp")), connect_timeout=3)
        st = psycopg.connect(conninfo(), connect_timeout=3)
    except Exception:
        pytest.skip("DW ou stage indisponível")
    if dw.execute("SELECT count(*) FROM ft_producao").fetchone()[0] == 0:
        pytest.skip("DW ainda não carregado pelo ETL 2")
    yield st, dw
    st.close(); dw.close()


def test_validacao_stage_dw_aprovada(bancos):
    erros, _ = validacao.validar(*bancos)
    assert erros == []


@pytest.mark.parametrize("sql, esperado", [
    ("SELECT count(*) FROM ft_producao", 2_257_246),
    ("SELECT count(*) FROM dim_poco WHERE sk_poco <> 0", 30_752),
    ("SELECT count(*) FROM dim_contrato WHERE sk_contrato <> 0", 1003),  # T15: a letra final distingue contratos (carga do zero)
    ("SELECT count(*) FROM ft_participacao", 1102),
    ("SELECT count(*) FROM (SELECT sk_contrato FROM ft_participacao GROUP BY 1 HAVING sum(md_percentual) <> 100) x", 0),
    ("SELECT count(*) FROM ft_producao WHERE sk_contrato = 0", 94),   # contrato "-" na fonte (T15)
])
def test_numeros_do_dw(bancos, sql, esperado):
    assert bancos[1].execute(sql).fetchone()[0] == esperado


def test_requisitos_tem_dados(bancos):
    dw = bancos[1]
    # RQ-05: preço para quase todo o volume de petróleo
    assert dw.execute("""SELECT 100 * sum(md_petroleo_bbl) FILTER (WHERE md_preco_rs_m3 IS NOT NULL) / sum(md_petroleo_bbl)
                         FROM ft_producao""").fetchone()[0] >= 98
    # RQ-09 (mapa): contorno para quase toda a produção de 2023
    assert dw.execute("""SELECT 100 * sum(f.md_petroleo_bbl) FILTER (WHERE c.desc_contorno_wkt IS NOT NULL) / sum(f.md_petroleo_bbl)
                         FROM ft_producao f JOIN dim_campo c USING (sk_campo) WHERE f.sk_data >= 20230101""").fetchone()[0] >= 97
    # cadeias de-para: LULA -> TUPI (renomeação), Jandaia Sul -> TANGARÁ (unificações em cadeia)
    assert dw.execute("SELECT nm_campo_atual FROM dim_campo WHERE nk_campo = 'LULA|SANTOS'").fetchone()[0] == "TUPI"
    assert dw.execute("SELECT nm_campo_sucessor FROM dim_campo WHERE nk_campo = 'JANDAIA SUL|RECONCAVO'").fetchone()[0] == "TANGARÁ"
    # grafias unidas: 3R Petroleum (ids 115 e 151 na stage) é uma empresa só
    assert dw.execute("SELECT count(*) FROM etl_depara WHERE nm_dimensao = 'dim_empresa' AND nk_dw = '3R PETROLEUM'").fetchone()[0] == 2


def test_trocas_de_operador_separam_venda_de_reorganizacao(bancos):
    # T23: a renomeação revisada pela ANP (Níon Energia -> Galo de Campina, 12/2023) não é venda; a venda foi em 12/2022
    dw = bancos[1]
    um = lambda campo: dw.execute("""SELECT dt_ultima_troca_operador, dt_ultima_venda FROM dim_campo
                                     WHERE nm_campo = %s AND etl_dt_fim = '2199-12-31'""", [campo]).fetchone()
    assert [d.isoformat()[:7] for d in um("ARRIBAÇÃ")] == ["2023-12", "2022-12"]
    assert um("ESTREITO")[0] == um("ESTREITO")[1]                   # Petrobras -> 3R Potiguar: venda
    assert um("ACAJÁ-BURIZINHO")[1] is None                         # só trocou entre empresas da PetroRecôncavo
    assert dw.execute("""SELECT dt_ultima_reorganizacao FROM dim_campo WHERE nm_campo = 'ARRIBAÇÃ'
                         AND etl_dt_fim = '2199-12-31'""").fetchone()[0].isoformat()[:7] == "2023-12"   # a renomeação da ANP
    assert dw.execute("""SELECT nm_grupo_economico FROM dim_empresa WHERE nm_empresa = 'Potiguar E&P S.A.'
                         AND etl_dt_fim = '2199-12-31'""").fetchone()[0] == "Petrorecôncavo S.A."
