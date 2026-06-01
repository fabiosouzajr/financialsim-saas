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
    valor: Decimal  # percentage, e.g. 10.75 for 10.75% a.a.
    unidade: Unidade
    fonte: str
