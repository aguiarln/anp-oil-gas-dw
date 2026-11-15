"""Diagrama relacional da stage (pé de galinha), a partir do catálogo do st_anp, para página em paisagem."""
import sys
from matplotlib.patches import Rectangle

from diag_comum import ST_DB, DW_DB, COR_FK, COR_PK, COR_UK, GRAFITE, HH, LINHA, RH, Diagrama, colunas, tipo, ESQ

B = ST_DB
GRUPOS = {  # cor e tabelas de cada assunto
    "Controle das cargas": ("#64748B", ["carga"]),
    "Empresas e contratos": ("#1F4E79", ["grupo_economico", "empresa", "participacao_contrato", "contrato"]),
    "Localização": ("#0F766E", ["bacia", "campo", "estado", "poco", "coordenada_campo", "coordenada_poco"]),
    "Instalações e petróleo": ("#B7791F", ["instalacao", "corrente", "caracterizacao_petroleo"]),
    "Eventos mensais (produção e preço)": ("#B91C1C", ["producao_mensal", "preco_petroleo"]),
}
COR = {t: c for c, ts in GRUPOS.values() for t in ts}
PKS = {(t, c) for t, c in ESQ[B]["pk"]}
UKS = {(t, c) for t, c in ESQ[B]["uk"]}
FKS = {(t, c): m for t, c, m, _ in ESQ[B]["fk"]}

# colunas agrupadas numa linha só, para caber na página
GRUPOS_COL = {
    "producao_mensal": [("volumes de líquidos (bbl/dia)",
                         ["oleo_bbl_dia", "condensado_bbl_dia", "petroleo_bbl_dia", "agua_bbl_dia"]),
                        ("volumes de gás (Mm³/dia)",
                         ["gas_assoc_mm3_dia", "gas_nao_assoc_mm3_dia", "gas_total_mm3_dia", "gas_royalties"])],
    "caracterizacao_petroleo": [("destilados (corte e %)",
                                 [c for c in colunas(B, "caracterizacao_petroleo") if c.startswith("dest_")]),
                                ("composição do gás (%)",
                                 [c for c in colunas(B, "caracterizacao_petroleo") if c.startswith("pct_")]),
                                ("densidades do GLP",
                                 [c for c in colunas(B, "caracterizacao_petroleo") if c.startswith("densidade_")])],
}
ROTULO = {("producao_mensal", "id_empresa"): "id_empresa (operador)",
          ("coordenada_poco", "geometria_wkt"): "geometria_wkt (ponto)",
          ("coordenada_campo", "geometria_wkt"): "geometria_wkt (contorno)",
          ("preco_petroleo", "campo_nome"): "campo_nome (texto)"}


def linhas(t):
    grupos = GRUPOS_COL.get(t, [])
    agrupadas = {c: g for g in grupos for c in g[1]}
    saida, feitos = [], set()
    for c in colunas(B, t):
        if c in agrupadas:
            rot, cols = agrupadas[c]
            if rot not in feitos:
                feitos.add(rot)
                saida.append(("", f"{rot}", f"{len(cols)} colunas", "grupo"))
            continue
        ty, nul = tipo(B, t, c)
        k = "/".join(x for x, ok in (("PK", (t, c) in PKS), ("UK", (t, c) in UKS and (t, c) not in PKS),
                                         ("FK", (t, c) in FKS)) if ok)
        est = "carga" if (c == "id_carga" and t != "carga") else ""
        rot = ROTULO.get((t, c), c)
        if est == "carga":
            rot = "id_carga  → carga"
        saida.append((k, rot, ty, est))
    return saida


d = Diagrama(18, 9.85)
X = [0.35, 8.35, 16.35, 24.35, 32.35]
POS = {  # coluna e topo
    "grupo_economico": (0, 0.5), "participacao_contrato": (0, 4.6), "bacia": (0, 10.4), "coordenada_campo": (1, 13.6),
    "empresa": (1, 0.5), "contrato": (1, 5.0), "campo": (1, 10.4),
    "producao_mensal": (2, 0.5), "preco_petroleo": (2, 10.6),
    "estado": (3, 0.5), "poco": (3, 4.0), "instalacao": (3, 6.6), "caracterizacao_petroleo": (3, 9.2), "corrente": (3, 14.2),
    "coordenada_poco": (4, 3.4), "carga": (4, 7.0),
}
for t, (col, topo) in POS.items():
    d.tabela(t, X[col], topo, linhas(t), COR[t])

