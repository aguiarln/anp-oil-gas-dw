"""Carga de cada arquivo na stage: controle por hash (C05), versionamento e gravação com COPY.

Versionamento: as linhas são agrupadas por chave e comparadas com a última versão já
gravada, ignorando a "Data de atualização". Só as chaves que mudaram (ou são novas) são
gravadas, com todas as suas linhas, inclusive as duplicatas que a própria ANP publica.
"""

import hashlib
from collections import Counter, defaultdict
from pathlib import Path

from . import leitores
from .cadastros import Cadastros
from .config import DADOS

PRODUCAO_CONTEUDO = [
    "id_estado", "id_empresa", "id_contrato", "id_instalacao", "tipo_instalacao", "id_caracterizacao",
    "oleo_bbl_dia", "condensado_bbl_dia", "petroleo_bbl_dia", "gas_assoc_mm3_dia", "gas_nao_assoc_mm3_dia",
    "gas_total_mm3_dia", "gas_royalties", "agua_bbl_dia", "horas_producao",
]
PRODUCAO_COLUNAS = ["id_carga", "arquivo_origem", "periodo", "id_poco", "id_campo", *PRODUCAO_CONTEUDO, "data_atualizacao"]
PRECO_COLUNAS = ["id_carga", "periodo", "id_contrato", "campo_nome", "id_corrente", "tipo_preco", "valor_rs_m3"]


