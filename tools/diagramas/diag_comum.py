"""Desenho de tabelas e relações (pé de galinha) para os diagramas dos documentos, a partir do catálogo dos bancos."""
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle

import psycopg

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from etl.python.etl1.config import conninfo  # noqa: E402  (lê as conexões do .env)

plt.rcParams["font.family"] = ["Segoe UI", "DejaVu Sans"]
ST_DB = os.environ.get("ST_DB", "st_anp")
DW_DB = os.environ.get("DW_DB", "dw_anp")


def catalogo(banco):
    """Colunas, chaves primárias, únicas e estrangeiras do banco, lidas do catálogo do PostgreSQL."""
    with psycopg.connect(conninfo(banco)) as c:
        cols = c.execute("""SELECT table_name, column_name, data_type, character_maximum_length, numeric_precision,
                                   numeric_scale, is_nullable
                            FROM information_schema.columns WHERE table_schema = 'public'
                            ORDER BY table_name, ordinal_position""").fetchall()
        chaves = {}
        for tipo_ in ("PRIMARY KEY", "UNIQUE"):
            chaves[tipo_] = c.execute("""SELECT tc.table_name, kcu.column_name FROM information_schema.table_constraints tc
                                         JOIN information_schema.key_column_usage kcu USING (constraint_schema, constraint_name)
                                         WHERE tc.constraint_type = %s AND tc.table_schema = 'public'""", [tipo_]).fetchall()
        fk = c.execute("""SELECT cl.relname, a.attname, clf.relname, af.attname
                          FROM pg_constraint co JOIN pg_class cl ON cl.oid = co.conrelid JOIN pg_class clf ON clf.oid = co.confrelid
                          JOIN pg_attribute a ON a.attrelid = co.conrelid AND a.attnum = co.conkey[1]
                          JOIN pg_attribute af ON af.attrelid = co.confrelid AND af.attnum = co.confkey[1]
                          WHERE co.contype = 'f' AND cl.relnamespace = 'public'::regnamespace""").fetchall()
    return {"cols": cols, "pk": chaves["PRIMARY KEY"], "uk": chaves["UNIQUE"], "fk": fk}


ESQ = {ST_DB: catalogo(ST_DB), DW_DB: catalogo(DW_DB)}

NAVY, GRAFITE, LINHA = "#0B1F3A", "#2D3748", "#475569"
COR_PK, COR_FK, COR_UK = "#B45309", "#1D4ED8", "#64748B"
RH, HH, W = 0.5, 0.66, 6.2


def tipo(banco, tabela, coluna):
    for t, c, dt, ln, prec, esc, nul in ESQ[banco]["cols"]:
        if t == tabela and c == coluna:
            nomes = {"character varying": "varchar", "character": "char", "timestamp without time zone": "timestamp"}
            base = nomes.get(dt, dt)
            if ln:
                base += f"({ln})"
            elif dt == "numeric" and prec:
                base += f"({prec},{esc})"
            return base, nul == "YES"
    raise KeyError(f"{banco}.{tabela}.{coluna} não existe")


def colunas(banco, tabela):
    return [c for t, c, *_ in ESQ[banco]["cols"] if t == tabela]


