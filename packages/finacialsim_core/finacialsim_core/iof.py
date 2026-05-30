"""IOF veiculo (Decreto 6.306/2007) - opcional por simulacao."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from finacialsim_core.money import quantize_brl
from finacialsim_core.price_table import Schedule, build_schedule


@dataclass(frozen=True)
class IofConfig:
    fixo_pct: Decimal
    diario_pct: Decimal
    max_dias: int


DEFAULT_IOF_CONFIG = IofConfig(
    fixo_pct=Decimal("0.0038"),
    diario_pct=Decimal("0.000082"),
    max_dias=365,
)


@dataclass(frozen=True)
class IofResult:
    fixo: Decimal
    diario: Decimal
    total: Decimal


def compute_iof(
    valor_financiado: Decimal,
    schedule: Schedule,
    data_liberacao: date,
    config: IofConfig,
) -> IofResult:
    """Compute IOF (fixo + diario) for the given schedule.

    IOF Fixo  = valor_financiado * fixo_pct
    IOF Diario = SUM over parcelas of amortizacao * diario_pct * min(dias, max_dias)
    """
    fixo = quantize_brl(valor_financiado * config.fixo_pct)

    diario_total = Decimal("0")
    for row in schedule.rows:
        dias_real = (row.data_vencimento - data_liberacao).days
        dias_efetivo = min(dias_real, config.max_dias)
        diario_total += row.amortizacao * config.diario_pct * Decimal(dias_efetivo)
    diario = quantize_brl(diario_total)

    return IofResult(fixo=fixo, diario=diario, total=quantize_brl(fixo + diario))


@dataclass(frozen=True)
class FinancedResult:
    valor_financiado: Decimal
    schedule: Schedule
    iof: IofResult
    iteracoes: int


def compute_financed_amount_with_iof(
    pv_inicial: Decimal,
    taxa_mensal: Decimal,
    n: int,
    d1: int,
    data_liberacao: date,
    config: IofConfig,
    incluir_iof: bool,
) -> FinancedResult:
    """Iterate IOF + PV until convergence.

    If incluir_iof=False, returns immediately with PV unchanged and IOF=0.
    Tolerancia and max_iteracoes are internal implementation details.
    """
    _TOLERANCIA = Decimal("0.01")
    _MAX_ITER = 10

    if not incluir_iof:
        schedule = build_schedule(pv_inicial, taxa_mensal, n, d1, data_liberacao)
        return FinancedResult(
            valor_financiado=pv_inicial,
            schedule=schedule,
            iof=IofResult(Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
            iteracoes=0,
        )

    pv = pv_inicial
    iteracoes = 0
    for _ in range(_MAX_ITER):
        iteracoes += 1
        schedule = build_schedule(pv, taxa_mensal, n, d1, data_liberacao)
        iof = compute_iof(pv, schedule, data_liberacao, config)
        novo_pv = pv_inicial + iof.total
        if abs(novo_pv - pv) < _TOLERANCIA:
            pv = novo_pv
            schedule = build_schedule(pv, taxa_mensal, n, d1, data_liberacao)
            iof = compute_iof(pv, schedule, data_liberacao, config)
            break
        pv = novo_pv

    return FinancedResult(
        valor_financiado=pv,
        schedule=schedule,
        iof=iof,
        iteracoes=iteracoes,
    )
