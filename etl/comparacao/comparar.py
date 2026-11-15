"""Conferência Python × PDI: compara o DW carregado pelo ETL 2 em Python (dw_anp) com o DW gêmeo
carregado pelo ETL 2 no Pentaho PDI (dw_anp_pdi).

Uso (na raiz do projeto):
    .venv/Scripts/python -m etl.comparacao.comparar
    .venv/Scripts/python -m etl.comparacao.comparar --python outro_dw --pdi outro_dw_pdi

As chaves substitutas são numeradas por cada carga, então a comparação é feita pelas chaves naturais:
- dimensões: a versão vigente de cada chave natural, atributo por atributo;
- ft_producao e ft_participacao: linha a linha, com as chaves naturais das dimensões e todas as medidas.
Uma chave que só existe no DW do Python, sem linha nas fatos, é histórico do SCD2 (uma versão de uma carga
anterior que a fonte não traz mais, ex.: a chave do contrato antes do T15) e não conta como diferença.
Sai com código 1 se houver diferença de regra.
"""

import argparse
import os
import sys
from decimal import Decimal

import psycopg

from etl.python.etl1.config import conninfo

DIMENSOES = {  # dimensão -> colunas comparadas (fora as de controle do SCD2)
    "dim_empresa": ["nm_empresa", "nm_razao_social", "nm_grupo_economico", "nm_pais"],
    "dim_contrato": ["nr_contrato", "nm_contrato", "nm_rodada", "nm_fase", "nm_ambiente", "nm_bacia"],
    "dim_campo": ["nm_campo", "nm_campo_atual", "nm_campo_sucessor", "nm_bacia", "nm_estado", "sg_estado", "nm_regiao", "desc_contorno_wkt",
                  "nr_latitude_centro", "nr_longitude_centro", "dt_ultima_troca_operador", "dt_ultima_venda", "dt_ultima_reorganizacao"],
    "dim_poco": ["nm_poco", "nm_estado", "sg_estado", "nm_regiao", "nm_ambiente", "nr_latitude", "nr_longitude",
                 "dt_primeira_producao", "dt_ultima_producao"],
    "dim_instalacao": ["nm_instalacao", "nm_tipo_instalacao"],
    "dim_corrente": ["nm_corrente", "nr_grau_api", "nm_dest_leve_corte", "nr_dest_leve_pct", "nm_dest_medio_corte", "nr_dest_medio_pct",
                     "nm_dest_pesado_corte", "nr_dest_pesado_pct", "etl_dt_inicio", "etl_dt_fim", "etl_versao"],
}
PRODUCAO = """SELECT f.sk_data, p.nk_poco, c.nk_campo, e.nk_empresa, ct.nk_contrato, i.nk_instalacao,
       co.nk_corrente || '@' || co.dt_periodo_carga AS corrente,
       round(md_oleo_bbl, 4), round(md_condensado_bbl, 4), round(md_petroleo_bbl, 4), round(md_agua_bbl, 4),
       round(md_gas_assoc_mil_m3, 4), round(md_gas_nao_assoc_mil_m3, 4), round(md_gas_total_mil_m3, 4),
       md_horas_producao, round(md_preco_rs_m3, 4), round(md_receita_estimada_rs, 2)
FROM ft_producao f JOIN dim_poco p USING (sk_poco) JOIN dim_campo c USING (sk_campo) JOIN dim_empresa e USING (sk_empresa)
JOIN dim_contrato ct USING (sk_contrato) JOIN dim_instalacao i USING (sk_instalacao) JOIN dim_corrente co USING (sk_corrente)"""
PARTICIPACAO = """SELECT f.sk_data, e.nk_empresa, ct.nk_contrato, f.md_percentual, f.dd_operador
FROM ft_participacao f JOIN dim_empresa e USING (sk_empresa) JOIN dim_contrato ct USING (sk_contrato)"""


def igual(a, b) -> bool:
    if isinstance(a, (Decimal, float)) and isinstance(b, (Decimal, float)):
        return abs(float(a) - float(b)) < 1e-6
    return a == b


