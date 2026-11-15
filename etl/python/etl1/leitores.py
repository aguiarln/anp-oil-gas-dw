"""Leitores das fontes da ANP. Cada leitor devolve linhas já convertidas (C02/C03), sem correções.

Formatos da produção por poço (identificados pelo número de colunas e pela posição do período):
  L19          2005-2017: 19 colunas
  L19_SEM_UF   terra 02-12/2010 e 02/2011: sem a coluna Estado; colunas 0-14 deslocadas, col. 15 extra
               (medida sem nome, não carregada) e instalação/tipo/horas nas posições normais (16-18)
  L47          2018-2020: caracterização do petróleo, sem "Data de atualização"
  L48          2021 em diante e consulta online (CDP): L47 + "Data de atualização"
  L49          parte de 2019: duas colunas sem nome no cabeçalho (20 e 29), não carregadas
"""

import csv
import io
import re
import zipfile
from pathlib import Path

from . import conversao as cv

_PERIODO = re.compile(r"\d{4}/\d{2}")

# Posição das colunas de caracterização em cada formato (None = não existe no formato).
_CARAC = {
    "L47": {"periodo_carga": 19, "corrente": 20, "api": 21, "frac": 22, "gas": 28, "dens": 44, "data_atualizacao": None},
    "L48": {"periodo_carga": 19, "corrente": 20, "api": 21, "frac": 22, "gas": 28, "dens": 44, "data_atualizacao": 47},
    "L49": {"periodo_carga": 19, "corrente": 21, "api": 22, "frac": 23, "gas": 30, "dens": 46, "data_atualizacao": None},
}
GAS = ["pct_metano", "pct_etano", "pct_propano", "pct_isobutano", "pct_butano", "pct_isopentano", "pct_n_pentano",
       "pct_hexanos", "pct_heptanos", "pct_octanos", "pct_nonanos", "pct_decanos", "pct_undecanos",
       "pct_oxigenio", "pct_nitrogenio", "pct_gas_carbonico"]


def decodificar(conteudo: bytes) -> str:
    """Os arquivos vêm em UTF-8 (com ou sem BOM) ou ISO-8859-1."""
    try:
        return conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        return conteudo.decode("latin1")


def _origem(nome_csv: str) -> str:
    nome = nome_csv.lower()
    if "presal" in nome or "pre_sal" in nome or "pre-sal" in nome:
        return "presal"
    if "terra" in nome:
        return "terra"
    if "mar" in nome:
        return "mar"
    raise ValueError(f"não foi possível identificar terra/mar/pré-sal pelo nome: {nome_csv}")


def _formato(r: list[str]) -> str | None:
    if len(r) > 7 and _PERIODO.fullmatch(r[7].strip()):
        return {19: "L19", 47: "L47", 48: "L48", 49: "L49"}.get(len(r), f"desconhecido({len(r)})")
    if len(r) > 6 and _PERIODO.fullmatch(r[6].strip()):
        return "L19_SEM_UF" if len(r) == 19 else f"desconhecido_sem_uf({len(r)})"
    return None  # título, cabeçalho ou linha vazia


def _linha_producao(r: list[str], fmt: str) -> dict:
    d = 1 if fmt == "L19_SEM_UF" else 0  # deslocamento quando falta a coluna Estado
    linha = {
        "estado": None if d else cv.texto(r[0]),
        "bacia": cv.texto(r[1 - d]),
        "poco": cv.texto(r[2 - d]),
        # r[3 - d] = "Nome Poço Operador": não carregado (decisão do autor)
        "campo": cv.texto(r[4 - d]),
        "operador": cv.texto(r[5 - d]),
        "contrato": cv.texto(r[6 - d]),
        "periodo": cv.periodo(r[7 - d]),
        "oleo_bbl_dia": cv.numero(r[8 - d]),
        "condensado_bbl_dia": cv.numero(r[9 - d]),
        "petroleo_bbl_dia": cv.numero(r[10 - d]),
        "gas_assoc_mm3_dia": cv.numero(r[11 - d]),
        "gas_nao_assoc_mm3_dia": cv.numero(r[12 - d]),
        "gas_total_mm3_dia": cv.numero(r[13 - d]),
        "gas_royalties": cv.numero(r[14 - d]),
        "agua_bbl_dia": cv.numero(r[15 - d]),   # no formato sem Estado, a água é a col. 14 (bate com o CSV anual)
        # instalação, tipo e horas ficam nas col. 16-18 nos dois formatos de 19 colunas (no sem Estado, a col. 15 é extra)
        "instalacao": cv.texto(r[16]),
        "tipo_instalacao": cv.texto(r[17]),
        "horas_producao": cv.inteiro(r[18]),
        "data_atualizacao": None,
        "caracterizacao": None,
    }
    if fmt in _CARAC:
        p = _CARAC[fmt]
        c = {
            "corrente": cv.texto(r[p["corrente"]]),
            "periodo_carga": cv.periodo_carga(r[p["periodo_carga"]]),
            "grau_api": cv.numero(r[p["api"]]),
            "dest_leve_corte": cv.texto(r[p["frac"]]),
            "dest_leve_pct": cv.numero(r[p["frac"] + 1]),
            "dest_medio_corte": cv.texto(r[p["frac"] + 2]),
            "dest_medio_pct": cv.numero(r[p["frac"] + 3]),
            "dest_pesado_corte": cv.texto(r[p["frac"] + 4]),
            "dest_pesado_pct": cv.numero(r[p["frac"] + 5]),
            **{nome: cv.numero(r[p["gas"] + i]) for i, nome in enumerate(GAS)},
            "densidade_glp_gas": cv.numero(r[p["dens"]]),
            "densidade_glp_liquido": cv.numero(r[p["dens"] + 1]),
            "pcs_kj_m3": cv.numero(r[p["dens"] + 2]),
        }
        # Só existe caracterização quando a linha traz alguma informação de análise.
        if any(v is not None for v in c.values()):
            linha["caracterizacao"] = c
        if p["data_atualizacao"] is not None:
            linha["data_atualizacao"] = cv.data_br(r[p["data_atualizacao"]])
    return linha


