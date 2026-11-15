"""Modelo dimensional (duas estrelas), a partir do catálogo do dw_anp, para página em paisagem."""
import sys
from matplotlib.patches import FancyBboxPatch, Rectangle

from diag_comum import ST_DB, DW_DB, COR_FK, COR_PK, COR_UK, GRAFITE, HH, LINHA, RH, Diagrama, colunas, tipo, ESQ

B = DW_DB
FATO, CONF, PROD, CTRL = "#0B1F3A", "#0F766E", "#3A6EA5", "#64748B"
PKS = {(t, c) for t, c in ESQ[B]["pk"]}
FKS = {(t, c) for t, c, *_ in ESQ[B]["fk"]}
ROT = {("ft_producao", "sk_empresa"): "sk_empresa (operadora)", ("ft_participacao", "sk_empresa"): "sk_empresa (sócia)",
       ("ft_participacao", "sk_data"): "sk_data (foto da ANP)"}


def linhas(t, so=None, extra=None):
    saida = []
    for c in colunas(B, t):
        if so and c not in so:
            continue
        ty, _ = tipo(B, t, c)
        if (t, c) in PKS and (t, c) in FKS:
            k = "PK/FK"
        elif (t, c) in PKS:
            k = "PK"
        elif (t, c) in FKS:
            k = "FK"
        elif c.startswith("nk_"):
            k = "NK"
        elif c.startswith("dd_"):
            k = "DD"
        else:
            k = ""
        est = "scd" if c.startswith("etl_") else ""
        saida.append((k, ROT.get((t, c), c), ty, est))
    if extra:
        saida.append(extra)
    return saida


d = Diagrama(18, 9.85)
ax = d.ax
uy = d.uy

# áreas das estrelas (a interseção guarda as dimensões conformadas)
ax.add_patch(FancyBboxPatch((0.15, 0.25), 29.6, uy - 0.5, boxstyle="round,pad=0,rounding_size=0.6",
                            fc="#EAF1F8", ec="#3A6EA5", lw=1.2, ls="--", zorder=0))
ax.add_patch(FancyBboxPatch((21.3, 0.25), 18.5, uy - 0.5, boxstyle="round,pad=0,rounding_size=0.6",
                            fc="#E6F4F1", ec="#0F766E", lw=1.2, ls="--", zorder=0, alpha=0.85))
ax.text(0.6, uy - 0.75, "ESTRELA 1 — PRODUÇÃO", fontsize=13, fontweight="bold", color="#1F4E79")
ax.text(0.6, uy - 1.3, "um poço × campo × mês", fontsize=10, color="#1F4E79", style="italic")
ax.text(39.4, uy - 0.75, "ESTRELA 2 — PARTICIPAÇÃO", fontsize=13, fontweight="bold", color="#0F766E", ha="right")
ax.text(39.4, uy - 1.3, "uma empresa × contrato × foto da ANP", fontsize=10, color="#0F766E", style="italic", ha="right")
ax.text(25.55, uy - 0.75, "dimensões conformadas", fontsize=10.5, fontweight="bold", color=GRAFITE, ha="center")
ax.text(25.55, uy - 1.25, "(servem às duas estrelas)", fontsize=9.5, color=GRAFITE, ha="center", style="italic")

