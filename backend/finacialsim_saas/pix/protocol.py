from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable


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
        expires_in: int,
        description: str,
        payer: str,
    ) -> PixChargeData: ...

    async def cancel_charge(self, txid: str) -> None: ...

    def verify_webhook(self, headers: dict, body: bytes) -> WebhookEvent: ...
