# Efí Pix Provider — Part 2: Service Layer (Tasks 5–6)

> Part of the [Phase 1 plan](2026-06-07-efi-pix-provider.md). Tasks 5–6: `_ensure_charge` shared core + `create_charge_for_parcela` wrapper; `handle_webhook` `query_params` threading.

---

### Task 5: `PixService._ensure_charge` + `create_charge_for_parcela` rewrite

**Files:**

- Modify: `backend/finacialsim_saas/pix/service.py:13-20,44-139`
- Test: Create `backend/tests/test_pix_service.py`

**Why:** `create_charge_for_parcela` currently monolithically contains the charge-creation logic. Phase 2's cron (`docs/superpowers/specs/2026-06-07-pix-cobranca-automatica-design.md`) needs to call that same logic without triggering the customer `pix_link` notification. Extracting `_ensure_charge` as a shared idempotent core returning `(charge, created)` — mirroring Django's `get_or_create` — gives both entry points exactly what they need with zero duplication.

`_ensure_charge` also moves the clientless-proposal guard (spec §2b) — a charge needs a payer; this applies equally to the cron.

- [ ] **Step 1: Write the tests**

Create `backend/tests/test_pix_service.py`:

```python
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

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
        expires_at=datetime(2026, 10, 31, tzinfo=UTC),
    )
    return provider


def _mock_storage() -> AsyncMock:
    storage = AsyncMock()
    storage.put.return_value = None
    storage.signed_url.return_value = "https://storage.test/signed"
    return storage


async def _seed_proposal_chain(session, tenant, admin_id, *, client_id, vencimento=None):
    if vencimento is None:
        vencimento = date.today() + timedelta(days=30)
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
        vencimento=vencimento,
        valor_parcela=Decimal("14000"), status=ParcelaPaymentStatus.open,
    )
    session.add(parcela)
    await session.commit()
    return parcela


@pytest_asyncio.fixture
async def pix_setup(session: AsyncSession):
    """Tenant + admin + client + customer user + confirmed sim + approved proposal +
    open parcela due 2026-09-01 (2026-09-01 + 60 days = 2026-10-31, the deterministic
    BRT-formula assertion target)."""
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

    parcela = await _seed_proposal_chain(
        session, tenant, admin.id, client_id=client.id, vencimento=date(2026, 9, 1)
    )

    admin_ctx = RequestContext(user_id=admin.id, tenant_id=tenant.id, role=Role.admin, iat=0.0)
    customer_user = await svc.invite_customer(client.id, admin_ctx)
    await session.commit()

    return {
        "session": session, "ctx": admin_ctx, "tenant": tenant, "admin_id": admin.id,
        "client": client, "customer_user": customer_user, "parcela": parcela,
    }


@pytest.mark.asyncio
async def test_ensure_charge_builds_payer_info_from_linked_client(pix_setup):
    provider = _mock_provider()
    svc = PixService(pix_setup["session"], provider, _mock_storage())

    await svc._ensure_charge(pix_setup["parcela"])

    _, kwargs = provider.create_charge.call_args
    assert kwargs["payer"] == PayerInfo(document="12345678909", document_type="cpf", name="Maria Silva")


@pytest.mark.asyncio
async def test_ensure_charge_threads_due_date_and_validity_days_from_rule(pix_setup):
    """_ensure_charge must pass due_date/validity_days, never expires_in (Cob concept)."""
    provider = _mock_provider()
    svc = PixService(pix_setup["session"], provider, _mock_storage())

    await svc._ensure_charge(pix_setup["parcela"])

    _, kwargs = provider.create_charge.call_args
    assert kwargs["due_date"] == date(2026, 9, 1)
    assert kwargs["validity_days"] == 60   # pix_validade_apos_vencimento_dias default
    assert "expires_in" not in kwargs


@pytest.mark.asyncio
async def test_ensure_charge_blocks_when_proposal_has_no_linked_client(pix_setup):
    """§2b guard — fires before provider.create_charge; applies to fake/efi/cron alike."""
    parcela = await _seed_proposal_chain(
        pix_setup["session"], pix_setup["tenant"], pix_setup["admin_id"], client_id=None
    )
    provider = _mock_provider()
    svc = PixService(pix_setup["session"], provider, _mock_storage())

    with pytest.raises(ValidationError, match="não é possível gerar Pix sem cliente vinculado"):
        await svc._ensure_charge(parcela)

    provider.create_charge.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_charge_reuses_existing_pending_charge_without_calling_provider(pix_setup):
    provider = _mock_provider()
    svc = PixService(pix_setup["session"], provider, _mock_storage())

    first, created_first = await svc._ensure_charge(pix_setup["parcela"])
    second, created_second = await svc._ensure_charge(pix_setup["parcela"])

    assert created_first is True
    assert created_second is False
    assert first.id == second.id
    provider.create_charge.assert_called_once()


@pytest.mark.asyncio
async def test_create_charge_for_parcela_sends_pix_link_only_on_fresh_creation(pix_setup):
    """Notification fires on first call (created=True), not on idempotent reuse (created=False).
    This test PASSES against the current code too — it's a regression-pin for the refactor,
    locking in pre-existing behavior so the _ensure_charge extraction can't silently break it."""
    provider = _mock_provider()
    svc = PixService(pix_setup["session"], provider, _mock_storage())

    with patch("finacialsim_saas.notifications.service.NotificationService") as MockNotif:
        mock_enqueue = AsyncMock()
        MockNotif.return_value.enqueue = mock_enqueue

        await svc.create_charge_for_parcela(pix_setup["parcela"].id, pix_setup["ctx"])
        await svc.create_charge_for_parcela(pix_setup["parcela"].id, pix_setup["ctx"])

        assert mock_enqueue.call_count == 1
```

