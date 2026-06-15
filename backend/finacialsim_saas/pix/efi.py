from __future__ import annotations

import asyncio
import base64
import hmac
import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from efipay import EfiPay
from loguru import logger

from finacialsim_saas.errors import ValidationError
from finacialsim_saas.pix.protocol import PayerInfo, PixChargeData, WebhookEvent
from finacialsim_saas.settings import Settings

UTC = timezone.utc
BRT = ZoneInfo("America/Sao_Paulo")


class EfiPixProvider:
    name = "efi"

    def __init__(self, settings: Settings, client: EfiPay | None = None) -> None:
        self._client = client or EfiPay({
            "client_id": settings.efi_client_id,
            "client_secret": settings.efi_client_secret,
            "sandbox": settings.efi_sandbox,
            "certificate": settings.efi_certificate_path,
        })
        self._pix_key = settings.efi_pix_key
        self._webhook_secret = settings.pix_webhook_secret

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
        body: dict[str, Any] = {
            "calendario": {
                "dataDeVencimento": due_date.isoformat(),
                "validadeAposVencimento": validity_days,
            },
            "valor": {"original": str(amount)},
            "chave": self._pix_key,
            "solicitacaoPagador": description,
            # Explicit zeros prevent Efí's default non-zero interest (2% day 1) when omitted
            "juros": {"modalidade": 2, "valorPerc": str(juros_diario_pct)},
            "multa": {"modalidade": 2, "valorPerc": str(multa_pct)},
        }
        if payer is not None:
            body["devedor"] = {payer.document_type: payer.document, "nome": payer.name}

        try:
            charge_resp = await asyncio.to_thread(
                self._client.pix_create_due_charge, params={"txid": txid}, body=body
            )
            qr_resp = await asyncio.to_thread(
                self._client.pix_generate_qrcode, params={"id": charge_resp["loc"]["id"]}
            )
        except Exception as exc:
            logger.error("efi create_charge failed for txid={}: {}", txid, exc)
            raise ValidationError("Não foi possível gerar o PIX no momento, tente novamente") from exc

        qr_b64 = qr_resp["imagemQrcode"].removeprefix("data:image/png;base64,")
        valid_through = due_date + timedelta(days=validity_days)
        expires_at = datetime.combine(valid_through, time(23, 59, 59), tzinfo=BRT).astimezone(UTC)

        return PixChargeData(
            txid=charge_resp["txid"],
            brcode=charge_resp["pixCopiaECola"],
            qr_png_bytes=base64.b64decode(qr_b64),
            amount=amount,
            expires_at=expires_at,
            provider_payload=charge_resp,
        )

    async def cancel_charge(self, txid: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.pix_update_due_charge,
                params={"txid": txid},
                body={"status": "REMOVIDA_PELO_USUARIO_RECEBEDOR"},
            )
        except Exception as exc:
            logger.warning("efi cancel_charge failed for txid={}: {}", txid, exc)

    async def register_webhook(self, url: str) -> None:
        """PUT /v2/webhook/:chave — idempotent. `x-skip-mtls-checking: true` required
        on registration, or Efí defaults to mTLS validation the Caddy proxy can't satisfy."""
        await asyncio.to_thread(
            self._client.pix_config_webhook,
            params={"chave": self._pix_key},
            body={"webhookUrl": url},
            headers={"x-skip-mtls-checking": "true"},
        )

    def verify_webhook(self, headers: dict, query_params: dict, body: bytes) -> WebhookEvent:
        """Efí echoes a static token in the callback URL's query string instead of
        HMAC-signing the body. Token compared constant-time — it IS the security boundary
        in skip-mTLS mode (spec §4)."""
        token = query_params.get("hmac", "")
        if not token or not hmac.compare_digest(token, self._webhook_secret):
            raise ValueError("Invalid or missing hmac query token")

        payload = json.loads(body)
        pix_entries = payload.get("pix", [])
        if not pix_entries:
            raise ValueError("No pix entries in webhook payload")

        entry = pix_entries[0]
        return WebhookEvent(
            txid=entry["txid"],
            status="paid",
            paid_amount=Decimal(str(entry["valor"])) if "valor" in entry else None,
            provider_payload=entry,
        )
