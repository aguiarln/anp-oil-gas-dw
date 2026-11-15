"""Identidade visual, formatos dos números (brasileiro ou americano, pelo idioma) e legendas das siglas do painel."""
import json
import math
from pathlib import Path

import streamlit as st

from idioma import SIGLAS_EN, atual, t

_CORES = json.loads((Path(__file__).resolve().parents[1] / "design" / "tokens.json").read_text(encoding="utf-8"))["cores"]
NAVY, ACO, MEDIO, GELO, GRAFITE = _CORES["navy"], _CORES["azul_aco"], _CORES["azul_medio"], _CORES["azul_gelo"], _CORES["grafite"]
TEAL, AMBAR, VERMELHO = "#0F766E", "#B7791F", "#B91C1C"
SEQUENCIA = [ACO, TEAL, AMBAR, MEDIO, NAVY, "#7BA3CC", "#5FA8A0", VERMELHO, "#94A3B8"]

SIGLAS = {
    "bbl": "barril de petróleo (1 bbl = 0,159 m³)",
    "bbl/dia": "barris por dia: o volume do período dividido pelos dias do período",
    "BSW": "Basic Sediment and Water: percentual de água e sedimentos no líquido produzido. Quanto mais água, mais maduro o campo",
    "RGO": "Razão Gás-Óleo: m³ de gás associado por m³ de óleo produzido; em alta, indica envelhecimento do reservatório",
    "m³": "metro cúbico; mil m³ = 1.000 m³ (unidade do gás natural)",
    "Petróleo": "óleo + condensado, como a ANP publica",
    "Poço parado": "poço que já produziu e está sem produção há pelo menos o número de meses escolhido",
    "Variação anual": "produção de petróleo do último ano comparada à do ano anterior; negativa = declínio",
    "Preço": "preço mínimo do petróleo (ANP) até 2017 e preço de referência a partir de 2018; as séries não são comparáveis",
    "Receita estimada": "petróleo produzido (m³) × preço do petróleo do campo no mês, em reais correntes",
    "ANP": "Agência Nacional do Petróleo, Gás Natural e Biocombustíveis",
    "WKT": "Well-Known Text: formato em que a ANP publica o contorno dos campos",
}


def sigla(nome: str) -> str:
    """Significado da sigla no idioma escolhido."""
    return (SIGLAS_EN if atual() == "en" else SIGLAS)[nome]


def configurar(titulo: str, icone: str = "🛢️"):
    st.set_page_config(page_title=titulo, page_icon=icone, layout="wide")
    aplicar_css()


def aplicar_css():
    st.markdown(f"""<style>
      .block-container {{padding-top: 1.4rem; padding-bottom: 0.5rem;}}
      h1 {{color: {NAVY}; font-size: 1.7rem !important; margin-bottom: 0;}}
      h3 {{color: {NAVY}; font-size: 1.05rem !important;}}
      [data-testid="stMetric"] {{background: white; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px 14px;}}
      [data-testid="stMetricLabel"] p {{font-size: 0.8rem; color: {GRAFITE};}}
      [data-testid="stMetricValue"] {{color: {NAVY}; font-size: 1.45rem;}}
      [data-testid="stSidebar"] {{background: {NAVY};}}
      [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3, [data-testid="stSidebar"] p,
      [data-testid="stSidebar"] label, [data-testid="stSidebar"] li, [data-testid="stSidebar"] span,
      [data-testid="stSidebar"] summary {{color: white !important;}}
      [data-testid="stSidebar"] [data-baseweb="select"] *, [data-testid="stSidebar"] [data-baseweb="tag"] * {{color: {NAVY} !important;}}
      [data-testid="stSidebar"] button[data-variant="segmented_control"] {{background: transparent !important; border-color: #FFFFFF80 !important;}}
      [data-testid="stSidebar"] button[data-variant="segmented_control"][aria-checked="true"] {{background: white !important; border-color: white !important;}}
      [data-testid="stSidebar"] button[data-variant="segmented_control"][aria-checked="true"] * {{color: {NAVY} !important;
        font-weight: 700;}}
      .legenda {{font-size: 0.78rem; color: #64748B; margin-top: -0.4rem;}}
    </style>""", unsafe_allow_html=True)


def barra_lateral():
    """Cabeçalho da barra lateral (em todas as telas)."""
    st.sidebar.markdown("## " + t("Campos maduros de petróleo e gás"))
    st.sidebar.caption(t("Produção, declínio, maturidade, receita e trocas de operador dos campos do Brasil"))


def glossario_lateral():
    with st.sidebar.expander(t("📖 Siglas e unidades")):
        for s in SIGLAS:
            st.markdown(f"**{t(s)}**: {sigla(s)}")
    st.sidebar.markdown("---")
    st.sidebar.caption(t("Fonte: dados públicos da ANP (2005–2023), Data Warehouse `dw_anp`."))


def legenda(*siglas: str):
    """Linha de legenda abaixo de um gráfico ou tabela, com as siglas usadas nele."""
    texto = " · ".join(f"<b>{t(s)}</b>: {sigla(s)}" for s in siglas)
    st.markdown(f"<div class='legenda'>{texto}</div>", unsafe_allow_html=True)


def _num(x, casas=0):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    if atual() == "en":
        return f"{x:,.{casas}f}"
    return f"{x:,.{casas}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def num(x, casas=0):
    return _num(x, casas)


def pct(x, casas=1, sinal=False):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    texto = f"{x * 100:+.{casas}f}%" if sinal else f"{x * 100:.{casas}f}%"
    return texto if atual() == "en" else texto.replace(".", ",")


def reais_mi(x):
    """Reais em milhões (mi) ou bilhões (bi)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"R$ {_num(x / 1e9, 1)} bi" if abs(x) >= 1e9 else f"R$ {_num(x / 1e6, 1)} mi"


def layout_grafico(fig, titulo: str, altura: int = 300):
    fig.update_layout(title=titulo, height=altura, margin=dict(l=10, r=10, t=45, b=10), plot_bgcolor="white",
                      paper_bgcolor="white", title_font_color=NAVY, title_font_size=14,
                      separators=".," if atual() == "en" else ",.",
                      legend=dict(orientation="h", y=-0.22), font=dict(color=GRAFITE))
    fig.update_xaxes(gridcolor="#EEF2F7")
    fig.update_yaxes(gridcolor="#EEF2F7")
    return fig
