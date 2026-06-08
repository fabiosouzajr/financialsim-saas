# Efí Pix Provider — Part 1: Foundation (Tasks 1–4)

> Part of the [Phase 1 plan](2026-06-07-efi-pix-provider.md). Tasks 1–4: settings, Protocol signature (CobV), fake provider (BRT-anchored expiry), `pix_validade_apos_vencimento_dias` rule + seed migration.

---

### Task 1: Settings — `efi_*` fields + `efipay` dependency

**Files:**

- Modify: `backend/finacialsim_saas/settings.py:41-42`
- Modify: `backend/pyproject.toml:25`
- Test: `backend/tests/test_settings.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_settings.py`:

```python
def test_settings_has_efi_pix_fields(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    s = Settings()
    assert s.efi_client_id == ""
    assert s.efi_client_secret == ""
    assert s.efi_certificate_path == ""
    assert s.efi_pix_key == ""
    assert s.efi_sandbox is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_settings.py::test_settings_has_efi_pix_fields -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'efi_client_id'`

- [ ] **Step 3: Write minimal implementation**

In `backend/finacialsim_saas/settings.py`, replace lines 41-42:

```python
    pix_provider: str = "fake"
    pix_webhook_secret: str = ""
```

with:

```python
    pix_provider: str = "fake"
    pix_webhook_secret: str = ""

    efi_client_id: str = ""
    efi_client_secret: str = ""
    efi_certificate_path: str = ""   # absolute in-container path to .pem
    efi_pix_key: str = ""            # registered Pix key (UUID format)
    efi_sandbox: bool = True
```

In `backend/pyproject.toml`, add `efipay` after `"qrcode[pil]>=7.4.2",` (line 25):

```toml
    "qrcode[pil]>=7.4.2",
    "efipay>=1.0.7",
```

Run: `cd /home/fj/git/financialsim-saas && uv sync --extra dev`
Expected: `efipay==1.0.7` (or compatible) resolved and installed.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_settings.py::test_settings_has_efi_pix_fields -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/settings.py backend/pyproject.toml backend/tests/test_settings.py uv.lock
git commit -m "feat: add efi_* Pix settings and efipay dependency"
```

---

### Task 2: `PayerInfo` dataclass + `PixProvider` Protocol — CobV signature

**Files:**

- Modify: `backend/finacialsim_saas/pix/protocol.py`
- Test: Create `backend/tests/test_pix_protocol.py`

**Why this task:** The old `create_charge(expires_in: int)` is a Cob concept. CobV charges are calendar-anchored — the provider needs `due_date: date` and `validity_days: int`, not a duration in seconds. This is the Protocol-level commitment; fake and efi both implement it.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_pix_protocol.py`:

```python
from __future__ import annotations

import inspect
from datetime import date

from finacialsim_saas.pix.protocol import PayerInfo, PixProvider


def test_payer_info_fields():
    payer = PayerInfo(document="12345678909", document_type="cpf", name="Maria Silva")
    assert payer.document == "12345678909"
    assert payer.document_type == "cpf"
    assert payer.name == "Maria Silva"


def test_create_charge_uses_date_based_due_date_and_validity_days():
    sig = inspect.signature(PixProvider.create_charge)
    assert "due_date" in sig.parameters
    assert "validity_days" in sig.parameters
    assert "expires_in" not in sig.parameters
    # protocol.py uses `from __future__ import annotations` so annotations are strings
    assert sig.parameters["due_date"].annotation == "date"
    assert sig.parameters["validity_days"].annotation == "int"


def test_create_charge_accepts_optional_payer_info():
    sig = inspect.signature(PixProvider.create_charge)
    assert sig.parameters["payer"].annotation == "PayerInfo | None"


def test_verify_webhook_signature_has_query_params():
    sig = inspect.signature(PixProvider.verify_webhook)
    assert list(sig.parameters) == ["self", "headers", "query_params", "body"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_pix_protocol.py -v`
Expected: FAIL — `ImportError: cannot import name 'PayerInfo'`

- [ ] **Step 3: Write minimal implementation**

`backend/finacialsim_saas/pix/protocol.py` currently has `from __future__ import annotations` on line 1.

Replace line 4 (`from datetime import datetime`) with:

```python
from datetime import date, datetime
```

Add `Literal` to line 6's typing import:

```python
from typing import Literal, Protocol, runtime_checkable
```

Add `PayerInfo` dataclass after `PixChargeData` (after line 17):

```python
@dataclass
class PayerInfo:
    """Structured payer identity — Efí's `devedor` needs distinct CPF/CNPJ fields."""
    document: str          # CPF or CNPJ, digits only (punctuation stripped)
    document_type: Literal["cpf", "cnpj"]
    name: str
```

Replace the `PixProvider` Protocol body (lines 33-45) with the CobV-shaped signature:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_pix_protocol.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/pix/protocol.py backend/tests/test_pix_protocol.py
git commit -m "feat: switch PixProvider.create_charge to CobV calendar signature (due_date/validity_days)"
```

---

### Task 3: `InMemoryFakePixProvider` — BRT-anchored calendar expiry

**Files:**

- Modify: `backend/finacialsim_saas/pix/fake.py:7,13,24-50,55`
- Test: Create `backend/tests/test_fake_pix_provider.py`

**Why:** Old fake used `datetime.now() + timedelta(seconds=expires_in)` — a Cob/duration concept. CobV expiry is `due_date + validity_days` at `23:59:59` in `America/Sao_Paulo` (spec §3b). Fake must mirror real so integration tests use accurate expiry math.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_fake_pix_provider.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_fake_pix_provider.py -v`
Expected: FAIL — `TypeError: InMemoryFakePixProvider.create_charge() got an unexpected keyword argument 'due_date'`

