from __future__ import annotations

import base64
import json
from datetime import date, datetime, time, timezone
from decimal import Decimal
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from finacialsim_saas.errors import ValidationError
from finacialsim_saas.pix.protocol import PayerInfo, PixChargeData
from finacialsim_saas.settings import Settings

UTC = timezone.utc
BRT = ZoneInfo("America/Sao_Paulo")


def _settings(**overrides) -> Settings:
    base: dict = dict(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        efi_client_id="cid", efi_client_secret="csecret",
        efi_certificate_path="/certs/efi.pem",
        efi_pix_key="11111111-2222-3333-4444-555555555555",
        efi_sandbox=True, pix_webhook_secret="webhook-secret",
    )
    base.update(overrides)
    return Settings(**base)


def _qrcode_payload() -> str:
    return "data:image/png;base64," + base64.b64encode(b"PNGDATA").decode()


def _due_charge_response(**overrides) -> dict:
    base = {
        "txid": "abc123",
        "pixCopiaECola": "00020126brcode...",
        "loc": {"id": 9876},
        "calendario": {
            "criacao": "2026-06-07T12:00:00.000Z",
            "dataDeVencimento": "2026-09-01",
            "validadeAposVencimento": 60,
        },
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_create_charge_sends_cobv_request_shape_and_maps_response():
    from finacialsim_saas.pix.efi import EfiPixProvider

    client = MagicMock()
    client.pix_create_due_charge.return_value = _due_charge_response()
    client.pix_generate_qrcode.return_value = {"imagemQrcode": _qrcode_payload()}

    provider = EfiPixProvider(_settings(), client=client)
    payer = PayerInfo(document="12345678909", document_type="cpf", name="Maria Silva")

    result = await provider.create_charge(
        txid="abc123", amount=Decimal("1987.34"),
        due_date=date(2026, 9, 1), validity_days=60,
        description="Parcela 1", payer=payer,
    )

    client.pix_create_due_charge.assert_called_once_with(
        params={"txid": "abc123"},
        body={
            "calendario": {"dataDeVencimento": "2026-09-01", "validadeAposVencimento": 60},
            "valor": {"original": "1987.34"},
            "chave": "11111111-2222-3333-4444-555555555555",
            "solicitacaoPagador": "Parcela 1",
            "devedor": {"cpf": "12345678909", "nome": "Maria Silva"},
            "juros": {"modalidade": 2, "valorPerc": "0.00"},
            "multa": {"modalidade": 2, "valorPerc": "0.00"},
        },
    )
    client.pix_generate_qrcode.assert_called_once_with(params={"id": 9876})
    assert isinstance(result, PixChargeData)
    assert result.txid == "abc123"
    assert result.brcode == "00020126brcode..."
    assert result.qr_png_bytes == b"PNGDATA"
    assert result.amount == Decimal("1987.34")
    # 2026-09-01 + 60 days = 2026-10-31; BRT 23:59:59 = UTC 2026-11-01T02:59:59
    expected_local = datetime(2026, 10, 31, 23, 59, 59, tzinfo=BRT)
    assert result.expires_at == expected_local.astimezone(UTC)


@pytest.mark.asyncio
async def test_create_charge_with_penalty_rates_sends_nonzero_juros_multa():
    from finacialsim_saas.pix.efi import EfiPixProvider

    client = MagicMock()
    client.pix_create_due_charge.return_value = _due_charge_response()
    client.pix_generate_qrcode.return_value = {"imagemQrcode": _qrcode_payload()}

    provider = EfiPixProvider(_settings(), client=client)

    await provider.create_charge(
        txid="abc123", amount=Decimal("1000.00"),
        due_date=date(2026, 9, 1), validity_days=60,
        description="Parcela 1", payer=None,
        multa_pct=Decimal("2.00"), juros_diario_pct=Decimal("0.033"), carencia_dias=0,
    )

    _, kwargs = client.pix_create_due_charge.call_args
    assert kwargs["body"]["juros"] == {"modalidade": 2, "valorPerc": "0.033"}
    assert kwargs["body"]["multa"] == {"modalidade": 2, "valorPerc": "2.00"}


@pytest.mark.asyncio
async def test_create_charge_omits_devedor_when_payer_is_none():
    from finacialsim_saas.pix.efi import EfiPixProvider

    client = MagicMock()
    client.pix_create_due_charge.return_value = _due_charge_response()
    client.pix_generate_qrcode.return_value = {"imagemQrcode": _qrcode_payload()}
    provider = EfiPixProvider(_settings(), client=client)

    await provider.create_charge(
        txid="abc123", amount=Decimal("100"),
        due_date=date(2026, 9, 1), validity_days=60,
        description="x", payer=None,
    )

    _, kwargs = client.pix_create_due_charge.call_args
    assert "devedor" not in kwargs["body"]


@pytest.mark.asyncio
async def test_create_charge_translates_sdk_errors_to_validation_error():
    from finacialsim_saas.pix.efi import EfiPixProvider

    client = MagicMock()
    client.pix_create_due_charge.side_effect = RuntimeError("efi unreachable")
    provider = EfiPixProvider(_settings(), client=client)

    with pytest.raises(ValidationError, match="Não foi possível gerar o PIX"):
        await provider.create_charge(
            txid="abc123", amount=Decimal("100"),
            due_date=date(2026, 9, 1), validity_days=60,
            description="x", payer=None,
        )


@pytest.mark.asyncio
async def test_cancel_charge_sends_cobv_patch_with_removal_status():
    from finacialsim_saas.pix.efi import EfiPixProvider

    client = MagicMock()
    client.pix_update_due_charge.return_value = {"status": "REMOVIDA_PELO_USUARIO_RECEBEDOR"}
    provider = EfiPixProvider(_settings(), client=client)

    await provider.cancel_charge("abc123")

    client.pix_update_due_charge.assert_called_once_with(
        params={"txid": "abc123"},
        body={"status": "REMOVIDA_PELO_USUARIO_RECEBEDOR"},
    )


@pytest.mark.asyncio
async def test_cancel_charge_swallows_provider_errors():
    """Matches PixService.cancel_charges_for_proposal's best-effort contract."""
    from finacialsim_saas.pix.efi import EfiPixProvider

    client = MagicMock()
    client.pix_update_due_charge.side_effect = RuntimeError("efi unreachable")
    provider = EfiPixProvider(_settings(), client=client)

    await provider.cancel_charge("abc123")  # must not raise


def _efi_webhook_payload(txid: str = "e2e-abc", valor: str = "1987.34") -> bytes:
    return json.dumps({
        "pix": [{
            "endToEndId": "E00000000202606071200000000000001",
            "txid": txid,
            "chave": "11111111-2222-3333-4444-555555555555",
            "valor": valor,
            "horario": "2026-06-07T12:00:05.000Z",
        }]
    }).encode()


def test_verify_webhook_accepts_matching_hmac_token_and_maps_efi_payload():
    from finacialsim_saas.pix.efi import EfiPixProvider

    provider = EfiPixProvider(_settings(pix_webhook_secret="shared-secret"), client=MagicMock())

    event = provider.verify_webhook(
        headers={},
        query_params={"hmac": "shared-secret", "ignorar": ""},
        body=_efi_webhook_payload(txid="e2e-abc", valor="1987.34"),
    )

    assert event.status == "paid"
    assert event.txid == "e2e-abc"
    assert event.paid_amount == Decimal("1987.34")


def test_verify_webhook_rejects_missing_or_mismatched_hmac_token():
    from finacialsim_saas.pix.efi import EfiPixProvider

    provider = EfiPixProvider(_settings(pix_webhook_secret="shared-secret"), client=MagicMock())
    body = _efi_webhook_payload()

    with pytest.raises(ValueError, match="Invalid or missing hmac"):
        provider.verify_webhook(headers={}, query_params={}, body=body)

    with pytest.raises(ValueError, match="Invalid or missing hmac"):
        provider.verify_webhook(headers={}, query_params={"hmac": "wrong-token"}, body=body)


@pytest.mark.asyncio
async def test_register_webhook_sends_url_with_skip_mtls_header():
    from finacialsim_saas.pix.efi import EfiPixProvider

    client = MagicMock()
    client.pix_config_webhook.return_value = {
        "webhookUrl": "https://app.test/api/v1/webhooks/pix?hmac=secret&ignorar="
    }
    provider = EfiPixProvider(_settings(), client=client)

    await provider.register_webhook("https://app.test/api/v1/webhooks/pix?hmac=secret&ignorar=")

    client.pix_config_webhook.assert_called_once_with(
        params={"chave": "11111111-2222-3333-4444-555555555555"},
        body={"webhookUrl": "https://app.test/api/v1/webhooks/pix?hmac=secret&ignorar="},
        headers={"x-skip-mtls-checking": "true"},
    )
