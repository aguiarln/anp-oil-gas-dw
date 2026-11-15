"""Base origem: as 16 tabelas da stage em CSV, para revisão e auditoria (README, "Base origem").

Premissas [autor]: quem revisa recria a stage pelos CSVs e chega ao mesmo banco; pode auditar o ETL 1
conferindo o banco contra o manifesto; a stage recriada continua aceitando cargas novas do ETL 1.
"""

import csv
import subprocess

import psycopg
import pytest

from etl.python.etl1 import exportar
from etl.python.etl1.config import conninfo

from .conftest import CARREGAR_BASE, ESPERADO, ambiente_psql, amostra, psql_executavel, rodar_etl1, valor

pytestmark = pytest.mark.integracao


def _exportar(banco, pasta):
    assert exportar.main([str(pasta), "--banco", banco]) == 0


def _carregar_base(banco, pasta):
    psql = psql_executavel()
    if not psql:
        pytest.skip("psql não encontrado")
    r = subprocess.run([psql, "-q", "-w", "-v", "ON_ERROR_STOP=1", "-U", ambiente_psql().get("PGUSER", "postgres"),
                        "-d", banco, "-f", str(CARREGAR_BASE)], cwd=pasta, env=ambiente_psql(), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_exporta_14_csvs_e_o_manifesto(banco, dados_teste, tmp_path):
    rodar_etl1(banco)
    pasta = tmp_path / "base-origem"
    _exportar(banco, pasta)
    assert sorted(p.name for p in pasta.iterdir()) == sorted([f"{t}.csv" for t in exportar.TABELAS] + ["manifesto.csv"])
    with open(pasta / "manifesto.csv", encoding="utf-8") as f:
        manifesto = {r["tabela"]: int(r["linhas"]) for r in csv.DictReader(f)}
    assert manifesto["producao_mensal"] == ESPERADO["producao_mensal"]
    assert manifesto["carga"] == ESPERADO["cargas"]
    # cada CSV tem cabeçalho + uma linha por registro
    with open(pasta / "preco_petroleo.csv", encoding="utf-8") as f:
        assert len(list(csv.reader(f))) == ESPERADO["preco_petroleo"] + 1


def test_reproduzir_a_stage_pelos_csvs(novo_banco, dados_teste, tmp_path):
    origem, copia = novo_banco(), novo_banco()
    rodar_etl1(origem)
    pasta = tmp_path / "base-origem"
    _exportar(origem, pasta)
    _carregar_base(copia, pasta)
    assert exportar.main([str(pasta), "--conferir", "--banco", copia]) == 0


def test_conferencia_detecta_diferenca(novo_banco, dados_teste, tmp_path):
    origem, copia = novo_banco(), novo_banco()
    rodar_etl1(origem)
    pasta = tmp_path / "base-origem"
    _exportar(origem, pasta)
    _carregar_base(copia, pasta)
    with psycopg.connect(conninfo(copia)) as c:
        c.execute("UPDATE producao_mensal SET oleo_bbl_dia = oleo_bbl_dia + 1 WHERE id_producao = 1")
    assert exportar.main([str(pasta), "--conferir", "--banco", copia]) == 1


def test_conferencia_ignora_so_o_horario_da_carga(novo_banco, dados_teste, tmp_path):
    # um ETL 1 rodado em outro momento tem outro data_hora_carga, mas é o mesmo banco
    origem, outro = novo_banco(), novo_banco()
    rodar_etl1(origem)
    rodar_etl1(outro)
    pasta = tmp_path / "base-origem"
    _exportar(origem, pasta)
    with psycopg.connect(conninfo(outro)) as c:
        c.execute("UPDATE carga SET data_hora_carga = data_hora_carga + interval '1 day'")
    assert exportar.main([str(pasta), "--conferir", "--banco", outro]) == 0


def test_stage_recriada_aceita_carga_nova(novo_banco, dados_teste, tmp_path):
    origem, copia = novo_banco(), novo_banco()
    rodar_etl1(origem)
    pasta = tmp_path / "base-origem"
    _exportar(origem, pasta)
    _carregar_base(copia, pasta)
    max_carga = valor(copia, "SELECT max(id_carga) FROM carga")
    max_producao = valor(copia, "SELECT max(id_producao) FROM producao_mensal")
    # arquivo novo da CDP: o 12/2023 com uma linha a mais (poço novo)
    texto = amostra("L48_2023_12_producao_Terra.csv").decode("latin1")
    ultima = texto.splitlines()[-1]
    nova = ultima.replace("7-RP-129-RN", "7-RP-999-RN", 1)
    cdp = dados_teste / "raw" / "anp" / "producao-por-poco-cdp" / "2026-02-01"
    cdp.mkdir(parents=True)
    (cdp / "2023_12_producao_Terra.csv").write_bytes((texto + nova + "\n").encode("latin1"))
    assert rodar_etl1(copia) == 0
    # os arquivos antigos são reconhecidos pelo hash; só a linha nova entra, com IDs que continuam a numeração
    assert valor(copia, "SELECT count(*) FROM carga WHERE situacao = 'repetida'") == ESPERADO["cargas"]
    assert valor(copia, "SELECT qtd_linhas FROM carga WHERE fonte = 'producao_por_poco_cdp'") == 1
    assert valor(copia, "SELECT min(id_carga) FROM carga WHERE id_carga > %s", [max_carga]) == max_carga + 1
    assert valor(copia, "SELECT max(id_producao) FROM producao_mensal") == max_producao + 1
