"""Diagramas dos documentos (tools/diagramas/): gerados a partir do catálogo dos bancos oficiais, só leitura.

Premissas [autor]: o diagrama da stage (pé de galinha) e o modelo dimensional mostram todas as tabelas dos bancos;
as figuras podem ser geradas de novo depois de uma mudança no DDL.
"""

import os
import re

import psycopg
import pytest

from etl.python.etl1.config import conninfo

from .conftest import RAIZ

pytestmark = pytest.mark.dados

DIAGRAMAS = RAIZ / "tools" / "diagramas"


def _tabelas(banco):
    try:
        with psycopg.connect(conninfo(banco), connect_timeout=3) as c:
            return {t for (t,) in c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
    except Exception:
        pytest.skip(f"{banco} indisponível")


def test_diagrama_da_stage_mostra_todas_as_tabelas():
    codigo = (DIAGRAMAS / "er_stage.py").read_text(encoding="utf-8")
    pos = codigo.split("\nPOS = {", 1)[1].split("}", 1)[0]  # "GRUPOS = {" também contém "POS = {"
    assert set(re.findall(r'"(\w+)": \(\d', pos)) == _tabelas(os.environ.get("ST_DB", "st_anp"))


def test_modelo_dimensional_mostra_todas_as_tabelas():
    codigo = (DIAGRAMAS / "dw_estrelas.py").read_text(encoding="utf-8")
    assert set(re.findall(r'd\.tabela\("(\w+)"', codigo)) == _tabelas(os.environ.get("DW_DB", "dw_anp"))


def test_figuras_geradas_a_partir_do_catalogo(tmp_path):
    _tabelas(os.environ.get("DW_DB", "dw_anp"))
    import runpy
    gerar = runpy.run_path(str(DIAGRAMAS / "gerar.py"))
    assert gerar["main"]([str(tmp_path)]) == 0
    for png in ("oltp_diagrama_relacional.png", "dw_diagrama_estrela.png", "processo_bi_croqui.png"):
        assert (tmp_path / png).stat().st_size > 100_000, png
        assert (RAIZ / "docs" / "modelagem" / png).is_file(), png
