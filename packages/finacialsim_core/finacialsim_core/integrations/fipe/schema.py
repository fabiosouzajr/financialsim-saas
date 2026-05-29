"""FIPE normalized schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal


@dataclass(frozen=True)
class VehicleQuote:
    tipo: Literal["carro", "moto", "caminhao"]
    marca: str
    marca_id: str
    modelo: str
    modelo_id: str
    ano_modelo: int
    combustivel: str
    codigo_fipe: str
    valor: Decimal
    mes_referencia: str
    fonte: str
    raw_payload: dict[str, Any] = field(default_factory=dict)


def parse_brl_price(text: str) -> Decimal:
    """Parse 'R$ 45.230,00' -> Decimal('45230.00')."""
    cleaned = text.replace("R$", "").replace(".", "").replace(",", ".").strip()
    return Decimal(cleaned)
