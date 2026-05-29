"""Tabela Price com dias corridos (convencao BACEN/CCB veiculos)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from app.core.money import quantize_brl


def _daily_rate(taxa_mensal: Decimal) -> Decimal:
    """i_d = (1 + i_m)^(1/30) - 1, computed via float and back to Decimal."""
    i_m = float(taxa_mensal)
    i_d_float = (1.0 + i_m) ** (1.0 / 30.0) - 1.0
    return Decimal(str(i_d_float))


def compute_pmt(
    pv: Decimal,
    taxa_mensal: Decimal,
    n: int,
    d1: int,
) -> Decimal:
    """Compute fixed installment (PMT) for Tabela Price with d1 days carencia.

    When d1 == 30, reduces to classic Price.
    # Rebuilt segments after extraordinary payments always use d1=30, treating
    # the post-payment saldo as a fresh 30-day loan anchored on the next vencimento.
    """
    if n < 1:
        raise ValueError("n must be >= 1")
    if d1 < 0:
        raise ValueError("d1 must be >= 0")
    if taxa_mensal < 0:
        raise ValueError("taxa_mensal must be >= 0")
    if taxa_mensal == Decimal("0"):
        return quantize_brl(pv / Decimal(n))

    i_m = taxa_mensal
    i_d = _daily_rate(taxa_mensal)
    one_plus_im_n = (Decimal("1") + i_m) ** n
    one_plus_im_n_minus_1 = (Decimal("1") + i_m) ** (n - 1)
    carencia_factor = (Decimal("1") + i_d) ** d1

    numerator = carencia_factor * i_m * one_plus_im_n_minus_1
    denominator = one_plus_im_n - Decimal("1")

    pmt = pv * (numerator / denominator)
    return quantize_brl(pmt)


@dataclass(frozen=True)
class ScheduleRow:
    numero_parcela: int
    data_vencimento: date
    dias_periodo: int
    saldo_anterior: Decimal
    juros: Decimal
    amortizacao: Decimal
    parcela: Decimal
    saldo_devedor: Decimal
    ajuste_arredondamento: Decimal


@dataclass(frozen=True)
class Schedule:
    rows: tuple[ScheduleRow, ...]
    pmt: Decimal
    total_pago: Decimal
    total_juros: Decimal


def build_schedule(
    pv: Decimal,
    taxa_mensal: Decimal,
    n: int,
    d1: int,
    data_liberacao: date,
) -> Schedule:
    """Build the full amortization schedule.

    - Row 1: juros = PV * ((1+i_d)^d1 - 1)
    - Rows 2..n-1: juros = saldo * i_m
    - Row n: saldo forced to 0; residual recorded in ajuste_arredondamento
    """
    pmt = compute_pmt(pv, taxa_mensal, n, d1)
    i_m = taxa_mensal
    i_d = _daily_rate(taxa_mensal)
    carencia_factor = (Decimal("1") + i_d) ** d1

    rows_list: list[ScheduleRow] = []
    saldo = pv
    data_venc_1 = data_liberacao + timedelta(days=d1)

    for k in range(1, n + 1):
        if k == 1:
            data_venc = data_venc_1
            dias_periodo = d1
        else:
            data_venc = data_venc_1 + relativedelta(months=k - 1)
            dias_periodo = (data_venc - (data_venc_1 + relativedelta(months=k - 2))).days

        saldo_anterior = saldo
        juros_raw = pv * (carencia_factor - Decimal("1")) if k == 1 else saldo * i_m

        juros = quantize_brl(juros_raw)

        if k < n:
            amort = quantize_brl(pmt - juros)
            saldo_new = saldo - amort
            parcela = pmt
            ajuste = Decimal("0.00")
        else:
            amort = saldo_anterior
            saldo_new = Decimal("0.00")
            parcela_real = quantize_brl(juros + amort)
            ajuste = parcela_real - pmt
            parcela = parcela_real

        rows_list.append(
            ScheduleRow(
                numero_parcela=k,
                data_vencimento=data_venc,
                dias_periodo=dias_periodo,
                saldo_anterior=quantize_brl(saldo_anterior),
                juros=juros,
                amortizacao=quantize_brl(amort),
                parcela=parcela,
                saldo_devedor=quantize_brl(saldo_new),
                ajuste_arredondamento=ajuste,
            )
        )
        saldo = saldo_new

    rows = tuple(rows_list)
    total_pago = sum((r.parcela for r in rows), start=Decimal("0"))
    total_juros = sum((r.juros for r in rows), start=Decimal("0"))
    return Schedule(rows=rows, pmt=pmt, total_pago=total_pago, total_juros=total_juros)
