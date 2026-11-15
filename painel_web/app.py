"""Painel web (Streamlit) dos campos maduros de petróleo e gás: as 4 telas, lendo o Data Warehouse.

Uso (na raiz do projeto): .venv/Scripts/python -m painel_web
"""
import streamlit as st

import dados
import estilo
import idioma
from idioma import t

idioma.seletor()
st.set_page_config(page_title=t("Campos maduros de petróleo e gás"), page_icon="🛢️", layout="wide")
estilo.aplicar_css()

paginas = st.navigation([
    st.Page("paginas/campos_candidatos.py", title=t("1. Campos candidatos"), icon="🎯", default=True),
    st.Page("paginas/ficha_do_campo.py", title=t("2. Ficha do campo"), icon="📋"),
    st.Page("paginas/vendedores_e_socios.py", title=t("3. Vendedores e sócios"), icon="🤝"),
    st.Page("paginas/trocas_de_operador.py", title=t("4. Trocas de operador"), icon="🔄"),
])

estilo.barra_lateral()
# recorte geográfico: região e estado do IBGE de cada campo (o estado com mais produção dos seus poços)
geo = dados.campos()[["nm_regiao", "sg_estado"]].query("nm_regiao != 'N/A'")
regioes = [dados.TODAS] + sorted(geo["nm_regiao"].unique())
st.session_state.setdefault("regiao", dados.TODAS)
st.session_state.setdefault("estado", dados.TODOS)
st.session_state.setdefault("meses_parado", 12)
traduz_todos = lambda x: t(x) if x in (dados.TODAS, dados.TODOS) else x  # nomes de região e siglas não são traduzidos
st.session_state["regiao"] = st.sidebar.selectbox(
    t("Região"), regioes, index=regioes.index(st.session_state["regiao"]), key=idioma.chave("regiao"), format_func=traduz_todos)
ufs = geo if st.session_state["regiao"] == dados.TODAS else geo[geo["nm_regiao"] == st.session_state["regiao"]]
estados = [dados.TODOS] + sorted(ufs["sg_estado"].unique())
if st.session_state["estado"] not in estados:
    st.session_state["estado"] = dados.TODOS
st.session_state["estado"] = st.sidebar.selectbox(
    t("Estado"), estados, index=estados.index(st.session_state["estado"]), key=idioma.chave("estado"), format_func=traduz_todos)
anos = dados.anos_com_dados()
st.session_state.setdefault("ano", anos[0])  # o ano mais recente com dados é o padrão
st.sidebar.selectbox(t("Ano de referência"), anos, key="ano",
                     help=t("Ano dos indicadores das telas 1 a 3; por padrão, o último com dados."))
st.sidebar.slider(t("Poço parado: meses sem produção"), 1, 36, key="meses_parado",
                  help=t("Um poço é considerado parado se já produziu e está sem produção há pelo menos esses meses."))
estilo.glossario_lateral()
paginas.run()
