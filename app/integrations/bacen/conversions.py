"""Conversions between rate periodicities."""

from __future__ import annotations

from decimal import Decimal


def mensal_para_anual(taxa_mensal: Decimal) -> Decimal:
    f = float(taxa_mensal)
    return Decimal(str((1.0 + f) ** 12 - 1.0)).quantize(Decimal("0.00000001"))


def anual_para_mensal(taxa_anual: Decimal) -> Decimal:
    f = float(taxa_anual)
    return Decimal(str((1.0 + f) ** (1.0 / 12.0) - 1.0)).quantize(Decimal("0.00000001"))


def diaria_252_para_anual(taxa_diaria: Decimal) -> Decimal:
    f = float(taxa_diaria)
    return Decimal(str((1.0 + f) ** 252 - 1.0)).quantize(Decimal("0.00000001"))


def diaria_252_para_mensal(taxa_diaria: Decimal) -> Decimal:
    f = float(taxa_diaria)
    return Decimal(str((1.0 + f) ** 21 - 1.0)).quantize(Decimal("0.00000001"))
