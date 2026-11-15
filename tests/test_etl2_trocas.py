"""Classificação das trocas de operador (T23): venda quando o grupo econômico muda; reorganização dentro do grupo.

Premissas: [autor] opção (a) de 22/10/2026: completar o grupo econômico das empresas que a ANP publica sem grupo
(de_para/grupos_economicos.csv, com a evidência de cada linha) e mostrar as vendas por padrão na tela de trocas.
"""

import csv
from datetime import date

import pytest

from etl.python.etl2 import de_para
from etl.python.etl2.dimensoes import ultimas_trocas
from etl.python.etl2.normalizacao import chave

pytestmark = pytest.mark.unidade

M = [date(2023, m, 1) for m in range(1, 13)]
GRUPO = {"PETROBRAS": "Sistema Petrobras", "3R MACAU": "3R Petroleum", "3R POTIGUAR": "3R Petroleum"}


def test_venda_quando_o_grupo_muda():
    meses = {M[0]: "PETROBRAS", M[1]: "PETROBRAS", M[2]: "3R MACAU"}
    assert ultimas_trocas(meses, GRUPO) == (M[2], M[2], None)


def test_reorganizacao_no_mesmo_grupo_nao_e_venda():
    # Petrobras -> 3R Macau (venda) e, depois, 3R Macau -> 3R Potiguar (mesmo grupo): a última venda continua a primeira
    meses = {M[0]: "PETROBRAS", M[3]: "3R MACAU", M[9]: "3R POTIGUAR"}
    assert ultimas_trocas(meses, GRUPO) == (M[9], M[3], M[9])


def test_empresa_sem_grupo_conta_como_grupo_proprio():
    assert ultimas_trocas({M[0]: "KARAVAN", M[1]: "SEACREST"}, {}) == (M[1], M[1], None)


def test_operador_nao_informado_nao_e_troca():
    # o "-" da fonte (sem operador) não gera troca na entrada nem na saída
    meses = {M[0]: "3R CANDEIAS S.A.", M[1]: "-", M[2]: "3R CANDEIAS S.A."}
    assert ultimas_trocas(meses, GRUPO) == (None, None, None)


def test_campo_sem_troca():
    assert ultimas_trocas({M[0]: "PETROBRAS", M[1]: "PETROBRAS"}, GRUPO) == (None, None, None)


def test_lista_de_grupos_tem_evidencia_e_grupos_conhecidos():
    caminho = de_para.PASTA / "grupos_economicos.csv"
    with open(caminho, encoding="utf-8", newline="") as f:
        linhas = list(csv.DictReader(f))
    assert linhas and all(l["evidencia"] in {"nome", "fonte pública", "revisão da ANP"} and l["fonte"].strip() for l in linhas)
    # toda linha de fonte pública traz o endereço da fonte
    assert all("http" in l["fonte"] for l in linhas if l["evidencia"] == "fonte pública")
    # uma empresa aparece uma vez só
    assert len({chave(l["empresa"]) for l in linhas}) == len(linhas)
    assert de_para.grupos_economicos()[chave("Potiguar E&P S.A.")] == ("Petrorecôncavo S.A.", "BRASIL")
