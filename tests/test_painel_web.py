"""Painel web em Streamlit (painel_web/): as 4 telas, lendo o DW oficial (só leitura).

Premissas: [recomendação aceita] o painel lê somente o DW; cada pergunta (RQ) tem uma tela (rastreabilidade do
projeto); [autor] legendas para as siglas e unidades; os números batem com o DW (volumes do mês somados e médias diárias pelos dias do período).
"""

import os
import sys

import psycopg
import pytest

from etl.python.etl1.config import conninfo

from .conftest import RAIZ

pytestmark = pytest.mark.dados

PAINEL = RAIZ / "painel_web"
PAGINAS = ["campos_candidatos", "ficha_do_campo", "vendedores_e_socios", "trocas_de_operador"]


@pytest.fixture(scope="module", autouse=True)
def dw_disponivel():
    try:
        psycopg.connect(conninfo(os.environ.get("DW_DB", "dw_anp")), connect_timeout=3).close()
    except Exception:
        pytest.skip("DW indisponível")
    sys.path.insert(0, str(PAINEL))
    yield
    sys.path.remove(str(PAINEL))


@pytest.mark.parametrize("pagina", PAGINAS)
def test_tela_abre_sem_erro(pagina):
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(PAINEL / "paginas" / f"{pagina}.py"), default_timeout=180).run()
    assert not app.exception, [e.message for e in app.exception]
    assert len(app.metric) >= 4  # cada tela abre com os indicadores do topo


def test_totais_do_painel_batem_com_o_dw():
    import dados
    ind = dados.indicadores_campos.__wrapped__(12)
    with psycopg.connect(conninfo(os.environ.get("DW_DB", "dw_anp"))) as c:
        petroleo, receita = c.execute("""SELECT sum(md_petroleo_bbl), sum(md_receita_estimada_rs) FROM ft_producao
                                         WHERE sk_data BETWEEN 20230101 AND 20231231""").fetchone()
    assert ind["petroleo_ano"].sum() == pytest.approx(float(petroleo))
    assert ind["receita_ano"].sum() == pytest.approx(float(receita))
    estreito = ind.set_index("nk_campo").loc["ESTREITO|POTIGUAR"]
    assert estreito["operadora"] == "3R Potiguar" and estreito["dt_ultima_troca_operador"].strftime("%Y-%m") == "2023-05"


def test_participacao_soma_100_por_contrato():
    import dados
    soc = dados.participacoes.__wrapped__()
    assert soc.groupby("nk_contrato")["participacao"].sum().round(4).eq(1).all()


def test_siglas_dos_titulos_estao_no_glossario():
    import estilo
    textos = " ".join((PAINEL / "paginas" / f"{p}.py").read_text(encoding="utf-8") for p in PAGINAS)
    for sigla in ("bbl/dia", "BSW", "RGO", "m³", "Poço parado", "Receita estimada", "Preço", "Variação anual"):
        assert sigla in estilo.SIGLAS, sigla
    assert "estilo.legenda(" in textos and "glossario_lateral" in (PAINEL / "app.py").read_text(encoding="utf-8")


# ---------- idioma do painel [autor, 24/10/2026]: botão PT | EN, português por padrão ----------

def _chamadas_de_traducao():
    import ast
    for arquivo in list(PAINEL.glob("*.py")) + list((PAINEL / "paginas").glob("*.py")):
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Call) and getattr(no.func, "id", None) == "t" and no.args \
                    and isinstance(no.args[0], ast.Constant):
                yield arquivo.name, no.args[0].value


def test_todo_texto_traduzido_tem_versao_em_ingles():
    import re
    import idioma
    faltam = [(a, s) for a, s in _chamadas_de_traducao() if s not in idioma.EN]
    assert faltam == []
    campos = lambda s: sorted(re.findall(r"{(\w+)}", s))  # noqa: E731
    assert [k for k, v in idioma.EN.items() if campos(k) != campos(v)] == []
    assert set(idioma.SIGLAS_EN) == set(__import__("estilo").SIGLAS)


@pytest.mark.parametrize("pagina", PAGINAS)
def test_tela_abre_em_ingles(pagina):
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(PAINEL / "paginas" / f"{pagina}.py"), default_timeout=180)
    app.session_state["idioma"] = "en"
    app.run()
    assert not app.exception, [e.message for e in app.exception]
    rotulos = " ".join(m.label for m in app.metric)
    assert not any(p in rotulos for p in ("Campos", "Petróleo", "Trocas", "Operadoras")), rotulos


def test_app_abre_pelo_link_em_ingles():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(PAINEL / "app.py"), default_timeout=180)
    app.query_params["lang"] = "en"
    app.run()
    assert not app.exception, [e.message for e in app.exception]
    assert app.session_state["idioma"] == "en"
    assert {"Region", "State"} <= {s.label for s in app.sidebar.selectbox}


