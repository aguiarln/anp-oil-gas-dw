"""ETL 1 (Python): fontes da ANP -> stage (st_anp).

Uso:
    .venv/Scripts/python -m etl.python.etl1                    # carrega tudo o que ainda não foi carregado
    .venv/Scripts/python -m etl.python.etl1 --ate 2026-09-30   # só pastas de download até essa data
    .venv/Scripts/python -m etl.python.etl1 --listar           # só lista os arquivos e a ordem, sem gravar
    .venv/Scripts/python -m etl.python.etl1 --banco outro_banco

Ordem de carga: país de origem -> concessionários -> produção (cronológica) -> preços -> coordenadas
(poços e campos).
Cada arquivo é gravado numa transação: ou entra inteiro, ou não entra nada. Nos zips de produção,
cada CSV interno é uma carga própria (o anual antes dos mensais).
"""

import argparse
import re
import sys
import time
from pathlib import Path

import psycopg

from . import carga, leitores
from .cadastros import Cadastros
from .config import DADOS, conninfo

RAW = DADOS / "raw" / "anp"
EXTRAIDO_2005_2008 = DADOS / "interim" / "anp" / "preco-minimo-petroleo-2005-2008.csv"


def _pastas(fonte: str, ate: str | None) -> list[Path]:
    """Subpastas de download (AAAA-MM-DD) de uma fonte, em ordem, até a data informada."""
    base = RAW / fonte
    if not base.exists():
        return []
    return [p for p in sorted(base.iterdir()) if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name)
            and (ate is None or p.name <= ate)]


def _ordem_producao(caminho: Path):
    """Ordena os zips de produção pelo período, apesar dos nomes inconsistentes entre anos."""
    nome = caminho.name
    ano = int(re.search(r"(20\d{2})", nome)[1])
    resto = nome.replace(str(ano), "", 1)
    mes = re.search(r"(?<!\d)(\d{2})(?!\d)", resto)
    return ano, int(mes[1]) if mes else 0, nome


def descobrir(ate: str | None) -> list[tuple[str, Path, str | None, dict]]:
    """Lista (fonte, arquivo, membro do zip ou None, opções) na ordem de carga."""
    fila = []
    for pasta in _pastas("concessionarios", ate):
        for nome, fonte in (("relacao-pais-origem-concessionarios.csv", "pais_origem"),
                            ("relacao-concessionarios.csv", "concessionarios")):
            if (pasta / nome).exists():
                fila.append((fonte, pasta / nome, None, {}))
    for pasta in _pastas("producao-por-poco", ate):
        for p in sorted(pasta.glob("*.zip"), key=_ordem_producao):
            fila += [("producao_por_poco", p, m, {}) for m in leitores.membros_zip(p)]
    for pasta in _pastas("producao-por-poco-cdp", ate):
        fila += [("producao_por_poco_cdp", p, None, {}) for p in sorted(pasta.glob("*.csv"))]
    if EXTRAIDO_2005_2008.exists():
        fila.append(("preco_minimo_pdf", EXTRAIDO_2005_2008, None, {"tipo": "minimo", "extraido": True}))
    for pasta in _pastas("preco-minimo-petroleo", ate):
        fila += [("preco_minimo", p, None, {"tipo": "minimo", "extraido": False}) for p in sorted(pasta.glob("*.csv"))]
    for pasta in _pastas("preco-referencia-petroleo", ate):
        anos = lambda p: int(re.search(r"(20\d{2})", p.name)[1])
        fila += [("preco_referencia", p, None, {"tipo": "referencia", "extraido": False}) for p in sorted(pasta.glob("*.csv"), key=anos)]
    # Coordenadas por último: os poços e campos que ainda não existem recebem IDs depois dos já cadastrados.
    for pasta in _pastas("pocos-georreferenciados", ate):
        fila += [("coordenada_poco", p, None, {}) for p in sorted(pasta.glob("*.csv"))]
    for pasta in _pastas("campos-georreferenciados", ate):
        fila += [("coordenada_campo", p, None, {}) for p in sorted(pasta.glob("*.csv"))]
    return fila