- [ ] **Step 2: Run tests to verify expected failure state**

Run: `cd backend && uv run pytest tests/test_pix_service.py -v`
Expected:
- `test_ensure_charge_*` (4 tests): FAIL — `AttributeError: 'PixService' object has no attribute '_ensure_charge'`
- `test_create_charge_for_parcela_sends_pix_link_only_on_fresh_creation`: PASS already (it's a characterization test, see docstring — confirm it's green now, must stay green after Step 3)

- [ ] **Step 3: Write minimal implementation**

In `backend/finacialsim_saas/pix/service.py`, replace the import block (lines 13-20):

```python
from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import (
    AuditLog, ParcelaPayment, ParcelaPaymentStatus, PixCharge,
    PixChargeStatus, PixWebhookEvent, Proposal, Role, Simulation, User,
)
from finacialsim_saas.errors import NotFoundError, ValidationError
from finacialsim_saas.pix.protocol import PixProvider
from finacialsim_saas.storage import StorageBackend
```

with:

```python
from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import (
    AuditLog, Client, ClientType, ParcelaPayment, ParcelaPaymentStatus, PixCharge,
    PixChargeStatus, PixWebhookEvent, Proposal, Role, Simulation, User,
)
from finacialsim_saas.errors import NotFoundError, ValidationError
from finacialsim_saas.pix.protocol import PayerInfo, PixProvider
from finacialsim_saas.services.rules_service import RulesService
from finacialsim_saas.storage import StorageBackend
```

Replace lines 44-139 (the entire `create_charge_for_parcela` method) with:

