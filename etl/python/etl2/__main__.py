"""ETL 2 (Python): stage (st_anp) -> Data Warehouse (dw_anp).

Uso:
    .venv/Scripts/python -m etl.python.etl2
    .venv/Scripts/python -m etl.python.etl2 --stage outro_st --dw outro_dw

Etapas (docs/etl/tratamentos.md; especificação passo a passo no guia do projeto):
    1. extração: versão mais recente (T17), sem o pré-sal repetido (T16), repetições consolidadas (T02)
    2. dimensões com SCD2: empresa, contrato, campo, poço, instalação e corrente
    3. tabela de controle etl_depara (T22)
    4. fatos (recarga completa): ft_producao e ft_participacao
A carga no DW é uma transação só: ou entra tudo, ou nada.
"""

import argparse
import os
import sys
import time
from datetime import datetime

import psycopg

from etl.python.etl1.config import conninfo

from . import dimensoes, extracao, fatos


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ETL 2: stage -> Data Warehouse")
    ap.add_argument("--stage", help="banco da stage (padrão: ST_DB do .env)")
    ap.add_argument("--dw", help="banco do DW (padrão: DW_DB do .env)")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    inicio, agora = time.time(), datetime.now().replace(microsecond=0)
    etapa = lambda nome: print(f"[{time.time() - inicio:6.0f}s] {nome}", flush=True)

    with psycopg.connect(conninfo(args.stage)) as st, psycopg.connect(conninfo(args.dw or os.environ["DW_DB"])) as dw:
        etapa("extração (T17, T16, T02)")
        extracao.preparar(st)
        print("   ", extracao.contagens(st))
        depara = []
        sk = {}
        etapa("dim_empresa");    sk["empresa"], nk_empresa = dimensoes.empresas(st, dw, agora, depara)
        etapa("dim_contrato");   sk["contrato"], _ = dimensoes.contratos(st, dw, agora, depara)
        etapa("dim_campo");      sk["campo"], _ = dimensoes.campos(st, dw, agora, depara, nk_empresa)
        etapa("dim_poco");       sk["poco"], _ = dimensoes.pocos(st, dw, agora, depara)
        etapa("dim_instalacao"); sk["instalacao"], _ = dimensoes.instalacoes(st, dw, agora, depara)
        etapa("dim_corrente");   sk["corrente"], _ = dimensoes.correntes(st, dw, agora, depara)
        etapa("etl_depara")
        dw.execute("TRUNCATE etl_depara")
        with dw.cursor().copy("COPY etl_depara (nm_dimensao, id_stage, nm_original, nk_dw) FROM STDIN") as cp:
            for linha in depara:
                cp.write_row(linha)
        etapa("ft_producao");     print("   ", fatos.producao(st, dw, sk))
        etapa("ft_participacao"); print("   ", fatos.participacao(st, dw, sk["empresa"], sk["contrato"]))
        for t in ("dim_empresa", "dim_contrato", "dim_campo", "dim_poco", "dim_instalacao", "dim_corrente", "ft_producao", "ft_participacao"):
            print(f"    {t:16} {dw.execute(f'SELECT count(*) FROM {t}').fetchone()[0]:>10,}")
        st.rollback()  # a stage só foi lida (tabelas temporárias)
    etapa("fim")
    return 0


if __name__ == "__main__":
    sys.exit(main())
