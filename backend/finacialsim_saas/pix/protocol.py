from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Protocol, runtime_checkable


@dataclass
class PixChargeData:
    """Value object returned by PixProvider.create_charge."""
    txid: str
    brcode: str
    qr_png_bytes: bytes
    amount: Decimal
    expires_at: datetime
    provider_payload: dict = field(default_factory=dict)


@dataclass
class PayerInfo:
    """Structured payer identity — Efí's `devedor` needs distinct CPF/CNPJ fields."""
    document: str          # CPF or CNPJ, digits only (punctuation stripped)
    document_type: Literal["cpf", "cnpj"]
    name: str


@dataclass
class WebhookEvent:
    """Parsed result of PixProvider.verify_webhook."""
    txid: str
    status: str  # "paid" | "expired" | "canceled"
    paid_amount: Decimal | None = None
    provider_payload: dict = field(default_factory=dict)


@runtime_checkable
class PixProvider(Protocol):
    name: str

    async def create_charge(
        self,
        *,
        txid: str,
        amount: Decimal,
        due_date: date,
        validity_days: int,
        description: str,
        payer: PayerInfo | None,
    ) -> PixChargeData: ...

    async def cancel_charge(self, txid: str) -> None: ...

    def verify_webhook(self, headers: dict, query_params: dict, body: bytes) -> WebhookEvent: ...
