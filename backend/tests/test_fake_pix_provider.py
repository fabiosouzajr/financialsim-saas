from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from finacialsim_saas.pix.fake import InMemoryFakePixProvider
from finacialsim_saas.pix.protocol import PayerInfo

UTC = timezone.utc
BRT = ZoneInfo("America/Sao_Paulo")


def _signed_body(secret: str, payload: dict) -> tuple[bytes, str]:
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return body, sig


@pytest.mark.asyncio
async def test_create_charge_anchors_expiry_to_due_date_plus_validity_days_in_brt():
    """2026-09-01 + 60 days = 2026-10-31; BRT 23:59:59 = UTC 2026-11-01T02:59:59."""
    provider = InMemoryFakePixProvider(secret="s")
    payer = PayerInfo(document="12345678909", document_type="cpf", name="Maria Silva")

    result = await provider.create_charge(
        txid="abc123", amount=Decimal("140.00"),
        due_date=date(2026, 9, 1), validity_days=60,
        description="Parcela 1", payer=payer,
    )

    from datetime import datetime, time, timedelta
    expected_local = datetime(2026, 10, 31, 23, 59, 59, tzinfo=BRT)
    assert result.expires_at == expected_local.astimezone(UTC)


def test_verify_webhook_accepts_query_params_and_ignores_them():
    secret = "test-secret"
    provider = InMemoryFakePixProvider(secret=secret)
    payload = {"pix": [{"txid": "abc123", "status": "paid", "valor": "100.00"}]}
    body, sig = _signed_body(secret, payload)

    event = provider.verify_webhook(
        headers={"X-Pix-Signature": sig},
        query_params={"hmac": "irrelevant-for-fake", "ignorar": ""},
        body=body,
    )

    assert event.txid == "abc123"
    assert event.status == "paid"


def test_verify_webhook_still_checks_body_hmac_not_query_params():
    secret = "test-secret"
    provider = InMemoryFakePixProvider(secret=secret)
    payload = {"pix": [{"txid": "abc123", "status": "paid", "valor": "100.00"}]}
    body, _ = _signed_body(secret, payload)

    with pytest.raises(ValueError, match="Missing or invalid X-Pix-Signature"):
        provider.verify_webhook(headers={}, query_params={"hmac": secret}, body=body)
