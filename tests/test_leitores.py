"""Leitores das fontes da ANP (C02a em docs/etl/tratamentos.md): 5 layouts de produção, codificações,
origem terra/mar/pré-sal, ordem dos CSVs nos zips, concessionários e preços.

Os valores esperados são os das primeiras linhas reais de cada amostra (tests/dados/amostras/).
"""

import zipfile
from datetime import date, datetime
from decimal import Decimal

import pytest

from etl.python.etl1 import leitores

from .conftest import AMOSTRAS, amostra

pytestmark = pytest.mark.unidade


def ler(nome_amostra: str, nome_csv: str | None = None):
    formatos = {}
    linhas = list(leitores.ler_csv_producao(nome_csv or nome_amostra, amostra(nome_amostra), formatos))
    return linhas, formatos


# ---------- codificação e origem ----------

def test_utf8_com_bom_ate_2020():
    b = amostra("L19_2005_producao_terra.csv")
    assert b.startswith(b"\xef\xbb\xbf")
    assert leitores.decodificar(b).startswith("ANP - Agência")


def test_iso_8859_1_a_partir_de_2021():
    b = amostra("L48_2023_12_producao_Terra.csv")
    with pytest.raises(UnicodeDecodeError):
        b.decode("utf-8")
    assert "Estação Coletora de Estreito B" in leitores.decodificar(b)


@pytest.mark.parametrize("nome, origem", [
    ("2005_producao_terra.csv", "terra"),
    ("2010_01_producao_mar.csv", "mar"),
    ("2018_producao_presal.csv", "presal"),
    ("2023_12_producao_Terra.csv", "terra"),
    ("2023_12_producao_Pre-Sal.csv", "presal"),
    ("2023_12_producao_Mar.csv", "mar"),
])
def test_origem_pelo_nome_do_arquivo(nome, origem):
    # o pré-sal entra separado (arquivo_origem); a remoção da duplicata com o mar é do ETL 2 (T16)
    assert leitores._origem(nome) == origem


def test_origem_desconhecida_para_a_carga():
    with pytest.raises(ValueError):
        leitores._origem("2023_12_producao.csv")


# ---------- os 5 layouts de produção ----------

@pytest.mark.parametrize("nome, formato, linhas", [
    ("L19_2005_producao_terra.csv", "L19", 6),
    ("L19_SEM_UF_2010_02_producao_terra.csv", "L19_SEM_UF", 6),
    ("L19_2010_01_producao_mar.csv", "L19", 5),
    ("L47_2018_producao_presal.csv", "L47", 5),
    ("L48_2023_12_producao_Terra.csv", "L48", 6),
    ("L49_2019_02_producao_terra.csv", "L49", 5),
])
def test_layout_identificado_e_cabecalhos_ignorados(nome, formato, linhas):
    lidas, formatos = ler(nome)
    assert formatos == {formato: linhas}
    assert len(lidas) == linhas


def test_layout_L19_2005():
    (origem, ln), *_ = ler("L19_2005_producao_terra.csv")[0]
    assert origem == "terra"
    assert (ln["estado"], ln["bacia"], ln["poco"], ln["campo"], ln["operador"], ln["contrato"]) == (
        "Bahia", "Recôncavo", "7-C-10-BA", "CANDEIAS", "Petrobras", "480000036389734")
    assert ln["periodo"] == date(2005, 1, 1)
    assert ln["oleo_bbl_dia"] == Decimal("9.4367")
    assert ln["horas_producao"] == 31
    assert ln["instalacao"] is None  # vazia em ~60% das linhas antigas
    assert ln["caracterizacao"] is None and ln["data_atualizacao"] is None


def test_layout_L19_sem_estado_desloca_as_colunas():
    # terra 02-12/2010 e 02/2011: sem a coluna Estado; a col. 15 é uma medida extra, não carregada
    (_, ln), *_ = ler("L19_SEM_UF_2010_02_producao_terra.csv")[0]
    assert ln["estado"] is None
    assert (ln["bacia"], ln["poco"], ln["campo"], ln["contrato"]) == ("Recôncavo", "7-C-10-BA", "CANDEIAS", "480000036389734")
    assert ln["periodo"] == date(2010, 2, 1)
    assert ln["oleo_bbl_dia"] == Decimal("2.9877")
    assert ln["gas_total_mm3_dia"] == Decimal("0.1362")
    assert ln["agua_bbl_dia"] == Decimal("0.0000")  # col. 14; a col. 15 (1.697,2608) não é a água
    assert (ln["instalacao"], ln["tipo_instalacao"], ln["horas_producao"]) == ("FPSO Polvo", "UEP", 673)