def ler_csv_producao(nome_csv: str, conteudo: bytes, formatos: dict):
    """Devolve (arquivo_origem, linha) de um CSV de produção. Conta os formatos em `formatos`."""
    origem = _origem(nome_csv)
    for r in csv.reader(io.StringIO(decodificar(conteudo)), delimiter=";"):
        fmt = _formato(r)
        if fmt is None:
            continue
        if fmt.startswith("desconhecido"):
            raise ValueError(f"{nome_csv}: formato de linha desconhecido {fmt}: {r[:9]}")
        formatos[fmt] = formatos.get(fmt, 0) + 1
        yield origem, _linha_producao(r, fmt)


def membros_zip(caminho: Path) -> list[str]:
    """CSVs de um zip de produção na ordem de carga: primeiro o(s) anual(is), depois os mensais.

    Os zips de 2010-2015 trazem cada mês duas vezes (CSV mensal + CSV anual). Cada CSV é uma
    carga própria; carregando o anual antes, o versionamento grava como versão mais recente o
    mensal, que tem a instalação mais preenchida (decisão do autor).
    """
    with zipfile.ZipFile(caminho) as zf:
        csvs = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    mensal = lambda n: re.search(r"_(\d{2})_produ", n.split("/")[-1])
    return sorted(csvs, key=lambda n: (mensal(n) is not None, int(mensal(n)[1]) if mensal(n) else 0, n))


def conteudo_arquivo(caminho: Path, membro: str | None) -> bytes:
    """Bytes de um CSV solto ou de um CSV dentro de um zip."""
    if membro is None:
        return caminho.read_bytes()
    with zipfile.ZipFile(caminho) as zf:
        return zf.read(membro)


def _linhas_csv(caminho: Path) -> list[list[str]]:
    rows = list(csv.reader(io.StringIO(decodificar(caminho.read_bytes())), delimiter=";"))
    return [r for r in rows[1:] if any(c.strip() for c in r)]  # pula o cabeçalho e linhas vazias


def ler_concessionarios(caminho: Path):
    """relacao-concessionarios.csv: BID; Número Contrato; Fase; Nome Fantasia; Bacia; CNPJ; Nome; % Participação; Ambiente."""
    for r in _linhas_csv(caminho):
        nome = cv.texto(r[6])
        operador = False
        if nome and (m := re.match(r"\(Operador\)\s*-\s*(.*)", nome)):  # o nome vem como "(Operador) - <empresa>"
            operador, nome = True, cv.texto(m[1])
        yield {
            "rodada": cv.texto(r[0]), "contrato": cv.texto(r[1]), "fase": cv.texto(r[2]),
            "nome_contrato": cv.texto(r[3]), "bacia": cv.texto(r[4]), "cnpj": cv.texto(r[5]),
            "empresa": nome, "operador": operador, "percentual": cv.numero(r[7]), "ambiente": cv.texto(r[8]),
        }


def ler_pais_origem(caminho: Path):
    """relacao-pais-origem-concessionarios.csv: Nome Fantasia; Razão Social; Grupo; País."""
    for r in _linhas_csv(caminho):
        yield {"empresa": cv.texto(r[0]), "razao_social": cv.texto(r[1]), "grupo": cv.texto(r[2]), "pais": cv.texto(r[3])}


def ler_preco(caminho: Path):
    """Preço mínimo (2009-2017) e de referência (2018+): data (serial Excel); contrato; campo; corrente; preço."""
    for r in _linhas_csv(caminho):
        yield {
            "periodo": cv.data_serial_excel(r[0]), "contrato": cv.texto(r[1]), "campo_nome": cv.texto(r[2]),
            "corrente": cv.texto(r[3]), "valor_rs_m3": cv.numero(r[4]),
        }


def ler_preco_minimo_extraido(caminho: Path):
    """CSV extraído dos PDFs de 2005-2008 (data/interim): periodo; n_linha_pdf; contrato; campo; corrente; preco_rs_m3; observacao."""
    for r in _linhas_csv(caminho):
        yield {
            "periodo": cv.periodo_aaaa_mm(r[0]), "contrato": cv.texto(r[2]), "campo_nome": cv.texto(r[3]),
            "corrente": cv.texto(r[4]), "valor_rs_m3": cv.numero(r[5]),
        }


def _linhas_csv_virgula(caminho: Path) -> list[dict]:
    """CSV com cabeçalho e vírgula como separador (exportação do GeoServer da ANP). Os contornos são longos."""
    csv.field_size_limit(2**31 - 1)
    return list(csv.DictReader(io.StringIO(decodificar(caminho.read_bytes()))))


def ler_coordenada_poco(caminho: Path):
    """POCOS_SIRGAS.csv (camada de poços da ANP): só o nome do poço e o ponto em WKT."""
    for r in _linhas_csv_virgula(caminho):
        yield {"poco": cv.texto(r["POCO"]), "geometria_wkt": cv.texto(r["GEOM"])}


def ler_coordenada_campo(caminho: Path):
    """CAMPOS_PRODUCAO_SIRGAS.csv (camada de campos da ANP): nome, bacia e o contorno em WKT."""
    for r in _linhas_csv_virgula(caminho):
        yield {"campo": cv.texto(r["NOM_CAMPO"]), "bacia": cv.texto(r["NOM_BACIA"]), "geometria_wkt": cv.texto(r["GEOMETRY"])}
