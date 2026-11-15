"""Pipeline completo (pipeline.py) e a recarga com dados novos, em bancos temporários.

Premissas: [autor] o pipeline é sempre o mesmo e só a carga de dados muda; nada é substituído na stage
(versões, C05/T17); arquivo repetido não é carregado de novo; o DW reflete a versão mais recente; a base
oficial (st_anp / dw_anp) nunca é alterada pelos testes.
"""

import psycopg
import pytest

import pipeline
from etl.python.etl1.config import conninfo
from etl.python.etl2 import validacao

from .conftest import AMOSTRAS, RAIZ, valor

pytestmark = pytest.mark.integracao

DW = RAIZ / "database" / "dw"
NOVO_DOWNLOAD = "2026-02-01"


@pytest.fixture
def bancos(novo_banco, dados_teste, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "LOG", tmp_path / "logs" / "pipeline.log")
    # as listas de-para citam campos e empresas reais que não estão nas amostras (como em test_etl2_carga)
    validar = validacao.validar
    def sem_de_para(*a):
        erros, info = validar(*a)
        return [e for e in erros if not e.startswith("listas de-para")], info
    monkeypatch.setattr(validacao, "validar", sem_de_para)
    st = novo_banco()
    dw = novo_banco(ddl=None)
    with psycopg.connect(conninfo(dw)) as c:
        c.execute((DW / "dim_data.sql").read_text(encoding="utf-8"))
        c.execute((DW / "criar_tabelas.sql").read_text(encoding="utf-8"))
    return st, dw, dados_teste


def rodar(st, dw, *extra):
    return pipeline.main(["--stage", st, "--dw", dw, *extra])


def operador(dw, poco, sk_data):
    return valor(dw, """SELECT e.nm_empresa FROM ft_producao f JOIN dim_poco p USING (sk_poco)
                        JOIN dim_empresa e USING (sk_empresa) WHERE p.nk_poco = %s AND f.sk_data = %s""", [poco, sk_data])


def test_pipeline_carrega_stage_e_dw_e_grava_o_log(bancos):
    st, dw, _ = bancos
    assert rodar(st, dw) == 0
    assert valor(st, "SELECT count(*) FROM producao_mensal") == 34
    assert valor(dw, "SELECT count(*) FROM ft_producao") == 34
    log = pipeline.LOG.read_text(encoding="utf-8")
    assert "pipeline concluído" in log and "Validação stage x DW" in log


def test_motor_pdi_nao_roda_pelo_pipeline(bancos):
    """[autor] O PDI reproduz só o ETL 2, pelo próprio Job; o pipeline recusa --motor pdi sem tocar na stage."""
    st, dw, _ = bancos
    assert rodar(st, dw, "--motor", "pdi") == 2
    assert valor(st, "SELECT count(*) FROM carga") == 0


def test_recarga_com_arquivo_repetido_mes_novo_e_revisao_da_anp(bancos):
    st, dw, dados = bancos
    assert rodar(st, dw) == 0
    cargas = valor(st, "SELECT count(*) FROM carga")

    # 1) mesmos arquivos de novo: só as tentativas são registradas; DW igual
    assert rodar(st, dw) == 0
    assert valor(st, "SELECT count(*) FROM carga WHERE situacao = 'carregada'") == cargas
    assert valor(st, "SELECT count(*) FROM producao_mensal") == 34
    assert valor(dw, "SELECT count(*) FROM ft_producao") == 34
    assert valor(dw, "SELECT max(etl_versao) FROM dim_poco") == 1

    # 2) novo download pela CDP: revisão de 12/2023 (troca do nome do operador num poço, como a ANP fez com
    #    Néon Energia -> Galo de Campina) e um mês novo (01/2024)
    original = (AMOSTRAS / "L48_2023_12_producao_Terra.csv").read_bytes().decode("latin1")
    cabecalho, *linhas = original.splitlines(keepends=True)
    revisado = [linhas[0].replace(";3R Potiguar;", ";Galo de Campina;", 1)] + linhas[1:]
    cdp = dados / "raw" / "anp" / "producao-por-poco-cdp" / NOVO_DOWNLOAD
    cdp.mkdir(parents=True)
    (cdp / "2023_12_producao_Terra.csv").write_bytes((cabecalho + "".join(revisado)).encode("latin1"))
    (cdp / "2024_01_producao_Terra.csv").write_bytes(original.replace(";2023/12;", ";2024/01;").encode("latin1"))
    assert rodar(st, dw) == 0

    # stage: a versão anterior fica preservada; só a linha que mudou ganha versão nova (+1) e o mês novo entra (+6)
    assert valor(st, "SELECT count(*) FROM producao_mensal") == 34 + 1 + 6
    assert valor(st, """SELECT count(*) FROM producao_mensal m JOIN poco p USING (id_poco)
                        WHERE p.nome_anp = '7-ET-994-RN' AND m.periodo = '2023-12-01'""") == 2
    # DW: a versão mais recente vale, e o mês novo aparece
    assert valor(dw, "SELECT count(*) FROM ft_producao") == 34 + 6
    assert operador(dw, "7-ET-994-RN", 20231201) == "Galo de Campina"
    assert operador(dw, "7-ET-995-RN", 20231201) == "3R Potiguar"
    assert valor(dw, "SELECT count(*) FROM ft_producao WHERE sk_data = 20240101") == 6

    # 3) o mesmo download outra vez (mesmos bytes): nada muda
    assert rodar(st, dw) == 0
    assert valor(st, "SELECT count(*) FROM producao_mensal") == 41
    assert valor(dw, "SELECT count(*) FROM ft_producao") == 40
