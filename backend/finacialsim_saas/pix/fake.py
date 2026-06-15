from __future__ import annotations

import hashlib
import hmac
import io
import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal

import qrcode
from qrcode.image.pil import PilImage

from finacialsim_saas.pix.protocol import PayerInfo, PixChargeData, WebhookEvent

UTC = timezone.utc
BRT = ZoneInfo("America/Sao_Paulo")


class InMemoryFakePixProvider:
    name = "fake"

    def __init__(self, secret: str = "") -> None:
        self._secret = secret

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
        brcode = (
            f"00020126330014BR.GOV.BCB.PIX0114{txid[:14]}"
            f"5204000053039865802BR5913{description[:13]}"
            f"6009SAOPAULO62070503***63040000"
        )
        buf = io.BytesIO()
        img = qrcode.make(brcode, image_factory=PilImage)
        img.save(buf, format="PNG")
        qr_png = buf.getvalue()

        valid_through = due_date + timedelta(days=validity_days)
        expires_at = datetime.combine(valid_through, time(23, 59, 59), tzinfo=BRT).astimezone(UTC)
        return PixChargeData(
            txid=txid,
            brcode=brcode,
            qr_png_bytes=qr_png,
            amount=amount,
            expires_at=expires_at,
        )

    async def cancel_charge(self, txid: str) -> None:
        pass  # no-op for fake

    def verify_webhook(self, headers: dict, query_params: dict, body: bytes) -> WebhookEvent:
        """`query_params` accepted for Protocol parity; unused in fake (keeps its own HMAC-over-body scheme)."""
        if self._secret:
            sig_header = headers.get("X-Pix-Signature", "")
            if not sig_header.startswith("sha256="):
                raise ValueError("Missing or invalid X-Pix-Signature header")
            expected = "sha256=" + hmac.new(
                self._secret.encode(), body, hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(sig_header, expected):
                raise ValueError("Invalid HMAC-SHA256 signature")

        payload = json.loads(body)
        pix_entries = payload.get("pix", [])
        if not pix_entries:
            raise ValueError("No pix entries in webhook payload")
        entry = pix_entries[0]
        paid_amount = Decimal(str(entry["valor"])) if "valor" in entry else None
        return WebhookEvent(
            txid=entry["txid"],
            status=entry["status"],
            paid_amount=paid_amount,
            provider_payload=entry,
        )
