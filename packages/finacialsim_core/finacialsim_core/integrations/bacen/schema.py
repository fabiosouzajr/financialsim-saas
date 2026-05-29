"""BACEN normalized indicator schema."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal


Unidade = Literal["pct_aa", "pct_am", "pct_ad"]


@dataclass(frozen=True)
class IndicatorPoint:
    codigo: str
    data_referencia: date
    valor_fracao: Decimal
    unidade: Unidade
    fonte: str
