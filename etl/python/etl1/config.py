"""Configuração do ETL 1: caminhos do projeto e conexão com o PostgreSQL (lida do .env)."""

import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[3]
DADOS = RAIZ / "data"

load_dotenv(RAIZ / ".env")


def conninfo(banco: str | None = None) -> str:
    """String de conexão do psycopg para o banco informado (padrão: ST_DB do .env)."""
    banco = banco or os.environ["ST_DB"]
    partes = {
        "host": os.environ.get("PGHOST", "localhost"),
        "port": os.environ.get("PGPORT", "5432"),
        "user": os.environ["PGUSER"],
        "password": os.environ.get("PGPASSWORD", ""),
        "dbname": banco,
    }
    return " ".join(f"{k}={v}" for k, v in partes.items() if v != "")
