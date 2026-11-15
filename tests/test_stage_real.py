"""Stage oficial (st_anp), só leitura: confere a carga contra os números documentados.

Premissas: a carga inicial documentada (ETL 1, --ate 2026-10-17); a base origem publicada
(dist/base-origem) é a própria stage; [autor] preço mínimo até 2017 e de referência a partir de
2018, sem preço em 07/2005.
Os testes são pulados se a stage não existir.
"""

import os
from datetime import date

import psycopg
import pytest

from etl.python.etl1 import exportar
from etl.python.etl1.config import conninfo

from .conftest import RAIZ

pytestmark = pytest.mark.dados

STAGE = os.environ.get("ST_DB", "st_anp")
BASE_ORIGEM = RAIZ / "dist" / "base-origem"


@pytest.fixture(scope="module")
def st():
    try:
        conn = psycopg.connect(conninfo(STAGE), connect_timeout=3)
    except Exception:
        pytest.skip(f"stage {STAGE} indisponível")
    if conn.execute("SELECT count(*) FROM carga").fetchone()[0] == 0:
        pytest.skip(f"stage {STAGE} vazia")
    yield conn
    conn.close()


def v(conn, sql, params=None):
    return conn.execute(sql, params).fetchone()[0]


# ---------- carga documentada ----------

@pytest.mark.parametrize("sql, esperado", [
    ("SELECT count(*) FROM carga WHERE situacao = 'carregada'", 378),          # uma carga por CSV (downloads até 17/10/2026)
    ("SELECT count(*) FROM carga WHERE situacao = 'repetida'", 0),             # stage recarregada do zero em 17/10
    ("SELECT count(*) FROM producao_mensal", 2_761_294),                       # 2.761.260 dos zips + 34 revisões da CDP
    ("SELECT sum(qtd_linhas) FROM carga WHERE fonte LIKE 'producao%%'", 2_761_294),
    ("SELECT qtd_linhas FROM carga WHERE fonte = 'producao_por_poco_cdp'", 34),  # só as linhas revisadas pela ANP
    ("SELECT count(*) FROM preco_petroleo", 83_357),
    ("SELECT count(*) FROM poco", 43_571),                                     # 30.752 da produção + os poços só da camada
    ("SELECT count(DISTINCT id_poco) FROM producao_mensal", 30_752),
    ("SELECT count(*) FROM coordenada_poco", 31_323),
    ("SELECT count(*) FROM coordenada_campo", 429),
    ("SELECT count(DISTINCT periodo) FROM producao_mensal", 228),
    ("SELECT min(periodo) FROM producao_mensal", date(2005, 1, 1)),
    ("SELECT max(periodo) FROM producao_mensal", date(2023, 12, 1)),
])
def test_carga_inicial_documentada(st, sql, esperado):
    assert v(st, sql) == esperado


def test_tres_origens_terra_mar_presal(st):
    assert {o for (o,) in st.execute("SELECT DISTINCT arquivo_origem FROM producao_mensal")} == {"terra", "mar", "presal"}


@pytest.mark.parametrize("tabela, coluna", [
    ("poco", "nome_anp"), ("campo", "nome"), ("empresa", "nome_fantasia"), ("bacia", "nome"), ("instalacao", "nome"),
    ("corrente", "nome"), ("contrato", "numero"), ("estado", "nome"), ("grupo_economico", "nome"),
    ("preco_petroleo", "campo_nome"),
])
def test_textos_sem_espacos_nas_pontas(st, tabela, coluna):
    # C02: sem isso, a stage teria 13.351 poços repetidos
    assert v(st, f"SELECT count(*) FROM {tabela} WHERE {coluna} <> btrim({coluna})") == 0


def test_todo_estado_tem_sigla_e_regiao(st):
    assert v(st, "SELECT count(*) FROM estado WHERE sigla IS NULL OR regiao IS NULL") == 0


# ---------- preços ----------

def test_preco_minimo_ate_2017_e_de_referencia_a_partir_de_2018(st):
    assert v(st, "SELECT max(periodo) FROM preco_petroleo WHERE tipo_preco = 'minimo'") == date(2017, 12, 1)
    assert v(st, "SELECT min(periodo) FROM preco_petroleo WHERE tipo_preco = 'minimo'") == date(2005, 1, 1)
    assert v(st, "SELECT min(periodo) FROM preco_petroleo WHERE tipo_preco = 'referencia'") == date(2018, 1, 1)
    assert v(st, "SELECT max(periodo) FROM preco_petroleo WHERE tipo_preco = 'referencia'") == date(2023, 12, 1)


def test_sem_preco_em_julho_de_2005(st):
    # o PDF de 07/2005 não foi publicado pela ANP
    assert v(st, "SELECT count(*) FROM preco_petroleo WHERE periodo = '2005-07-01'") == 0


# ---------- base origem publicada ----------

def test_stage_identica_a_base_origem_publicada(st):
    if not (BASE_ORIGEM / "manifesto.csv").exists():
        pytest.skip("dist/base-origem ainda não gerada")
    assert exportar.conferir(st, BASE_ORIGEM) == 0
