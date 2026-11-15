"""Pipeline completo: arquivos da ANP -> stage -> Data Warehouse.

O pipeline é sempre o mesmo; o que muda são os dados. Depois de baixar arquivos novos da ANP para
data/raw/anp/<fonte>/AAAA-MM-DD/ (README, "Como atualizar os dados"), rode:

    .venv/Scripts/python pipeline.py                  # ETL 1 -> ETL 2 -> validação
    .venv/Scripts/python pipeline.py --exportar-base  # ... e gera de novo a base origem (dist/base-origem)
    pipeline.bat                                      # o mesmo, com duplo clique no Windows

Opções: --motor python|pdi (padrão: MOTOR_PRINCIPAL do .env), --ate AAAA-MM-DD (só pastas de download até
essa data), --stage e --dw (outros bancos). O resumo de cada execução vai para logs/pipeline.log.
"""

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from etl.python.etl1 import __main__ as etl1
from etl.python.etl1 import exportar
from etl.python.etl1.config import RAIZ
from etl.python.etl2 import __main__ as etl2
from etl.python.etl2 import validacao

LOG = RAIZ / "logs" / "pipeline.log"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pipeline: arquivos da ANP -> stage -> DW")
    ap.add_argument("--motor", choices=["python", "pdi"], default=os.environ.get("MOTOR_PRINCIPAL", "python"))
    ap.add_argument("--ate", help="carregar só as pastas de download até esta data (AAAA-MM-DD)")
    ap.add_argument("--stage", help="banco da stage (padrão: ST_DB do .env)")
    ap.add_argument("--dw", help="banco do DW (padrão: DW_DB do .env)")
    ap.add_argument("--exportar-base", action="store_true", help="gerar de novo os CSVs da base origem")
    ap.add_argument("--pasta-base", type=Path, default=RAIZ / "dist" / "base-origem")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.motor == "pdi":
        print("O pipeline executa o motor Python. No Pentaho, só o ETL 2 é reproduzido: rode o Job "
              "etl/pdi/jobs/job_etl2.kjb no Spoon ou no Kitchen (etl/pdi/README.md). Use --motor python.")
        return 2

    inicio = time.time()
    resumo = []

    def etapa(nome, funcao):
        print(f"\n===== {nome} =====", flush=True)
        t0 = time.time()
        codigo = funcao()
        resumo.append(f"{nome}: {'ok' if codigo == 0 else f'ERRO ({codigo})'} em {time.time() - t0:.0f}s")
        return codigo

    banco = ["--banco", args.stage] if args.stage else []
    destino = (["--stage", args.stage] if args.stage else []) + (["--dw", args.dw] if args.dw else [])
    passos = [("ETL 1: arquivos da ANP -> stage", lambda: etl1.main(banco + (["--ate", args.ate] if args.ate else []))),
              ("ETL 2: stage -> DW", lambda: etl2.main(destino)),
              ("Validação stage x DW", lambda: validacao.main(destino))]
    if args.exportar_base:
        passos.append(("Base origem (CSVs da stage)", lambda: exportar.main([str(args.pasta_base)] + banco)))
    codigo = 0
    for nome, funcao in passos:
        codigo = etapa(nome, funcao)
        if codigo != 0:
            break  # uma etapa com erro interrompe o pipeline; o DW só muda numa transação completa do ETL 2

    situacao = "concluído" if codigo == 0 else "interrompido"
    linhas = [f"{datetime.now():%Y-%m-%d %H:%M} pipeline {situacao} (motor {args.motor}, {time.time() - inicio:.0f}s)"] + \
             [f"    {r}" for r in resumo]
    print("\n" + "\n".join(linhas))
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    return codigo


if __name__ == "__main__":
    sys.exit(main())