def sha256(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def nome_relativo(caminho: Path, membro: str | None = None) -> str:
    """Caminho relativo a data/. Um CSV dentro de zip vira 'raw/.../arquivo.zip::pasta/membro.csv'."""
    rel = caminho.resolve().relative_to(DADOS).as_posix()
    return f"{rel}::{membro}" if membro else rel


def ja_carregado(conn, hash_arquivo: str) -> bool:
    return conn.execute("SELECT 1 FROM carga WHERE hash_sha256 = %s AND situacao = 'carregada'",
                        [hash_arquivo]).fetchone() is not None


def registrar_carga(conn, nome_arquivo: str, fonte: str, hash_arquivo: str, situacao: str) -> int:
    return conn.execute(
        "INSERT INTO carga (nome_arquivo, fonte, hash_sha256, situacao) VALUES (%s, %s, %s, %s) RETURNING id_carga",
        [nome_arquivo, fonte, hash_arquivo, situacao]).fetchone()[0]


def _copy(conn, tabela: str, colunas: list[str], linhas):
    with conn.cursor().copy(f"COPY {tabela} ({', '.join(colunas)}) FROM STDIN") as cp:
        for linha in linhas:
            cp.write_row(linha)


def carregar_producao(conn, cad: Cadastros, nome_csv: str, conteudo: bytes, id_carga: int) -> dict:
    formatos = {}
    grupos = defaultdict(list)  # (id_poco, id_campo, periodo, arquivo_origem) -> [linha]
    lidas = 0
    for origem, ln in leitores.ler_csv_producao(nome_csv, conteudo, formatos):
        lidas += 1
        reg = {
            "id_carga": id_carga, "arquivo_origem": origem, "periodo": ln["periodo"],
            "id_poco": cad.id_poco(ln["poco"]), "id_campo": cad.id_campo(ln["campo"], ln["bacia"]),
            "id_estado": cad.id_estado(ln["estado"]), "id_empresa": cad.id_empresa(ln["operador"]),
            "id_contrato": cad.id_contrato(ln["contrato"]), "id_instalacao": cad.id_instalacao(ln["instalacao"]),
            "tipo_instalacao": ln["tipo_instalacao"], "id_caracterizacao": cad.id_caracterizacao(ln["caracterizacao"]),
            **{c: ln[c] for c in PRODUCAO_CONTEUDO if c in ln}, "data_atualizacao": ln["data_atualizacao"],
        }
        grupos[(reg["id_poco"], reg["id_campo"], reg["periodo"], origem)].append(reg)

    # Última versão já gravada de cada chave dos períodos deste arquivo.
    periodos = sorted({k[2] for k in grupos})
    ultima = {}
    if periodos:
        cols = ", ".join(PRODUCAO_CONTEUDO)
        rows = conn.execute(
            f"""SELECT id_poco, id_campo, periodo, arquivo_origem, id_carga, {cols}
                FROM producao_mensal WHERE periodo = ANY(%s)""", [periodos]).fetchall()
        por_chave = defaultdict(lambda: defaultdict(list))
        for r in rows:
            por_chave[tuple(r[:4])][r[4]].append(tuple(r[5:]))
        for chave, versoes in por_chave.items():
            ultima[chave] = Counter(versoes[max(versoes)])

    novas = alteradas = iguais = 0
    gravar = []
    for chave, linhas in grupos.items():
        conteudo = Counter(tuple(ln[c] for c in PRODUCAO_CONTEUDO) for ln in linhas)
        if chave in ultima and ultima[chave] == conteudo:
            iguais += 1
            continue
        alteradas += chave in ultima
        novas += chave not in ultima
        gravar.extend(tuple(ln[c] for c in PRODUCAO_COLUNAS) for ln in linhas)
    _copy(conn, "producao_mensal", PRODUCAO_COLUNAS, gravar)
    return {"lidas": lidas, "gravadas": len(gravar), "chaves_novas": novas, "chaves_alteradas": alteradas,
            "chaves_iguais": iguais, "formatos": formatos}


def carregar_preco(conn, cad: Cadastros, caminho: Path, id_carga: int, tipo: str, extraido: bool) -> dict:
    leitor = leitores.ler_preco_minimo_extraido if extraido else leitores.ler_preco
    grupos = defaultdict(list)  # (id_contrato, campo_nome, id_corrente, periodo, tipo) -> [valor]
    lidas = 0
    for ln in leitor(caminho):
        lidas += 1
        chave = (cad.id_contrato(ln["contrato"]), ln["campo_nome"], cad.id_corrente(ln["corrente"]), ln["periodo"], tipo)
        grupos[chave].append(ln["valor_rs_m3"])

    periodos = sorted({k[3] for k in grupos})
    ultima = {}
    if periodos:
        rows = conn.execute(
            """SELECT id_contrato, campo_nome, id_corrente, periodo, tipo_preco, id_carga, valor_rs_m3
               FROM preco_petroleo WHERE periodo = ANY(%s) AND tipo_preco = %s""", [periodos, tipo]).fetchall()
        por_chave = defaultdict(lambda: defaultdict(list))
        for r in rows:
            por_chave[tuple(r[:5])][r[5]].append(r[6])
        for chave, versoes in por_chave.items():
            ultima[chave] = Counter(versoes[max(versoes)])

    novas = alteradas = iguais = 0
    gravar = []
    for chave, valores in grupos.items():
        if chave in ultima and ultima[chave] == Counter(valores):
            iguais += 1
            continue
        alteradas += chave in ultima
        novas += chave not in ultima
        id_contrato, campo_nome, id_corrente, periodo, tipo_preco = chave
        gravar.extend((id_carga, periodo, id_contrato, campo_nome, id_corrente, tipo_preco, v) for v in valores)
    _copy(conn, "preco_petroleo", PRECO_COLUNAS, gravar)
    return {"lidas": lidas, "gravadas": len(gravar), "chaves_novas": novas, "chaves_alteradas": alteradas, "chaves_iguais": iguais}


def carregar_concessionarios(conn, cad: Cadastros, caminho: Path, id_carga: int) -> dict:
    """Cada carga é uma foto completa das sociedades vigentes."""
    lidas, gravar = 0, {}
    for ln in leitores.ler_concessionarios(caminho):
        lidas += 1
        id_bacia = cad.id_bacia(ln["bacia"])
        id_contrato = cad.id_contrato(ln["contrato"], ln["nome_contrato"], ln["rodada"], ln["fase"], ln["ambiente"], id_bacia)
        id_empresa = cad.id_empresa(ln["empresa"], cnpj=ln["cnpj"])
        chave = (id_empresa, id_contrato, id_carga)
        if chave in gravar:
            raise ValueError(f"empresa repetida no mesmo contrato da mesma foto: {ln}")
        gravar[chave] = (*chave, ln["percentual"], ln["operador"])
    _copy(conn, "participacao_contrato", ["id_empresa", "id_contrato", "id_carga", "percentual", "operador"], gravar.values())
    return {"lidas": lidas, "gravadas": len(gravar)}


def carregar_pais_origem(conn, cad: Cadastros, caminho: Path, id_carga: int) -> dict:
    """Completa empresas e grupos econômicos (só preenche o que está vazio).

    Mesma assinatura dos outros carregadores; o país de origem só completa os cadastros e não grava linhas ligadas
    à carga, por isso `conn` e `id_carga` não são usados aqui."""
    lidas = 0
    for ln in leitores.ler_pais_origem(caminho):
        lidas += 1
        cad.id_empresa(ln["empresa"], razao_social=ln["razao_social"], id_grupo=cad.id_grupo(ln["grupo"], ln["pais"]))
    return {"lidas": lidas, "gravadas": lidas}


def _carregar_coordenadas(conn, tabela: str, chave: str, linhas: list[tuple[int, str]], id_carga: int) -> dict:
    """Grava (id, geometria) só quando a coordenada é nova ou mudou em relação à última versão (C05)."""
    ultima = dict(conn.execute(
        f"""SELECT DISTINCT ON ({chave}) {chave}, geometria_wkt FROM {tabela}
            ORDER BY {chave}, id_carga DESC""").fetchall())
    vistos, gravar = set(), []
    for id_, geometria in linhas:
        if id_ in vistos:
            raise ValueError(f"{tabela}: {chave} {id_} repetido no mesmo arquivo")
        vistos.add(id_)
        if ultima.get(id_) != geometria:
            gravar.append((id_, id_carga, geometria))
    novas = sum(1 for id_, _, _ in gravar if id_ not in ultima)
    _copy(conn, tabela, [chave, "id_carga", "geometria_wkt"], gravar)
    return {"lidas": len(linhas), "gravadas": len(gravar), "chaves_novas": novas,
            "chaves_alteradas": len(gravar) - novas, "chaves_iguais": len(linhas) - len(gravar)}


def carregar_coordenada_poco(conn, cad: Cadastros, caminho: Path, id_carga: int) -> dict:
    """Ponto de cada poço. Poço que ainda não existe no cadastro é criado pela grafia exata (C01)."""
    linhas = [(cad.id_poco(ln["poco"]), ln["geometria_wkt"]) for ln in leitores.ler_coordenada_poco(caminho)]
    return _carregar_coordenadas(conn, "coordenada_poco", "id_poco", linhas, id_carga)


def carregar_coordenada_campo(conn, cad: Cadastros, caminho: Path, id_carga: int) -> dict:
    """Contorno de cada campo, identificado pelo nome e pela bacia da camada (grafia exata, C01)."""
    linhas = [(cad.id_campo(ln["campo"], ln["bacia"]), ln["geometria_wkt"]) for ln in leitores.ler_coordenada_campo(caminho)]
    return _carregar_coordenadas(conn, "coordenada_campo", "id_campo", linhas, id_carga)
