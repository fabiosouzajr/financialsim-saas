# Efí Pix Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `StubExternalPixProvider` with a working `EfiPixProvider` that implements the `PixProvider` Protocol against Efí's real Pix PSP API, wired through `pix/deps.py`'s provider selector, plus the small Protocol/service-layer changes (`PayerInfo`, webhook `query_params`, clientless-proposal guard) this requires.

**Architecture:** `EfiPixProvider` wraps the sync `efipay` SDK in `asyncio.to_thread` (matching the existing pattern for WeasyPrint/boto3 — `workers/tasks.py:292`, `storage/s3.py`), translating Efí's REST shapes (`devedor`, `pixCopiaECola`, `imagemQrcode`, `calendario`) to/from the existing `PixChargeData`/`WebhookEvent` value objects. Two Protocol gaps surfaced by Efí's real API — structured payer identity and webhook query-param validation — are generic (not Efí-specific) and threaded mechanically through `InMemoryFakePixProvider`, `PixService`, and `api/webhooks.py`. One small *non*-mechanical change rides along: `PixService.create_charge_for_parcela` now blocks Pix charges on clientless proposals — a real "a Pix charge needs a payer" business rule, deliberately applied to `fake` too.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x async, `efipay` SDK v1.0.7 (sync, `requests`-based, OAuth2 + mTLS), `asyncio.to_thread`, `typer` CLI, `pytest`/`pytest-asyncio`, `MagicMock`/`AsyncMock` for boundary mocking (no live Efí account in CI).

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/pyproject.toml` | Add `efipay>=1.0.7` dependency |
| `backend/finacialsim_saas/settings.py` | New `efi_*` settings fields |
| `backend/finacialsim_saas/pix/protocol.py` | New `PayerInfo` dataclass; `create_charge`/`verify_webhook` signature changes |
| `backend/finacialsim_saas/pix/fake.py` | Mechanical signature threading (`payer: PayerInfo \| None`, `query_params`) |
| `backend/finacialsim_saas/pix/service.py` | `create_charge_for_parcela` builds `PayerInfo` from `Client`, raises on clientless proposal; `handle_webhook` threads `query_params` |
| `backend/finacialsim_saas/pix/efi.py` | **New** — `EfiPixProvider`: `create_charge`, `cancel_charge`, `verify_webhook`, `register_webhook` |
| `backend/finacialsim_saas/pix/deps.py` | `efi` branch wiring, cached singleton, startup validation guards |
| `backend/finacialsim_saas/pix/stub.py` | **Deleted** — superseded by `EfiPixProvider` (no test references it) |
| `backend/finacialsim_saas/api/webhooks.py` | Threads `query_params` from `request.query_params` |
| `backend/finacialsim_saas/api/pix_admin.py` | Gate rename `== "external"` → `!= "fake"` |
| `backend/finacialsim_saas/main.py` | Calls `get_pix_provider` at startup (fail-fast); logs sandbox-in-production warning |
| `backend/finacialsim_saas/cli/pix_cli.py` | **New** — `pix register-webhook` command |
| `backend/finacialsim_saas/cli/main.py` | Registers `pix_app` sub-app |
| `docs/agents/efi-pix-setup.md` | **New** — setup runbook |

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
    efi_certificate_path: str = ""   # absolute path to .pem on disk (inside the container)
    efi_pix_key: str = ""            # the recipient's registered Pix key (UUID format)
    efi_sandbox: bool = True
```

In `backend/pyproject.toml`, add the `efipay` dependency to the `dependencies` array (after `"qrcode[pil]>=7.4.2",` on line 25):

```toml
    "qrcode[pil]>=7.4.2",
    "efipay>=1.0.7",
```

Then install it:

Run: `cd /home/fj/git/financialsim-saas && uv sync --extra dev`
Expected: `efipay==1.0.7` (or compatible) appears in the resolved lockfile/install output

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_settings.py::test_settings_has_efi_pix_fields -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/settings.py backend/pyproject.toml backend/tests/test_settings.py uv.lock
git commit -m "feat: add efi_* Pix settings and efipay dependency"
```

---

### Task 2: `PayerInfo` dataclass + `PixProvider` Protocol signature changes

**Files:**
- Modify: `backend/finacialsim_saas/pix/protocol.py`
- Test: Create `backend/tests/test_pix_protocol.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_pix_protocol.py`:

```python
from __future__ import annotations

import inspect

from finacialsim_saas.pix.protocol import PayerInfo, PixProvider


def test_payer_info_fields():
    payer = PayerInfo(document="12345678909", document_type="cpf", name="Maria Silva")
    assert payer.document == "12345678909"
    assert payer.document_type == "cpf"
    assert payer.name == "Maria Silva"


def test_create_charge_accepts_optional_payer_info():
    sig = inspect.signature(PixProvider.create_charge)
    assert sig.parameters["payer"].annotation == "PayerInfo | None"