def test_filtro_de_regiao_e_estado():
    # [autor, 15/11/2026] o recorte geográfico é a região e o estado do IBGE de cada campo (o estado com mais produção
    # dos seus poços); escolhido um estado, as telas só mostram os campos dele
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(PAINEL / "paginas" / "campos_candidatos.py"), default_timeout=180)
    app.session_state["regiao"] = "Nordeste"
    app.session_state["estado"] = "SE"
    app.run()
    assert not app.exception, [e.message for e in app.exception]
    import dados
    campos = dados.campos.__wrapped__()
    assert set(campos.loc[campos["sg_estado"] == "SE", "nm_regiao"]) == {"Nordeste"}
    assert campos.loc[campos["nk_campo"] == "CARMOPOLIS|SERGIPE", "sg_estado"].item() == "SE"
    assert (campos["sg_estado"] != "NA").all()


# ---------- ano de referência [autor, 24/10/2026]: qualquer ano da série, o último como padrão ----------

def test_indicadores_do_ano_escolhido_batem_com_o_dw():
    import dados
    ind = dados.indicadores_campos.__wrapped__(12, 2022)
    with psycopg.connect(conninfo(os.environ.get("DW_DB", "dw_anp"))) as c:
        petroleo, receita = c.execute("""SELECT sum(md_petroleo_bbl), sum(md_receita_estimada_rs) FROM ft_producao
                                         WHERE sk_data BETWEEN 20220101 AND 20221231""").fetchone()
    assert ind["petroleo_ano"].sum() == pytest.approx(float(petroleo))
    assert ind["receita_ano"].sum() == pytest.approx(float(receita))
    assert dados.anos_com_dados()[0] == dados.mes_de_referencia().year  # o padrão é o último ano com dados
    assert dados.indicadores_campos.__wrapped__(12, 2005)["variacao_anual"].isna().all()  # 2005 não tem ano anterior


def test_petroleo_antes_de_parar_e_a_media_dos_12_meses_ate_o_ultimo_mes():
    # [autor] RQ-04: a lista de poços parados mostra quanto o poço produzia antes de parar
    import dados
    import pandas as pd
    p = dados.pocos.__wrapped__(pd.Timestamp("2023-12-01")).set_index(["nk_poco", "nk_campo"])
    poco = p.loc[("7-CP-1087-SE", "CARMOPOLIS|SERGIPE")]
    with psycopg.connect(conninfo(os.environ.get("DW_DB", "dw_anp"))) as c:
        petroleo = c.execute("""SELECT sum(f.md_petroleo_bbl) FROM ft_producao f JOIN dim_poco p USING (sk_poco)
                                JOIN dim_campo c USING (sk_campo)
                                WHERE p.nk_poco = '7-CP-1087-SE' AND c.nk_campo = 'CARMOPOLIS|SERGIPE'
                                  AND f.sk_data BETWEEN 20050101 AND 20050201""").fetchone()[0]
    assert poco["ultimo_mes"] == pd.Timestamp("2005-02-01")
    assert poco["petroleo_antes_bbl_dia"] == pytest.approx(float(petroleo) / 59)  # jan + fev/2005 (a série começa em 2005)


@pytest.mark.parametrize("pagina", PAGINAS[:3])
def test_tela_abre_com_um_ano_antigo(pagina):
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(PAINEL / "paginas" / f"{pagina}.py"), default_timeout=180)
    app.session_state["ano"] = 2015
    app.run()
    assert not app.exception, [e.message for e in app.exception]


def test_operadora_antes_da_troca_e_a_do_ultimo_mes_com_producao():
    # [autor] RQ-07: ILHA PEQUENA produziu com a Petrobras até 10/2022, ficou parada em 11/2022 e voltou com a Carmo em
    # 12/2022; a operadora "antes" é a do último mês com produção, e não a do mês anterior à troca (que ficaria vazia)
    import dados
    trocas = dados.trocas_de_operador.__wrapped__("Vendas").set_index("nm_campo")
    for campo in ("ILHA PEQUENA", "ANGELIM"):
        assert trocas.loc[campo, "operadora_antes"] == "Petrobras", campo
        assert trocas.loc[campo, "operadora_depois"] == "Carmo", campo


def test_ficha_mostra_a_producao_anual_de_todos_os_fluidos():
    # [autor] RQ-01 e RQ-02: óleo, condensado, petróleo, gás associado, não associado e total, água e as variações do
    # petróleo e do gás, ano a ano, desde 2005
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(PAINEL / "paginas" / "ficha_do_campo.py"), default_timeout=180)
    app.session_state["campo"] = "CARMOPOLIS|SERGIPE"
    app.run()
    assert not app.exception, [e.message for e in app.exception]
    tabela = next(df.value for df in app.dataframe if "gas_nao_assoc" in df.value.columns)
    assert {"oleo", "condensado", "petroleo", "gas_assoc", "gas_total", "agua", "var_petroleo", "var_gas"} <= set(tabela.columns)
    assert tabela["ano"].min() == 2005 and tabela["ano"].max() == 2023
    linha = tabela.set_index("ano").loc[2023]
    assert linha["petroleo"] == pytest.approx(3656.8, abs=0.1)  # Carmópolis em 2023 (bbl/dia)
    assert linha["var_petroleo"] == pytest.approx(0.967, abs=0.001)
