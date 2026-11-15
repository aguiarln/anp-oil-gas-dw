"""Consultas ao Data Warehouse (dw_anp) e indicadores do painel.

O painel lê somente o DW, nunca a stage. As consultas trazem tabelas pequenas (campo × mês × operadora, poços,
participações), guardadas em cache; os indicadores são calculados em pandas com estas regras:
volumes do mês somados, médias diárias pelos dias do período (nunca somando bbl/dia entre meses),
contagens pela chave natural e participação só na foto mais recente.
"""
import io
import os
import re
import sys
from pathlib import Path

import pandas as pd
import psycopg
import streamlit as st

TODAS, TODOS = "Todas", "Todos"  # opções "sem filtro" dos seletores de região e de estado

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
from etl.python.etl1.config import conninfo  # noqa: E402  (conexões do .env)

BBL_M3 = 0.158987294928
DW_DB = os.environ.get("DW_DB", "dw_anp")


def consultar(sql: str, params=()) -> pd.DataFrame:
    with psycopg.connect(conninfo(DW_DB)) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        df = pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])
    for c in df.columns:  # numeric do PostgreSQL chega como Decimal
        if df[c].dtype == object and len(df) and df[c].map(type).astype(str).str.contains("Decimal").any():
            df[c] = df[c].astype(float)
    return df


@st.cache_data(ttl=3600, show_spinner="Lendo a produção do Data Warehouse · Reading production from the Data Warehouse...")
def producao_campo_mes_operadora() -> pd.DataFrame:
    """Produção mensal de cada campo, por operadora (volumes do mês)."""
    df = consultar("""
        SELECT c.nk_campo, d.nk_data AS mes, e.nk_empresa, e.nm_empresa, e.nm_grupo_economico, e.nm_pais,
               sum(f.md_petroleo_bbl) AS petroleo, sum(f.md_oleo_bbl) AS oleo, sum(f.md_condensado_bbl) AS condensado,
               sum(f.md_agua_bbl) AS agua, sum(f.md_gas_nao_assoc_mil_m3) AS gas_nao_assoc,
               sum(f.md_gas_assoc_mil_m3) AS gas_assoc, sum(f.md_gas_total_mil_m3) AS gas_total,
               sum(f.md_receita_estimada_rs) AS receita,
               sum(f.md_petroleo_bbl) FILTER (WHERE f.md_preco_rs_m3 IS NOT NULL) AS petroleo_com_preco
        FROM ft_producao f JOIN dim_campo c USING (sk_campo) JOIN dim_data d USING (sk_data) JOIN dim_empresa e USING (sk_empresa)
        GROUP BY 1, 2, 3, 4, 5, 6""")
    df["mes"] = pd.to_datetime(df["mes"])
    return df.fillna({"receita": 0.0, "petroleo_com_preco": 0.0})


def recorte(df: pd.DataFrame) -> pd.DataFrame:
    """Linhas (campos) da região e do estado escolhidos na barra lateral."""
    regiao, uf = st.session_state.get("regiao", TODAS), st.session_state.get("estado", TODOS)
    if regiao != TODAS:
        df = df[df["nm_regiao"] == regiao]
    if uf != TODOS:
        df = df[df["sg_estado"] == uf]
    return df


def nivel_do_recorte() -> str:
    """'brasil', 'regiao' ou 'estado': o recorte geográfico escolhido (usado no zoom do mapa)."""
    if st.session_state.get("estado", TODOS) != TODOS:
        return "estado"
    return "regiao" if st.session_state.get("regiao", TODAS) != TODAS else "brasil"


def rotulo_recorte() -> str:
    """Texto do recorte para o título das telas: 'Brasil', a região ou o estado."""
    from idioma import t
    regiao, uf = st.session_state.get("regiao", TODAS), st.session_state.get("estado", TODOS)
    return uf if uf != TODOS else regiao if regiao != TODAS else t("Brasil")


@st.cache_data(ttl=3600)
def campos() -> pd.DataFrame:
    """Versão vigente de cada campo, com o contorno, o estado e a região."""
    df = consultar("""
        SELECT nk_campo, nm_campo, nm_campo_atual, nm_campo_sucessor, nm_bacia, nm_estado, sg_estado, nm_regiao,
               desc_contorno_wkt, nr_latitude_centro, nr_longitude_centro, dt_ultima_troca_operador, dt_ultima_venda, dt_ultima_reorganizacao
        FROM dim_campo WHERE sk_campo <> 0 AND etl_dt_fim = '2199-12-31'""")
    for c in ("dt_ultima_troca_operador", "dt_ultima_venda", "dt_ultima_reorganizacao"):
        df[c] = pd.to_datetime(df[c])
    return df