def vigentes(con, dim: str, colunas: list[str]) -> dict:
    suf = dim[4:]
    if dim == "dim_corrente":  # cada período de carga é uma versão (T19)
        sql = f"SELECT nk_corrente, dt_periodo_carga, {', '.join(colunas)} FROM dim_corrente WHERE sk_corrente <> 0"
        return {(r[0], r[1]): r[2:] for r in con.execute(sql)}
    sql = f"SELECT nk_{suf}, {', '.join(colunas)} FROM {dim} WHERE sk_{suf} <> 0 AND etl_dt_fim >= '2199-12-31'"
    return {r[0]: r[1:] for r in con.execute(sql)}


def usadas_nas_fatos(con, dim: str) -> set:
    suf = dim[4:]
    fatos = ["ft_producao"] + (["ft_participacao"] if dim in ("dim_empresa", "dim_contrato") else [])
    uniao = " UNION ".join(f"SELECT DISTINCT sk_{suf} FROM {f}" for f in fatos)
    return {r[0] for r in con.execute(f"SELECT d.nk_{suf} FROM {dim} d WHERE d.sk_{suf} IN ({uniao})")}


def comparar(py, pdi) -> int:
    erros = 0
    for dim, colunas in DIMENSOES.items():
        a, b = vigentes(py, dim, colunas), vigentes(pdi, dim, colunas)
        so_py, so_pdi = set(a) - set(b), set(b) - set(a)
        historico = so_py - (usadas_nas_fatos(py, dim) if dim != "dim_corrente" else set())
        diferentes = [k for k in set(a) & set(b) if not all(igual(x, y) for x, y in zip(a[k], b[k]))]
        problemas = len(so_py - historico) + len(so_pdi) + len(diferentes)
        erros += problemas
        print(f"{'OK  ' if not problemas else 'ERRO'} {dim:15} Python {len(a):>6,} | PDI {len(b):>6,} | iguais {len(set(a) & set(b)) - len(diferentes):>6,}"
              f" | diferentes {len(diferentes)} | só no PDI {len(so_pdi)} | só no Python {len(so_py - historico)}"
              + (f" | histórico do SCD2 no Python: {len(historico)} ({', '.join(map(str, sorted(historico, key=str)[:3]))})" if historico else ""))
        for k in sorted(diferentes, key=str)[:3]:
            cols = [c for c, x, y in zip(colunas, a[k], b[k]) if not igual(x, y)]
            print(f"       {k}: colunas {', '.join(cols)}; Python {[str(x)[:60] for x in a[k]]} | PDI {[str(y)[:60] for y in b[k]]}")
    for nome, sql, n_chave in [("ft_producao", PRODUCAO, 3), ("ft_participacao", PARTICIPACAO, 3)]:
        a = {r[:n_chave]: r[n_chave:] for r in py.execute(sql)}
        b = {r[:n_chave]: r[n_chave:] for r in pdi.execute(sql)}
        diferentes = [k for k in set(a) & set(b) if a[k] != b[k]]
        problemas = len(set(a) ^ set(b)) + len(diferentes)
        erros += problemas
        print(f"{'OK  ' if not problemas else 'ERRO'} {nome:15} Python {len(a):>9,} | PDI {len(b):>9,} | diferentes {len(diferentes)}"
              f" | só no PDI {len(set(b) - set(a))} | só no Python {len(set(a) - set(b))}")
        for k in sorted(diferentes, key=str)[:3]:
            print(f"       {k}: Python {a[k]} | PDI {b[k]}")
    print("Conferência aprovada: o PDI reproduz o ETL 2 em Python." if not erros else f"Conferência reprovada: {erros} diferença(s).")
    return 0 if not erros else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Conferência do DW do Python com o DW gêmeo do PDI")
    ap.add_argument("--python", default=os.environ.get("DW_DB", "dw_anp"))
    ap.add_argument("--pdi", default=os.environ.get("DW_DB_PDI", "dw_anp_pdi"))
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with psycopg.connect(conninfo(args.python)) as py, psycopg.connect(conninfo(args.pdi)) as pdi:
        return comparar(py, pdi)


if __name__ == "__main__":
    sys.exit(main())
