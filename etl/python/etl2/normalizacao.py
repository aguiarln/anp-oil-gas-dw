"""Regras de uniformização do ETL 2 (docs/etl/tratamentos.md): grafias (T14, T20), contratos (T15), estado
do poço (T13) e geometrias (WKT em SIRGAS 2000)."""

import re
import unicodedata

def chave(nome: str | None) -> str | None:
    """Chave de comparação de grafias (T14, T20): sem caracteres invisíveis, sem acento, maiúsculas,
    '_' como espaço e um espaço só entre as palavras. Ex.: 'Cabiúnas  mistura' -> 'CABIUNAS MISTURA'."""
    if nome is None:
        return None
    nome = nome.replace("\xad", "").replace("_", " ")
    nome = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", nome).upper().strip() or None


def chave_contrato(numero: str | None) -> str | None:
    """Chave do contrato (T15): os dígitos e, se o número termina numa única letra, essa letra em maiúscula.

    '48000.003552/97-11' -> '480000035529711'; '486100038862000A' e '48610.003886/2000a' -> '486100038862000A'.
    A letra final distingue contratos diferentes (BM-S-11 e BM-S-11A). Sufixos maiores, que o arquivo de preço
    acrescenta ao número ('-IBU', '-mgn', '-es-t-466'), não fazem parte do contrato.
    """
    if numero is None:
        return None
    base = re.sub(r"\D", "", numero)
    if not base:
        return None
    letra = re.search(r"\d([A-Za-z])$", numero.strip())
    return base + letra[1].upper() if letra else base


def sigla_pelo_nome_do_poco(nome_poco: str, siglas: set[str]) -> str | None:
    """Estado pelo sufixo do nome ANP do poço (T13a): '7-ET-994-RN' -> 'RN'; poços no mar usam a sigla
    seguida de 'S' ('3-BRSA-1017D-RJS' -> 'RJ'). Devolve None se o sufixo não for uma sigla de estado."""
    sufixo = nome_poco.rsplit("-", 1)[-1].upper()
    if sufixo in siglas:
        return sufixo
    if len(sufixo) == 3 and sufixo.endswith("S") and sufixo[:2] in siglas:
        return sufixo[:2]
    return None


def ponto(wkt: str | None) -> tuple[float, float] | None:
    """'POINT (lon lat)' -> (latitude, longitude)."""
    if not wkt:
        return None
    m = re.match(r"\s*POINT\s*\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)", wkt, re.I)
    return (float(m[2]), float(m[1])) if m else None


def centro(wkt: str | None) -> tuple[float, float] | None:
    """Centroide do anel externo de um 'POLYGON ((...))' (fórmula da área com sinal) -> (latitude, longitude)."""
    if not wkt:
        return None
    m = re.match(r"\s*POLYGON\s*\(\((.+?)\)", wkt, re.I | re.S)
    if not m:
        return None
    pts = [tuple(map(float, p.split()[:2])) for p in m[1].split(",")]
    area = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        f = x1 * y2 - x2 * y1
        area += f; cx += (x1 + x2) * f; cy += (y1 + y2) * f
    if abs(area) < 1e-12:  # polígono degenerado: média dos vértices
        return (sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts))
    area /= 2
    return (cy / (6 * area), cx / (6 * area))


def mais_frequente(contagem: dict[str, int]) -> str:
    """Grafia de exibição: a mais frequente; no empate, a primeira em ordem alfabética."""
    return sorted(contagem.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
