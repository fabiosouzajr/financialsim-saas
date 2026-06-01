"""Brazilian display formatters: R$, %, dd/mm/yyyy, CPF/CNPJ."""
from __future__ import annotations

from datetime import date
from decimal import Decimal


def format_brl(value: Decimal) -> str:
    negative = value < 0
    abs_val = abs(value)
    integer, _, decimals = f"{abs_val:.2f}".partition(".")
    chunks: list[str] = []
    while len(integer) > 3:
        chunks.append(integer[-3:])
        integer = integer[:-3]
    chunks.append(integer)
    formatted_int = ".".join(reversed(chunks))
    sign = "-" if negative else ""
    return f"{sign}R$ {formatted_int},{decimals}"


def format_pct(value: Decimal, decimals: int = 2) -> str:
    pct = value * Decimal("100")
    s = f"{pct:.{decimals}f}".replace(".", ",")
    return f"{s}%"


def format_date_br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def format_cpf_cnpj(s: str, tipo: str) -> str:
    if tipo == "PF" and len(s) == 11:
        return f"{s[:3]}.{s[3:6]}.{s[6:9]}-{s[9:]}"
    if tipo == "PJ" and len(s) == 14:
        return f"{s[:2]}.{s[2:5]}.{s[5:8]}/{s[8:12]}-{s[12:]}"
    return s
