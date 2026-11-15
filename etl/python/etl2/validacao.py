"""Validação stage × DW (passo 5.5): confere o DW carregado pelo ETL 2 contra a stage.

Uso:
    .venv/Scripts/python -m etl.python.etl2.validacao [--stage st] [--dw dw]

Verificações que reprovam (código de saída 1): grão da fato, somas dos volumes mensais, chaves obrigatórias
sem a linha 0 e entradas das listas de-para sem correspondência na stage. As demais são informativas
(cobertura de preço, coordenadas e contornos; T06 e T09).
"""

import argparse
import os
import sys

import psycopg

from etl.python.etl1.config import conninfo

from . import de_para, extracao
from .normalizacao import chave

VOLUMES = [("oleo_bbl_dia", "md_oleo_bbl"), ("petroleo_bbl_dia", "md_petroleo_bbl"), ("agua_bbl_dia", "md_agua_bbl"),
           ("gas_total_mm3_dia", "md_gas_total_mil_m3")]


def validar(st, dw) -> tuple[list, list]:
    """Devolve (reprovações, informações)."""
    extracao.preparar(st)
    um = lambda c, s: c.execute(s).fetchone()[0]
    erros, info = [], []

    grao, fato = um(st, "SELECT count(*) FROM cons"), um(dw, "SELECT count(*) FROM ft_producao")
    (info if grao == fato else erros).append(f"grão: {fato:,} linhas na ft_producao, {grao:,} esperadas")

    for orig, dest in VOLUMES:
        esperado = um(st, f"""SELECT coalesce(sum({orig} * extract(day FROM (periodo + interval '1 month' - interval '1 day'))), 0) FROM cons""")
        obtido = um(dw, f"SELECT coalesce(sum({dest}), 0) FROM ft_producao")
        ok = abs(float(esperado) - float(obtido)) <= max(1.0, abs(float(esperado)) * 1e-9)
        (info if ok else erros).append(f"soma de {dest}: {float(obtido):,.0f} no DW, {float(esperado):,.0f} na stage")

    for col in ("sk_poco", "sk_campo", "sk_empresa"):
        n = um(dw, f"SELECT count(*) FROM ft_producao WHERE {col} = 0")
        (info if n == 0 else erros).append(f"{col} = 0 (linha não qualificada) em {n:,} linhas da ft_producao")
    # contrato: só as linhas em que a fonte não informa o número (ex.: "-") podem cair na linha 0 (DNQ)
    sem_numero = um(st, "SELECT count(*) FROM cons c JOIN contrato k USING (id_contrato) WHERE k.numero !~ '[0-9]'")
    n = um(dw, "SELECT count(*) FROM ft_producao WHERE sk_contrato = 0")
    (info if n == sem_numero else erros).append(
        f"sk_contrato = 0 em {n:,} linhas; a fonte não informa o contrato em {sem_numero:,} (ex.: DOM JOÃO, QUIAMBINA)")

    empresas = {chave(n) for (n,) in st.execute("SELECT nome_fantasia FROM empresa").fetchall()}
    campos = {(chave(n), chave(b)) for n, b in st.execute("SELECT c.nome, b.nome FROM campo c JOIN bacia b USING (id_bacia)").fetchall()}
    faltam = [o for o in de_para.empresas() if o not in empresas] + \
             [e["origem"] for e in de_para.campos() if e["origem"] not in campos] + \
             [g for g in de_para.grupos_economicos() if g not in empresas]
    (info if not faltam else erros).append(f"listas de-para sem correspondência na stage: {faltam or 'nenhuma'}")
    trocas, vendas = dw.execute("""SELECT count(dt_ultima_troca_operador), count(dt_ultima_venda) FROM dim_campo
                                   WHERE sk_campo <> 0 AND etl_dt_fim = '2199-12-31'""").fetchone()
    info.append(f"T23 campos com troca de operador: {trocas}; com venda (o grupo econômico muda): {vendas}")

    # informativas
    pct = um(dw, """SELECT round(100 * sum(md_petroleo_bbl) FILTER (WHERE md_preco_rs_m3 IS NOT NULL) / nullif(sum(md_petroleo_bbl), 0), 1)
                    FROM ft_producao""")
    info.append(f"volume de petróleo com preço: {pct}%")
    info.append("campos com contorno: {} de {}".format(*dw.execute(
        "SELECT count(*) FILTER (WHERE desc_contorno_wkt IS NOT NULL), count(*) FROM dim_campo WHERE sk_campo <> 0").fetchone()))
    info.append("poços com coordenada: {} de {}".format(*dw.execute(
        "SELECT count(*) FILTER (WHERE nr_latitude IS NOT NULL), count(*) FROM dim_poco WHERE sk_poco <> 0").fetchone()))
    fora = um(dw, """SELECT count(*) FROM (SELECT sk_data, sk_contrato FROM ft_participacao GROUP BY 1, 2
                     HAVING abs(sum(md_percentual) - 100) > 0.5) x""")
    (erros if fora else info).append(f"contratos cuja participação não soma 100% numa foto: {fora}")  # T15
    info.append("T09 petróleo diferente de óleo + condensado: {} linhas; gás total diferente de associado + não associado: {} linhas".format(
        um(st, "SELECT count(*) FROM cons WHERE abs(coalesce(petroleo_bbl_dia,0) - coalesce(oleo_bbl_dia,0) - coalesce(condensado_bbl_dia,0)) > 0.01"),
        um(st, "SELECT count(*) FROM cons WHERE abs(coalesce(gas_total_mm3_dia,0) - coalesce(gas_assoc_mm3_dia,0) - coalesce(gas_nao_assoc_mm3_dia,0)) > 0.01")))
    vai_volta = st.execute("""
        WITH unico AS (SELECT id_poco, periodo, min(id_campo) id_campo FROM cons GROUP BY 1, 2 HAVING count(*) = 1),
             seq AS (SELECT id_poco, periodo, id_campo, lag(id_campo) OVER w ant FROM unico WINDOW w AS (PARTITION BY id_poco ORDER BY periodo)),
             trocas AS (SELECT id_poco, id_campo, ant, row_number() OVER (PARTITION BY id_poco ORDER BY periodo) n FROM seq WHERE ant <> id_campo)
        SELECT p.nome_anp FROM trocas t1 JOIN trocas t2 ON t2.id_poco = t1.id_poco AND t2.n > t1.n AND t2.id_campo = t1.ant
        JOIN poco p ON p.id_poco = t1.id_poco GROUP BY 1 ORDER BY 1""").fetchall()
    info.append(f"T06 poços que vão e voltam de campo: {len(vai_volta)} (ex.: {', '.join(r[0] for r in vai_volta[:5])})")
    st.rollback()
    return erros, info


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validação stage x DW")
    ap.add_argument("--stage")
    ap.add_argument("--dw")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with psycopg.connect(conninfo(args.stage)) as st, psycopg.connect(conninfo(args.dw or os.environ["DW_DB"])) as dw:
        erros, info = validar(st, dw)
    for linha in info:
        print("OK     ", linha)
    for linha in erros:
        print("ERRO   ", linha)
    print("Validação aprovada." if not erros else f"{len(erros)} verificação(ões) reprovada(s).")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())