class Diagrama:
    def __init__(self, largura_pol, altura_pol, unidades_x=40.0):
        self.ux = unidades_x
        self.uy = unidades_x * altura_pol / largura_pol
        self.fig, self.ax = plt.subplots(figsize=(largura_pol, altura_pol))
        self.fig.subplots_adjust(0, 0, 1, 1)
        self.ax.set_xlim(0, self.ux)
        self.ax.set_ylim(0, self.uy)
        self.ax.axis("off")
        self.t = {}

    def Y(self, y_topo):
        return self.uy - y_topo

    def tabela(self, nome, x, y_topo, linhas, cor, largura=W, titulo=None):
        """linhas: (chave, rótulo, tipo, estilo) — estilo: '' | 'grupo' | 'scd' | 'carga'."""
        ax, h = self.ax, HH + RH * len(linhas)
        y0 = self.Y(y_topo)
        ax.add_patch(FancyBboxPatch((x, y0 - h), largura, h, boxstyle="round,pad=0,rounding_size=0.12",
                                    fc="white", ec=cor, lw=1.8, zorder=2))
        ax.add_patch(FancyBboxPatch((x, y0 - HH), largura, HH, boxstyle="round,pad=0,rounding_size=0.12",
                                    fc=cor, ec=cor, lw=1.8, zorder=3))
        ax.add_patch(Rectangle((x, y0 - HH), largura, HH / 2, fc=cor, ec=cor, lw=0, zorder=3))
        ax.text(x + largura / 2, y0 - HH / 2, titulo or nome, ha="center", va="center", color="white",
                fontsize=11.5, fontweight="bold", zorder=4)
        ys = {}
        for i, (k, rot, ty, est) in enumerate(linhas):
            yy = y0 - HH - RH * (i + 0.5)
            if i % 2:
                ax.add_patch(Rectangle((x + 0.03, yy - RH / 2), largura - 0.06, RH, fc="#F1F5F9", ec="none", zorder=2.5))
            kc = COR_PK if "PK" in k else (COR_FK if ("FK" in k or k == "DD") else COR_UK)
            ax.text(x + 0.14, yy, k, va="center", fontsize=8, color=kc, fontweight="bold", zorder=4)
            cor_t, estilo = GRAFITE, "normal"
            if est in ("grupo", "scd", "carga"):
                cor_t, estilo = "#64748B", "italic"
            peso = "bold" if "PK" in k else "normal"
            ax.text(x + 1.05, yy, rot, va="center", fontsize=9.5, color=cor_t, style=estilo, fontweight=peso, zorder=4)
            if ty:
                ax.text(x + largura - 0.12, yy, ty, va="center", ha="right", fontsize=7.8, color="#94A3B8", zorder=4)
            ys[rot.split(" ")[0]] = yy
        self.t[nome] = {"x": x, "w": largura, "ys": ys, "topo": y0, "base": y0 - h}
        return self.t[nome]

    # ---- relações ----
    def _simbolo(self, x, y, d, tipo_):
        """d = +1 se a linha sai para a direita da borda; tipo_: 'um', 'zero_um', 'zero_muitos', 'um_muitos'."""
        ax, cor, lw = self.ax, LINHA, 1.3
        if tipo_ in ("zero_muitos", "um_muitos"):
            for dy in (-0.17, 0, 0.17):
                ax.plot([x, x + d * 0.34], [y + dy, y], color=cor, lw=lw, zorder=5)
        else:
            ax.plot([x + d * 0.14, x + d * 0.14], [y - 0.15, y + 0.15], color=cor, lw=lw, zorder=5)
        if tipo_ in ("um", "um_muitos"):
            ax.plot([x + d * 0.42, x + d * 0.42], [y - 0.15, y + 0.15], color=cor, lw=lw, zorder=5)
        if tipo_ in ("zero_um", "zero_muitos"):
            ax.add_patch(Circle((x + d * 0.5, y), 0.09, fc="white", ec=cor, lw=lw, zorder=6))

    def borda(self, tab, lado):
        t = self.t[tab]
        return t["x"] + t["w"] if lado == "d" else t["x"]

    def ligar(self, filha, col_f, lado_f, mae, col_m, lado_m, faixa, obrigatoria=True, estilo="-", cor=LINHA):
        """Linha ortogonal: borda da filha -> faixa vertical x=faixa -> borda da mãe."""
        x1, y1 = self.borda(filha, lado_f), self.t[filha]["ys"][col_f]
        x2, y2 = self.borda(mae, lado_m), self.t[mae]["ys"][col_m]
        self.ax.plot([x1, faixa, faixa, x2], [y1, y1, y2, y2], color=cor, lw=1.3, ls=estilo, zorder=1,
                     solid_joinstyle="miter")
        self._simbolo(x1, y1, 1 if faixa > x1 else -1, "zero_muitos")
        self._simbolo(x2, y2, 1 if faixa > x2 else -1, "um" if obrigatoria else "zero_um")

    def salvar(self, caminho, dpi=250):
        self.fig.savefig(caminho, dpi=dpi, facecolor="white")
        plt.close(self.fig)
