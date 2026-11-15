"""Regras de uniformização do ETL 2 (T13, T14, T15, T20, T21)."""

import pytest

from etl.python.etl2 import de_para
from etl.python.etl2.normalizacao import centro, chave, chave_contrato, mais_frequente, ponto, sigla_pelo_nome_do_poco

pytestmark = pytest.mark.unidade


@pytest.mark.parametrize("a, b", [
    ("3R Petroleum", "3R PETROLEUM"),                      # T14 maiúsculas (ids 115 e 151 na stage)
    ("Cabiúnas Mistura", "cabiunas  mistura"),             # acento e espaços internos
    ("Espí\xadrito Santo", "Espírito Santo"),              # T20 hífen oculto da camada de contornos
    ("AnC_TARTARUGA_VERDE", "AnC_TARTARUGA VERDE"),        # sublinhado como espaço
])
def test_grafias_equivalentes_tem_a_mesma_chave(a, b):
    assert chave(a) == chave(b)


def test_chave_preserva_o_que_distingue_entidades():
    assert chave("FAZENDA BELÉM CE") != chave("FAZENDA BELÉM BA")
    assert chave(None) is None and chave("   ") is None


@pytest.mark.parametrize("bruto, esperado", [
    ("480000037939797", "480000037939797"), ("48000.003552/97-11", "480000035529711"),
    ("48610.07984/2004", "48610079842004"), ("-", None), (None, None),
    # T15: a letra final distingue contratos (BM-S-11 x BM-S-11A), em qualquer formato e caixa
    ("486100038862000A", "486100038862000A"), ("48610.003886/2000a", "486100038862000A"),
    ("48610001427/2008-39a", "48610001427200839A"), ("486100092272002B", "486100092272002B"),
    # sufixos maiores do arquivo de preço não fazem parte do contrato
    ("48610.010735/2001-IBU", "486100107352001"), ("48610009197/2005-11-mgn", "48610009197200511"),
])
def test_chave_do_contrato(bruto, esperado):
    assert chave_contrato(bruto) == esperado


@pytest.mark.parametrize("poco, sigla", [
    ("7-ET-994-RN", "RN"), ("3-BRSA-1017D-RJS", "RJ"), ("1-BRSA-658-SPS", "SP"), ("7-C-10-BA", "BA"), ("ANC-XYZ", None),
])
def test_estado_pelo_sufixo_do_poco(poco, sigla):
    assert sigla_pelo_nome_do_poco(poco, {"RN", "RJ", "SP", "BA"}) == sigla


def test_ponto_e_centro_das_geometrias():
    assert ponto("POINT (-35.9147941666 -9.614755)") == (-9.614755, -35.9147941666)
    lat, lon = centro("POLYGON ((0 0, 2 0, 2 2, 0 2, 0 0))")
    assert (round(lat, 6), round(lon, 6)) == (1.0, 1.0)
    assert ponto(None) is None and centro("LINESTRING (0 0, 1 1)") is None


def test_grafia_de_exibicao_e_a_mais_frequente():
    assert mais_frequente({"3R PETROLEUM": 885, "3R Petroleum": 45}) == "3R PETROLEUM"


def test_cadeia_de_campos_ate_o_ultimo_destino():
    eventos = de_para.campos()
    jandaia_sul = (chave("Jandaia Sul"), chave("Recôncavo"))
    assert de_para.resolver(jandaia_sul, eventos, {"renomeacao", "unificacao"}) == (chave("TANGARÁ"), chave("Recôncavo"))
    lula = (chave("LULA"), chave("Santos"))
    assert de_para.resolver(lula, eventos, {"renomeacao"}) == (chave("TUPI"), chave("Santos"))
    baleia = (chave("BALEIA AZUL"), chave("Campos"))
    assert de_para.resolver(baleia, eventos, {"renomeacao"}) == baleia  # unificação não muda o nome atual


def test_ciclo_na_lista_de_para_e_recusado():
    ciclo = [{"origem": ("A", "X"), "destino": ("B", "X"), "tipo": "renomeacao"},
             {"origem": ("B", "X"), "destino": ("A", "X"), "tipo": "renomeacao"}]
    with pytest.raises(ValueError, match="ciclo"):
        de_para.resolver(("A", "X"), ciclo, {"renomeacao"})


def test_listas_de_para_validas():
    empresas = de_para.empresas()
    assert empresas[chave("Potiguar")] == chave("Potiguar E&P S.A.")
    assert all(o != d for o, d in empresas.items())
    tipos = {e["tipo"] for e in de_para.campos()}
    assert tipos == {"renomeacao", "unificacao"}
