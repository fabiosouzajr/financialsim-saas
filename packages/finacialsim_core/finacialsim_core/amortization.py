"""Amortizacao extraordinaria (quitacoes parciais/total)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from enum import StrEnum

from finacialsim_core.price_table import Schedule, ScheduleRow, build_schedule, compute_pmt


class AmortizationMode(StrEnum):
    REDUZIR_PARCELA = "reduzir_parcela"
    REDUZIR_PRAZO = "reduzir_prazo"


@dataclass(frozen=True)
class ExtraPayment:
    data: date
    valor: Decimal
    modo: AmortizationMode


def apply_extraordinary_amortizations(
    schedule_original: Schedule,
    pagamentos: list[ExtraPayment],
    taxa_mensal: Decimal,
) -> Schedule:
    """Apply each extra payment in order, recomputing the rest of the schedule.

    Strategy (MVP):
    - Find the first parcela on/after the payment date.
    - Reduce saldo_devedor at that point by the payment value.
    - REDUZIR_PRAZO: keep PMT <= original, rebuild over fewer months.
    - REDUZIR_PARCELA: keep remaining n, recompute PMT for new saldo.

    Rebuilt segments always use d1=30: the post-payment saldo is treated as a
    fresh 30-day loan anchored on the next vencimento. The original
    data_liberacao is not needed — rebuilt anchors derive from vencimento dates.
    """
    rows: list[ScheduleRow] = list(schedule_original.rows)
    pmt_original = schedule_original.pmt
    final_pmt = pmt_original

    for pagamento in pagamentos:
        idx_apply = next(
            (i for i, r in enumerate(rows) if r.data_vencimento >= pagamento.data),
            len(rows) - 1,
        )

        rows_paid = rows[:idx_apply]
        saldo_after_payment = rows[idx_apply].saldo_anterior - pagamento.valor

        if saldo_after_payment <= Decimal("0"):
            rows = rows_paid
            break

        remaining_meses = len(rows) - idx_apply
        next_venc = rows[idx_apply].data_vencimento

        if pagamento.modo is AmortizationMode.REDUZIR_PARCELA:
            new_pmt = compute_pmt(
                pv=saldo_after_payment, taxa_mensal=taxa_mensal, n=remaining_meses, d1=30
            )
            new_segment = _rebuild_segment(
                pv=saldo_after_payment,
                taxa_mensal=taxa_mensal,
                n=remaining_meses,
                start_numero=idx_apply + 1,
                data_primeiro_venc=next_venc,
            )
            final_pmt = new_pmt
        else:
            # REDUZIR_PRAZO: find minimum n where PMT <= pmt_original (fewest installments)
            n_new = 1
            while n_new < remaining_meses:
                test_pmt = compute_pmt(saldo_after_payment, taxa_mensal, n_new, 30)
                if test_pmt <= pmt_original:
                    break
                n_new += 1
            new_segment = _rebuild_segment(
                pv=saldo_after_payment,
                taxa_mensal=taxa_mensal,
                n=n_new,
                start_numero=idx_apply + 1,
                data_primeiro_venc=next_venc,
            )
            final_pmt = pmt_original

        rows = rows_paid + new_segment

    rows_tuple = tuple(rows)
    total_pago = sum((r.parcela for r in rows_tuple), start=Decimal("0"))
    total_juros = sum((r.juros for r in rows_tuple), start=Decimal("0"))
    return Schedule(rows=rows_tuple, pmt=final_pmt, total_pago=total_pago, total_juros=total_juros)


def _rebuild_segment(
    pv: Decimal,
    taxa_mensal: Decimal,
    n: int,
    start_numero: int,
    data_primeiro_venc: date,
) -> list[ScheduleRow]:
    """Rebuild rows for remaining saldo. d1=30 hardcoded: post-payment saldo
    is treated as a fresh 30-day loan anchored on the next vencimento date."""
    schedule = build_schedule(
        pv=pv,
        taxa_mensal=taxa_mensal,
        n=n,
        d1=30,
        data_liberacao=data_primeiro_venc,
    )
    return [replace(r, numero_parcela=start_numero + i) for i, r in enumerate(schedule.rows)]