@st.cache_data(ttl=3600, show_spinner="Lendo a produção dos poços · Reading well production...")
def producao_poco_mes() -> pd.DataFrame:
    """Produção de cada poço, em cada campo, em cada mês (o grão da ft_producao), com o mês em AAAAMM.

    São 2,26 milhões de linhas: vêm por COPY (cerca de 5 s, uma vez só, em cache) para que os poços de qualquer ano
    sejam calculados em pandas sem consultar o banco de novo.
    """
    buf = io.BytesIO()
    with psycopg.connect(conninfo(DW_DB)) as conn, conn.cursor() as cur:
        with cur.copy("""COPY (SELECT p.nk_poco, c.nk_campo, f.sk_data / 100 AS mes, f.md_petroleo_bbl AS petroleo,
                                      (f.md_petroleo_bbl > 0 OR f.md_gas_total_mil_m3 > 0) AS produziu
                               FROM ft_producao f JOIN dim_poco p USING (sk_poco) JOIN dim_campo c USING (sk_campo))
                         TO STDOUT WITH CSV""") as copia:
            for bloco in copia:
                buf.write(bloco)
    buf.seek(0)
    df = pd.read_csv(buf, names=["nk_poco", "nk_campo", "mes", "petroleo", "produziu"],
                     dtype={"nk_poco": "category", "nk_campo": "category"})
    df["produziu"] = df["produziu"].eq("t")
    return df


@st.cache_data(ttl=3600)
def cadastro_pocos() -> pd.DataFrame:
    """Versão vigente de cada poço: ambiente e coordenadas."""
    return consultar("""SELECT nk_poco, nm_ambiente, nr_latitude, nr_longitude FROM dim_poco
                        WHERE sk_poco <> 0 AND etl_dt_fim = '2199-12-31'""")


@st.cache_data(ttl=3600, show_spinner="Lendo os poços · Reading the wells...")
def pocos(ate: pd.Timestamp | None = None) -> pd.DataFrame:
    """Cada poço em cada campo, olhando a produção até o mês `ate` (por padrão, toda a série): ambiente e coordenadas,
    o último mês com produção e o petróleo médio (bbl/dia) nos 12 meses até esse mês (RQ-04: o tamanho da
    oportunidade de voltar a produzir num poço parado)."""
    chave = ["nk_poco", "nk_campo"]
    m = producao_poco_mes()
    if ate is not None:
        m = m[m["mes"] <= ate.year * 100 + ate.month]
    u = m[m["produziu"]].groupby(chave, observed=True)["mes"].max().rename("ultimo").reset_index()
    janela = m.merge(u, on=chave)
    janela = janela[(janela["mes"] > janela["ultimo"] - 100) & (janela["mes"] <= janela["ultimo"])]  # 12 meses (AAAAMM)
    p = u.merge(janela.groupby(chave, observed=True)["petroleo"].sum().rename("petroleo_12m").reset_index(), on=chave)
    p["ultimo_mes"] = pd.to_datetime(p["ultimo"].astype(str), format="%Y%m")
    inicio = (p["ultimo_mes"] - pd.DateOffset(months=11)).clip(lower=pd.Timestamp("2005-01-01"))  # a série começa em 2005
    p["petroleo_antes_bbl_dia"] = p["petroleo_12m"] / ((p["ultimo_mes"] + pd.offsets.MonthEnd(0) - inicio).dt.days + 1)
    p[chave] = p[chave].astype(str)
    p = p.merge(cadastro_pocos(), on="nk_poco", how="left")
    return p[["nk_poco", "nk_campo", "nm_ambiente", "nr_latitude", "nr_longitude", "ultimo_mes", "petroleo_antes_bbl_dia"]]


@st.cache_data(ttl=3600)
def participacoes() -> pd.DataFrame:
    """Sócias de cada contrato na foto mais recente da relação de concessionários (percentual semiaditivo)."""
    df = consultar("""
        SELECT ct.nk_contrato, ct.nm_contrato, e.nk_empresa, e.nm_empresa, e.nm_grupo_economico, e.nm_pais,
               p.md_percentual / 100 AS participacao, p.dd_operador = 'S' AS operadora, d.nk_data AS foto
        FROM ft_participacao p JOIN dim_contrato ct USING (sk_contrato) JOIN dim_empresa e USING (sk_empresa)
        JOIN dim_data d USING (sk_data)
        WHERE p.sk_data = (SELECT max(sk_data) FROM ft_participacao)""")
    df["foto"] = pd.to_datetime(df["foto"])
    return df


