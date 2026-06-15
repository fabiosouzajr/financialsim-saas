from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from finacialsim_saas.schemas.types import DecimalStr


class RateCurvePointOut(BaseModel):
    ate_meses: int
    taxa_mensal: DecimalStr


class BusinessRulesOut(BaseModel):
    entrada_minima_pct: DecimalStr
    prazo_minimo_meses: int
    prazo_maximo_meses: int
    taxa_minima_mes: DecimalStr
    taxa_maxima_mes: DecimalStr
    dias_max_carencia: int
    valor_minimo_financiado: DecimalStr
    iof_fixo_pct: DecimalStr
    iof_diario_pct: DecimalStr
    iof_diario_max_dias: int
    incluir_iof_default: bool
    rateio_ipva_meses_default: int
    rateio_emplacamento_meses_default: int
    taxa_por_prazo_curva: list[RateCurvePointOut]
    ipva_pct_carro: DecimalStr
    ipva_pct_moto: DecimalStr
    ipva_pct_caminhao: DecimalStr
    emplacamento_valor_carro: DecimalStr
    emplacamento_valor_moto: DecimalStr
    emplacamento_valor_caminhao: DecimalStr
    inadimplencia_multa_pct: DecimalStr
    inadimplencia_juros_diario_pct: DecimalStr
    inadimplencia_carencia_dias: int


class BusinessRuleUpdateIn(BaseModel):
    valor: Any
    motivo: str | None = None
