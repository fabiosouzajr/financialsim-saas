"""Curva de taxa sugerida por prazo. Loaded from DB in Phase 2; pure function here."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RateCurvePoint:
    ate_meses: int
    taxa_mensal: Decimal


def suggest_rate(prazo_meses: int, curva: list[RateCurvePoint]) -> Decimal:
    """Return suggested taxa_mensal for the given prazo.

    Walks the sorted curve; first point where prazo <= ate_meses wins.
    Beyond the last band, returns the last point's rate.
    """
    if not curva:
        raise ValueError("curva must contain at least one point")
    sorted_curva = sorted(curva, key=lambda p: p.ate_meses)
    for point in sorted_curva:
        if prazo_meses <= point.ate_meses:
            return point.taxa_mensal
    return sorted_curva[-1].taxa_mensal