@st.cache_data(ttl=3600)
def contratos_dos_campos(ano: int | None = None) -> pd.DataFrame:
    """Contratos que produziram em cada campo no ano escolhido (por padrão, o último ano com dados)."""
    ano = ano or mes_de_referencia().year
    return consultar("""
        SELECT DISTINCT c.nk_campo, ct.nk_contrato
        FROM ft_producao f JOIN dim_campo c USING (sk_campo) JOIN dim_contrato ct USING (sk_contrato)
        WHERE f.sk_data BETWEEN %(ano)s * 10000 + 101 AND %(ano)s * 10000 + 1231 AND ct.sk_contrato <> 0""", {"ano": ano})


def anos_com_dados() -> list[int]:
    """Anos com produção, do mais recente ao mais antigo (o seletor de ano só oferece anos com dados)."""
    return sorted(producao_campo_mes_operadora()["mes"].dt.year.unique().tolist(), reverse=True)


def mes_de_referencia(ano: int | None = None) -> pd.Timestamp:
    """Último mês com dados do ano escolhido; sem ano, o último mês com dados da série."""
    meses = producao_campo_mes_operadora()["mes"]
    return meses.max() if ano is None else meses[meses.dt.year == ano].max()


def por_campo_mes() -> pd.DataFrame:
    """Produção mensal de cada campo (todas as operadoras), com a média diária do mês."""
    df = producao_campo_mes_operadora()
    m = df.groupby(["nk_campo", "mes"], as_index=False)[
        ["petroleo", "oleo", "condensado", "agua", "gas_assoc", "gas_nao_assoc", "gas_total", "receita", "petroleo_com_preco"]].sum()
    m["dias"] = m["mes"].dt.days_in_month
    m["petroleo_bbl_dia"] = m["petroleo"] / m["dias"]
    return m


def bsw(agua, petroleo):
    """BSW: água ÷ (petróleo + água)."""
    total = petroleo + agua
    return agua / total if total else float("nan")


def rgo(gas_assoc_mil_m3, oleo_bbl):
    """RGO: gás associado (m³) ÷ óleo (m³)."""
    return gas_assoc_mil_m3 * 1000 / (oleo_bbl * BBL_M3) if oleo_bbl else float("nan")


def dias_no_ano(ano: int, ate: pd.Timestamp) -> int:
    fim = min(pd.Timestamp(ano, 12, 31), ate + pd.offsets.MonthEnd(0))
    return (fim - pd.Timestamp(ano, 1, 1)).days + 1


@st.cache_data(ttl=3600, show_spinner="Calculando os indicadores dos campos · Computing field indicators...")
def indicadores_campos(meses_parado: int = 12, ano: int | None = None) -> pd.DataFrame:
    """Uma linha por campo com os indicadores do ano escolhido (por padrão, o último com dados) (RQ-09)."""
    ref = mes_de_referencia(ano)
    ano = ref.year
    m = por_campo_mes()
    m["ano"] = m["mes"].dt.year
    valores = ["petroleo", "oleo", "agua", "gas_assoc", "receita"]
    a = m[m["ano"].isin([ano, ano - 1])].pivot_table(index="nk_campo", columns="ano", values=valores,
                                                      aggfunc="sum", fill_value=0)
    # o primeiro ano da série não tem ano anterior: a coluna entra zerada e a variação fica vazia
    a = a.reindex(columns=pd.MultiIndex.from_product([valores, [ano - 1, ano]]), fill_value=0)
    ind = pd.DataFrame(index=a.index)
    ind["petroleo_ano"] = a[("petroleo", ano)]
    ind["petroleo_ano_anterior"] = a[("petroleo", ano - 1)]
    ind["petroleo_bbl_dia"] = ind["petroleo_ano"] / dias_no_ano(ano, ref)
    ind["variacao_anual"] = (ind["petroleo_ano"] - ind["petroleo_ano_anterior"]) / ind["petroleo_ano_anterior"].where(ind["petroleo_ano_anterior"] > 0)
    ind["bsw"] = a[("agua", ano)] / (a[("petroleo", ano)] + a[("agua", ano)]).where(lambda s: s > 0)
    ind["rgo"] = a[("gas_assoc", ano)] * 1000 / (a[("oleo", ano)] * BBL_M3).where(lambda s: s > 0)
    ind["receita_ano"] = a[("receita", ano)]
    ind = ind.reset_index()
    # poços produtores no mês de referência e parados há N meses
    p = pocos(ref)
    corte = ref - pd.DateOffset(months=meses_parado)
    pp = p.assign(produtor=p["ultimo_mes"] == ref, parado=p["ultimo_mes"] <= corte).groupby("nk_campo")[["produtor", "parado"]].sum()
    ind = ind.merge(pp.rename(columns={"produtor": "pocos_produtores", "parado": "pocos_parados"}),
                    left_on="nk_campo", right_index=True, how="left")
    amb = p.groupby("nk_campo")["nm_ambiente"].agg(lambda s: s.mode().iat[0] if len(s.mode()) else "N/A")
    ind = ind.merge(amb.rename("ambiente"), left_on="nk_campo", right_index=True, how="left")
    # operadora no mês de referência
    o = producao_campo_mes_operadora()
    o = o[(o["petroleo"] + o["gas_total"] > 0) & (o["mes"] <= ref)]
    o = o[o["mes"] == o.groupby("nk_campo")["mes"].transform("max")]  # operadora do último mês com produção, até o mês de referência
    o = o.groupby("nk_campo")["nm_empresa"].agg(lambda s: ", ".join(sorted(set(s))))
    ind = ind.merge(o.rename("operadora"), left_on="nk_campo", right_index=True, how="left")
    ind = ind.merge(campos(), on="nk_campo", how="left")
    # variação anual da bacia (para comparar o declínio de cada campo com a média da sua bacia)
    bac = ind.groupby("nm_bacia")[["petroleo_ano", "petroleo_ano_anterior"]].sum()
    bac["variacao_bacia"] = (bac["petroleo_ano"] - bac["petroleo_ano_anterior"]) / bac["petroleo_ano_anterior"].where(bac["petroleo_ano_anterior"] > 0)
    ind = ind.merge(bac["variacao_bacia"], left_on="nm_bacia", right_index=True, how="left")
    ind["diferenca_bacia"] = ind["variacao_anual"] - ind["variacao_bacia"]
    return ind[ind["petroleo_ano"] > 0].sort_values("petroleo_bbl_dia", ascending=False).reset_index(drop=True)


