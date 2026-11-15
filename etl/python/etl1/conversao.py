"""Conversões de leitura do ETL 1 (C02 e C03 em docs/etl/tratamentos.md).

Só o que o PostgreSQL exige para colunas tipadas, e a remoção dos espaços no início e
no fim dos textos (formato dos arquivos de 2005-2017). Nenhum valor é corrigido.
"""

import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation


def texto(valor: str | None) -> str | None:
    """Remove os espaços das pontas (C02). Texto vazio vira NULL."""
    if valor is None:
        return None
    valor = valor.strip()
    return valor or None


def numero(valor: str | None) -> Decimal | None:
    """Converte '3,6158', ',0015', '3.637,4574', '20,6%' ou '27.64%' em Decimal (C03).

    Vazio, '-', '%' sozinho e códigos de erro do Excel publicados pela ANP no lugar do número
    ('#REF!', '#N/D'...) viram NULL: uma coluna numérica não aceita texto.
    """
    valor = texto(valor)
    if valor is None:
        return None
    valor = valor.replace("%", "").strip()
    if valor in ("", "-") or valor.startswith("#"):
        return None
    if "," in valor:
        valor = valor.replace(".", "").replace(",", ".")
    try:
        return Decimal(valor)
    except InvalidOperation:
        raise ValueError(f"número inválido: {valor!r}") from None


def inteiro(valor: str | None) -> int | None:
    valor = texto(valor)
    return None if valor is None else int(valor)


def periodo(valor: str | None) -> date | None:
    """Período da produção 'AAAA/MM' -> 1º dia do mês."""
    valor = texto(valor)
    if valor is None:
        return None
    ano, mes = valor.split("/")
    return date(int(ano), int(mes), 1)


def periodo_carga(valor: str | None) -> date | None:
    """Período da carga em 'AAAA/MM', 'AAAAMM' ou 'MM/AAAA' -> 1º dia do mês."""
    valor = texto(valor)
    if valor is None:
        return None
    if m := re.fullmatch(r"(\d{4})/(\d{2})", valor):
        return date(int(m[1]), int(m[2]), 1)
    if m := re.fullmatch(r"(\d{4})(\d{2})", valor):
        return date(int(m[1]), int(m[2]), 1)
    if m := re.fullmatch(r"(\d{2})/(\d{4})", valor):
        return date(int(m[2]), int(m[1]), 1)
    raise ValueError(f"período da carga em formato desconhecido: {valor!r}")


def data_br(valor: str | None) -> datetime | None:
    """Data 'dd/mm/aaaa' ou 'dd/mm/aaaa hh:mm' -> datetime (a hora é preservada quando existe)."""
    valor = texto(valor)
    if valor is None:
        return None
    for mascara in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(valor, mascara)
        except ValueError:
            pass
    raise ValueError(f"data de atualização em formato desconhecido: {valor!r}")


def data_serial_excel(valor: str | None) -> date | None:
    """Número serial de data do Excel (ex.: 44927) -> date (44927 = 01/01/2023)."""
    valor = texto(valor)
    return None if valor is None else date(1899, 12, 30) + timedelta(days=int(valor))


def periodo_aaaa_mm(valor: str | None) -> date | None:
    """Período 'AAAA-MM' (CSV extraído dos PDFs de preço mínimo) -> 1º dia do mês."""
    valor = texto(valor)
    if valor is None:
        return None
    ano, mes = valor.split("-")
    return date(int(ano), int(mes), 1)
