from __future__ import annotations

from datetime import date
from decimal import Decimal

from finacialsim_saas.pix.protocol import PayerInfo, PixChargeData, WebhookEvent


class StubExternalPixProvider:
    name = "external"

    async def create_charge(
        self,
        *,
        txid: str,
        amount: Decimal,
        due_date: date,
        validity_days: int,
        description: str,
        payer: PayerInfo | None,
        multa_pct: Decimal = Decimal("0.00"),
        juros_diario_pct: Decimal = Decimal("0.00"),
        carencia_dias: int = 0,
    ) -> PixChargeData:
        raise NotImplementedError("External Pix provider not wired — set PIX_PROVIDER=fake")

    async def cancel_charge(self, txid: str) -> None:
        raise NotImplementedError("External Pix provider not wired — set PIX_PROVIDER=fake")

    def verify_webhook(self, headers: dict, query_params: dict, body: bytes) -> WebhookEvent:
        raise NotImplementedError("External Pix provider not wired — set PIX_PROVIDER=fake")