TIPOS_DE_TROCA = {"Vendas": "dt_ultima_venda", "Reorganizações": "dt_ultima_reorganizacao",
                  "Todas as trocas": "dt_ultima_troca_operador"}


@st.cache_data(ttl=3600, show_spinner="Calculando as trocas de operador · Computing operator changes...")
def trocas_de_operador(tipo: str = "Vendas") -> pd.DataFrame:
    """Última troca de cada campo, do tipo escolhido: operadoras e produção nos 12 meses antes e depois (RQ-07).

    Tipos (T23): venda (o grupo econômico muda), reorganização (mesmo grupo) ou todas as trocas.
    """
    coluna = TIPOS_DE_TROCA[tipo]
    c = campos().dropna(subset=[coluna])
    m = por_campo_mes()
    o = producao_campo_mes_operadora()
    linhas = []
    for _, r in c.iterrows():
        t = r[coluna]
        mc = m[m["nk_campo"] == r["nk_campo"]]
        antes = mc[(mc["mes"] >= t - pd.DateOffset(months=12)) & (mc["mes"] < t)]
        depois = mc[(mc["mes"] >= t) & (mc["mes"] < t + pd.DateOffset(months=12))]
        oc = o[o["nk_campo"] == r["nk_campo"]]
        op = lambda mes: ", ".join(sorted(set(oc.loc[oc["mes"] == mes, "nm_empresa"]))) or None
        # a operadora do último mês com produção antes da troca: o campo pode ter ficado parado na transição
        ultimo_antes = oc.loc[oc["mes"] < t, "mes"].max()
        media = lambda d: d["petroleo"].sum() / d["dias"].sum() if d["dias"].sum() else float("nan")
        linhas.append({
            "nk_campo": r["nk_campo"], "nm_campo": r["nm_campo"], "nm_bacia": r["nm_bacia"],
            "sg_estado": r["sg_estado"], "nm_regiao": r["nm_regiao"], "troca": t,
            "operadora_antes": op(ultimo_antes) if pd.notna(ultimo_antes) else None, "operadora_depois": op(t),
            "antes_bbl_dia": media(antes), "depois_bbl_dia": media(depois), "meses_depois": len(depois),
            "bsw_antes": bsw(antes["agua"].sum(), antes["petroleo"].sum()),
            "bsw_depois": bsw(depois["agua"].sum(), depois["petroleo"].sum())})
    t = pd.DataFrame(linhas)
    t["variacao"] = (t["depois_bbl_dia"] - t["antes_bbl_dia"]) / t["antes_bbl_dia"].where(t["antes_bbl_dia"] > 0)
    return t.sort_values("troca", ascending=False).reset_index(drop=True)


def aneis_wkt(wkt: str | None) -> list[list[list[float]]]:
    """Anéis (listas de [longitude, latitude]) de um POLYGON ou MULTIPOLYGON em WKT."""
    if not isinstance(wkt, str) or not wkt:
        return []
    return [[[float(v) for v in par.split()] for par in anel.split(",")] for anel in re.findall(r"\(([^()]+)\)", wkt)]
