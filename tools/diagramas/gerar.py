"""Gera de novo as figuras dos documentos em docs/modelagem/ (ou noutra pasta).

Uso: .venv/Scripts/python tools/diagramas/gerar.py [pasta]
Os diagramas da stage e do modelo dimensional são desenhados a partir do catálogo dos bancos do .env (ST_DB e DW_DB);
rode depois de qualquer mudança no DDL. O croqui do processo de BI não depende dos bancos.
"""
import runpy
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
FIGURAS = {"er_stage.py": "oltp_diagrama_relacional.png", "dw_estrelas.py": "dw_diagrama_estrela.png",
           "croqui.py": "processo_bi_croqui.png"}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    pasta = Path(argv[0]) if argv else AQUI.parents[1] / "docs" / "modelagem"
    pasta.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(AQUI))
    for script, png in FIGURAS.items():
        sys.argv = [script, str(pasta / png)]
        runpy.run_path(str(AQUI / script), run_name="__main__")
        print("gerado:", pasta / png)
    return 0


if __name__ == "__main__":
    sys.exit(main())
