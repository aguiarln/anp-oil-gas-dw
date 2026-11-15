"""dim_data: o script de calendário de terceiros (crédito no cabeçalho), com a única alteração do período,
aplicado num banco temporário.

Premissas [autor]: a dimensão tempo vem do script original (database/dw/dim_data.sql), mantém o nome
dim_data e vai de 2005-01-01 a 2035-12-31; a fato liga pelo 1º dia do mês (sk_data = AAAAMM01).
"""

from datetime import date

import psycopg
import pytest

from etl.python.etl1.config import conninfo

from .conftest import RAIZ, valor

pytestmark = pytest.mark.integracao

SCRIPT = RAIZ / "database" / "dw" / "dim_data.sql"


@pytest.fixture
def dw(novo_banco):
    nome = novo_banco(ddl=None)
    with psycopg.connect(conninfo(nome)) as c:
        c.execute(SCRIPT.read_text(encoding="utf-8"))
    return nome


def test_periodo_de_2005_a_2035(dw):
    datas = "nk_data BETWEEN '2005-01-01' AND '2035-12-31'"
    assert valor(dw, f"SELECT min(nk_data) FROM dim_data WHERE {datas}") == date(2005, 1, 1)
    assert valor(dw, f"SELECT max(nk_data) FROM dim_data WHERE {datas}") == date(2035, 12, 31)
    assert valor(dw, f"SELECT count(*) FROM dim_data WHERE {datas}") == 11322  # um dia por linha, sem buracos


def test_primeiro_dia_do_mes_tem_sk_aaaammdd(dw):
    assert valor(dw, "SELECT sk_data FROM dim_data WHERE nk_data = '2023-12-01'") == 20231201


def test_sk_data_unica(dw):
    assert valor(dw, "SELECT count(*) - count(DISTINCT sk_data) FROM dim_data") == 0


def test_script_original_com_credito_e_so_o_periodo_alterado():
    texto = SCRIPT.read_text(encoding="utf-8")
    assert texto.startswith("---script dim_tempo versão:20220630\n---autor original: Anderson Nascimento (versão 20220630)")
    assert "select '2005-01-01'::date + sequence.day as datum" in texto
    assert "generate_series(0,11321)" in texto
    assert "---[anp-oil-gas-dw] ajuste do autor" in texto
