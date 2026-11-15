"""Conversões do ETL 1 (C02 e C03 em docs/etl/tratamentos.md).

Premissa [autor]: o transacional guarda o dado bruto. Só se converte o que o PostgreSQL exige para colunas
tipadas, e a única limpeza é tirar os espaços das pontas dos textos (C02).
"""

from datetime import date, datetime
from decimal import Decimal

import pytest

from etl.python.etl1 import conversao as cv

pytestmark = pytest.mark.unidade


@pytest.mark.parametrize("bruto, esperado", [
    ("3,6158", Decimal("3.6158")),          # decimal com vírgula
    (",0015", Decimal("0.0015")),           # decimal sem o zero inicial (achado da análise)
    ("3.637,4574", Decimal("3637.4574")),   # milhar com ponto
    ("1.600,09830", Decimal("1600.09830")),
    ("20,6%", Decimal("20.6")),             # percentual com vírgula...
    ("27.64%", Decimal("27.64")),           # ...e com ponto, em outro ano
    ("0", Decimal("0")),
    ("  5,5  ", Decimal("5.5")),
])
def test_numero_converte_os_formatos_da_anp(bruto, esperado):
    assert cv.numero(bruto) == esperado


@pytest.mark.parametrize("bruto", [None, "", "   ", "-", "%", "#REF!", "#N/D", "#VALOR!"])
def test_numero_vazio_ou_codigo_de_erro_do_excel_vira_null(bruto):
    assert cv.numero(bruto) is None


def test_numero_invalido_para_a_carga():
    with pytest.raises(ValueError):
        cv.numero("abc")


def test_texto_remove_so_os_espacos_das_pontas():
    # os arquivos de 2005-2017 completam os nomes com espaços até 20 caracteres (C02)
    assert cv.texto("7BR23HPRJS          ") == "7BR23HPRJS"
    assert cv.texto("  Recôncavo ") == "Recôncavo"


def test_texto_preserva_a_grafia_exata():
    # [autor] nada de unificar maiúsculas, acentos ou espaços internos
    assert cv.texto("ÁGUA GRANDE") == "ÁGUA GRANDE"
    assert cv.texto("agua grande") == "agua grande"
    assert cv.texto("7C   0010  BA") == "7C   0010  BA"


@pytest.mark.parametrize("bruto", [None, "", "    "])
def test_texto_vazio_vira_null(bruto):
    assert cv.texto(bruto) is None


def test_inteiro():
    assert cv.inteiro(" 744 ") == 744
    assert cv.inteiro("") is None


def test_periodo_da_producao_vira_primeiro_dia_do_mes():
    assert cv.periodo("2023/12") == date(2023, 12, 1)


@pytest.mark.parametrize("bruto", ["2015/07", "201507", "07/2015"])
def test_periodo_da_carga_aceita_os_tres_formatos(bruto):
    assert cv.periodo_carga(bruto) == date(2015, 7, 1)


def test_periodo_da_carga_desconhecido_para_a_carga():
    with pytest.raises(ValueError):
        cv.periodo_carga("jul/2015")


def test_data_de_atualizacao_sem_hora():
    assert cv.data_br("26/11/2025") == datetime(2025, 11, 26)


def test_data_de_atualizacao_com_hora_preserva_a_hora():
    # 69 mil linhas trazem a hora; por isso a coluna é timestamp
    assert cv.data_br("01/10/2026 14:35") == datetime(2026, 10, 1, 14, 35)


def test_data_de_atualizacao_em_formato_desconhecido_para_a_carga():
    with pytest.raises(ValueError):
        cv.data_br("2025-11-26")


@pytest.mark.parametrize("serial, esperado", [
    ("44927", date(2023, 1, 1)),   # exemplo documentado no CLAUDE.md
    ("44197", date(2021, 1, 1)),
    ("39814", date(2009, 1, 1)),
])
def test_data_serial_do_excel(serial, esperado):
    assert cv.data_serial_excel(serial) == esperado


def test_periodo_do_csv_extraido_dos_pdfs():
    assert cv.periodo_aaaa_mm("2005-01") == date(2005, 1, 1)
