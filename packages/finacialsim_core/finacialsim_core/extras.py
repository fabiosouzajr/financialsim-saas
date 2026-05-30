"""Custos adicionais mensais (extras) acrescidos a parcela."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import assert_never

from finacialsim_core.money import quantize_brl


class ExtraModalidade(StrEnum):
    MENSAL_CONTINUO = "mensal_continuo"
    RATEIO_MESES = "rateio_meses"
    UNICO_INICIAL = "unico_inicial"


@dataclass(frozen=True)
class Extra:
    tipo: str
    nome: str
    valor_total: Decimal
    modalidade: ExtraModalidade
    duracao_meses: int
    ordem: int


def _valor_por_parcela(extra: Extra) -> Decimal:
    if extra.modalidade is ExtraModalidade.MENSAL_CONTINUO:
        return quantize_brl(extra.valor_total)
    if extra.modalidade is ExtraModalidade.RATEIO_MESES:
        return quantize_brl(extra.valor_total / Decimal(extra.duracao_meses))
    if extra.modalidade is ExtraModalidade.UNICO_INICIAL:
        return quantize_brl(extra.valor_total)
    assert_never(extra.modalidade)


def compute_extras_per_parcela(extras: list[Extra], prazo_total: int) -> list[Decimal]:
    """Return list of Decimal totals (one per parcela) summing all applicable extras.

    List is 0-indexed: index = numero_parcela - 1.
    For RATEIO_MESES, the last installment absorbs any rounding residual so
    that sum(result[0:duracao_meses]) == valor_total exactly.
    """
    result = [Decimal("0.00")] * prazo_total
    for extra in extras:
        per = _valor_por_parcela(extra)
        if extra.modalidade is ExtraModalidade.UNICO_INICIAL:
            result[0] += per
        elif extra.modalidade is ExtraModalidade.RATEIO_MESES:
            limit = min(extra.duracao_meses, prazo_total)
            for i in range(limit - 1):
                result[i] += per
            # Last installment absorbs rounding so total == valor_total
            residual = extra.valor_total - per * Decimal(limit - 1)
            result[limit - 1] += quantize_brl(residual)
        else:
            limit = min(extra.duracao_meses, prazo_total)
            for i in range(limit):
                result[i] += per
    return [quantize_brl(v) for v in result]
