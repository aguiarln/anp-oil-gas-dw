"""Recursos compartilhados pelos testes.

Amostras (tests/dados/amostras/): trechos dos arquivos reais da ANP, com o cabeçalho original e as
primeiras linhas de dados de cada layout, gravados com a codificação original. Foram tirados dos brutos de
data/raw/anp/<fonte>/2026-09-30/ e de data/interim/anp/. O L19_2010_producao_mar_anual.csv traz, do CSV
anual de 2010, as linhas de 01/2010 que também estão no L19_2010_01_producao_mar.csv (o mesmo mês
publicado duas vezes nos zips de 2010-2015) e mais uma linha de 02/2010, para que os dois arquivos difiram.
POCOS_SIRGAS.csv e CAMPOS_PRODUCAO_SIRGAS.csv são linhas das camadas de coordenadas da ANP (download de
17/10/2026), com o cabeçalho original.

Bancos temporários: os testes de integração criam bancos "st_teste_pytest_*" e apagam no fim. A stage
oficial (st_anp) nunca é alterada pelos testes.
"""

import glob
import os
import shutil
import uuid
import zipfile
from pathlib import Path

import psycopg
import pytest

from etl.python.etl1 import __main__ as etl1_main
from etl.python.etl1 import carga as etl1_carga
from etl.python.etl1.config import conninfo

RAIZ = Path(__file__).resolve().parents[1]
AMOSTRAS = RAIZ / "tests" / "dados" / "amostras"
DDL_STAGE = RAIZ / "database" / "st" / "criar_tabelas.sql"
CARREGAR_BASE = RAIZ / "database" / "st" / "carregar_base.sql"
DOWNLOAD = "2026-01-01"  # data fictícia da pasta de download nos dados de teste


def amostra(nome: str) -> bytes:
    return (AMOSTRAS / nome).read_bytes()


# ---------- PostgreSQL ----------

def _postgres_disponivel() -> bool:
    try:
        with psycopg.connect(conninfo("postgres"), connect_timeout=3):
            return True
    except Exception:
        return False


