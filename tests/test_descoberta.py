"""Descoberta dos arquivos e ordem de carga do ETL 1 (passo 1 da especificação no PASSO-A-PASSO).

Premissas [autor]: cada download fica em data/raw/anp/<fonte>/AAAA-MM-DD/; a carga segue a ordem
país de origem -> concessionários -> produção (cronológica) -> preços -> coordenadas; --ate limita as pastas
de download.
"""

import hashlib
from pathlib import Path

import pytest

from etl.python.etl1 import __main__ as etl1_main
from etl.python.etl1 import carga

pytestmark = pytest.mark.unidade

# Nomes reais dos zips de produção, que mudam de padrão entre os anos (ver README).
ZIPS_REAIS = [
    "2023_producao-01.zip", "producao-por-poco-2005.zip", "2021-08-producao.zip", "2022_producao-2022-04.zip",
    "2021_01_producao.zip", "2022_2022_05_producao.zip", "producao-por-poco-2020.zip", "2022_producao-2022-01.zip",
]


def test_zips_de_producao_em_ordem_cronologica_apesar_dos_nomes():
    ordenados = sorted((Path(n) for n in ZIPS_REAIS), key=etl1_main._ordem_producao)
    assert [p.name for p in ordenados] == [
        "producao-por-poco-2005.zip", "producao-por-poco-2020.zip", "2021_01_producao.zip", "2021-08-producao.zip",
        "2022_producao-2022-01.zip", "2022_producao-2022-04.zip", "2022_2022_05_producao.zip", "2023_producao-01.zip",
    ]


def test_ordem_de_carga_das_fontes(dados_teste):
    fila = etl1_main.descobrir(None)
    fontes = [f for f, *_ in fila]
    assert fontes[:2] == ["pais_origem", "concessionarios"]  # empresas e grupos antes das participações
    assert fontes[2:9] == ["producao_por_poco"] * 7
    assert fontes[9:] == ["preco_minimo_pdf", "preco_minimo", "preco_referencia", "coordenada_poco", "coordenada_campo"]
    membros = [m for f, _, m, _ in fila if f == "producao_por_poco"]
    assert membros == [
        "2005/2005_producao_terra.csv",
        "2010/2010_producao_mar.csv", "2010/2010_01_producao_mar.csv", "2010/2010_02_producao_terra.csv",
        "2018/2018_producao_presal.csv", "2019/2019_02_producao_terra.csv", "2023_12_producao_Terra.csv",
    ]


def test_ate_ignora_downloads_posteriores(dados_teste):
    nova = dados_teste / "raw" / "anp" / "producao-por-poco-cdp" / "2026-02-01"
    nova.mkdir(parents=True)
    (nova / "2023_12_producao_Terra.csv").write_bytes(b"x")
    assert any(f == "producao_por_poco_cdp" for f, *_ in etl1_main.descobrir(None))
    assert not any(f == "producao_por_poco_cdp" for f, *_ in etl1_main.descobrir("2026-01-31"))


def test_pasta_fora_do_padrao_de_data_e_ignorada(dados_teste):
    errada = dados_teste / "raw" / "anp" / "producao-por-poco-cdp" / "novos"
    errada.mkdir(parents=True)
    (errada / "2023_12_producao_Terra.csv").write_bytes(b"x")
    assert not any(f == "producao_por_poco_cdp" for f, *_ in etl1_main.descobrir(None))


def test_listar_nao_grava_nada(dados_teste, capsys):
    # --listar não abre conexão com o banco
    assert etl1_main.main(["--listar"]) == 0
    assert "14 arquivos" in capsys.readouterr().out


def test_hash_sha256_do_conteudo():
    assert carga.sha256(b"abc") == hashlib.sha256(b"abc").hexdigest()


def test_nome_relativo_de_csv_dentro_de_zip(dados_teste):
    z = dados_teste / "raw" / "anp" / "producao-por-poco" / "2026-01-01" / "producao-por-poco-2010.zip"
    assert carga.nome_relativo(z, "2010/2010_producao_mar.csv") == \
        "raw/anp/producao-por-poco/2026-01-01/producao-por-poco-2010.zip::2010/2010_producao_mar.csv"
    assert carga.nome_relativo(z) == "raw/anp/producao-por-poco/2026-01-01/producao-por-poco-2010.zip"
