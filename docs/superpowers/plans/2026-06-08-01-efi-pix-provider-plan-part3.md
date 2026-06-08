# Efí Pix Provider — Part 3: EfiPixProvider (Tasks 7–9)

> Part of the [Phase 1 plan](2026-06-07-efi-pix-provider.md). Tasks 7–9: `EfiPixProvider` CobV `create_charge`, `cancel_charge`, `verify_webhook`.

---

### Task 7: `EfiPixProvider.__init__` + `create_charge` (CobV)

**Files:**

- Create: `backend/finacialsim_saas/pix/efi.py`
- Test: Create `backend/tests/test_efi_pix_provider.py`

**Why CobV vs Cob:** `pix_create_due_charge` (`PUT /v2/cobv/:txid`) takes `calendario.dataDeVencimento`/`calendario.validadeAposVencimento` instead of `calendario.expiracao`. The charge lives from issuance until `vencimento + validadeAposVencimento` days, so the same `brcode` is payable before, on, and after the due date — one charge covers the whole parcela lifecycle.

**Explicit-zero `juros`/`multa`:** Efí defaults `juros.modalidade` to a non-zero value (2% on day 1) when the blocks are omitted — silently producing wrong amounts after `vencimento`. Sending `{"modalidade": 2, "valorPerc": "0.00"}` prevents this. `modalidade: 2` = percentual; the field name `valorPerc` confirms this choice per BACEN's Pix-cobrança spec.

**`expires_at` BRT formula (spec §3b):** `valid_through = due_date + timedelta(days=validity_days)`; `expires_at = datetime.combine(valid_through, time(23, 59, 59), tzinfo=BRT).astimezone(UTC)`. Computed from inputs — not parsed from the response's `calendario.criacao` (that was the Cob approach).

- [ ] **Step 1: Verify `modalidade` integer against the SDK's bundled example**

Locate the CobV creation example in the installed `efipay` package:

```bash
find $(uv run python -c "import efipay, os; print(os.path.dirname(efipay.__file__))") \
     -path '*cobv*' -name 'pix_create_due_charge*'
```

Read the matched file. Find the `juros`/`multa` block in its example request body. If `modalidade` is `2` — proceed with Step 3 as written. If it differs, replace every `"modalidade": 2` below (in both test and implementation) with the value the example shows, then document the discrepancy in a comment.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_efi_pix_provider.py`:

```python
from __future__ import annotations

import base64
from datetime import date, datetime, timezone
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
    from datetime import datetime, time
    expected_local = datetime(2026, 10, 31, 23, 59, 59, tzinfo=BRT)
    assert result.expires_at == expected_local.astimezone(UTC)


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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_efi_pix_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'finacialsim_saas.pix.efi'`

- [ ] **Step 4: Write minimal implementation**

Create `backend/finacialsim_saas/pix/efi.py`:

```python
from __future__ import annotations

import asyncio
import base64
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
    ) -> PixChargeData:
        body: dict[str, Any] = {
            "calendario": {
                "dataDeVencimento": due_date.isoformat(),
                "validadeAposVencimento": validity_days,
            },
            "valor": {"original": str(amount)},
            "chave": self._pix_key,
            "solicitacaoPagador": description,
            # Explicit zeros — Efí defaults juros.modalidade to non-zero (2% day 1) when omitted
            "juros": {"modalidade": 2, "valorPerc": "0.00"},
            "multa": {"modalidade": 2, "valorPerc": "0.00"},
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_efi_pix_provider.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/pix/efi.py backend/tests/test_efi_pix_provider.py
git commit -m "feat: implement EfiPixProvider.create_charge against efipay CobV API"
```

---

### Task 8: `EfiPixProvider.cancel_charge` (CobV)

**Files:**

- Modify: `backend/finacialsim_saas/pix/efi.py`
- Test: extend `backend/tests/test_efi_pix_provider.py`

**Why CobV vs Cob:** cancellation is `PATCH /v2/cobv/:txid` via `pix_update_due_charge` instead of `pix_update_charge`. The status string is the same BACEN lifecycle value.

- [ ] **Step 1: Verify the cancellation status string against the SDK's bundled example**

```bash
find $(uv run python -c "import efipay, os; print(os.path.dirname(efipay.__file__))") \
     -path '*cobv*' -name 'pix_update_due_charge*'
```

Read the matched file. Confirm the cancellation status string is `"REMOVIDA_PELO_USUARIO_RECEBEDOR"` (same BACEN Pix-cobrança lifecycle vocabulary as Cob). If it differs, replace every occurrence of `REMOVIDA_PELO_USUARIO_RECEBEDOR` below with the value from the example.

- [ ] **Step 2: Write the failing test**

Append to `backend/tests/test_efi_pix_provider.py`:

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_efi_pix_provider.py -k cancel_charge -v`
Expected: FAIL — `AttributeError: 'EfiPixProvider' object has no attribute 'cancel_charge'`

- [ ] **Step 4: Write minimal implementation**

Add to `EfiPixProvider` in `backend/finacialsim_saas/pix/efi.py` (after `create_charge`):

```python
    async def cancel_charge(self, txid: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.pix_update_due_charge,
                params={"txid": txid},
                body={"status": "REMOVIDA_PELO_USUARIO_RECEBEDOR"},
            )
        except Exception as exc:
            logger.warning("efi cancel_charge failed for txid={}: {}", txid, exc)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_efi_pix_provider.py -k cancel_charge -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/pix/efi.py backend/tests/test_efi_pix_provider.py
git commit -m "feat: implement EfiPixProvider.cancel_charge (CobV PATCH) with best-effort error swallowing"
```

---

### Task 9: `EfiPixProvider.verify_webhook`

**Files:**

- Modify: `backend/finacialsim_saas/pix/efi.py`
- Test: extend `backend/tests/test_efi_pix_provider.py`

**Validation strategy (spec §4 — skip-mTLS):** Efí doesn't HMAC-sign the body. Instead, it echoes a static token in the callback URL's query string (`?hmac=<token>&ignorar=`). This token is compared constant-time; it IS the security boundary in skip-mTLS mode. Webhook payload shape is identical for Cob and CobV.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_efi_pix_provider.py`:

```python
def _efi_webhook_payload(txid: str = "e2e-abc", valor: str = "1987.34") -> bytes:
    import json
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_efi_pix_provider.py -k verify_webhook -v`
Expected: FAIL — `AttributeError: 'EfiPixProvider' object has no attribute 'verify_webhook'`

- [ ] **Step 3: Write minimal implementation**

Add `hmac` and `json` to the imports at the top of `backend/finacialsim_saas/pix/efi.py` (alongside `asyncio`/`base64`):

```python
import asyncio
import base64
import hmac
import json
```

Add to `EfiPixProvider` (after `cancel_charge`):

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_efi_pix_provider.py -v`
Expected: PASS (7 passed — all tasks 7–9 tests together)

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/pix/efi.py backend/tests/test_efi_pix_provider.py
git commit -m "feat: implement EfiPixProvider.verify_webhook with hmac query-token validation (skip-mTLS)"
```