L = d.ligar
# empresas e contratos / localização (canal entre as colunas 1 e 2)
L("empresa", "id_grupo", "e", "grupo_economico", "id_grupo", "d", 7.05, obrigatoria=False)
L("participacao_contrato", "id_empresa", "d", "empresa", "id_empresa", "e", 7.35)
L("participacao_contrato", "id_contrato", "d", "contrato", "id_contrato", "e", 7.65)
L("contrato", "id_bacia", "e", "bacia", "id_bacia", "d", 7.35, obrigatoria=False)
L("campo", "id_bacia", "e", "bacia", "id_bacia", "d", 7.35)
L("coordenada_campo", "id_campo", "d", "campo", "id_campo", "d", 15.0)
# produção e preço -> empresas, contratos e campos (canal entre as colunas 2 e 3)
L("producao_mensal", "id_empresa", "e", "empresa", "id_empresa", "d", 15.0)
L("producao_mensal", "id_contrato", "e", "contrato", "id_contrato", "d", 15.35)
L("preco_petroleo", "id_contrato", "e", "contrato", "id_contrato", "d", 15.35)
L("producao_mensal", "id_campo", "e", "campo", "id_campo", "d", 15.7)
# produção e preço -> localização e petróleo (canal entre as colunas 3 e 4)
L("producao_mensal", "id_estado", "d", "estado", "id_estado", "e", 23.0, obrigatoria=False)
L("producao_mensal", "id_poco", "d", "poco", "id_poco", "e", 23.3)
L("producao_mensal", "id_instalacao", "d", "instalacao", "id_instalacao", "e", 23.9, obrigatoria=False)
L("producao_mensal", "id_caracterizacao", "d", "caracterizacao_petroleo", "id_caracterizacao", "e", 23.6, obrigatoria=False)
L("preco_petroleo", "id_corrente", "d", "corrente", "id_corrente", "e", 23.3, obrigatoria=False)
# dentro da coluna 4 e para a coluna 5
L("caracterizacao_petroleo", "id_corrente", "d", "corrente", "id_corrente", "d", 31.3, obrigatoria=False)
L("coordenada_poco", "id_poco", "e", "poco", "id_poco", "d", 31.3)

# legenda
ax = d.ax
x0, y = X[4], d.Y(12.4)
ax.text(x0, y, "Assuntos", fontsize=11, fontweight="bold", color=GRAFITE)
for i, (g, (c, _)) in enumerate(GRUPOS.items()):
    yy = y - 0.55 - i * 0.48
    ax.add_patch(Rectangle((x0, yy - 0.16), 0.5, 0.32, fc=c, ec=c))
    ax.text(x0 + 0.7, yy, g, va="center", fontsize=9.5, color=GRAFITE)
y = y - 0.55 - len(GRUPOS) * 0.48 - 0.35
ax.text(x0, y, "Relações (pé de galinha)", fontsize=11, fontweight="bold", color=GRAFITE)
for i, (tp, txt) in enumerate((("um", "exatamente um (FK obrigatória)"),
                                ("zero_um", "zero ou um (FK opcional)"),
                                ("zero_muitos", "zero ou muitos (lado da tabela filha)"))):
    yy = y - 0.6 - i * 0.55
    ax.plot([x0, x0 + 1.1], [yy, yy], color=LINHA, lw=1.3)
    d._simbolo(x0 + 1.1 if tp == "zero_muitos" else x0, yy, -1 if tp == "zero_muitos" else 1, tp)
    ax.text(x0 + 1.4, yy, txt, va="center", fontsize=9.5, color=GRAFITE)
yy = y - 0.6 - 3 * 0.55 - 0.1
for i, (k, cor, txt) in enumerate((("PK", COR_PK, "chave primária"), ("FK", COR_FK, "chave estrangeira"),
                                    ("UK", COR_UK, "chave única"))):
    ax.text(x0, yy - i * 0.45, k, fontsize=9, fontweight="bold", color=cor, va="center")
    ax.text(x0 + 0.9, yy - i * 0.45, txt, fontsize=9.5, color=GRAFITE, va="center")
yy -= 0.9
ax.text(x0, yy - 0.75, "id_carga → carga: toda linha de dado aponta para a carga\n(o arquivo da ANP) de onde veio. Essas 5 relações não\nforam desenhadas, para não poluir o diagrama.",
        fontsize=8.5, color="#64748B", style="italic", va="top", linespacing=1.35)

d.salvar(sys.argv[1])
