"""Tela 4: Trocas de operador (RQ-07). Os campos melhoraram depois de trocar de operador?"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

import dados  # noqa: E402
import estilo  # noqa: E402
from estilo import num, pct  # noqa: E402
import idioma  # noqa: E402
from idioma import t  # noqa: E402

estilo.aplicar_css()
tipo = st.session_state.get(idioma.chave("tipo_troca"), st.session_state.get("tipo_troca", "Vendas"))
st.session_state["tipo_troca"] = tipo
trocas = dados.trocas_de_operador(tipo)
trocas = dados.recorte(trocas)

st.markdown(f"# {t('Trocas de operador')} <span style='font-size:1rem;color:{estilo.MEDIO}'>· {dados.rotulo_recorte()}</span>",
            unsafe_allow_html=True)
st.caption(t("Os campos vendidos melhoraram com os novos operadores? Comparação da produção média nos 12 meses antes e "
             "depois da última venda de cada campo. Venda é a troca em que o grupo econômico da operadora muda; as "
             "reorganizações dentro do mesmo grupo (subsidiárias, mudanças de nome) aparecem escolhendo o tipo de troca."))

f0, f1, f2, f3 = st.columns([1, 1.3, 1, 1])
f0.selectbox(t("Tipo de troca"), list(dados.TIPOS_DE_TROCA), index=list(dados.TIPOS_DE_TROCA).index(tipo),
             key=idioma.chave("tipo_troca"), format_func=t,
             help=t("Venda: o grupo econômico da operadora muda. Reorganização: troca dentro do mesmo grupo, "
                    "como 3R Macau → 3R Potiguar ou uma mudança de nome revisada pela ANP."))
if trocas.empty:
    st.info(t("Nenhuma troca desse tipo com os filtros escolhidos."))
    st.stop()
anos = sorted(trocas["troca"].dt.year.unique())
faixa = f1.select_slider(t("Ano da troca"), options=anos, value=(anos[0], anos[-1])) if len(anos) > 1 else (anos[0], anos[0])
so_petrobras = f2.toggle(t("Só campos que saíram da Petrobras"), value=(tipo == "Vendas"))
completos = f3.toggle(t("Só com 12 meses depois da troca"), value=False,
                      help=t("Trocas recentes ainda não têm 12 meses de dados depois da troca."))
sel = trocas[trocas["troca"].dt.year.between(*faixa)]
if so_petrobras:
    sel = sel[sel["operadora_antes"].fillna("").str.upper().str.contains("PETROBRAS")]
if completos:
    sel = sel[sel["meses_depois"] >= 12]
sel = sel.dropna(subset=["variacao"])

k = st.columns(4)
k[0].metric(t("Trocas analisadas"), num(len(sel)))
k[1].metric(t("Campos que melhoraram"), f"{num((sel['variacao'] > 0).sum())} ({pct((sel['variacao'] > 0).mean() if len(sel) else float('nan'), 0)})")
med = sel["variacao"].median() if len(sel) else float("nan")
k[2].metric(t("Variação mediana da produção"), pct(med, sinal=True),
            help=t("Produção média (bbl/dia) dos 12 meses depois ÷ 12 meses antes da troca."))
k[3].metric(t("Variação mediana do BSW (p.p.)"), num((sel["bsw_depois"] - sel["bsw_antes"]).median() * 100, 1) if len(sel) else "—",
            help=estilo.sigla("BSW"))

esq, dir_ = st.columns([1, 1.25])
with esq:
    sel = sel.assign(resultado=sel["variacao"].gt(0).map({True: t("melhorou"), False: t("piorou")}))
    fig = px.scatter(sel, x="antes_bbl_dia", y="depois_bbl_dia", color="resultado", hover_name="nm_campo",
                     hover_data={"operadora_antes": True, "operadora_depois": True, "resultado": False},
                     color_discrete_map={t("melhorou"): estilo.TEAL, t("piorou"): estilo.VERMELHO}, log_x=True, log_y=True,
                     labels={"antes_bbl_dia": t("12 meses antes (bbl/dia)"), "depois_bbl_dia": t("12 meses depois (bbl/dia)"),
                             "resultado": ""})
    if len(sel):
        lo, hi = max(sel[["antes_bbl_dia", "depois_bbl_dia"]].min().min(), 0.1), sel[["antes_bbl_dia", "depois_bbl_dia"]].max().max()
        fig.add_shape(type="line", x0=lo, y0=lo, x1=hi, y1=hi, line=dict(dash="dot", color=estilo.GRAFITE))
    st.plotly_chart(estilo.layout_grafico(fig, t("Antes × depois: acima da diagonal, o campo melhorou"), 420), width="stretch")
    estilo.legenda("bbl/dia")
with dir_:
    st.markdown("### " + t("Campos com troca de operador"))
    tab = sel[["nm_campo", "nm_bacia", "troca", "operadora_antes", "operadora_depois", "antes_bbl_dia", "depois_bbl_dia",
               "variacao", "bsw_antes", "bsw_depois"]].copy()
    tab[["antes_bbl_dia", "depois_bbl_dia"]] = tab[["antes_bbl_dia", "depois_bbl_dia"]].round(0)
    tab[["variacao", "bsw_antes", "bsw_depois"]] = tab[["variacao", "bsw_antes", "bsw_depois"]].round(3)
    st.dataframe(tab, hide_index=True, width="stretch", height=420, column_config={
        "nm_campo": st.column_config.TextColumn(t("Campo"), pinned=True), "nm_bacia": t("Bacia"),
        "troca": st.column_config.DateColumn(t("Troca"), format="MM/YYYY"), "operadora_antes": t("Antes"),
        "operadora_depois": t("Depois"),
        "antes_bbl_dia": st.column_config.NumberColumn(t("Antes (bbl/dia)"), format="localized"),
        "depois_bbl_dia": st.column_config.NumberColumn(t("Depois (bbl/dia)"), format="localized"),
        "variacao": st.column_config.NumberColumn(t("Variação"), format="percent"),
        "bsw_antes": st.column_config.NumberColumn(t("BSW antes"), format="percent"),
        "bsw_depois": st.column_config.NumberColumn(t("BSW depois"), format="percent")})
    estilo.legenda("bbl/dia", "BSW")