def _criar_banco(nome: str, ddl: Path | None = DDL_STAGE):
    with psycopg.connect(conninfo("postgres"), autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {nome} WITH (FORCE)")
        c.execute(f"CREATE DATABASE {nome} ENCODING 'UTF8' TEMPLATE template0")
    if ddl:
        with psycopg.connect(conninfo(nome)) as c:
            c.execute(ddl.read_text(encoding="utf-8"))


def _apagar_banco(nome: str):
    with psycopg.connect(conninfo("postgres"), autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {nome} WITH (FORCE)")


@pytest.fixture
def novo_banco():
    """Fábrica de bancos temporários com o DDL da stage. Uso: nome = novo_banco()."""
    if not _postgres_disponivel():
        pytest.skip("PostgreSQL indisponível (confira o .env)")
    criados = []

    def criar(ddl: Path | None = DDL_STAGE) -> str:
        nome = f"st_teste_pytest_{uuid.uuid4().hex[:8]}"
        _criar_banco(nome, ddl)
        criados.append(nome)
        return nome

    yield criar
    for nome in criados:
        _apagar_banco(nome)


@pytest.fixture
def banco(novo_banco):
    return novo_banco()


def consultar(banco: str, sql: str, params=None):
    with psycopg.connect(conninfo(banco)) as c:
        return c.execute(sql, params).fetchall()


def valor(banco: str, sql: str, params=None):
    return consultar(banco, sql, params)[0][0]


def psql_executavel() -> str | None:
    achado = shutil.which("psql")
    if achado:
        return achado
    candidatos = sorted(glob.glob(r"C:\Program Files\PostgreSQL\*\bin\psql.exe"), reverse=True)
    return candidatos[0] if candidatos else None


def ambiente_psql() -> dict:
    env = dict(os.environ)
    env.setdefault("PGHOST", "localhost")
    env.setdefault("PGPORT", "5432")
    return env


# ---------- pasta de dados fictícia (mesma estrutura de data/) ----------

def _zip(destino: Path, membros: dict[str, bytes]):
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
        for nome, conteudo in membros.items():
            zf.writestr(nome, conteudo)


def montar_dados(base: Path) -> Path:
    """Cria base/data com as amostras, na mesma organização de data/raw/anp e data/interim/anp."""
    dados = base / "data"
    raw = dados / "raw" / "anp"
    conc = raw / "concessionarios" / DOWNLOAD
    conc.mkdir(parents=True)
    for nome in ("relacao-concessionarios.csv", "relacao-pais-origem-concessionarios.csv"):
        (conc / nome).write_bytes(amostra(nome))
    prod = raw / "producao-por-poco" / DOWNLOAD
    _zip(prod / "producao-por-poco-2005.zip", {"2005/2005_producao_terra.csv": amostra("L19_2005_producao_terra.csv")})
    _zip(prod / "producao-por-poco-2010.zip", {
        "2010/2010_01_producao_mar.csv": amostra("L19_2010_01_producao_mar.csv"),
        "2010/2010_02_producao_terra.csv": amostra("L19_SEM_UF_2010_02_producao_terra.csv"),
        "2010/2010_producao_mar.csv": amostra("L19_2010_producao_mar_anual.csv"),
    })
    _zip(prod / "producao-por-poco-2018.zip", {"2018/2018_producao_presal.csv": amostra("L47_2018_producao_presal.csv")})
    _zip(prod / "producao-por-poco-2019.zip", {"2019/2019_02_producao_terra.csv": amostra("L49_2019_02_producao_terra.csv")})
    _zip(prod / "2023_producao-12.zip", {"2023_12_producao_Terra.csv": amostra("L48_2023_12_producao_Terra.csv")})
    pmin = raw / "preco-minimo-petroleo" / DOWNLOAD
    pmin.mkdir(parents=True)
    (pmin / "precominpetro_2009.csv").write_bytes(amostra("precominpetro_2009.csv"))
    pref = raw / "preco-referencia-petroleo" / DOWNLOAD
    pref.mkdir(parents=True)
    (pref / "preco-referencia-petroleo-2021.csv").write_bytes(amostra("preco-referencia-petroleo-2021.csv"))
    interim = dados / "interim" / "anp"
    interim.mkdir(parents=True)
    (interim / "preco-minimo-petroleo-2005-2008.csv").write_bytes(amostra("preco-minimo-petroleo-2005-2008.csv"))
    for fonte, nome in (("pocos-georreferenciados", "POCOS_SIRGAS.csv"), ("campos-georreferenciados", "CAMPOS_PRODUCAO_SIRGAS.csv")):
        pasta = raw / fonte / DOWNLOAD
        pasta.mkdir(parents=True)
        (pasta / nome).write_bytes(amostra(nome))
    return dados


def apontar_etl1(monkeypatch, dados: Path):
    """Faz o ETL 1 ler a pasta `dados` em vez de data/ do projeto (sem alterar o código do ETL)."""
    monkeypatch.setattr(etl1_main, "RAW", dados / "raw" / "anp")
    monkeypatch.setattr(etl1_main, "EXTRAIDO_2005_2008", dados / "interim" / "anp" / "preco-minimo-petroleo-2005-2008.csv")
    monkeypatch.setattr(etl1_carga, "DADOS", dados)


@pytest.fixture
def dados_teste(tmp_path, monkeypatch) -> Path:
    """Pasta data/ fictícia, montada com as amostras, já apontada para o ETL 1."""
    dados = montar_dados(tmp_path)
    apontar_etl1(monkeypatch, dados)
    return dados


def rodar_etl1(banco: str, *args: str) -> int:
    return etl1_main.main(["--banco", banco, *args])


# Totais esperados da carga das amostras (conferidos linha a linha nos arquivos de tests/dados/amostras).
ESPERADO = {
    "cargas": 14,  # 2 concessionários + 7 CSVs de produção + 3 de preço + coordenadas de poços e de campos
    "producao_mensal": 34,  # 6 (2005) + 6 (2010 anual) + 0 (mensal 01/2010, igual ao anual) + 6 (02/2010) + 5 + 5 + 6
    "preco_petroleo": 17,  # 5 (2005-2008) + 5 (2009) + 7 (2021)
    "participacao_contrato": 8,
    "coordenada_poco": 6,   # 4 poços que estão nas amostras de produção + 2 que nunca produziram
    "coordenada_campo": 3,  # ESTREITO (Potiguar), CANDEIAS (Recôncavo) e CANCÃ (bacia grafada com hífen oculto)
}
