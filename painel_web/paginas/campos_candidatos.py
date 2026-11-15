"""Tela 1: Campos candidatos (RQ-09, RQ-02, RQ-03). Os campos comparados lado a lado, com o mapa dos contornos."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pydeck as pdk  # noqa: E402
import streamlit as st  # noqa: E402

import dados  # noqa: E402
import estilo  # noqa: E402
from estilo import num, reais_mi  # noqa: E402
from idioma import t  # noqa: E402

estilo.aplicar_css()
ano = st.session_state.get("ano")  # ano de referência da barra lateral; sem escolha, o último com dados
ref = dados.mes_de_referencia(ano)
ind = dados.indicadores_campos(st.session_state.get("meses_parado", 12), ano)
ind = dados.recorte(ind)

st.markdown(f"# {t('Campos candidatos')} <span style='font-size:1rem;color:{estilo.MEDIO}'>· {dados.rotulo_recorte()} · "
            f"{t('ano {ano}', ano=ref.year)}</span>",
            unsafe_allow_html=True)
st.caption(t("Quais campos merecem atenção? Compare produção, declínio, maturidade e receita, e abra a ficha do campo."))

# filtros da tela
f1, f2, f3, f4 = st.columns([1.2, 1, 1.4, 1.6])
bacias = f1.multiselect(t("Bacia"), sorted(ind["nm_bacia"].dropna().unique()), placeholder=t("Todas"))
ambientes = f2.multiselect(t("Ambiente"), sorted(ind["ambiente"].dropna().unique()), placeholder=t("Todos"))
operadoras = f3.multiselect(t("Operadora"), sorted({o for s in ind["operadora"].dropna() for o in s.split(", ")}),
                            placeholder=t("Todas"))
maximo = float(np.ceil(ind["petroleo_bbl_dia"].max() / 100) * 100) if len(ind) else 100.0
faixa = f4.slider(t("Faixa de produção de petróleo (bbl/dia)"), 0.0, maximo, (0.0, min(maximo, 5000.0)), step=50.0, format="%.0f",
                  help=t("Campos maduros de pequena e média produção são os candidatos típicos à venda para operadoras independentes."))
sel = ind[ind["petroleo_bbl_dia"].between(*faixa)]
if bacias:
    sel = sel[sel["nm_bacia"].isin(bacias)]
if ambientes:
    sel = sel[sel["ambiente"].isin(ambientes)]
if operadoras:
    sel = sel[sel["operadora"].fillna("").apply(lambda s: any(o in s.split(", ") for o in operadoras))]

k = st.columns(5)
k[0].metric(t("Campos na seleção"), num(len(sel)))
k[1].metric(t("Petróleo em {ano} (bbl/dia)", ano=ref.year), num(sel["petroleo_bbl_dia"].sum()), help=estilo.sigla("bbl/dia"))
k[2].metric(t("Campos em declínio"), t("{n} de {total}", n=num((sel["variacao_anual"] < 0).sum()),
                                       total=num(sel["variacao_anual"].notna().sum())), help=estilo.sigla("Variação anual"))
k[3].metric(t("Caem menos que a bacia"), num((sel["diferenca_bacia"] > 0).sum()),
            help=t("Campos cuja variação anual é melhor que a da sua bacia: os melhores candidatos."))
k[4].metric(t("Receita estimada {ano}", ano=ref.year), reais_mi(sel["receita_ano"].sum()), help=estilo.sigla("Receita estimada"))

esq, dir_ = st.columns([1.6, 1])
with esq:
    st.markdown("### " + t("Indicadores por campo"))
    tabela = sel[["nm_campo", "nm_bacia", "ambiente", "operadora", "petroleo_bbl_dia", "variacao_anual", "diferenca_bacia",
                  "bsw", "rgo", "pocos_produtores", "pocos_parados", "receita_ano", "dt_ultima_venda"]].copy()
    tabela["diferenca_bacia"] = (tabela["diferenca_bacia"] * 100).round(1)
    tabela["receita_ano"] = (tabela["receita_ano"] / 1e6).round(1)
    tabela[["petroleo_bbl_dia", "rgo"]] = tabela[["petroleo_bbl_dia", "rgo"]].round(0)
    tabela[["variacao_anual", "bsw"]] = tabela[["variacao_anual", "bsw"]].round(3)
    st.dataframe(tabela, hide_index=True, width="stretch", height=430, column_config={
        "nm_campo": st.column_config.TextColumn(t("Campo"), pinned=True),
        "nm_bacia": t("Bacia"), "ambiente": t("Ambiente"), "operadora": t("Operadora"),
        "petroleo_bbl_dia": st.column_config.NumberColumn(t("Petróleo (bbl/dia)"), format="localized"),
        "variacao_anual": st.column_config.NumberColumn(t("Variação anual"), format="percent"),
        "diferenca_bacia": st.column_config.NumberColumn(t("Diferença p/ bacia (p.p.)"), format="localized",
                                                         help=t("Variação anual do campo menos a da bacia, em pontos percentuais.")),
        "bsw": st.column_config.ProgressColumn("BSW", format="percent", min_value=0, max_value=1),
        "rgo": st.column_config.NumberColumn(t("RGO (m³/m³)"), format="localized"),
        "pocos_produtores": st.column_config.NumberColumn(t("Poços produtores"), format="%d"),
        "pocos_parados": st.column_config.NumberColumn(t("Poços parados"), format="%d"),
        "receita_ano": st.column_config.NumberColumn(t("Receita (R$ mi)"), format="localized"),
        "dt_ultima_venda": st.column_config.DateColumn(t("Última venda"), format="MM/YYYY",
                                                       help=t("Última troca de operador em que o grupo econômico mudou.")),
    })
    estilo.legenda("bbl/dia", "BSW", "RGO", "Variação anual")
    c1, c2 = st.columns([3, 1])
    escolhido = c1.selectbox(t("Abrir a ficha do campo"), sel["nm_campo"] + " (" + sel["nm_bacia"] + ")", index=None,
                             placeholder=t("Escolha um campo da seleção"))
    if c2.button(t("Abrir ficha"), width="stretch", disabled=escolhido is None):
        st.session_state["campo"] = sel.loc[(sel["nm_campo"] + " (" + sel["nm_bacia"] + ")") == escolhido, "nk_campo"].iat[0]
        st.switch_page("paginas/ficha_do_campo.py")
with dir_:
    st.markdown("### " + t("Mapa dos campos selecionados"))
    linhas = []
    escala = np.log1p(sel["petroleo_bbl_dia"].clip(lower=0))
    escala = (escala / escala.max()).fillna(0) if len(sel) and escala.max() > 0 else escala
    for (_, r), e in zip(sel.iterrows(), escala):
        for anel in dados.aneis_wkt(r["desc_contorno_wkt"]):
            linhas.append({"contorno": anel, "campo": r["nm_campo"], "producao": num(r["petroleo_bbl_dia"]),
                           "cor": [int(214 - 183 * e), int(228 - 150 * e), int(240 - 119 * e), 200]})
    camada = pdk.Layer("PolygonLayer", linhas, get_polygon="contorno", get_fill_color="cor", get_line_color=[11, 31, 58],
                       line_width_min_pixels=1, pickable=True)
    com_centro = sel.dropna(subset=["nr_latitude_centro"])
    vista = pdk.ViewState(latitude=float(com_centro["nr_latitude_centro"].mean()) if len(com_centro) else -12.0,
                          longitude=float(com_centro["nr_longitude_centro"].mean()) if len(com_centro) else -40.0,
                          # Brasil inteiro, uma região ou um estado
                          zoom={"brasil": 4.2, "regiao": 5.2, "estado": 6.3}[dados.nivel_do_recorte()])
    st.pydeck_chart(pdk.Deck(layers=[camada], map_style="light", initial_view_state=vista,
                             tooltip={"text": "{campo}\n{producao} " + t("bbl/dia")}), height=430)
    sem = len(sel) - sel["desc_contorno_wkt"].notna().sum()
    st.markdown("<div class='legenda'>" + t("Cor mais escura = mais produção (bbl/dia, escala logarítmica). "
                                            "{sem} campo(s) da seleção sem contorno publicado pela ANP.", sem=num(sem))
                + "</div>", unsafe_allow_html=True)
