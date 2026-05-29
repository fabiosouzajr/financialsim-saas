"""Brazilian formatters: R$, %, dd/mm/yyyy."""

from __future__ import annotations

from datetime import date
from decimal import Decimal


def format_brl(value: Decimal) -> str:
    """Format Decimal as 'R$ 1.234,56'."""
    negative = value < 0
    abs_val = abs(value)
    integer, _, decimals = f"{abs_val:.2f}".partition(".")
    # Insert thousand separators
    chunks = []
    while len(integer) > 3:
        chunks.append(integer[-3:])
        integer = integer[:-3]
    chunks.append(integer)
    formatted_int = ".".join(reversed(chunks))
    sign = "-" if negative else ""
    return f"{sign}R$ {formatted_int},{decimals}"


def parse_brl(text: str) -> Decimal:
    """Parse 'R$ 1.234,56' -> Decimal('1234.56'). Accepts leading '-'."""
    cleaned = text.replace("R$", "").replace(".", "").replace(",", ".").strip()
    return Decimal(cleaned)


def format_pct(value: Decimal, decimals: int = 2) -> str:
    """Format 0.0189 -> '1,89%'."""
    pct = value * Decimal("100")
    s = f"{pct:.{decimals}f}".replace(".", ",")
    return f"{s}%"


def format_date_br(d: date) -> str:
    return d.strftime("%d/%m/%Y")