```python
    async def _ensure_charge(self, parcela: ParcelaPayment) -> tuple[PixCharge, bool]:
        """Idempotent: one CobV charge per parcela, ever.
        Returns (charge, created) — callers that notify only on fresh creation branch on it."""
        if parcela.last_pix_charge_id is not None:
            existing = await self._s.get(PixCharge, parcela.last_pix_charge_id)
            if existing is not None:
                await self._lazy_flip_expired(existing)
                if existing.status == PixChargeStatus.pending:
                    await self._s.flush()
                    return existing, False

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

        rules = await RulesService(self._s).get_rules(parcela.tenant_id)
        validity_days = int(rules["pix_validade_apos_vencimento_dias"])

        charge_id = uuid.uuid4()
        txid = str(charge_id).replace("-", "")[:35]

        charge_data = await self._provider.create_charge(
            txid=txid,
            amount=parcela.valor_parcela,
            due_date=parcela.vencimento,
            validity_days=validity_days,
            description=f"Parcela {parcela.parcela_num}",
            payer=payer,
        )

        qr_key = f"pix/{charge_id}/qr.png"
        await self._storage.put(qr_key, charge_data.qr_png_bytes, "image/png")

        now = datetime.now(UTC)
        charge = PixCharge(
            id=charge_id,
            tenant_id=parcela.tenant_id,
            parcela_payment_id=parcela.id,
            txid=txid,
            brcode=charge_data.brcode,
            qrcode_png_key=qr_key,
            amount=charge_data.amount,
            expires_at=charge_data.expires_at,
            status=PixChargeStatus.pending,
            provider_payload_json=charge_data.provider_payload,
            criado_em=now,
            atualizado_em=now,
        )
        self._s.add(charge)
        parcela.last_pix_charge_id = charge_id
        await self._s.commit()
        return charge, True

    async def create_charge_for_parcela(
        self, parcela_payment_id: uuid.UUID, ctx: RequestContext
    ) -> tuple[PixCharge, str]:
        """Customer/staff-facing entry point. Verifies ownership, delegates to
        _ensure_charge (idempotent), notifies only on fresh creation."""
        parcela = await self._s.get(ParcelaPayment, parcela_payment_id)
        if parcela is None or parcela.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"parcela payment {parcela_payment_id} not found")

        if ctx.client_id is not None:
            proposal = await self._s.get(Proposal, parcela.proposal_id)
            sim = await self._s.get(Simulation, proposal.simulation_id) if proposal else None
            if sim is None or sim.client_id != ctx.client_id:
                raise NotFoundError(f"parcela payment {parcela_payment_id} not found")

        if parcela.status not in (ParcelaPaymentStatus.open, ParcelaPaymentStatus.overdue):
            raise ValidationError("parcela must be open or overdue to pay")

        charge, created = await self._ensure_charge(parcela)
        qr_url = await self._storage.signed_url(charge.qrcode_png_key, expires_in=1800)

        if created:
            try:
                from finacialsim_saas.notifications.service import NotificationService
                proposal_obj = await self._s.get(Proposal, parcela.proposal_id)
                if proposal_obj is not None:
                    sim_obj = await self._s.get(Simulation, proposal_obj.simulation_id)
                    if sim_obj is not None and sim_obj.client_id is not None:
                        cu_result = await self._s.execute(
                            select(User).where(
                                User.client_id == sim_obj.client_id,
                                User.role == Role.customer,
                                User.is_active.is_(True),
                            )
                        )
                        customer = cu_result.scalar_one_or_none()
                        if customer and "@" in (customer.email or ""):
                            pix_url = await self._storage.signed_url(charge.qrcode_png_key, expires_in=1800)
                            await NotificationService(self._s).enqueue(
                                template_key="portal.pix_link",
                                payload={
                                    "user_name": customer.name,
                                    "valor_parcela": str(parcela.valor_parcela),
                                    "parcela_num": parcela.parcela_num,
                                    "pix_url": pix_url,
                                },
                                target_email=customer.email,
                                tenant_id=ctx.tenant_id,
                                idempotency_key=f"portal.pix_link:{parcela_payment_id}",
                            )
            except Exception as exc:
                logger.warning("pix_link notification failed", exc=str(exc))

        return charge, qr_url
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_pix_service.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/pix/service.py backend/tests/test_pix_service.py
git commit -m "feat: extract _ensure_charge shared idempotent core from create_charge_for_parcela"
```

---

### Task 6: `PixService.handle_webhook` + `api/webhooks.py` — thread `query_params`

**Files:**

- Modify: `backend/finacialsim_saas/pix/service.py` (`handle_webhook` signature + `verify_webhook` call)
- Modify: `backend/finacialsim_saas/api/webhooks.py:23-27`
- Test: extend `backend/tests/test_pix_service.py`

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_pix_service.py`:

1. Change `from unittest.mock import AsyncMock, patch` → `from unittest.mock import AsyncMock, MagicMock, patch`
2. Change `from finacialsim_saas.pix.protocol import PayerInfo, PixChargeData` → add `WebhookEvent`
3. Append this test:

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
Expected: FAIL — `TypeError: PixService.handle_webhook() takes 3 positional arguments but 4 were given`

- [ ] **Step 3: Write minimal implementation**

In `backend/finacialsim_saas/pix/service.py`, change the `handle_webhook` method signature (currently `async def handle_webhook(self, headers: dict[str, str], body: bytes) -> None:`):

```python
    async def handle_webhook(self, headers: dict[str, str], query_params: dict[str, str], body: bytes) -> None:
```

Change the `verify_webhook` call inside `handle_webhook` (currently `self._provider.verify_webhook(headers, body)`):

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
Expected: PASS (2 passed) — smoke test still passes because `dict(request.query_params)` is `{}` when no query string is posted

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/pix/service.py backend/finacialsim_saas/api/webhooks.py backend/tests/test_pix_service.py
git commit -m "feat: thread webhook query_params through PixService to provider"
```
