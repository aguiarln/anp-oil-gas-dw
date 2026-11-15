"""Tela 2: Ficha do campo (RQ-01 a RQ-05, RQ-07). Produção, declínio, maturidade, poços, receita e sócios de um campo."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import pydeck as pdk  # noqa: E402
import streamlit as st  # noqa: E402

import dados  # noqa: E402
import estilo  # noqa: E402
from estilo import num, pct, reais_mi  # noqa: E402
from idioma import t  # noqa: E402

estilo.aplicar_css()
ano = st.session_state.get("ano")  # ano de referência da barra lateral; sem escolha, o último com dados
ref = dados.mes_de_referencia(ano)
meses_parado = st.session_state.get("meses_parado", 12)
ind = dados.indicadores_campos(meses_parado, ano)
lista = dados.recorte(ind)
lista = lista.sort_values("nm_campo")
rotulos = (lista["nm_campo"] + " (" + lista["nm_bacia"] + ")").tolist()
chaves = lista["nk_campo"].tolist()
atual = st.session_state.get("campo", "ESTREITO|POTIGUAR")
nk = st.selectbox(t("Campo"), chaves, index=chaves.index(atual) if atual in chaves else 0,
                  format_func=lambda c: rotulos[chaves.index(c)])
st.session_state["campo"] = nk
info = ind[ind["nk_campo"] == nk].iloc[0]

serie = dados.producao_campo_mes_operadora()
serie = serie[serie["nk_campo"] == nk].copy()
mensal = dados.por_campo_mes()
mensal = mensal[mensal["nk_campo"] == nk].sort_values("mes")
mensal["bsw"] = mensal["agua"] / (mensal["petroleo"] + mensal["agua"]).where(lambda s: s > 0)
pocos = dados.pocos(ref)
pocos = pocos[pocos["nk_campo"] == nk]
ult12 = mensal[mensal["mes"] > ref - pd.DateOffset(months=12)]
troca = info["dt_ultima_venda"]
reorganizacao = info["dt_ultima_troca_operador"]

st.markdown(f"# {info['nm_campo']} <span style='font-size:1rem;color:{estilo.MEDIO}'>· {t('bacia {bacia}', bacia=info['nm_bacia'])} · "
            f"{info['ambiente']} · {info['nm_estado']} ({info['nm_regiao']})</span>", unsafe_allow_html=True)
extras = [t("dados até {mes}", mes=f"{ref:%m/%Y}"), t("operadora atual: **{op}**", op=info["operadora"])]
if pd.notna(troca):
    extras.append(t("última venda em {mes}", mes=f"{troca:%m/%Y}"))
if pd.notna(reorganizacao) and reorganizacao != troca:
    extras.append(t("reorganização no mesmo grupo em {mes}", mes=f"{reorganizacao:%m/%Y}"))
if pd.notna(info["nm_campo_atual"]) and info["nm_campo_atual"] != info["nm_campo"]:
    extras.append(t("nome atual: {nome}", nome=info["nm_campo_atual"]))
if pd.notna(info["nm_campo_sucessor"]) and info["nm_campo_sucessor"] != info["nm_campo"]:
    extras.append(t("unificado em: {nome}", nome=info["nm_campo_sucessor"]))
st.caption(" · ".join(extras))

k = st.columns(6)
ultimo = mensal[mensal["mes"] == ref]
k[0].metric(t("Petróleo em {mes}", mes=f"{ref:%m/%Y}"), t("{valor} bbl/dia", valor=num(ultimo["petroleo_bbl_dia"].sum())),
            help=estilo.sigla("bbl/dia"))
k[1].metric(t("Variação {ano} × {anterior}", ano=ref.year, anterior=ref.year - 1), pct(info["variacao_anual"], sinal=True),
            delta=t("bacia: {valor}", valor=pct(info["variacao_bacia"], sinal=True)), delta_color="off",
            help=estilo.sigla("Variação anual"))
k[2].metric(t("BSW (12 meses)"), pct(dados.bsw(ult12["agua"].sum(), ult12["petroleo"].sum())), help=estilo.sigla("BSW"))
k[3].metric(t("RGO (m³/m³)"), num(dados.rgo(ult12["gas_assoc"].sum(), ult12["oleo"].sum())), help=estilo.sigla("RGO"))
k[4].metric(t("Produtores / parados"), f"{num(info['pocos_produtores'])} / {num(info['pocos_parados'])}",
            help=t("Produtores em {mes}. {parado} ({meses} meses).", mes=f"{ref:%m/%Y}", parado=estilo.sigla("Poço parado"),
                   meses=meses_parado))
k[5].metric(t("Receita estimada {ano}", ano=ref.year), reais_mi(info["receita_ano"]), help=estilo.sigla("Receita estimada"))

esq, dir_ = st.columns([1.55, 1])
with esq:
    anual = serie.assign(ano=serie["mes"].dt.year).groupby(["ano", "nm_empresa"], as_index=False)["petroleo"].sum()
    # a série inteira, para ver o histórico em qualquer ano escolhido; os dias vão até o último mês da série
    fim_da_serie = dados.mes_de_referencia()
    anual["bbl_dia"] = anual.apply(lambda r: r["petroleo"] / dados.dias_no_ano(int(r["ano"]), fim_da_serie), axis=1)
    fig = px.bar(anual, x="ano", y="bbl_dia", color="nm_empresa", color_discrete_sequence=estilo.SEQUENCIA,
                 labels={"bbl_dia": t("petróleo (bbl/dia)"), "ano": "", "nm_empresa": t("operadora")})
    if pd.notna(troca):
        fig.add_vline(x=troca.year - 0.5, line_dash="dot", line_color=estilo.VERMELHO)
    st.plotly_chart(estilo.layout_grafico(fig, t("Produção de petróleo por ano e operadora (a troca aparece na mudança de cor)"), 290),
                    width="stretch")
    aba0, aba1, aba2 = st.tabs([t("Produção por ano"), t("Maturidade (BSW)"), t("Receita e preço")])
    with aba0:  # RQ-01 e RQ-02: todos os fluidos, como média diária de cada ano, e a variação anual do petróleo e do gás
        fluidos = ["oleo", "condensado", "petroleo", "gas_assoc", "gas_nao_assoc", "gas_total", "agua"]
        por_ano = mensal.assign(ano=mensal["mes"].dt.year).groupby("ano", as_index=False)[fluidos].sum()
        dias = por_ano["ano"].map(lambda a: dados.dias_no_ano(int(a), fim_da_serie))
        variacao = por_ano[["petroleo", "gas_total"]].pct_change().where(por_ano[["petroleo", "gas_total"]].shift() > 0)
        por_ano[fluidos] = por_ano[fluidos].div(dias, axis=0)
        por_ano["var_petroleo"], por_ano["var_gas"] = variacao["petroleo"], variacao["gas_total"]
        rotulo = {"oleo": t("Óleo"), "condensado": t("Condensado"), "petroleo": t("Petróleo"), "gas_assoc": t("Gás assoc."),
                  "gas_nao_assoc": t("Gás não assoc."), "gas_total": t("Gás total"), "agua": t("Água")}
        st.dataframe(por_ano.sort_values("ano", ascending=False), hide_index=True, width="stretch", height=220,
                     column_config={"ano": st.column_config.NumberColumn(t("Ano"), format="%d"),
                                    **{f: st.column_config.NumberColumn(rotulo[f], format="localized") for f in fluidos},
                                    "var_petroleo": st.column_config.NumberColumn(t("Var. petróleo"), format="percent"),
                                    "var_gas": st.column_config.NumberColumn(t("Var. gás"), format="percent")})
        st.markdown("<div class='legenda'>" + t("Médias diárias de cada ano: óleo, condensado, petróleo e água em bbl/dia; "
                                                "gás em mil m³/dia.") + "</div>", unsafe_allow_html=True)
    with aba1:
        g = go.Figure(go.Scatter(x=mensal["mes"], y=mensal["bsw"], line=dict(color=estilo.AMBAR, width=2), name="BSW"))
        g.update_yaxes(tickformat=".0%", range=[max(0, (mensal["bsw"].min() or 0) - 0.05), 1])
        st.plotly_chart(estilo.layout_grafico(g, t("BSW mensal: quanto mais água, mais maduro o campo"), 220), width="stretch")
        estilo.legenda("BSW")
    with aba2:
        rec = mensal.assign(ano=mensal["mes"].dt.year).groupby("ano", as_index=False)[["receita", "petroleo_com_preco"]].sum()
        rec["preco"] = rec["receita"] / (rec["petroleo_com_preco"] * dados.BBL_M3).where(lambda s: s > 0)
        g = go.Figure(go.Bar(x=rec["ano"], y=rec["receita"] / 1e6, marker_color=estilo.ACO, name=t("receita (R$ mi)")))
        g.add_trace(go.Scatter(x=rec["ano"], y=rec["preco"], yaxis="y2", line=dict(color=estilo.AMBAR, width=2), name=t("preço médio (R$/m³)")))
        g.update_layout(yaxis=dict(title=t("R$ milhões")), yaxis2=dict(title="R$/m³", overlaying="y", side="right", showgrid=False))
        g.add_vline(x=2017.5, line_dash="dot", line_color=estilo.GRAFITE)
        g.add_annotation(x=2017.5, y=1, yref="paper", text=t(" preço mínimo → referência"), showarrow=False, font_size=10, xanchor="left")
        st.plotly_chart(estilo.layout_grafico(g, t("Receita estimada por ano e preço médio do petróleo"), 220), width="stretch")
        estilo.legenda("Receita estimada", "Preço")
with dir_:
    st.markdown(f"**{t('Mapa: contorno do campo e poços')}** <span style='color:{estilo.TEAL}'>● {t('produtor')}</span> "
                f"<span style='color:{estilo.VERMELHO}'>● {t('parado há {meses}+ meses', meses=meses_parado)}</span> "
                f"<span style='color:#94A3B8'>● {t('sem produção recente')}</span>", unsafe_allow_html=True)
    corte = ref - pd.DateOffset(months=meses_parado)
    mapa = pocos.dropna(subset=["nr_latitude"]).copy()
    mapa["situacao"] = "sem produção recente"
    mapa.loc[mapa["ultimo_mes"] == ref, "situacao"] = "produtor"
    mapa.loc[mapa["ultimo_mes"] <= corte, "situacao"] = "parado"
    cores = {"produtor": [15, 118, 110, 220], "parado": [185, 28, 28, 200], "sem produção recente": [148, 163, 184, 200]}
    mapa["cor"] = mapa["situacao"].map(cores)
    mapa["situacao"] = mapa["situacao"].map(t)
    mapa["ultimo"] = mapa["ultimo_mes"].dt.strftime("%m/%Y")
    camadas = [pdk.Layer("PolygonLayer", [{"contorno": a} for a in dados.aneis_wkt(info["desc_contorno_wkt"])],
                         get_polygon="contorno", get_fill_color=[31, 78, 121, 40], get_line_color=[11, 31, 58], line_width_min_pixels=2),
               pdk.Layer("ScatterplotLayer", mapa, get_position="[nr_longitude, nr_latitude]", get_fill_color="cor",
                         get_radius=60, radius_min_pixels=3, pickable=True)]
    lat = float(mapa["nr_latitude"].mean()) if len(mapa) else float(info["nr_latitude_centro"]) if pd.notna(info["nr_latitude_centro"]) else -12.0
    lon = float(mapa["nr_longitude"].mean()) if len(mapa) else float(info["nr_longitude_centro"]) if pd.notna(info["nr_longitude_centro"]) else -40.0
    st.pydeck_chart(pdk.Deck(layers=camadas, map_style="light", tooltip={"text": t("{poco}\n{situacao}, último mês com produção: {ultimo}", poco="{nk_poco}", situacao="{situacao}",
                                                                  ultimo="{ultimo}")},
                             initial_view_state=pdk.ViewState(latitude=lat, longitude=lon, zoom=10.3)), height=260)
    if pd.isna(info["desc_contorno_wkt"]):
        st.markdown("<div class='legenda'>" + t("A ANP não publica o contorno deste campo; o mapa mostra só os poços.") + "</div>",
                    unsafe_allow_html=True)
    s1, s2 = st.tabs([t("Sócios dos contratos"), t("Poços parados")])
    with s1:
        contratos = dados.contratos_dos_campos(ref.year)
        soc = dados.participacoes()
        soc = soc[soc["nk_contrato"].isin(contratos.loc[contratos["nk_campo"] == nk, "nk_contrato"])]
        st.dataframe(soc.assign(papel=soc["operadora"].map({True: t("operadora"), False: t("sócia")}))
                     [["nm_contrato", "nm_empresa", "participacao", "papel"]], hide_index=True, width="stretch", height=180,
                     column_config={"nm_contrato": t("Contrato"), "nm_empresa": t("Empresa"), "papel": t("Papel"),
                                    "participacao": st.column_config.ProgressColumn(t("Participação"), format="percent",
                                                                                    min_value=0, max_value=1)})
        if len(soc):
            st.markdown("<div class='legenda'>" + t("Foto da relação de concessionários da ANP de {data}.",
                                                    data=f"{soc['foto'].max():%d/%m/%Y}") + "</div>", unsafe_allow_html=True)
    with s2:
        par = pocos[pocos["ultimo_mes"] <= corte].sort_values("ultimo_mes", ascending=False)
        st.dataframe(par.assign(ultimo=par["ultimo_mes"].dt.strftime("%m/%Y"), antes=par["petroleo_antes_bbl_dia"].round(1))
                     [["nk_poco", "ultimo", "antes"]], hide_index=True, width="stretch", height=180,
                     column_config={"nk_poco": t("Poço"),
                                    "ultimo": st.column_config.TextColumn(t("Último mês"), help=t("Último mês com produção")),
                                    "antes": st.column_config.NumberColumn(
                                        t("Antes de parar (bbl/dia)"), format="localized",
                                        help=t("Petróleo médio do poço nos 12 meses até o último mês com produção: o "
                                               "tamanho da oportunidade de voltar a produzir nele."))})
        estilo.legenda("Poço parado")
