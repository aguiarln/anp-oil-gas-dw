"""Croqui do processo de BI: fontes -> ETL 1 -> stage -> ETL 2 -> Data Warehouse -> painel web."""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, FancyArrowPatch, FancyBboxPatch, Rectangle

plt.rcParams["font.family"] = ["Segoe UI", "DejaVu Sans"]
NAVY, ACO, MEDIO, GELO, GRAF = "#0B1F3A", "#1F4E79", "#3A6EA5", "#D6E4F0", "#2D3748"
TEAL, AMBAR, CINZA = "#0F766E", "#B7791F", "#64748B"

fig, ax = plt.subplots(figsize=(13, 5.2))
fig.subplots_adjust(0, 0, 1, 1)
ax.set_xlim(0, 52); ax.set_ylim(0, 20.8); ax.axis("off")


def caixa(x, y, w, h, titulo, linhas, cor, fundo="white"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.5", fc=fundo, ec=cor, lw=2, zorder=2))
    ax.add_patch(FancyBboxPatch((x, y + h - 1.6), w, 1.6, boxstyle="round,pad=0,rounding_size=0.5", fc=cor, ec=cor, lw=2, zorder=3))
    ax.add_patch(Rectangle((x, y + h - 1.6), w, 0.8, fc=cor, ec=cor, lw=0, zorder=3))
    ax.text(x + w / 2, y + h - 0.8, titulo, ha="center", va="center", color="white", fontsize=11, fontweight="bold", zorder=4)
    for i, l in enumerate(linhas):
        ax.text(x + 0.45, y + h - 2.4 - i * 0.95, l, va="center", fontsize=8.6, color=GRAF, zorder=4)


def banco(x, y, w, h, titulo, linhas, cor):
    e = 1.0
    ax.add_patch(Rectangle((x, y + e / 2), w, h - e, fc="white", ec="none", zorder=2))
    ax.plot([x, x], [y + e / 2, y + h - e / 2], color=cor, lw=2, zorder=3)
    ax.plot([x + w, x + w], [y + e / 2, y + h - e / 2], color=cor, lw=2, zorder=3)
    ax.add_patch(Ellipse((x + w / 2, y + e / 2), w, e, fc="white", ec=cor, lw=2, zorder=2.5))
    ax.add_patch(Rectangle((x + 0.05, y + e / 2), w - 0.1, 0.6, fc="white", ec="none", zorder=2.6))
    ax.add_patch(Ellipse((x + w / 2, y + h - e / 2), w, e, fc=cor, ec=cor, lw=2, zorder=3))
    ax.text(x + w / 2, y + h - 1.75, titulo, ha="center", va="center", color=cor, fontsize=11, fontweight="bold", zorder=4)
    for i, l in enumerate(linhas):
        ax.text(x + w / 2, y + h - 2.8 - i * 0.95, l, ha="center", va="center", fontsize=8.6, color=GRAF, zorder=4)


def seta(x1, y1, x2, y2, texto=None, cor=NAVY, ls="-"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=18, lw=2, color=cor, ls=ls, zorder=1))
    if texto:
        ax.text((x1 + x2) / 2, max(y1, y2) + 0.55, texto, ha="center", fontsize=8, color=cor, style="italic")


Y, H = 9.2, 11.2
caixa(0.5, Y, 8.4, H, "Fontes (ANP e IBGE)", ["• produção por poço (zip e CDP)", "• concessionários e sócias",
      "• preços mínimo e de referência", "• coordenadas e contornos", "  (GeoServer)", "• divisão regional (IBGE)",
      "→ download manual, numa", "   pasta por data"], CINZA, "#F8FAFC")
caixa(10.6, Y + 1.2, 6.6, H - 2.4, "ETL 1", ["Python e SQL", "• lê todos os formatos", "• grava o dado bruto",
      "• versiona cada carga", "  (hash SHA-256)", "• ignora arquivo repetido"], ACO)
banco(18.9, Y + 1.2, 6.4, H - 2.4, "Stage", ["st_anp", "PostgreSQL 17", "16 tabelas (3FN)", "dado bruto e", "todas as versões"], ACO)
caixa(27.0, Y + 1.2, 6.6, H - 2.4, "ETL 2", ["Python e SQL (ou PDI)", "• versão mais recente", "• 23 tratamentos", "  (de-para, duplicatas)",
      "• dimensões SCD2", "• carga das fatos"], TEAL)
banco(35.3, Y + 1.2, 6.4, H - 2.4, "Data Warehouse", ["dw_anp", "PostgreSQL 17", "2 estrelas", "7 dimensões", "2 fatos"], TEAL)
caixa(43.4, Y, 8.1, H, "Painel web", ["Streamlit, 4 telas", "• campos candidatos", "• ficha do campo",
      "• vendedores e sócios", "• trocas de operador", "", "filtros por região, estado,", "bacia e ano; PT | EN"], NAVY, "#F8FAFC")

ym = Y + H / 2
seta(8.9, ym, 10.6, ym)
seta(17.2, ym, 18.9, ym)
seta(25.3, ym, 27.0, ym)
seta(33.6, ym, 35.3, ym)
seta(41.7, ym, 43.4, ym)

# saídas logo abaixo dos bancos e orquestração embaixo
caixa(18.9, 4.6, 6.4, 3.4, "Base origem", ["16 CSVs + manifesto"], CINZA)
caixa(35.3, 4.6, 6.4, 3.4, "Validação", ["grão e somas: DW = stage"], AMBAR)
seta(22.1, Y + 1.2, 22.1, 8.0, cor=CINZA, ls="--")
seta(38.5, Y + 1.2, 38.5, 8.0, cor=AMBAR, ls="--")
ax.add_patch(FancyBboxPatch((10.6, 0.5), 31.1, 2.8, boxstyle="round,pad=0,rounding_size=0.5", fc=GELO, ec=MEDIO, lw=1.6, zorder=2))
ax.text(26.15, 2.35, "pipeline.py / pipeline.bat — um comando roda ETL 1 → ETL 2 → validação", ha="center", va="center",
        fontsize=10.5, fontweight="bold", color=NAVY)
ax.text(26.15, 1.25, "mensal, depois de cada download da ANP · uma etapa com erro interrompe as seguintes · o DW só muda numa transação completa",
        ha="center", va="center", fontsize=8.6, color=GRAF)
for x in (13.9, 30.3):
    seta(x, 3.3, x, Y + 1.2, cor=MEDIO, ls="--")
fig.savefig(sys.argv[1], dpi=250, facecolor="white")
