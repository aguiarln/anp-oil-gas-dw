"""Listas de-para revisadas pelo autor (T21): empresas (T07), campos (T04 renomeação, T05 unificação) e o grupo
econômico das empresas que a ANP publica sem grupo (T23).

A ligação com a stage é pela chave normalizada (normalizacao.chave), então a grafia da lista não precisa
ser exata.
"""

import csv
from pathlib import Path

from .normalizacao import chave

PASTA = Path(__file__).resolve().parent / "de_para"


def _ler(nome: str) -> list[dict]:
    with open(PASTA / nome, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def empresas() -> dict[str, str]:
    """chave da grafia de origem -> chave da empresa de destino."""
    return {chave(r["empresa_origem"]): chave(r["empresa_destino"]) for r in _ler("empresas.csv")}


def grupos_economicos() -> dict[str, tuple[str, str]]:
    """chave da empresa -> (grupo econômico, país), para as empresas sem grupo na relação de concessionários (T23)."""
    return {chave(r["empresa"]): (r["grupo_economico"], r["pais"]) for r in _ler("grupos_economicos.csv")}


def campos() -> list[dict]:
    """Eventos de campo: origem e destino como (chave do nome, chave da bacia), mês e tipo."""
    return [{"origem": (chave(r["campo_origem"]), chave(r["bacia_origem"])),
             "destino": (chave(r["campo_destino"]), chave(r["bacia_destino"])),
             "destino_nome": r["campo_destino"], "mes": r["mes"], "tipo": r["tipo"]} for r in _ler("campos.csv")]


def resolver(inicio: tuple, eventos: list[dict], tipos: set[str]) -> tuple:
    """Segue a cadeia de eventos (ex.: Jandaia Sul -> JANDAIA -> TANGARÁ) até o último destino."""
    seguinte = {e["origem"]: e["destino"] for e in eventos if e["tipo"] in tipos}
    atual, vistos = inicio, {inicio}
    while atual in seguinte:
        atual = seguinte[atual]
        if atual in vistos:  # proteção contra ciclo na lista
            raise ValueError(f"ciclo na lista de-para de campos a partir de {inicio}")
        vistos.add(atual)
    return atual
