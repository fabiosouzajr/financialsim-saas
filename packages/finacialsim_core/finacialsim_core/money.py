"""Decimal helpers and bank-grade rounding for FinacialSim."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, getcontext

getcontext().prec = 28

CENTAVO: Decimal = Decimal("0.01")
PCT_DEC: Decimal = Decimal("0.0001")
TAXA_DEC: Decimal = Decimal("0.00000001")


def quantize_brl(value: Decimal) -> Decimal:
    """Round Decimal to 2 places using half-up (Brazilian banking convention)."""
    return value.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def to_decimal(value: str | int | float | Decimal) -> Decimal:
    """Convert input to Decimal, avoiding float binary noise via str()."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(value)
