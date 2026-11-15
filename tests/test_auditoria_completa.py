"""Auditoria completa (~10 min): os brutos da ANP geram exatamente a base origem entregue, e a stage recriada
pelos CSVs reconhece todos os arquivos já carregados. Rode antes da entrega com: pytest -m lento

Premissas [autor]: quem revisa chega ao mesmo banco pelos CSVs e pode auditar o ETL 1; outra pessoa
consegue baixar dados novos da ANP e atualizar o pipeline. A amostra da CDP (12/2023, terra, exportada
em 01/10/2026) faz parte da base desde 17/10/2026, com as 34 linhas revisadas pela ANP.
"""

import pytest

from etl.python.etl1 import exportar

from .conftest import RAIZ, rodar_etl1, valor
from .test_base_origem import _carregar_base

pytestmark = [pytest.mark.lento, pytest.mark.integracao]

BASE_ORIGEM = RAIZ / "dist" / "base-origem"
RAW = RAIZ / "data" / "raw" / "anp"


@pytest.fixture(autouse=True)
def _pre_requisitos():
    if not RAW.exists():
        pytest.skip("brutos da ANP ausentes em data/raw/anp")
    if not (BASE_ORIGEM / "manifesto.csv").exists():
        pytest.skip("dist/base-origem ainda não gerada")


def test_etl1_sobre_os_brutos_gera_a_base_origem(banco):
    assert rodar_etl1(banco, "--ate", "2026-10-17") == 0
    assert exportar.main([str(BASE_ORIGEM), "--conferir", "--banco", banco]) == 0


def test_stage_recriada_reconhece_os_arquivos_ja_carregados(banco):
    # a stage recriada pelos CSVs sabe o que já foi carregado (hash na tabela carga): rodar o ETL 1 de novo
    # não grava nada, só registra as tentativas; um arquivo novo da ANP entraria como carga nova
    _carregar_base(banco, BASE_ORIGEM)
    linhas = valor(banco, "SELECT count(*) FROM producao_mensal")
    assert rodar_etl1(banco, "--ate", "2026-10-17") == 0
    assert valor(banco, "SELECT count(*) FROM carga WHERE situacao = 'repetida'") == 378
    assert valor(banco, "SELECT count(*) FROM producao_mensal") == linhas