def test_layout_L47_traz_caracterizacao_sem_data_de_atualizacao():
    (origem, ln), *_ = ler("L47_2018_producao_presal.csv")[0]
    assert origem == "presal"
    assert ln["poco"] == "3-BRSA-1017D-RJS" and ln["campo"] == "MARLIM LESTE"
    c = ln["caracterizacao"]
    assert c["corrente"] == "Marlim Leste"
    assert c["periodo_carga"] == date(2015, 7, 1)
    assert c["grau_api"] == Decimal("24.7")
    assert c["dest_leve_corte"] == "< 290ºC" and c["dest_leve_pct"] == Decimal("32.18")
    assert c["pct_metano"] == Decimal("66.035")
    assert ln["data_atualizacao"] is None


def test_layout_L48_2021_em_diante_e_cdp():
    (origem, ln), *_ = ler("L48_2023_12_producao_Terra.csv")[0]
    assert origem == "terra"
    assert (ln["estado"], ln["poco"], ln["campo"], ln["operador"]) == ("Rio Grande do Norte", "7-ET-994-RN", "ESTREITO", "3R Potiguar")
    assert ln["gas_assoc_mm3_dia"] == Decimal("0.0015")   # ",0015"
    assert ln["gas_royalties"] == Decimal("0.045")         # ",045" (m³/mês a partir de 2021)
    assert ln["agua_bbl_dia"] == Decimal("280.8163")
    assert ln["instalacao"] == "Estação Coletora de Estreito B"
    assert ln["data_atualizacao"] == datetime(2025, 11, 26)
    c = ln["caracterizacao"]
    assert (c["corrente"], c["periodo_carga"], c["grau_api"], c["dest_leve_pct"]) == (
        "RGN Mistura", date(2020, 11, 1), Decimal("23.2"), Decimal("20.6"))  # "20,6%"
    assert c["pct_metano"] is None  # análise do gás em branco


def test_layout_L49_ignora_as_colunas_sem_nome():
    # parte de 2019: colunas 20 e 29 sem nome no cabeçalho; a corrente vem na col. 21
    (_, ln), *_ = ler("L49_2019_02_producao_terra.csv")[0]
    assert (ln["poco"], ln["campo"], ln["operador"], ln["contrato"]) == ("1-ALV-2-BA", "TIÊ", "Maha Energy", "48610001427200839A")
    c = ln["caracterizacao"]
    assert c["corrente"] == "Tiê"
    assert c["periodo_carga"] == date(2016, 2, 1)
    assert c["grau_api"] == Decimal("37.6")
    assert c["dest_leve_corte"] == "< 210ºC" and c["dest_leve_pct"] == Decimal("24.90")


def test_layout_desconhecido_para_a_carga():
    # se a ANP criar um 6º layout, a carga para em vez de gravar colunas deslocadas
    linha = ";".join(["Bahia", "Recôncavo", "P", "P", "C", "Op", "123", "2030/01"] + ["0"] * 22)
    with pytest.raises(ValueError, match="formato de linha desconhecido"):
        list(leitores.ler_csv_producao("2030_01_producao_terra.csv", linha.encode("utf-8"), {}))


# ---------- zips ----------

def test_membros_do_zip_anual_antes_dos_mensais(tmp_path):
    # C05a: cada CSV é uma carga; o anual vem antes, e o mensal (igual) vira versão "igual"
    z = tmp_path / "producao-por-poco-2010.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for nome in ("2010/2010_02_producao_mar.csv", "2010/2010_producao_terra.csv", "2010/2010_01_producao_terra.csv",
                     "2010/2010_producao_mar.csv", "2010/2010_01_producao_mar.csv", "2010/leiame.txt"):
            zf.writestr(nome, "x")
    assert leitores.membros_zip(z) == [
        "2010/2010_producao_mar.csv", "2010/2010_producao_terra.csv",
        "2010/2010_01_producao_mar.csv", "2010/2010_01_producao_terra.csv",
        "2010/2010_02_producao_mar.csv",
    ]


