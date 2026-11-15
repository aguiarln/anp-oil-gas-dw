"""Tela 3: Vendedores e sócios (RQ-06, RQ-08). Quem opera os campos, quem pode vender e com quem negociar."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import plotly.express as px  # noqa: E402
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

st.markdown(f"# {t('Vendedores e sócios')} <span style='font-size:1rem;color:{estilo.MEDIO}'>· {dados.rotulo_recorte()} · "
            f"{ref:%m/%Y}</span>",
            unsafe_allow_html=True)
st.caption(t("Quem opera os campos hoje? As operadoras com muitos campos pequenos e os campos ainda com a Petrobras "
             "são os vendedores mais prováveis."))

# operadora de cada campo no mês de referência (um campo pode ter mais de uma operadora, por contrato)
prod = dados.producao_campo_mes_operadora()
atual = prod[(prod["mes"] == ref) & prod["nk_campo"].isin(ind["nk_campo"])]
limite = st.slider(t("Campo pequeno: produção de até (bbl/dia)"), 50, 5000, 1000, step=50,
                   help=t("Campos com produção de petróleo no último ano abaixo desse valor contam como pequenos."))
por_campo = ind.set_index("nk_campo")["petroleo_bbl_dia"]
op = atual.groupby(["nk_empresa", "nm_empresa", "nm_grupo_economico", "nm_pais"], dropna=False).agg(
    campos=("nk_campo", "nunique"), petroleo=("petroleo", "sum")).reset_index()
op["petroleo_bbl_dia"] = op["petroleo"] / ref.days_in_month
pequenos = atual.drop_duplicates(["nk_empresa", "nk_campo"]).assign(peq=lambda d: d["nk_campo"].map(por_campo) <= limite)
op = op.merge(pequenos.groupby("nk_empresa")["peq"].sum().rename("campos_pequenos"), on="nk_empresa", how="left")
op = op.sort_values("campos", ascending=False)
op["petroleo_bbl_dia"] = op["petroleo_bbl_dia"].round(0)

k = st.columns(4)
k[0].metric(t("Operadoras com produção"), num(len(op)))
petro = op[op["nm_empresa"].str.upper().str.startswith("PETROBRAS")]
k[1].metric(t("Campos ainda com a Petrobras"), num(petro["campos"].sum()))
k[2].metric(t("Operadoras com 5+ campos pequenos"), num((op["campos_pequenos"] >= 5).sum()))
k[3].metric(t("Receita estimada {ano}", ano=ref.year), reais_mi(ind["receita_ano"].sum()), help=estilo.sigla("Receita estimada"))

esq, dir_ = st.columns([1.15, 1])
with esq:
    top = op.head(15).sort_values("campos")
    fig = px.bar(top, y="nm_empresa", x=["campos_pequenos"], orientation="h", color_discrete_sequence=[estilo.ACO],
                 labels={"value": t("campos operados"), "nm_empresa": ""}, hover_data={"campos": True, "petroleo_bbl_dia": ":.0f"})
    fig.add_bar(y=top["nm_empresa"], x=top["campos"] - top["campos_pequenos"], orientation="h", marker_color="#7BA3CC",
                name=t("outros campos"))
    fig.data[0].name = t("campos pequenos (até {limite} bbl/dia)", limite=num(limite))
    fig.update_layout(barmode="stack", showlegend=True, legend_title_text="")
    st.plotly_chart(estilo.layout_grafico(fig, t("Operadoras com mais campos (as 15 maiores)"), 430), width="stretch")
    estilo.legenda("bbl/dia")
with dir_:
    st.markdown("### " + t("Operadoras"))
    st.dataframe(op[["nm_empresa", "nm_grupo_economico", "nm_pais", "campos", "campos_pequenos", "petroleo_bbl_dia"]],
                 hide_index=True, width="stretch", height=430, column_config={
                     "nm_empresa": st.column_config.TextColumn(t("Operadora"), pinned=True), "nm_grupo_economico": t("Grupo econômico"),
                     "nm_pais": t("País"), "campos": st.column_config.NumberColumn(t("Campos"), format="%d"),
                     "campos_pequenos": st.column_config.NumberColumn(t("Pequenos"), format="%d"),
                     "petroleo_bbl_dia": st.column_config.NumberColumn(t("Petróleo {mes} (bbl/dia)", mes=f"{ref:%m/%Y}"),
                                                                       format="localized")})

st.markdown("### " + t("Campos e sócios de uma operadora"))
nomes = op["nm_empresa"].tolist()
escolha = st.selectbox(t("Operadora"), nomes, index=nomes.index(petro["nm_empresa"].iat[0]) if len(petro) else 0)
chave = op.loc[op["nm_empresa"] == escolha, "nk_empresa"].iat[0]
seus = atual.loc[atual["nk_empresa"] == chave, "nk_campo"].unique()
c1, c2 = st.columns([1, 1.2])
with c1:
    campos_op = ind[ind["nk_campo"].isin(seus)][["nm_campo", "nm_bacia", "petroleo_bbl_dia", "bsw", "pocos_parados"]].copy()
    campos_op["petroleo_bbl_dia"] = campos_op["petroleo_bbl_dia"].round(0)
    st.dataframe(campos_op, hide_index=True, width="stretch", height=260, column_config={
        "nm_campo": t("Campo"), "nm_bacia": t("Bacia"),
        "petroleo_bbl_dia": st.column_config.NumberColumn(t("Petróleo (bbl/dia)"), format="localized"),
        "bsw": st.column_config.ProgressColumn("BSW", format="percent", min_value=0, max_value=1),
        "pocos_parados": st.column_config.NumberColumn(t("Poços parados"), format="%d")})
    estilo.legenda("BSW", "Poço parado")
with c2:
    contratos = dados.contratos_dos_campos(ref.year)
    ks = contratos.loc[contratos["nk_campo"].isin(seus), "nk_contrato"].unique()
    soc = dados.participacoes()
    soc = soc[soc["nk_contrato"].isin(ks)].sort_values(["nm_contrato", "participacao"], ascending=[True, False])
    st.dataframe(soc.assign(papel=soc["operadora"].map({True: t("operadora"), False: t("sócia")}))
                 [["nm_contrato", "nm_empresa", "participacao", "papel"]], hide_index=True, width="stretch", height=260,
                 column_config={"nm_contrato": t("Contrato"), "nm_empresa": t("Empresa"), "papel": t("Papel"),
                                "participacao": st.column_config.ProgressColumn(t("Participação"), format="percent",
                                                                                min_value=0, max_value=1)})
    if len(soc):
        st.markdown("<div class='legenda'>" + t("Sócios dos contratos desses campos na foto da ANP de {data}: "
                                                "com quem negociar, e se a compra seria do contrato inteiro ou de uma parte.",
                                                data=f"{soc['foto'].max():%d/%m/%Y}") + "</div>", unsafe_allow_html=True)