def processar(conn, cad: Cadastros, fonte: str, caminho: Path, membro: str | None, conteudo: bytes, opcoes: dict) -> dict:
    if fonte.startswith("producao"):
        return carga.carregar_producao(conn, cad, membro or caminho.name, conteudo, opcoes["id_carga"])
    if fonte.startswith("preco"):
        return carga.carregar_preco(conn, cad, caminho, opcoes["id_carga"], opcoes["tipo"], opcoes["extraido"])
    if fonte == "concessionarios":
        return carga.carregar_concessionarios(conn, cad, caminho, opcoes["id_carga"])
    if fonte == "pais_origem":
        return carga.carregar_pais_origem(conn, cad, caminho, opcoes["id_carga"])
    if fonte == "coordenada_poco":
        return carga.carregar_coordenada_poco(conn, cad, caminho, opcoes["id_carga"])
    if fonte == "coordenada_campo":
        return carga.carregar_coordenada_campo(conn, cad, caminho, opcoes["id_carga"])
    raise ValueError(fonte)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ETL 1: fontes da ANP -> stage")
    ap.add_argument("--banco", help="banco de destino (padrão: ST_DB do .env)")
    ap.add_argument("--ate", help="carregar só as pastas de download até esta data (AAAA-MM-DD)")
    ap.add_argument("--listar", action="store_true", help="só listar os arquivos, sem gravar")
    args = ap.parse_args(argv)
    # Nomes de arquivos dentro dos zips podem ter caracteres que o terminal do Windows não exibe.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    fila = descobrir(args.ate)
    if args.listar:
        for i, (fonte, caminho, membro, _) in enumerate(fila, 1):
            print(f"{i:3}. {fonte:22} {carga.nome_relativo(caminho, membro)}")
        print(f"{len(fila)} arquivos")
        return 0

    inicio = time.time()
    totais = {"carregados": 0, "repetidos": 0, "linhas": 0}
    with psycopg.connect(conninfo(args.banco), autocommit=True) as conn:
        cad = Cadastros(conn)
        for i, (fonte, caminho, membro, opcoes) in enumerate(fila, 1):
            t0 = time.time()
            rel = carga.nome_relativo(caminho, membro)
            conteudo = leitores.conteudo_arquivo(caminho, membro)
            h = carga.sha256(conteudo)
            if carga.ja_carregado(conn, h):
                carga.registrar_carga(conn, rel, fonte, h, "repetida")
                totais["repetidos"] += 1
                print(f"[{i:3}/{len(fila)}] REPETIDO  {rel}")
                continue
            try:
                with conn.transaction():
                    id_carga = carga.registrar_carga(conn, rel, fonte, h, "carregada")
                    res = processar(conn, cad, fonte, caminho, membro, conteudo, {**opcoes, "id_carga": id_carga})
                    conn.execute("UPDATE carga SET qtd_linhas = %s WHERE id_carga = %s", [res["gravadas"], id_carga])
            except Exception as e:
                print(f"[{i:3}/{len(fila)}] ERRO      {rel}: {e}", file=sys.stderr)
                print("A transação deste arquivo foi desfeita; a carga parou aqui.", file=sys.stderr)
                return 1
            totais["carregados"] += 1
            totais["linhas"] += res["gravadas"]
            extra = ""
            if "chaves_novas" in res:
                extra = f" | chaves novas {res['chaves_novas']:,}, alteradas {res['chaves_alteradas']:,}, iguais {res['chaves_iguais']:,}"
            if res.get("formatos"):
                extra += f" | formatos {res['formatos']}"
            print(f"[{i:3}/{len(fila)}] OK        {rel}: lidas {res['lidas']:,}, gravadas {res['gravadas']:,}{extra} ({time.time() - t0:.1f}s)")
        print(f"\nResumo: {totais['carregados']} arquivos carregados, {totais['repetidos']} repetidos, "
              f"{totais['linhas']:,} linhas gravadas em {time.time() - inicio:.0f}s")
        if cad.novos:
            print("Cadastros criados:", ", ".join(f"{t} {n:,}" for t, n in sorted(cad.novos.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