def test_conteudo_de_arquivo_solto_e_de_membro_do_zip(tmp_path):
    z = tmp_path / "a.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("pasta/b.csv", b"conteudo")
    assert leitores.conteudo_arquivo(z, "pasta/b.csv") == b"conteudo"
    assert leitores.conteudo_arquivo(AMOSTRAS / "precominpetro_2009.csv", None) == amostra("precominpetro_2009.csv")


# ---------- concessionários e preços ----------

def test_concessionarios_separa_o_marcador_de_operador():
    linhas = list(leitores.ler_concessionarios(AMOSTRAS / "relacao-concessionarios.csv"))
    assert len(linhas) == 8
    assert linhas[0] == {
        "rodada": "AM1", "contrato": "48610009275200571", "fase": "Produção", "nome_contrato": "Carapitanga",
        "bacia": "Sergipe", "cnpj": "11210501000119", "empresa": "EPG Brasil", "operador": True,
        "percentual": Decimal("100.00"), "ambiente": "Terra",
    }


def test_pais_de_origem():
    linhas = list(leitores.ler_pais_origem(AMOSTRAS / "relacao-pais-origem-concessionarios.csv"))
    assert len(linhas) == 5
    assert linhas[0] == {"empresa": "Aguila", "razao_social": "Aguila Energia e Participações Ltda.",
                         "grupo": "Aguila Capital", "pais": "BRASIL"}  # o país vem completado com espaços


def test_preco_de_referencia_com_data_serial_e_codigo_de_erro():
    linhas = list(leitores.ler_preco(AMOSTRAS / "preco-referencia-petroleo-2021.csv"))
    assert len(linhas) == 7
    assert linhas[0] == {"periodo": date(2021, 1, 1), "contrato": "48000.003552/97-11", "campo_nome": "Abalone",
                         "corrente": "Ostra", "valor_rs_m3": Decimal("1640.86922")}
    # dado bruto: o contrato "#N/D" publicado pela ANP fica como veio; a resolução é do ETL 2
    assert {ln["contrato"] for ln in linhas[5:]} == {"#N/D"}


def test_preco_minimo_2009_mantem_a_grafia():
    linhas = list(leitores.ler_preco(AMOSTRAS / "precominpetro_2009.csv"))
    assert len(linhas) == 5
    assert linhas[0]["periodo"] == date(2009, 1, 1)
    assert linhas[2]["campo_nome"] == "agua grande"  # minúsculas e sem acento, como a ANP publicou


def test_preco_minimo_extraido_dos_pdfs():
    linhas = list(leitores.ler_preco_minimo_extraido(AMOSTRAS / "preco-minimo-petroleo-2005-2008.csv"))
    assert len(linhas) == 5
    assert linhas[0] == {"periodo": date(2005, 1, 1), "contrato": "48000.003629/97-43", "campo_nome": "ÁGUA GRANDE",
                         "corrente": "Baiano Mistura", "valor_rs_m3": Decimal("711.2281")}


# ---------- coordenadas (camadas georreferenciadas da ANP) ----------

def test_coordenada_de_poco():
    linhas = list(leitores.ler_coordenada_poco(AMOSTRAS / "POCOS_SIRGAS.csv"))
    assert len(linhas) == 6
    poco = next(ln for ln in linhas if ln["poco"] == "7-ET-994-RN")
    assert poco["geometria_wkt"].startswith("POINT (-3")  # longitude e latitude em SIRGAS 2000, como a ANP publica


def test_contorno_de_campo_com_a_grafia_da_camada():
    linhas = list(leitores.ler_coordenada_campo(AMOSTRAS / "CAMPOS_PRODUCAO_SIRGAS.csv"))
    assert len(linhas) == 3
    estreito = next(ln for ln in linhas if ln["campo"] == "ESTREITO")
    assert estreito["bacia"] == "Potiguar" and estreito["geometria_wkt"].startswith("POLYGON ((")
    # dado bruto: a bacia com o hífen oculto (\xad) fica como veio; a unificação é do ETL 2
    assert any("\xad" in ln["bacia"] for ln in linhas)
