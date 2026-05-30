"""CET (Custo Efetivo Total) via TIR (pure-Python bisection)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from finacialsim_core.price_table import Schedule


@dataclass(frozen=True)
class CetResult:
    cet_mes: Decimal
    cet_ano: Decimal


def _npv(rate: float, valor_liberado: float, fluxos: list[tuple[float, float]]) -> float:
    """Net present value. fluxos = [(meses_from_t0, parcela), ...]"""
    total = -valor_liberado
    for meses, parcela in fluxos:
        total += parcela / ((1.0 + rate) ** meses)
    return total


def compute_cet(
    valor_liberado: Decimal,
    schedule: Schedule,
    d1: int = 30,
) -> CetResult:
    """Compute CET monthly TIR via bisection.

    Timing model: meses = numero_parcela * (d1 / 30.0), matching build_schedule's
    convention. This preserves CET == taxa when no IOF/extras.
    valor_liberado = what the customer effectively received.
    """
    fluxos: list[tuple[float, float]] = []
    d1_factor = d1 / 30.0
    for row in schedule.rows:
        meses = row.numero_parcela * d1_factor
        fluxos.append((meses, float(row.parcela)))

    vl = float(valor_liberado)
    total_parcelas = sum(f[1] for f in fluxos)
    if vl >= total_parcelas:
        raise ValueError(
            f"valor_liberado ({valor_liberado}) >= total_parcelas ({total_parcelas}): "
            "CET is undefined — caller passed invalid inputs"
        )

    lo, hi = 1e-8, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if _npv(mid, vl, fluxos) > 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-10:
            break

    cet_mes_float = (lo + hi) / 2.0
    cet_mes = Decimal(str(cet_mes_float)).quantize(Decimal("0.00000001"))
    cet_ano_float = (1.0 + cet_mes_float) ** 12 - 1.0
    cet_ano = Decimal(str(cet_ano_float)).quantize(Decimal("0.00000001"))

    return CetResult(cet_mes=cet_mes, cet_ano=cet_ano)
