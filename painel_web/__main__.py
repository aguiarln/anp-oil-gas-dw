"""Abre o painel web: .venv/Scripts/python -m painel_web (na raiz do projeto).

Roda o Streamlit de dentro da pasta painel_web/, para usar o tema de painel_web/.streamlit/config.toml.
"""
import subprocess
import sys
from pathlib import Path

PASTA = Path(__file__).resolve().parent

if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, "-m", "streamlit", "run", "app.py", *sys.argv[1:]], cwd=PASTA))
