"""Base origem da stage: exporta as 16 tabelas em CSV (uma por tabela) e confere um banco contra elas.

Uso:
    .venv/Scripts/python -m etl.python.etl1.exportar <pasta>              # stage -> 16 CSVs + manifesto.csv
    .venv/Scripts/python -m etl.python.etl1.exportar <pasta> --conferir   # compara um banco com o manifesto
    ... --banco outro_banco                                              # banco de origem/conferência (padrão: ST_DB)

Os CSVs são recarregados no PostgreSQL por database/st/carregar_base.sql. O manifesto guarda, por tabela, a
quantidade de linhas e um SHA-256 do conteúdo, calculado sobre as linhas em ordem de chave primária. O hash
de "carga" ignora data_hora_carga, porque o horário muda a cada execução do ETL 1; assim, um banco
recarregado pelo ETL 1 a partir dos brutos tem de bater com o manifesto, tabela por tabela.
"""

import argparse
import csv
import hashlib
import sys
from pathlib import Path

import psycopg

from .config import conninfo

# Ordem das chaves estrangeiras: cada tabela vem depois das que ela referencia.
TABELAS = [
    "carga", "grupo_economico", "empresa", "bacia", "estado", "contrato", "participacao_contrato", "campo",
    "poco", "instalacao", "corrente", "caracterizacao_petroleo", "producao_mensal", "preco_petroleo",
    "coordenada_poco", "coordenada_campo",
]
IGNORAR_NO_HASH = {"carga": {"data_hora_carga"}}


def _colunas(conn, tabela):
    return [r[0] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s "
        "ORDER BY ordinal_position", [tabela])]


def _chave_primaria(conn, tabela):
    return [r[0] for r in conn.execute(
        """SELECT a.attname FROM pg_index i
           JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
           WHERE i.indrelid = %s::regclass AND i.indisprimary
           ORDER BY array_position(i.indkey, a.attnum)""", [tabela])]


def _copiar(conn, tabela, colunas, destino=None):
    """COPY das colunas em ordem de PK; grava em `destino` (arquivo) se informado. Devolve (linhas, sha256)."""
    ordem = ", ".join(_chave_primaria(conn, tabela))
    sql = f"COPY (SELECT {', '.join(colunas)} FROM {tabela} ORDER BY {ordem}) TO STDOUT WITH (FORMAT csv, HEADER true)"
    h = hashlib.sha256()
    with conn.cursor().copy(sql) as cp:
        for bloco in cp:
            bloco = bytes(bloco)
            h.update(bloco)
            if destino:
                destino.write(bloco)
    linhas = conn.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]
    return linhas, h.hexdigest()


def _hash_conteudo(conn, tabela):
    colunas = [c for c in _colunas(conn, tabela) if c not in IGNORAR_NO_HASH.get(tabela, set())]
    return _copiar(conn, tabela, colunas)


def exportar(conn, pasta: Path):
    pasta.mkdir(parents=True, exist_ok=True)
    manifesto = []
    for t in TABELAS:
        with open(pasta / f"{t}.csv", "wb") as f:
            linhas, _ = _copiar(conn, t, _colunas(conn, t), f)
        _, h = _hash_conteudo(conn, t)
        manifesto.append((t, linhas, h))
        print(f"{t:25} {linhas:>10,} linhas  {(pasta / f'{t}.csv').stat().st_size / 1e6:8.1f} MB")
    with open(pasta / "manifesto.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tabela", "linhas", "sha256_conteudo"])
        w.writerows(manifesto)
    print(f"manifesto: {pasta / 'manifesto.csv'}")


def conferir(conn, pasta: Path) -> int:
    with open(pasta / "manifesto.csv", encoding="utf-8") as f:
        esperado = {r["tabela"]: (int(r["linhas"]), r["sha256_conteudo"]) for r in csv.DictReader(f)}
    erros = 0
    for t in TABELAS:
        linhas, h = _hash_conteudo(conn, t)
        ok = (linhas, h) == esperado[t]
        erros += not ok
        print(f"{'OK     ' if ok else 'DIFERE '} {t:25} {linhas:>10,} linhas (esperado {esperado[t][0]:,})")
    print("Banco idêntico à base origem." if not erros else f"{erros} tabela(s) diferem da base origem.")
    return 1 if erros else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Exporta a stage em CSVs (um por tabela) ou confere um banco contra eles")
    ap.add_argument("pasta", type=Path, help="pasta dos CSVs e do manifesto.csv")
    ap.add_argument("--conferir", action="store_true", help="comparar o banco com o manifesto, sem exportar")
    ap.add_argument("--banco", help="banco a exportar ou conferir (padrão: ST_DB do .env)")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with psycopg.connect(conninfo(args.banco)) as conn:
        if args.conferir:
            return conferir(conn, args.pasta)
        exportar(conn, args.pasta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