- [ ] **Step 3: Write minimal implementation**

Replace line 7 in `backend/finacialsim_saas/pix/fake.py`:

```python
from datetime import datetime, timedelta, timezone
```

with:

```python
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
```

Add `BRT` constant after `UTC = timezone.utc` (line 15):

```python
UTC = timezone.utc
BRT = ZoneInfo("America/Sao_Paulo")
```

Replace line 13 (protocol import) to add `PayerInfo`:

```python
from finacialsim_saas.pix.protocol import PayerInfo, PixChargeData, WebhookEvent
```

Replace lines 24-50 (the entire `create_charge` method):

```python
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
```

Replace the `verify_webhook` signature (line 55) to add `query_params`:

```python
    def verify_webhook(self, headers: dict, query_params: dict, body: bytes) -> WebhookEvent:
        """`query_params` accepted for Protocol parity; unused in fake (keeps its own HMAC-over-body scheme)."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_fake_pix_provider.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/pix/fake.py backend/tests/test_fake_pix_provider.py
git commit -m "feat: switch InMemoryFakePixProvider to BRT-anchored CobV expiry (due_date + validity_days)"
```

---

### Task 4: `pix_validade_apos_vencimento_dias` rule + seed migration

**Files:**

- Modify: `backend/finacialsim_saas/services/rules_service.py:41-42`
- Create: `backend/alembic/versions/011_seed_pix_validade_apos_vencimento_rule.py`
- Modify: `backend/tests/test_simulation_service.py:56-64` (ripple: count goes 20→21)

**Why:** `_ensure_charge` (Task 5) reads this rule to determine `validity_days` for every CobV charge. It must exist in `_RULE_DEFAULTS` so `RulesService.get_rules()` returns it for every tenant. The seed migration back-fills existing tenants. The `test_get_rules_returns_all_20_keys` test will fail as-is; rename + bump it now so Task 5 doesn't break the test suite.

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_simulation_service.py`, replace lines 56–64:

```python
async def test_get_rules_returns_all_20_keys(session, tenant, rules_seeded):
    from finacialsim_saas.services.rules_service import RulesService
    svc = RulesService(session)
    rules = await svc.get_rules(tenant.id)
    assert "entrada_minima_pct" in rules
    assert "taxa_por_prazo_curva" in rules
    assert "ipva_pct_carro" in rules
    assert "emplacamento_valor_moto" in rules
    assert len(rules) == 20
```

with:

```python
async def test_get_rules_returns_all_21_keys(session, tenant, rules_seeded):
    from finacialsim_saas.services.rules_service import RulesService
    svc = RulesService(session)
    rules = await svc.get_rules(tenant.id)
    assert "entrada_minima_pct" in rules
    assert "taxa_por_prazo_curva" in rules
    assert "ipva_pct_carro" in rules
    assert "emplacamento_valor_moto" in rules
    assert rules["pix_validade_apos_vencimento_dias"] == 60
    assert len(rules) == 21
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_simulation_service.py::test_get_rules_returns_all_21_keys -v`
Expected: FAIL — `KeyError: 'pix_validade_apos_vencimento_dias'`

- [ ] **Step 3: Write minimal implementation**

In `backend/finacialsim_saas/services/rules_service.py`, replace lines 41-42:

```python
    "emplacamento_valor_caminhao":     ("220.46", "Emplacamento — caminhão (R$)"),
}
```

with:

```python
    "emplacamento_valor_caminhao":     ("220.46", "Emplacamento — caminhão (R$)"),
    "pix_validade_apos_vencimento_dias": (60,     "Dias de validade do Pix após o vencimento da parcela"),
}
```

Create `backend/alembic/versions/011_seed_pix_validade_apos_vencimento_rule.py`:

```python
"""seed pix_validade_apos_vencimento_dias business rule

Revision ID: 011
Revises: 010
Create Date: 2026-06-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None

_NEW_RULES = [
    ("pix_validade_apos_vencimento_dias", 60, "Dias de validade do Pix após o vencimento da parcela"),
]


def upgrade() -> None:
    for chave, valor, descricao in _NEW_RULES:
        op.execute(
            sa.text(
                """
                INSERT INTO business_rules (id, tenant_id, chave, valor_json, descricao, atualizado_em)
                SELECT gen_random_uuid(), t.id, :chave, cast(:valor as jsonb), :descricao, now()
                FROM tenants t
                ON CONFLICT (tenant_id, chave) DO NOTHING
                """
            ).bindparams(chave=chave, valor=str(valor), descricao=descricao)
        )


def downgrade() -> None:
    for chave, _, _ in _NEW_RULES:
        op.execute(
            sa.text("DELETE FROM business_rules WHERE chave = :chave").bindparams(chave=chave)
        )
```

Note: `valor=str(60)` → `cast('60' as jsonb)` produces JSON integer `60`, not a string. Do **not** quote-wrap (unlike string rules in migration 010 which use `f'"{valor}"'`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_simulation_service.py::test_get_rules_returns_all_21_keys -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/services/rules_service.py \
        backend/alembic/versions/011_seed_pix_validade_apos_vencimento_rule.py \
        backend/tests/test_simulation_service.py
git commit -m "feat: add pix_validade_apos_vencimento_dias business rule (default 60 days)"
```