# dimensões só da produção, à esquerda e embaixo da fato
d.tabela("dim_poco", 0.6, 1.8, linhas("dim_poco"), PROD)
d.tabela("dim_instalacao", 7.6, 10.0, linhas("dim_instalacao"), PROD)
d.tabela("dim_campo", 0.6, 9.6, linhas("dim_campo"), PROD)
cor_cols = [c for c in colunas(B, "dim_corrente") if not c.startswith(("nm_dest", "nr_dest"))]
d.tabela("dim_corrente", 7.6, 15.2, linhas("dim_corrente", so=cor_cols, extra=("", "destilados (corte e %)", "6 colunas", "grupo")), PROD)
# fatos
d.tabela("ft_producao", 14.6, 5.2, linhas("ft_producao"), FATO)
d.tabela("ft_participacao", 33.2, 8.2, linhas("ft_participacao"), FATO)
# conformadas, no meio
dat_cols = ["sk_data", "nk_data", "nr_ano", "nm_trimestre", "nr_mes", "nm_mes"]
n_dat = len(colunas(B, "dim_data")) - len(dat_cols)
d.tabela("dim_data", 22.4, 1.8, linhas("dim_data", so=dat_cols, extra=("", "outras colunas do calendário", f"+{n_dat} colunas", "grupo")), CONF)
d.tabela("dim_empresa", 22.4, 7.7, linhas("dim_empresa"), CONF)
d.tabela("dim_contrato", 22.4, 13.4, linhas("dim_contrato"), CONF)
# tabela de controle do ETL (sem relação)
d.tabela("etl_depara", 33.2, 1.8, linhas("etl_depara"), CTRL)

L = d.ligar
L("ft_producao", "sk_poco", "e", "dim_poco", "sk_poco", "d", 13.6)
L("ft_producao", "sk_instalacao", "e", "dim_instalacao", "sk_instalacao", "d", 14.0)
L("ft_producao", "sk_campo", "e", "dim_campo", "sk_campo", "d", 7.15)
L("ft_producao", "sk_corrente", "e", "dim_corrente", "sk_corrente", "d", 14.25)
L("ft_producao", "sk_data", "d", "dim_data", "sk_data", "e", 21.4)
L("ft_producao", "sk_empresa", "d", "dim_empresa", "sk_empresa", "e", 21.75)
L("ft_producao", "sk_contrato", "d", "dim_contrato", "sk_contrato", "e", 21.4)
L("ft_participacao", "sk_data", "e", "dim_data", "sk_data", "d", 31.4)
L("ft_participacao", "sk_empresa", "e", "dim_empresa", "sk_empresa", "d", 31.0)
L("ft_participacao", "sk_contrato", "e", "dim_contrato", "sk_contrato", "d", 30.6)

# legenda
x0, y = 33.2, d.Y(12.2)
ax.text(x0, y, "Legenda", fontsize=11, fontweight="bold", color=GRAFITE)
for i, (c, txt) in enumerate(((FATO, "tabela fato"), (CONF, "dimensão conformada (duas estrelas)"),
                               (PROD, "dimensão só da produção"), (CTRL, "controle do ETL (de-para)"))):
    yy = y - 0.55 - i * 0.46
    ax.add_patch(Rectangle((x0, yy - 0.16), 0.5, 0.32, fc=c, ec=c))
    ax.text(x0 + 0.7, yy, txt, va="center", fontsize=9.5, color=GRAFITE)
yy = y - 0.55 - 4 * 0.46 - 0.2
for i, (k, cor, txt) in enumerate((("PK", COR_PK, "chave primária (surrogate key)"), ("FK", COR_FK, "chave estrangeira"),
                                    ("NK", COR_UK, "chave natural (de negócio)"), ("DD", COR_FK, "dimensão degenerada"))):
    ax.text(x0, yy - i * 0.42, k, fontsize=9, fontweight="bold", color=cor, va="center")
    ax.text(x0 + 0.9, yy - i * 0.42, txt, fontsize=9.5, color=GRAFITE, va="center")
yy -= 4 * 0.42 + 0.15
ax.plot([x0, x0 + 1.1], [yy, yy], color=LINHA, lw=1.3)
d._simbolo(x0, yy, 1, "um")
d._simbolo(x0 + 1.1, yy, -1, "zero_muitos")
ax.text(x0 + 1.4, yy, "1 linha da dimensão : N linhas da fato", va="center", fontsize=9.5, color=GRAFITE)
ax.text(x0, yy - 0.55, "Em itálico: colunas do histórico (SCD tipo 2).\nToda dimensão tem a linha 0 (não qualificada).",
        fontsize=8.8, color="#64748B", style="italic", va="top", linespacing=1.35)

d.salvar(sys.argv[1])
