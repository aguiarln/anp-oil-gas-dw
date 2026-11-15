"""ETL 2 no Pentaho PDI (etl/pdi/) e a conferência com o motor em Python (etl/comparacao/).

Premissas: [autor] o PDI reproduz o ETL 2 do Python, gravando no DW gêmeo dw_anp_pdi, com uma
transformação por dimensão, as fatos e um Job; [autor] nenhuma senha em arquivo versionado; [autor] a
conferência Python × PDI aprova a carga.
"""

import os
import re
import xml.dom.minidom

import psycopg
import pytest
from dotenv import dotenv_values

from etl.python.etl1.config import conninfo

from .conftest import RAIZ

PDI = RAIZ / "etl" / "pdi"
TRANSFORMACOES = ["tr_01_extracao", "tr_02_de_para", "tr_03_dim_empresa", "tr_04_dim_contrato", "tr_05_dim_campo",
                  "tr_06_dim_poco", "tr_07_dim_instalacao", "tr_08_dim_corrente", "tr_09_ft_producao", "tr_10_ft_participacao"]


@pytest.mark.regras
def test_arquivos_do_pdi_sao_xml_valido():
    arquivos = list(PDI.glob("etl2/*.ktr")) + list(PDI.glob("jobs/*.kjb"))
    assert sorted(a.stem for a in PDI.glob("etl2/*.ktr")) == TRANSFORMACOES
    for a in arquivos:
        xml.dom.minidom.parse(str(a))


@pytest.mark.regras
def test_job_encadeia_todas_as_transformacoes_na_ordem():
    job = (PDI / "jobs" / "job_etl2.kjb").read_text(encoding="utf-8")
    assert "<name>START</name>" in job and "00_area_de_trabalho.sql" in job
    posicoes = [job.index(f"/../etl2/{t}.ktr") for t in TRANSFORMACOES]
    assert posicoes == sorted(posicoes)
    # aceita o XML compacto do gerador e o indentado que o Spoon grava ao salvar o Job
    destinos = [b for _, b in re.findall(r"<hop>\s*<from>([^<]+)</from>\s*<to>([^<]+)</to>", job)]
    assert [d for d in destinos if d.startswith("tr_")] == TRANSFORMACOES and destinos[-1] == "Sucesso"
    # tabelas recém-carregadas precisam de estatísticas (ANALYZE) antes das consultas pesadas
    assert destinos.index("Estatísticas da área de trabalho") == destinos.index("tr_03_dim_empresa") - 1
    assert destinos.index("Estatísticas das dimensões") == destinos.index("tr_09_ft_producao") - 1


@pytest.mark.regras
def test_dimensoes_usam_scd2_do_pdi():
    # [autor] todas as dimensões versionadas; no PDI, o passo Dimension lookup/update (a corrente é por período, T19)
    for t in TRANSFORMACOES[2:7]:
        assert "<type>DimensionLookup</type>" in (PDI / "etl2" / f"{t}.ktr").read_text(encoding="utf-8"), t
    assert "<type>InsertUpdate</type>" in (PDI / "etl2" / "tr_08_dim_corrente.ktr").read_text(encoding="utf-8")


@pytest.mark.regras
def test_nenhuma_senha_nos_arquivos_do_pdi():
    env = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}
    senha = env.get("PGPASSWORD")
    # como em test_regras_projeto: se a senha for uma palavra comum (o usuário "postgres"), só as atribuições contam
    comum = senha in (env.get("PGUSER"), "postgres")
    for a in PDI.rglob("*"):
        if a.is_file():
            texto = a.read_text(encoding="utf-8", errors="ignore")
            for conexao in re.findall(r"<password>([^<]*)</password>", texto):
                assert conexao == "${PG_SENHA}", a.name
            if senha:
                assert not re.search(r"(?i)(pg_?senha|password|senha)\s*[=:]\s*" + re.escape(senha), texto), a.name
                assert comum or senha not in texto, a.name


def _dw_pdi_carregado() -> bool:
    try:
        with psycopg.connect(conninfo(os.environ.get("DW_DB_PDI", "dw_anp_pdi")), connect_timeout=3) as c:
            return c.execute("SELECT count(*) FROM ft_producao").fetchone()[0] > 0
    except Exception:
        return False


@pytest.mark.dados
def test_pdi_reproduz_o_etl2_em_python():
    if not _dw_pdi_carregado():
        pytest.skip("DW gêmeo do PDI vazio ou indisponível: rode etl/pdi/jobs/job_etl2.kjb")
    from etl.comparacao.comparar import comparar
    with psycopg.connect(conninfo(os.environ.get("DW_DB", "dw_anp"))) as py, \
            psycopg.connect(conninfo(os.environ.get("DW_DB_PDI", "dw_anp_pdi"))) as pdi:
        assert comparar(py, pdi) == 0