def test_verify_webhook_signature_has_query_params():
    sig = inspect.signature(PixProvider.verify_webhook)
    assert list(sig.parameters) == ["self", "headers", "query_params", "body"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_pix_protocol.py -v`
Expected: FAIL — `ImportError: cannot import name 'PayerInfo'` (collection error for all three tests)

- [ ] **Step 3: Write minimal implementation**

In `backend/finacialsim_saas/pix/protocol.py`, add `Literal` to the typing import (line 6):

```python
from typing import Literal, Protocol, runtime_checkable
```

Add the `PayerInfo` dataclass after `PixChargeData` (after line 17):

```python
@dataclass
class PayerInfo:
    """Structured payer identity — Efí's `devedor` needs distinct CPF/CNPJ fields, not a blob."""
    document: str          # CPF or CNPJ, digits only (punctuation stripped)
    document_type: Literal["cpf", "cnpj"]
    name: str
```

Replace the `PixProvider` Protocol body (lines 33-45):

```python
    async def create_charge(
        self,
        *,
        txid: str,
        amount: Decimal,
        expires_in: int,
        description: str,
        payer: PayerInfo | None,
    ) -> PixChargeData: ...

    async def cancel_charge(self, txid: str) -> None: ...

    def verify_webhook(self, headers: dict, query_params: dict, body: bytes) -> WebhookEvent: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_pix_protocol.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/pix/protocol.py backend/tests/test_pix_protocol.py
git commit -m "feat: add PayerInfo and thread query_params through PixProvider Protocol"
```

---

### Task 3: `InMemoryFakePixProvider` — accept `PayerInfo | None` and `query_params`

**Files:**
- Modify: `backend/finacialsim_saas/pix/fake.py:13,31,55`
- Test: Create `backend/tests/test_fake_pix_provider.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_fake_pix_provider.py`:

```python
from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from finacialsim_saas.pix.fake import InMemoryFakePixProvider


def _signed_body(secret: str, payload: dict) -> tuple[bytes, str]:
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return body, sig


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
Expected: FAIL with `TypeError: InMemoryFakePixProvider.verify_webhook() got an unexpected keyword argument 'query_params'`

- [ ] **Step 3: Write minimal implementation**

In `backend/finacialsim_saas/pix/fake.py`, add `PayerInfo` to the protocol import (line 13):

```python
from finacialsim_saas.pix.protocol import PayerInfo, PixChargeData, WebhookEvent
```

Change the `create_charge` signature (line 31) from `payer: str` to:

```python
        payer: PayerInfo | None,
```

Change the `verify_webhook` signature (line 55) from `def verify_webhook(self, headers: dict, body: bytes) -> WebhookEvent:` to:

```python
    def verify_webhook(self, headers: dict, query_params: dict, body: bytes) -> WebhookEvent:
        """`query_params` is accepted for Protocol parity but unused — the fake keeps its
        own HMAC-over-body scheme (a test convenience; real PSPs like Efí use URL tokens)."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_fake_pix_provider.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/pix/fake.py backend/tests/test_fake_pix_provider.py
git commit -m "feat: thread PayerInfo and query_params through InMemoryFakePixProvider"
```

---

### Task 4: `PixService.create_charge_for_parcela` — `PayerInfo` from `Client` + clientless guard

**Files:**
- Modify: `backend/finacialsim_saas/pix/service.py:14-19,72-82`
- Test: Create `backend/tests/test_pix_service.py` (the existing `test_pix_service_smoke.py` already names this file as where the real tests live — Plan 6E note)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_pix_service.py`:

```python
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.models import (
    Client, ClientType, ParcelaPayment, ParcelaPaymentStatus, Proposal,
    ProposalRenderStatus, ProposalStatus, Role, Simulation, SimulationStatus, Tenant,
)
from finacialsim_saas.errors import ValidationError
from finacialsim_saas.pix.protocol import PayerInfo, PixChargeData
from finacialsim_saas.pix.service import PixService
from finacialsim_saas.settings import get_settings

UTC = timezone.utc


def _mock_provider() -> AsyncMock:
    provider = AsyncMock()
    provider.create_charge.return_value = PixChargeData(
        txid="ignored-by-service",
        brcode="00020126brcode",
        qr_png_bytes=b"PNGDATA",
        amount=Decimal("14000"),
        expires_at=datetime.now(UTC) + timedelta(seconds=1800),
    )
    return provider


def _mock_storage() -> AsyncMock:
    storage = AsyncMock()
    storage.put.return_value = None
    storage.signed_url.return_value = "https://storage.test/signed"
    return storage


async def _seed_proposal_chain(session, tenant, admin_id, *, client_id):
    sim = Simulation(
        tenant_id=tenant.id, codigo=f"SIM-{uuid.uuid4().hex[:6]}",
        valor_veiculo=Decimal("50000"), valor_entrada=Decimal("10000"),
        valor_financiado=Decimal("40000"), taxa_mensal=Decimal("0.02"),
        prazo_meses=3, data_liberacao=date.today(), primeiro_vencimento=date.today(),
        incluir_iof=False, iof_total=Decimal("0"), parcela_financiamento=Decimal("14000"),
        total_pago=Decimal("42000"), total_juros=Decimal("2000"),
        cet_mensal=Decimal("0.021"), cet_anual=Decimal("0.28"),
        status=SimulationStatus.confirmado, rules_snapshot_json={},
        client_id=client_id, vehicle_id=None, criado_por=admin_id,
    )
    session.add(sim)
    await session.flush()

    proposal = Proposal(
        tenant_id=tenant.id, simulation_id=sim.id,
        codigo=f"PROP-{uuid.uuid4().hex[:6]}", gerado_por=admin_id,
        validade_dias=7,
        snapshot_json={"sim": {}, "cronograma": [], "loja": {}, "vendedor": {}, "cliente": None, "veiculo": None},
        render_status=ProposalRenderStatus.ready, status=ProposalStatus.aprovada,
    )
    session.add(proposal)
    await session.flush()

    parcela = ParcelaPayment(
        tenant_id=tenant.id, proposal_id=proposal.id, parcela_num=1,
        vencimento=date.today() + timedelta(days=30),
        valor_parcela=Decimal("14000"), status=ParcelaPaymentStatus.open,
    )
    session.add(parcela)
    await session.commit()
    return parcela


@pytest_asyncio.fixture
async def pix_setup(session: AsyncSession):
    """Tenant + admin + client + confirmed simulation + approved proposal + open parcela."""
    tenant = Tenant(name="PixCo", slug=f"pix-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()

    svc = AuthService(session, get_settings())
    admin = await svc.register_user(
        tenant_id=tenant.id, email=f"adm-{uuid.uuid4().hex[:6]}@t.com",
        password="x", name="Admin", role=Role.admin,
    )

    client = Client(
        tenant_id=tenant.id, nome="Maria Silva",
        cpf_cnpj="123.456.789-09", tipo=ClientType.pf,
        email=f"maria-{uuid.uuid4().hex[:6]}@example.com", criado_por=admin.id,
    )
    session.add(client)
    await session.flush()

    parcela = await _seed_proposal_chain(session, tenant, admin.id, client_id=client.id)

    ctx = RequestContext(user_id=admin.id, tenant_id=tenant.id, role=Role.admin, iat=0.0)
    return {
        "session": session, "ctx": ctx, "tenant": tenant,
        "admin_id": admin.id, "client": client, "parcela": parcela,
    }


@pytest.mark.asyncio
async def test_create_charge_builds_payer_info_from_linked_client(pix_setup):
    provider = _mock_provider()
    svc = PixService(pix_setup["session"], provider, _mock_storage())

    await svc.create_charge_for_parcela(pix_setup["parcela"].id, pix_setup["ctx"])

    _, kwargs = provider.create_charge.call_args
    assert kwargs["payer"] == PayerInfo(document="12345678909", document_type="cpf", name="Maria Silva")


@pytest.mark.asyncio
async def test_create_charge_blocks_when_proposal_has_no_linked_client(pix_setup):
    """§2a guard ('a Pix charge needs a payer') lives in PixService — fires before
    provider.create_charge, so it's provider-agnostic and applies to fake and efi alike."""
    parcela = await _seed_proposal_chain(
        pix_setup["session"], pix_setup["tenant"], pix_setup["admin_id"], client_id=None
    )
    provider = _mock_provider()
    svc = PixService(pix_setup["session"], provider, _mock_storage())

    with pytest.raises(ValidationError, match="não é possível gerar Pix sem cliente vinculado"):
        await svc.create_charge_for_parcela(parcela.id, pix_setup["ctx"])

    provider.create_charge.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_pix_service.py -v`
Expected: FAIL —
- `test_create_charge_builds_payer_info_from_linked_client`: `AssertionError: assert '' == PayerInfo(document='12345678909', ...)`
- `test_create_charge_blocks_when_proposal_has_no_linked_client`: `Failed: DID NOT RAISE <class 'ValidationError'>`

- [ ] **Step 3: Write minimal implementation**

In `backend/finacialsim_saas/pix/service.py`, add `Client`, `ClientType` to the models import (lines 14-17):

```python
from finacialsim_saas.data.models import (
    AuditLog, Client, ClientType, ParcelaPayment, ParcelaPaymentStatus, PixCharge,
    PixChargeStatus, PixWebhookEvent, Proposal, Role, Simulation, User,
)
```

Add `PayerInfo` to the protocol import (line 19):

```python
from finacialsim_saas.pix.protocol import PayerInfo, PixProvider
```

Replace lines 72-82 (the "Create new charge" block's `txid`/`payer` setup):

```python
        # Create new charge
        charge_id = uuid.uuid4()
        txid = str(charge_id).replace("-", "")[:35]

        charge_data = await self._provider.create_charge(
            txid=txid,
            amount=parcela.valor_parcela,
            expires_in=1800,
            description=f"Parcela {parcela.parcela_num}",
            payer="",
        )
```

with:

```python
        # Build payer identity — a Pix charge needs a payer (§2a); blocks clientless
        # proposals for fake too (deliberate — was a silent gap before this change)
        proposal = await self._s.get(Proposal, parcela.proposal_id)
        sim = await self._s.get(Simulation, proposal.simulation_id) if proposal else None
        client = await self._s.get(Client, sim.client_id) if sim and sim.client_id else None
        if client is None:
            raise ValidationError("não é possível gerar Pix sem cliente vinculado à proposta")

        payer = PayerInfo(
            document="".join(ch for ch in client.cpf_cnpj if ch.isdigit()),
            document_type="cpf" if client.tipo == ClientType.pf else "cnpj",
            name=client.nome,
        )

        # Create new charge
        charge_id = uuid.uuid4()
        txid = str(charge_id).replace("-", "")[:35]

        charge_data = await self._provider.create_charge(
            txid=txid,
            amount=parcela.valor_parcela,
            expires_in=1800,
            description=f"Parcela {parcela.parcela_num}",
            payer=payer,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_pix_service.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/pix/service.py backend/tests/test_pix_service.py
git commit -m "feat: build PayerInfo from linked Client and block Pix charges on clientless proposals"
```

---

### Task 5: `PixService.handle_webhook` + `api/webhooks.py` — thread `query_params`

**Files:**
- Modify: `backend/finacialsim_saas/pix/service.py:141,152`
- Modify: `backend/finacialsim_saas/api/webhooks.py:23-27`
- Test: extend `backend/tests/test_pix_service.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_pix_service.py` (add `MagicMock` to the existing `unittest.mock` import — change `from unittest.mock import AsyncMock` to `from unittest.mock import AsyncMock, MagicMock` — and add `from finacialsim_saas.pix.protocol import WebhookEvent` to the protocol import line, making it `from finacialsim_saas.pix.protocol import PayerInfo, PixChargeData, WebhookEvent`):

```python
@pytest.mark.asyncio
async def test_handle_webhook_threads_query_params_to_provider(pix_setup):
    provider = _mock_provider()
    provider.verify_webhook = MagicMock(
        return_value=WebhookEvent(txid="no-such-txid", status="paid", paid_amount=Decimal("10"))
    )
    svc = PixService(pix_setup["session"], provider, _mock_storage())
    headers = {"Content-Type": "application/json"}
    query_params = {"hmac": "shared-secret-token", "ignorar": ""}
    body = b'{"pix": [{"txid": "no-such-txid", "valor": "10.00"}]}'

    await svc.handle_webhook(headers, query_params, body)

    provider.verify_webhook.assert_called_once_with(headers, query_params, body)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_pix_service.py::test_handle_webhook_threads_query_params_to_provider -v`
Expected: FAIL with `TypeError: PixService.handle_webhook() takes 3 positional arguments but 4 were given`

- [ ] **Step 3: Write minimal implementation**

In `backend/finacialsim_saas/pix/service.py`, change line 141:

```python
    async def handle_webhook(self, headers: dict[str, str], query_params: dict[str, str], body: bytes) -> None:
```

And change line 152:

```python
            event = self._provider.verify_webhook(headers, query_params, body)
```

In `backend/finacialsim_saas/api/webhooks.py`, replace lines 23-27:

```python
    body = await request.body()
    headers = dict(request.headers)
    settings = get_settings()
    svc = PixService(session, get_pix_provider(settings), get_storage_backend(settings))
    await svc.handle_webhook(headers, body)
```

with:

```python
    body = await request.body()
    headers = dict(request.headers)
    query_params = dict(request.query_params)
    settings = get_settings()
    svc = PixService(session, get_pix_provider(settings), get_storage_backend(settings))
    await svc.handle_webhook(headers, query_params, body)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_pix_service.py::test_handle_webhook_threads_query_params_to_provider tests/test_portal_endpoints_smoke.py::test_webhook_pix_always_200 -v`
Expected: PASS (2 passed) — the existing smoke test keeps passing because `dict(request.query_params)` is `{}` when no query string is posted, threaded through harmlessly

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/pix/service.py backend/finacialsim_saas/api/webhooks.py backend/tests/test_pix_service.py
git commit -m "feat: thread webhook query_params from FastAPI request through PixService to provider"
```

---

### Task 6: `EfiPixProvider` — `__init__` + `create_charge`

**Files:**
- Create: `backend/finacialsim_saas/pix/efi.py`
- Test: Create `backend/tests/test_efi_pix_provider.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_efi_pix_provider.py`:

```python
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from finacialsim_saas.errors import ValidationError
from finacialsim_saas.pix.protocol import PayerInfo, PixChargeData
from finacialsim_saas.settings import Settings

UTC = timezone.utc


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


def _charge_response(**overrides) -> dict:
    base = {
        "txid": "abc123",
        "pixCopiaECola": "00020126brcode...",
        "loc": {"id": 9876},
        "calendario": {"criacao": "2026-06-07T12:00:00.000Z", "expiracao": 1800},
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_create_charge_sends_correct_request_shape_and_maps_response():
    from finacialsim_saas.pix.efi import EfiPixProvider

    client = MagicMock()
    client.pix_create_charge.return_value = _charge_response()
    client.pix_generate_qrcode.return_value = {"imagemQrcode": _qrcode_payload()}

    provider = EfiPixProvider(_settings(), client=client)
    payer = PayerInfo(document="12345678909", document_type="cpf", name="Maria Silva")

    result = await provider.create_charge(
        txid="abc123", amount=Decimal("1987.34"), expires_in=1800,
        description="Parcela 1", payer=payer,
    )

    client.pix_create_charge.assert_called_once_with(
        params={"txid": "abc123"},
        body={
            "calendario": {"expiracao": 1800},
            "valor": {"original": "1987.34"},
            "chave": "11111111-2222-3333-4444-555555555555",
            "solicitacaoPagador": "Parcela 1",
            "devedor": {"cpf": "12345678909", "nome": "Maria Silva"},
        },
    )
    client.pix_generate_qrcode.assert_called_once_with(params={"id": 9876})
    assert isinstance(result, PixChargeData)
    assert result.txid == "abc123"
    assert result.brcode == "00020126brcode..."
    assert result.qr_png_bytes == b"PNGDATA"
    assert result.amount == Decimal("1987.34")
    assert result.expires_at == datetime(2026, 6, 7, 12, 0, tzinfo=UTC) + timedelta(seconds=1800)


@pytest.mark.asyncio
async def test_create_charge_omits_devedor_when_payer_is_none():
    from finacialsim_saas.pix.efi import EfiPixProvider

    client = MagicMock()
    client.pix_create_charge.return_value = _charge_response()
    client.pix_generate_qrcode.return_value = {"imagemQrcode": _qrcode_payload()}
    provider = EfiPixProvider(_settings(), client=client)

    await provider.create_charge(
        txid="abc123", amount=Decimal("100"), expires_in=1800,
        description="x", payer=None,
    )

    _, kwargs = client.pix_create_charge.call_args
    assert "devedor" not in kwargs["body"]


@pytest.mark.asyncio
async def test_create_charge_translates_sdk_errors_to_validation_error():
    from finacialsim_saas.pix.efi import EfiPixProvider

    client = MagicMock()
    client.pix_create_charge.side_effect = RuntimeError("efi unreachable")
    provider = EfiPixProvider(_settings(), client=client)

    with pytest.raises(ValidationError, match="Não foi possível gerar o PIX"):
        await provider.create_charge(
            txid="abc123", amount=Decimal("100"), expires_in=1800,
            description="x", payer=None,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_efi_pix_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'finacialsim_saas.pix.efi'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/finacialsim_saas/pix/efi.py`:

```python
from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from efipay import EfiPay
from loguru import logger

from finacialsim_saas.errors import ValidationError
from finacialsim_saas.pix.protocol import PayerInfo, PixChargeData, WebhookEvent
from finacialsim_saas.settings import Settings

UTC = timezone.utc


class EfiPixProvider:
    name = "efi"  # matches pix_provider selector value (renamed from generic "external" — see deps.py)

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
        expires_in: int,
        description: str,
        payer: PayerInfo | None,
    ) -> PixChargeData:
        body: dict[str, Any] = {
            "calendario": {"expiracao": expires_in},
            "valor": {"original": str(amount)},
            "chave": self._pix_key,
            "solicitacaoPagador": description,
        }
        if payer is not None:
            body["devedor"] = {payer.document_type: payer.document, "nome": payer.name}

        try:
            charge_resp = await asyncio.to_thread(
                self._client.pix_create_charge, params={"txid": txid}, body=body
            )
            qr_resp = await asyncio.to_thread(
                self._client.pix_generate_qrcode, params={"id": charge_resp["loc"]["id"]}
            )
        except Exception as exc:
            logger.error("efi create_charge failed for txid={}: {}", txid, exc)
            raise ValidationError("Não foi possível gerar o PIX no momento, tente novamente") from exc

        qr_b64 = qr_resp["imagemQrcode"].removeprefix("data:image/png;base64,")
        criacao = datetime.fromisoformat(charge_resp["calendario"]["criacao"])
        expiracao = charge_resp["calendario"]["expiracao"]

        return PixChargeData(
            txid=charge_resp["txid"],
            brcode=charge_resp["pixCopiaECola"],
            qr_png_bytes=base64.b64decode(qr_b64),
            amount=amount,
            expires_at=criacao + timedelta(seconds=expiracao),
            provider_payload=charge_resp,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_efi_pix_provider.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/pix/efi.py backend/tests/test_efi_pix_provider.py
git commit -m "feat: implement EfiPixProvider.create_charge against efipay SDK"
```

---

### Task 7: `EfiPixProvider.cancel_charge`

**Files:**
- Modify: `backend/finacialsim_saas/pix/efi.py`
- Test: extend `backend/tests/test_efi_pix_provider.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_efi_pix_provider.py`:

```python
@pytest.mark.asyncio
async def test_cancel_charge_sends_remocao_status_patch():
    from finacialsim_saas.pix.efi import EfiPixProvider

    client = MagicMock()
    client.pix_update_charge.return_value = {"status": "REMOVIDA_PELO_USUARIO_RECEBEDOR"}
    provider = EfiPixProvider(_settings(), client=client)

    await provider.cancel_charge("abc123")

    client.pix_update_charge.assert_called_once_with(
        params={"txid": "abc123"},
        body={"status": "REMOVIDA_PELO_USUARIO_RECEBEDOR"},
    )


@pytest.mark.asyncio
async def test_cancel_charge_swallows_provider_errors():
    """Matches PixService.cancel_charges_for_proposal's best-effort contract (service.py:319-322)."""
    from finacialsim_saas.pix.efi import EfiPixProvider

    client = MagicMock()
    client.pix_update_charge.side_effect = RuntimeError("efi unreachable")
    provider = EfiPixProvider(_settings(), client=client)

    await provider.cancel_charge("abc123")  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_efi_pix_provider.py -k cancel_charge -v`
Expected: FAIL with `AttributeError: 'EfiPixProvider' object has no attribute 'cancel_charge'`

- [ ] **Step 3: Write minimal implementation**

In `backend/finacialsim_saas/pix/efi.py`, add this method to `EfiPixProvider` (after `create_charge`):

```python
    async def cancel_charge(self, txid: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.pix_update_charge,
                params={"txid": txid},
                body={"status": "REMOVIDA_PELO_USUARIO_RECEBEDOR"},
            )
        except Exception as exc:
            logger.warning("efi cancel_charge failed for txid={}: {}", txid, exc)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_efi_pix_provider.py -k cancel_charge -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/pix/efi.py backend/tests/test_efi_pix_provider.py
git commit -m "feat: implement EfiPixProvider.cancel_charge with best-effort error swallowing"
```

---

### Task 8: `EfiPixProvider.verify_webhook`

**Files:**
- Modify: `backend/finacialsim_saas/pix/efi.py`
- Test: extend `backend/tests/test_efi_pix_provider.py`

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


def test_verify_webhook_accepts_matching_hmac_token_and_maps_real_efi_shape():
    from finacialsim_saas.pix.efi import EfiPixProvider

    provider = EfiPixProvider(_settings(pix_webhook_secret="shared-secret"), client=MagicMock())

    event = provider.verify_webhook(
        headers={}, query_params={"hmac": "shared-secret", "ignorar": ""},
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
Expected: FAIL with `AttributeError: 'EfiPixProvider' object has no attribute 'verify_webhook'`

- [ ] **Step 3: Write minimal implementation**

In `backend/finacialsim_saas/pix/efi.py`, add `hmac` and `json` to the top-level imports (alongside `asyncio`/`base64`):

```python
import asyncio
import base64
import hmac
import json
```

Add this method to `EfiPixProvider` (after `cancel_charge`):

```python
    def verify_webhook(self, headers: dict, query_params: dict, body: bytes) -> WebhookEvent:
        """Efí doesn't HMAC-sign the body — it echoes a static token in the callback URL's
        query string instead (`?hmac=<token>&ignorar=`, registered via `register_webhook`).
        Skip-mTLS mode (§3): this token IS the security boundary, constant-time compared."""
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
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/pix/efi.py backend/tests/test_efi_pix_provider.py
git commit -m "feat: implement EfiPixProvider.verify_webhook with hmac query-token validation"
```

---

### Task 9: `pix/deps.py` — wire `efi`, cached singleton, startup guards; remove stub

**Files:**
- Modify: `backend/finacialsim_saas/pix/deps.py`
- Modify: `backend/finacialsim_saas/api/pix_admin.py:41`
- Delete: `backend/finacialsim_saas/pix/stub.py`
- Test: Create `backend/tests/test_pix_deps.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_pix_deps.py`:

```python
from __future__ import annotations

import pytest

from finacialsim_saas.pix import deps as pix_deps
from finacialsim_saas.settings import Settings


def _settings(**overrides) -> Settings:
    base: dict = dict(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        pix_provider="fake",
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture(autouse=True)
def _reset_efi_singleton(monkeypatch):
    monkeypatch.setattr(pix_deps, "_efi_provider", None)


def test_external_provider_value_no_longer_supported():
    """Selector rename fake|external -> fake|efi (spec §4) — "external" must now raise."""
    with pytest.raises(ValueError, match="Unknown PIX_PROVIDER"):
        pix_deps.get_pix_provider(_settings(pix_provider="external"))


def test_efi_provider_requires_settings_to_be_set():
    settings = _settings(
        pix_provider="efi",
        efi_client_id="", efi_client_secret="x", efi_certificate_path="/no/file", efi_pix_key="key",
    )
    with pytest.raises(ValueError, match="EFI_CLIENT_ID"):
        pix_deps.get_pix_provider(settings)


def test_efi_provider_requires_certificate_file_to_exist():
    settings = _settings(
        pix_provider="efi",
        efi_client_id="id", efi_client_secret="secret",
        efi_certificate_path="/no/such/file.pem", efi_pix_key="key",
    )
    with pytest.raises(ValueError, match="does not exist"):
        pix_deps.get_pix_provider(settings)


def test_efi_provider_is_cached_as_singleton(monkeypatch, tmp_path):
    cert = tmp_path / "efi.pem"
    cert.write_text("cert")
    settings = _settings(
        pix_provider="efi",
        efi_client_id="id", efi_client_secret="secret",
        efi_certificate_path=str(cert), efi_pix_key="key",
    )

    constructed = []

    class _FakeEfiProvider:
        name = "efi"

        def __init__(self, settings):
            constructed.append(settings)

    monkeypatch.setattr(pix_deps, "EfiPixProvider", _FakeEfiProvider)

    first = pix_deps.get_pix_provider(settings)
    second = pix_deps.get_pix_provider(settings)

    assert first is second
    assert len(constructed) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_pix_deps.py -v`
Expected: FAIL —
- `test_external_provider_value_no_longer_supported`: `Failed: DID NOT RAISE` (still returns `StubExternalPixProvider`)
- `test_efi_provider_requires_settings_to_be_set` / `..._certificate_file_to_exist`: `ValueError: Unknown PIX_PROVIDER: 'efi'` (wrong message — `efi` isn't wired yet)
- `test_efi_provider_is_cached_as_singleton`: `AttributeError: <module 'finacialsim_saas.pix.deps'> does not have the attribute 'EfiPixProvider'`

- [ ] **Step 3: Write minimal implementation**

Replace the entire contents of `backend/finacialsim_saas/pix/deps.py`:

```python
from __future__ import annotations

from pathlib import Path

from finacialsim_saas.pix.efi import EfiPixProvider
from finacialsim_saas.pix.fake import InMemoryFakePixProvider
from finacialsim_saas.pix.protocol import PixProvider
from finacialsim_saas.settings import Settings

# Cached singleton for the `efi` branch only — EfiPixProvider.__init__ builds an EfiPay
# client that reads a cert from disk and authenticates with Efí's OAuth2 token endpoint;
# constructing it fresh per-request (as fake/stub do today, harmlessly) would multiply
# auth calls on every charge/cancel/admin-check/webhook and risk throttling. Not lru_cache
# on get_pix_provider itself — that would also wrongly cache fake/stub across test settings.
_efi_provider: EfiPixProvider | None = None


def _validate_efi_settings(settings: Settings) -> None:
    missing = [
        name for name, value in (
            ("EFI_CLIENT_ID", settings.efi_client_id),
            ("EFI_CLIENT_SECRET", settings.efi_client_secret),
            ("EFI_CERTIFICATE_PATH", settings.efi_certificate_path),
            ("EFI_PIX_KEY", settings.efi_pix_key),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"PIX_PROVIDER=efi requires {', '.join(missing)} to be set")
    if not Path(settings.efi_certificate_path).exists():
        raise ValueError(f"EFI_CERTIFICATE_PATH does not exist: {settings.efi_certificate_path}")


def get_pix_provider(settings: Settings) -> PixProvider:
    global _efi_provider
    if settings.pix_provider == "fake":
        return InMemoryFakePixProvider(secret=settings.pix_webhook_secret)
    if settings.pix_provider == "efi":
        if _efi_provider is None:
            _validate_efi_settings(settings)
            _efi_provider = EfiPixProvider(settings)
        return _efi_provider
    raise ValueError(f"Unknown PIX_PROVIDER: {settings.pix_provider!r}")
```

Delete the now-superseded stub (its sole purpose — a placeholder for "real PSP wiring" — is fulfilled, and no test references it):

Run: `git rm backend/finacialsim_saas/pix/stub.py`

In `backend/finacialsim_saas/api/pix_admin.py`, change line 41 from:

```python
    if settings.pix_provider == "external":
```

to:

```python
    if settings.pix_provider != "fake":
```

(Semantically exact — "block the demo button whenever a real provider is active" — and stays correct if a third provider is ever added. No existing test covers this gate; it's a one-line mechanical rename per spec §4, not new behavior worth a fixture chain on its own.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_pix_deps.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/pix/deps.py backend/finacialsim_saas/api/pix_admin.py backend/tests/test_pix_deps.py
git commit -m "feat: wire EfiPixProvider into get_pix_provider with cached singleton and startup validation"
```

---

### Task 10: `main.py` lifespan — fail-fast Pix validation + sandbox-in-production warning

**Files:**
- Modify: `backend/finacialsim_saas/main.py:23-36`
- Test: Create `backend/tests/test_main_pix_startup.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_main_pix_startup.py`:

```python
from __future__ import annotations

from finacialsim_saas.settings import Settings


def _settings(**overrides) -> Settings:
    base: dict = dict(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        pix_provider="efi", app_env="production", efi_sandbox=True,
    )
    base.update(overrides)
    return Settings(**base)


def test_pix_sandbox_warning_fires_for_efi_sandbox_in_production():
    from finacialsim_saas.main import _pix_sandbox_warning

    warning = _pix_sandbox_warning(_settings())
    assert warning is not None
    assert "sandbox" in warning.lower()


def test_pix_sandbox_warning_silent_outside_efi_sandbox_production_combo():
    from finacialsim_saas.main import _pix_sandbox_warning

    assert _pix_sandbox_warning(_settings(app_env="development")) is None
    assert _pix_sandbox_warning(_settings(efi_sandbox=False)) is None
    assert _pix_sandbox_warning(_settings(pix_provider="fake")) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_main_pix_startup.py -v`
Expected: FAIL with `ImportError: cannot import name '_pix_sandbox_warning' from 'finacialsim_saas.main'`

- [ ] **Step 3: Write minimal implementation**

In `backend/finacialsim_saas/main.py`, add this function after the `app_state` declaration (after line 18):

```python
def _pix_sandbox_warning(settings) -> str | None:
    """A real-PSP-in-sandbox-in-production combo silently lands charges in Efí's sandbox —
    customers think they paid, nothing shows up in the real account. Loud warning, not a
    hard stop (a legitimate staged-rollout could legitimately hit this combination)."""
    if settings.pix_provider == "efi" and settings.app_env == "production" and settings.efi_sandbox:
        return (
            "PIX_PROVIDER=efi with EFI_SANDBOX=true in production — Pix charges will land "
            "in Efí's sandbox; customers will think they paid and nothing will show up in "
            "the real account. This is almost certainly a misconfiguration."
        )
    return None
```

In the `lifespan` function, replace lines 33-35:

```python
    app.state.arq = await create_pool(ArqRedisSettings.from_dsn(str(settings.redis_url)))
    logger.info("startup", env=settings.app_env, sha=settings.git_sha)
    yield
```

with:

```python
    app.state.arq = await create_pool(ArqRedisSettings.from_dsn(str(settings.redis_url)))

    from finacialsim_saas.pix.deps import get_pix_provider
    get_pix_provider(settings)  # fail fast on efi misconfiguration — not on the first charge
    sandbox_warning = _pix_sandbox_warning(settings)
    if sandbox_warning:
        logger.warning(sandbox_warning)

    logger.info("startup", env=settings.app_env, sha=settings.git_sha)
    yield
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_main_pix_startup.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/main.py backend/tests/test_main_pix_startup.py
git commit -m "feat: validate Pix provider at startup and warn on efi sandbox-in-production"
```

---

### Task 11: CLI `pix register-webhook` + `EfiPixProvider.register_webhook`

**Files:**
- Create: `backend/finacialsim_saas/cli/pix_cli.py`
- Modify: `backend/finacialsim_saas/cli/main.py:28-32`
- Modify: `backend/finacialsim_saas/pix/efi.py`
- Test: extend `backend/tests/test_cli.py` and `backend/tests/test_efi_pix_provider.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_efi_pix_provider.py`:

```python
@pytest.mark.asyncio
async def test_register_webhook_sends_url_with_skip_mtls_header():
    from finacialsim_saas.pix.efi import EfiPixProvider

    client = MagicMock()
    client.pix_config_webhook.return_value = {"webhookUrl": "https://app.test/api/v1/webhooks/pix?hmac=secret&ignorar="}
    provider = EfiPixProvider(_settings(), client=client)

    await provider.register_webhook("https://app.test/api/v1/webhooks/pix?hmac=secret&ignorar=")

    client.pix_config_webhook.assert_called_once_with(
        params={"chave": "11111111-2222-3333-4444-555555555555"},
        body={"webhookUrl": "https://app.test/api/v1/webhooks/pix?hmac=secret&ignorar="},
        headers={"x-skip-mtls-checking": "true"},
    )
```

Append to `backend/tests/test_cli.py`:

```python
def test_pix_register_webhook_builds_url_and_calls_provider(runner, monkeypatch):
    from finacialsim_saas.cli import pix_cli
    from finacialsim_saas.settings import Settings

    test_settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        pix_provider="efi", pix_webhook_secret="test-secret",
        frontend_base_url="https://app.test",
    )
    monkeypatch.setattr(pix_cli, "get_settings", lambda: test_settings)

    registered = {}

    class _FakeProvider:
        def __init__(self, settings):
            pass

        async def register_webhook(self, url):
            registered["url"] = url

    monkeypatch.setattr(pix_cli, "EfiPixProvider", _FakeProvider)

    from finacialsim_saas.cli.main import app
    result = runner.invoke(app, ["pix", "register-webhook"])

    assert result.exit_code == 0, result.output
    assert registered["url"] == "https://app.test/api/v1/webhooks/pix?hmac=test-secret&ignorar="
    assert "Webhook registered" in result.output


def test_pix_register_webhook_rejects_non_efi_provider(runner, monkeypatch):
    from finacialsim_saas.cli import pix_cli
    from finacialsim_saas.settings import Settings

    test_settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        pix_provider="fake",
    )
    monkeypatch.setattr(pix_cli, "get_settings", lambda: test_settings)

    from finacialsim_saas.cli.main import app
    result = runner.invoke(app, ["pix", "register-webhook"])

    assert result.exit_code != 0
    assert "PIX_PROVIDER is not 'efi'" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_efi_pix_provider.py::test_register_webhook_sends_url_with_skip_mtls_header tests/test_cli.py -k pix_register -v`
Expected: FAIL —
- `test_register_webhook_sends_url_with_skip_mtls_header`: `AttributeError: 'EfiPixProvider' object has no attribute 'register_webhook'`
- both CLI tests: `ModuleNotFoundError: No module named 'finacialsim_saas.cli.pix_cli'`

- [ ] **Step 3: Write minimal implementation**

In `backend/finacialsim_saas/pix/efi.py`, add this method to `EfiPixProvider` (after `verify_webhook`):

```python
    async def register_webhook(self, url: str) -> None:
        """PUT /v2/webhook/:chave — idempotent. Skip-mTLS mode (§3) requires this header
        on registration, or Efí defaults to mTLS validation, which the Caddy proxy can't satisfy."""
        await asyncio.to_thread(
            self._client.pix_config_webhook,
            params={"chave": self._pix_key},
            body={"webhookUrl": url},
            headers={"x-skip-mtls-checking": "true"},
        )
```

Create `backend/finacialsim_saas/cli/pix_cli.py`:

```python
from __future__ import annotations

import asyncio

import typer

from finacialsim_saas.pix.efi import EfiPixProvider
from finacialsim_saas.settings import get_settings

pix_app = typer.Typer(help="Pix PSP management commands")


@pix_app.command("register-webhook")
def pix_register_webhook():
    """Registers (or re-registers) the Pix webhook callback URL with Efí. Idempotent (PUT)."""
    settings = get_settings()
    if settings.pix_provider != "efi":
        typer.echo("Error: PIX_PROVIDER is not 'efi'.", err=True)
        raise typer.Exit(1)

    url = (
        f"{settings.frontend_base_url}/api/v1/webhooks/pix"
        f"?hmac={settings.pix_webhook_secret}&ignorar="
    )

    async def _register():
        provider = EfiPixProvider(settings)
        await provider.register_webhook(url)

    asyncio.run(_register())
    typer.echo(f"Webhook registered: {url}")
```

In `backend/finacialsim_saas/cli/main.py`, replace lines 28-32:

```python
from finacialsim_saas.cli.db import db_app
from finacialsim_saas.cli.notifications_cli import notifications_app

app.add_typer(db_app, name="db")
app.add_typer(notifications_app, name="notifications")
```

with:

```python
from finacialsim_saas.cli.db import db_app
from finacialsim_saas.cli.notifications_cli import notifications_app
from finacialsim_saas.cli.pix_cli import pix_app

app.add_typer(db_app, name="db")
app.add_typer(notifications_app, name="notifications")
app.add_typer(pix_app, name="pix")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_efi_pix_provider.py::test_register_webhook_sends_url_with_skip_mtls_header tests/test_cli.py -k pix_register -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/pix/efi.py backend/finacialsim_saas/cli/pix_cli.py backend/finacialsim_saas/cli/main.py backend/tests/test_efi_pix_provider.py backend/tests/test_cli.py
git commit -m "feat: add pix register-webhook CLI command and EfiPixProvider.register_webhook"
```

---

### Task 12: Setup runbook doc

**Files:**
- Create: `docs/agents/efi-pix-setup.md`

- [ ] **Step 1: Write the runbook**

Create `docs/agents/efi-pix-setup.md`:

```markdown
# Efí Pix provider setup

One-time runbook for wiring the real `EfiPixProvider` into a deployment — sandbox account
through go-live verification. Run `pix register-webhook` (step 5) again whenever the domain
or `PIX_WEBHOOK_SECRET` changes (env migration, secret rotation) — it's idempotent (`PUT`).

## 1. Create an Efí sandbox account

Sign up for Efí's "homologação" (sandbox) environment via their developer portal and
register a Pix key (`chave Pix`) for the recipient account. This becomes `EFI_PIX_KEY`.

## 2. Generate and convert the mTLS certificate

Download the `.p12` certificate from Efí's dashboard and convert it to `.pem` — the
`efipay` SDK expects `.pem`:

```bash
openssl pkcs12 -in certificado.p12 -out certificado.pem -nodes -password pass:""
```

## 3. Mount the certificate into the container

`EFI_CERTIFICATE_PATH` is an in-container path — the file must be bind-mounted there.
`ops/docker-compose.yml` already follows this pattern for `PDF_OUTPUT_DIR` (the
`worker`/`api` services pair an env var pointing at `/var/lib/finacialsim/pdfs` with
`volumes: pdf-store:/var/lib/finacialsim/pdfs`). Mirror it for the cert on **both**
`api` and `worker` (both construct `EfiPixProvider` — `worker` at startup via
`pix.deps.get_pix_provider`, `api` on the first Pix-related request):

```yaml
environment:
  EFI_CERTIFICATE_PATH: /var/lib/finacialsim/certs/efi.pem
volumes:
  - ./certs/efi.pem:/var/lib/finacialsim/certs/efi.pem:ro
```

## 4. Populate `.env`

```env
EFI_CLIENT_ID=...
EFI_CLIENT_SECRET=...
EFI_CERTIFICATE_PATH=/var/lib/finacialsim/certs/efi.pem
EFI_PIX_KEY=11111111-2222-3333-4444-555555555555
EFI_SANDBOX=true
PIX_PROVIDER=efi
```

The app refuses to boot with `PIX_PROVIDER=efi` if any `EFI_*` setting is empty or the
certificate file doesn't exist (`pix/deps.py`'s startup guard) — fix `.env` and restart
rather than chasing a runtime 500 on the first customer's "Pagar com Pix" click.

## 5. Register the webhook

```bash
uv run finacialsim-saas pix register-webhook
```

Registers `PUT /v2/webhook/:chave` with
`webhookUrl: "<frontend_base_url>/api/v1/webhooks/pix?hmac=<PIX_WEBHOOK_SECRET>&ignorar="`
and header `x-skip-mtls-checking: true` (required to register skip-mTLS mode — omitting
it risks Efí defaulting to mTLS validation, which the Caddy proxy can't satisfy, silently
breaking webhook delivery).

## 6. Verify webhook delivery — don't skip this

The `?hmac=...&ignorar=` URL trick (which prevents Efí from appending `/pix` to the
registered URL) is sourced from a community forum post, not Efí's official docs. If it
behaves differently than described, the webhook silently 404s — Efí retries up to 9
times, then gives up, and "payment confirmation just doesn't happen" is brutal to debug
post-launch.

After registering, Efí sends an automatic test notification. Check **Efí's dashboard
delivery log** for the actual URL/path it called. If it doesn't match
`/api/v1/webhooks/pix`, adjust the registered URL (with/without the trailing `/pix`,
with/without `?ignorar=`) and re-run step 5.

## 7. Manual smoke test

1. Create a sandbox charge — e.g. via "Pagar com Pix" on a proposal with a linked client
   (a clientless proposal is now blocked by design — see §2a in the design spec).
2. Pay it with Efí's sandbox payment simulator. **Sandbox charges ≤ R$10.01 auto-confirm**
   — keep the test amount under that.
3. Confirm the webhook fires: the parcela flips to `paid`, and `pix_webhook_events` /
   `audit_logs` rows are created (check the admin UI or query the tables directly).

## Hardening deferred to a later phase

Phase 1 ships skip-mTLS + hmac-token validation only (`pix/efi.py:verify_webhook`) — no
IP allowlist, no mTLS handshake. Both depend on reverse-proxy/cert-handling infrastructure
this project doesn't have configured (the Caddy proxy doesn't expose a trustworthy
`request.client`/`X-Forwarded-For`). Revisit when that infrastructure exists.
```

- [ ] **Step 2: Review against the design spec checklist**

Confirm the doc covers all 7 points from `docs/superpowers/specs/2026-06-07-efi-pix-provider-design.md` §6:
sandbox account + Pix key (1), `.p12`→`.pem` conversion (2), Docker volume mount (3),
`.env` population (4), `pix register-webhook` (5), webhook delivery verification (6),
manual smoke-test checklist incl. the ≤R$10.01 auto-confirm note (7).

- [ ] **Step 3: Commit**

```bash
git add docs/agents/efi-pix-setup.md
git commit -m "docs: add Efí Pix provider setup runbook"
```

---

## Self-Review

**1. Spec coverage** — every in-scope section of the design spec maps to a task:
- §1 `EfiPixProvider` (`create_charge`, `cancel_charge`) → Tasks 6, 7
- §1 `efipay` dependency → Task 1
- §2a `PayerInfo` + Protocol signature + clientless guard → Tasks 2, 4
- §2b webhook `query_params` (Protocol, fake, service, endpoint) → Tasks 2, 3, 5
- §3 skip-mTLS `verify_webhook` (hmac query token) → Task 8
- §4 new `efi_*` settings, selector rename `fake|external`→`fake|efi`, cached singleton, `pix_admin.py` gate, startup guards → Tasks 1, 9, 10
- §5 `pix register-webhook` CLI + `register_webhook` → Task 11
- §6 setup runbook → Task 12
- "Tests" checklist (`EfiPixProvider` request/response shape, `cancel_charge` PATCH + swallow, `verify_webhook` token + real-shaped payload, `PayerInfo`/guard in `PixService`, CLI URL assertion) → Tasks 4, 6, 7, 8, 11

**2. Placeholder scan** — every code block is complete and runnable; no `TBD`/`...`/"similar to Task N". The one deliberate omission (`pix_admin.py` gate rename has no dedicated test) is explicitly justified inline in Task 9 rather than hand-waved.

**3. Type/signature consistency** — traced through every task:
- `PayerInfo(document, document_type, name)` — defined in Task 2, constructed identically in Task 4 (`PixService`) and Task 6 (test fixtures), consumed identically in Task 6 (`EfiPixProvider.create_charge`'s `devedor` mapping)
- `create_charge(*, txid, amount, expires_in, description, payer: PayerInfo | None)` — Protocol (Task 2), `fake` (Task 3), `service.py` call site (Task 4), `EfiPixProvider` (Task 6) all match
- `verify_webhook(headers, query_params, body)` — Protocol (Task 2), `fake` (Task 3), `service.py` (Task 5), `EfiPixProvider` (Task 8) all match
- `EfiPixProvider(settings, client=None)` constructor-injection shape used consistently across Tasks 6-9, 11
- `_efi_provider`/`_validate_efi_settings`/`get_pix_provider` names in Task 9 match the assertions in `test_pix_deps.py`
- `_pix_sandbox_warning` name/signature in Task 10 matches its test
- `pix_app`/`pix_register_webhook` names in Task 11 match `main.py`'s `add_typer` call and the CLI test's `runner.invoke(app, ["pix", "register-webhook"])`

No gaps found.

---

**Plan complete and saved to `docs/superpowers/plans/2026-06-07-efi-pix-provider.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
