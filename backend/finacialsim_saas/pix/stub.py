from __future__ import annotations

from decimal import Decimal

from finacialsim_saas.pix.protocol import PixChargeData, WebhookEvent


class StubExternalPixProvider:
    name = "external"

    async def create_charge(
        self,
        *,
        txid: str,
        amount: Decimal,
        expires_in: int,
        description: str,
        payer: str,
    ) -> PixChargeData:
        raise NotImplementedError("External Pix provider not wired — set PIX_PROVIDER=fake")

    async def cancel_charge(self, txid: str) -> None:
        raise NotImplementedError("External Pix provider not wired — set PIX_PROVIDER=fake")

    def verify_webhook(self, headers: dict, body: bytes) -> WebhookEvent:
        raise NotImplementedError("External Pix provider not wired — set PIX_PROVIDER=fake")
