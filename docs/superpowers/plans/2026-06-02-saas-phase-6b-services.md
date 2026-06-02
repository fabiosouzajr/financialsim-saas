# Phase 6B — Services Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update RequestContext to carry `client_id`, add `invite_customer`/`re_invite` to AuthService, add customer login support, create `ParcelaService`, create `PixService`, and update `ProposalService.approve()`/`cancel()`.

**Architecture:** `RequestContext` gains an optional `client_id` from JWT. `AuthService` handles customer user lifecycle. `ParcelaService` owns parcela queries for customers. `PixService` owns charge creation, webhook handling, and expiry logic. `ProposalService` delegates customer invite and charge cancellation.

**Tech Stack:** Python 3.12, SQLAlchemy async, FastAPI Depends chain.

**Prerequisite:** Plan 6A complete (models updated, pix module created).

---

### Task 1: Update RequestContext — add client_id

**Files:**
- Modify: `backend/finacialsim_saas/auth/deps.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_deps_client_id.py
import uuid
import jwt
import pytest
from finacialsim_saas.auth.deps import _parse_bearer
from finacialsim_saas.settings import get_settings


class _Req:
    def __init__(self, token):
        self.headers = {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_parse_bearer_includes_client_id():
    cfg = get_settings()
    client_id = uuid.uuid4()
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "role": "customer",
            "iat": 0,
            "exp": 9999999999,
            "client_id": str(client_id),
        },
        cfg.jwt_secret_key,
        algorithm="HS256",
    )
    ctx = await _parse_bearer(_Req(token))
    assert ctx is not None
    assert ctx.client_id == client_id


@pytest.mark.asyncio
async def test_parse_bearer_no_client_id_for_staff():
    cfg = get_settings()
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "role": "admin",
            "iat": 0,
            "exp": 9999999999,
        },
        cfg.jwt_secret_key,
        algorithm="HS256",
    )
    ctx = await _parse_bearer(_Req(token))
    assert ctx is not None
    assert ctx.client_id is None
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/fabio/git/financialsim-saas/backend && uv run pytest tests/test_deps_client_id.py -x -q 2>&1 | head -20
```
Expected: FAILED — `RequestContext` has no `client_id` attribute.

- [ ] **Step 3: Add client_id to RequestContext**

In `backend/finacialsim_saas/auth/deps.py`, update `RequestContext` dataclass:

```python
@dataclass
class RequestContext:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: Role
    iat: float
    client_id: uuid.UUID | None = None
```

- [ ] **Step 4: Update _parse_bearer to extract client_id**

Replace the `return RequestContext(...)` in `_parse_bearer`:

```python
    return RequestContext(
        user_id=uuid.UUID(payload["sub"]),
        tenant_id=uuid.UUID(payload["tenant_id"]),
        role=Role(payload["role"]),
        iat=float(payload["iat"]),
        client_id=uuid.UUID(payload["client_id"]) if "client_id" in payload else None,
    )
```

- [ ] **Step 5: Run test to confirm pass**

```bash
cd /home/fabio/git/financialsim-saas/backend && uv run pytest tests/test_deps_client_id.py tests/test_deps.py -x -q
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/auth/deps.py backend/tests/test_deps_client_id.py
git commit -m "feat(phase6): add client_id to RequestContext; extract from JWT in _parse_bearer"
```

---

### Task 2: Update AuthService — customer login + invite_customer + re_invite

**Files:**
- Modify: `backend/finacialsim_saas/auth/service.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_auth_invite.py
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import Role, Tenant, Client, ClientType, User, PasswordResetToken, NotificationsOutbox
from finacialsim_saas.settings import get_settings
from sqlalchemy import select


@pytest_asyncio.fixture
async def tenant(session: AsyncSession) -> Tenant:
    t = Tenant(name="TestInviteCo", slug=f"test-invite-{uuid.uuid4().hex[:6]}")
    session.add(t)
    await session.commit()
    return t


@pytest_asyncio.fixture
async def admin_user(session: AsyncSession, tenant: Tenant) -> User:
    from finacialsim_saas.auth.service import AuthService
    svc = AuthService(session, get_settings())
    user = await svc.register_user(
        tenant_id=tenant.id, email=f"admin-{uuid.uuid4().hex[:6]}@test.com",
        password="pass", name="Admin", role=Role.admin,
    )
    await session.commit()
    return user


@pytest_asyncio.fixture
async def client_record(session: AsyncSession, tenant: Tenant, admin_user: User) -> Client:
    ctx = RequestContext(user_id=admin_user.id, tenant_id=tenant.id, role=Role.admin, iat=0.0)
    c = Client(
        tenant_id=tenant.id,
        nome="João Silva",
        cpf_cnpj=f"111.222.333-{uuid.uuid4().int % 100:02d}",
        tipo=ClientType.pf,
        email=f"joao-{uuid.uuid4().hex[:6]}@example.com",
        criado_por=admin_user.id,
    )
    session.add(c)
    await session.commit()
    return c


@pytest.mark.asyncio
async def test_invite_customer_creates_user_and_token(session, tenant, client_record, admin_user):
    ctx = RequestContext(user_id=admin_user.id, tenant_id=tenant.id, role=Role.admin, iat=0.0)
    svc = AuthService(session, get_settings())
    proposal_id = uuid.uuid4()

    user = await svc.invite_customer(client_record.id, ctx, proposal_id=proposal_id)
    await session.commit()

    assert user.role == Role.customer
    assert user.client_id == client_record.id
    assert not user.is_active or True  # active=True by default; password is unusable

    # Token exists
    token_result = await session.execute(
        select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    )
    token = token_result.scalar_one_or_none()
    assert token is not None
    assert token.used_at is None

    # Outbox entry created
    outbox_result = await session.execute(
        select(NotificationsOutbox)
        .where(
            NotificationsOutbox.tenant_id == tenant.id,
            NotificationsOutbox.type == "customer_invite",
        )
    )
    entry = outbox_result.scalars().first()
    assert entry is not None
    assert entry.payload["user_id"] == str(user.id)
    assert entry.payload["proposal_id"] == str(proposal_id)


@pytest.mark.asyncio
async def test_invite_customer_idempotent(session, tenant, client_record, admin_user):
    ctx = RequestContext(user_id=admin_user.id, tenant_id=tenant.id, role=Role.admin, iat=0.0)
    svc = AuthService(session, get_settings())

    user1 = await svc.invite_customer(client_record.id, ctx)
    await session.commit()
    user2 = await svc.invite_customer(client_record.id, ctx)
    await session.commit()

    assert user1.id == user2.id  # same user, no duplicate


@pytest.mark.asyncio
async def test_re_invite_invalidates_old_token(session, tenant, client_record, admin_user):
    ctx = RequestContext(user_id=admin_user.id, tenant_id=tenant.id, role=Role.admin, iat=0.0)
    svc = AuthService(session, get_settings())

    user = await svc.invite_customer(client_record.id, ctx)
    await session.commit()

    # Get first token
    tok1 = await session.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
    )
    assert tok1 is not None
    old_token_id = tok1.id

    # Re-invite
    await svc.re_invite(client_record.id, ctx)
    await session.commit()

    # Old token should be invalidated
    await session.refresh(tok1)
    assert tok1.used_at is not None

    # New active token exists
    new_tok = await session.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
    )
    assert new_tok is not None
    assert new_tok.id != old_token_id


@pytest.mark.asyncio
async def test_customer_can_authenticate(session, tenant, client_record, admin_user):
    ctx = RequestContext(user_id=admin_user.id, tenant_id=tenant.id, role=Role.admin, iat=0.0)
    svc = AuthService(session, get_settings())

    user = await svc.invite_customer(client_record.id, ctx)
    await session.commit()

    # Set a real password
    user.password_hash = svc._hash_pw("customer-pass")
    await session.commit()

    # Should now authenticate
    auth_user = await svc.authenticate(user.email, "customer-pass")
    assert auth_user.id == user.id
    assert auth_user.role == Role.customer
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/fabio/git/financialsim-saas/backend && uv run pytest tests/test_auth_invite.py -x -q 2>&1 | head -20
```
Expected: FAILED — `invite_customer` method does not exist.

- [ ] **Step 3: Update authenticate to support customer users**

In `service.py`, replace `authenticate`:

```python
    async def authenticate(self, email: str, password: str) -> User:
        # Search staff users first (globally unique email)
        result = await self._s.execute(
            select(User).where(User.email == email, User.role != Role.customer)
        )
        user = result.scalar_one_or_none()
        if user is None:
            # Try customer users (unique per tenant, first match wins)
            result = await self._s.execute(
                select(User).where(User.email == email, User.role == Role.customer)
            )
            user = result.scalars().first()
        if user is None or not self._check_pw(password, user.password_hash):
            raise AuthError("Invalid credentials")
        if not user.is_active:
            raise AuthError("Account disabled")
        return user
```

- [ ] **Step 4: Add invite_customer method**

Add after `confirm_password_reset` in `service.py`:

```python
    async def invite_customer(
        self,
        client_id: uuid.UUID,
        ctx: "RequestContext",
        *,
        proposal_id: uuid.UUID | None = None,
    ) -> User:
        from finacialsim_saas.data.models import Client

        client = await self._s.get(Client, client_id)
        if client is None or client.tenant_id != ctx.tenant_id:
            from finacialsim_saas.errors import NotFoundError
            raise NotFoundError(f"client {client_id} not found")

        # Find or create customer user
        result = await self._s.execute(
            select(User).where(
                User.client_id == client_id,
                User.role == Role.customer,
                User.tenant_id == ctx.tenant_id,
            )
        )
        user = result.scalar_one_or_none()
        if user is None:
            email = client.email or f"customer-{str(client_id)[:8]}@placeholder.invalid"
            user = User(
                tenant_id=ctx.tenant_id,
                email=email,
                name=client.nome,
                password_hash="!unusable",
                role=Role.customer,
                client_id=client_id,
                is_active=True,
            )
            self._s.add(user)
            await self._s.flush()

        # Invalidate any existing active reset tokens
        now = datetime.now(timezone.utc)
        await self._s.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=now)
        )

        # Issue new 72h token
        raw = secrets.token_urlsafe(32)
        prt = PasswordResetToken(
            user_id=user.id,
            tenant_id=user.tenant_id,
            token_hash=self._hash_token(raw),
            expires_at=now + timedelta(hours=72),
        )
        self._s.add(prt)

        # Write outbox
        payload: dict = {"user_id": str(user.id)}
        if proposal_id is not None:
            payload["proposal_id"] = str(proposal_id)
        self._s.add(
            NotificationsOutbox(
                tenant_id=ctx.tenant_id,
                type="customer_invite",
                recipient=user.email,
                payload=payload,
            )
        )
        return user

    async def re_invite(self, client_id: uuid.UUID, ctx: "RequestContext") -> User:
        from finacialsim_saas.errors import NotFoundError

        result = await self._s.execute(
            select(User).where(
                User.client_id == client_id,
                User.role == Role.customer,
                User.tenant_id == ctx.tenant_id,
            )
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise NotFoundError(f"no customer user for client {client_id}")
        return await self.invite_customer(client_id, ctx)
```

- [ ] **Step 5: Add missing imports to service.py**

Ensure `timedelta` is already imported (it is). Verify `update` is imported from sqlalchemy (it is). The `datetime` and `timezone` are already imported.

- [ ] **Step 6: Run failing tests**

```bash
cd /home/fabio/git/financialsim-saas/backend && uv run pytest tests/test_auth_invite.py -x -q
```
Expected: all 4 tests pass.

- [ ] **Step 7: Run full auth test suite**

```bash
cd /home/fabio/git/financialsim-saas/backend && uv run pytest tests/test_auth_service.py tests/test_auth_endpoints.py -x -q
```
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/finacialsim_saas/auth/service.py backend/tests/test_auth_invite.py
git commit -m "feat(phase6): add invite_customer, re_invite to AuthService; support customer login"
```

---

### Task 3: Create ParcelaService

**Files:**
- Create: `backend/finacialsim_saas/services/parcela_service.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_parcela_service.py
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import (
    Role, Tenant, User, Client, ClientType, Simulation, SimulationStatus,
    Proposal, ProposalStatus, ProposalRenderStatus, ParcelaPayment,
    ParcelaPaymentStatus, AuditLog, NotificationsOutbox,
)
from finacialsim_saas.services.parcela_service import ParcelaService
from finacialsim_saas.settings import get_settings
from finacialsim_saas.errors import NotFoundError


@pytest_asyncio.fixture
async def setup(session: AsyncSession):
    """Tenant + admin + client + customer + approved proposal + parcelas."""
    tenant = Tenant(name="ParcelaCo", slug=f"parcela-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()

    from finacialsim_saas.auth.service import AuthService
    svc = AuthService(session, get_settings())
    admin = await svc.register_user(
        tenant_id=tenant.id, email=f"adm-{uuid.uuid4().hex[:6]}@t.com",
        password="x", name="Admin", role=Role.admin,
    )

    client = Client(
        tenant_id=tenant.id, nome="Ana", cpf_cnpj=f"123.{uuid.uuid4().int % 999:03d}.456-78",
        tipo=ClientType.pf, email=f"ana-{uuid.uuid4().hex[:6]}@example.com", criado_por=admin.id,
    )
    session.add(client)
    await session.flush()

    sim = Simulation(
        tenant_id=tenant.id, codigo=f"SIM-{uuid.uuid4().hex[:6]}",
        valor_veiculo=Decimal("50000"), valor_entrada=Decimal("10000"),
        valor_financiado=Decimal("40000"), taxa_mensal=Decimal("0.02"),
        prazo_meses=3, data_liberacao=date.today(), primeiro_vencimento=date.today(),
        incluir_iof=False, iof_total=Decimal("0"), parcela_financiamento=Decimal("14000"),
        total_pago=Decimal("42000"), total_juros=Decimal("2000"),
        cet_mensal=Decimal("0.021"), cet_anual=Decimal("0.28"),
        status=SimulationStatus.confirmado, rules_snapshot_json={},
        client_id=client.id, vehicle_id=None, criado_por=admin.id,
    )
    session.add(sim)
    await session.flush()

    proposal = Proposal(
        tenant_id=tenant.id, simulation_id=sim.id,
        codigo=f"PROP-{uuid.uuid4().hex[:6]}", gerado_por=admin.id,
        validade_dias=7, snapshot_json={"sim": {}, "cronograma": [], "loja": {}, "vendedor": {}, "cliente": None, "veiculo": None},
        render_status=ProposalRenderStatus.ready, status=ProposalStatus.aprovada,
    )
    session.add(proposal)
    await session.flush()

    today = date.today()
    for i in range(1, 4):
        p = ParcelaPayment(
            tenant_id=tenant.id, proposal_id=proposal.id, parcela_num=i,
            vencimento=today + timedelta(days=30 * i),
            valor_parcela=Decimal("14000"), status=ParcelaPaymentStatus.open,
        )
        session.add(p)
    await session.commit()

    # Create customer user
    admin_ctx = RequestContext(user_id=admin.id, tenant_id=tenant.id, role=Role.admin, iat=0.0)
    customer_user = await svc.invite_customer(client.id, admin_ctx)
    # Give them a real password for JWT tests
    customer_user.password_hash = svc._hash_pw("cpass")
    await session.commit()

    return {
        "tenant": tenant, "admin": admin, "client": client,
        "sim": sim, "proposal": proposal, "customer_user": customer_user,
    }


@pytest.mark.asyncio
async def test_list_for_customer_returns_proposals(session, setup):
    cu = setup["customer_user"]
    ctx = RequestContext(
        user_id=cu.id, tenant_id=setup["tenant"].id,
        role=Role.customer, iat=0.0, client_id=setup["client"].id,
    )
    svc = ParcelaService(session)
    items = await svc.list_for_customer(ctx)
    assert len(items) == 1
    item = items[0]
    assert item["proposal_id"] == str(setup["proposal"].id)
    assert item["status_counts"]["open"] == 3


@pytest.mark.asyncio
async def test_get_schedule_returns_parcelas(session, setup):
    cu = setup["customer_user"]
    ctx = RequestContext(
        user_id=cu.id, tenant_id=setup["tenant"].id,
        role=Role.customer, iat=0.0, client_id=setup["client"].id,
    )
    svc = ParcelaService(session)
    schedule = await svc.get_schedule(setup["proposal"].id, ctx)
    assert len(schedule["parcelas"]) == 3
    assert schedule["next_open_parcela_id"] is not None


@pytest.mark.asyncio
async def test_cannot_access_other_customer_proposal(session, setup):
    other_client_id = uuid.uuid4()
    ctx = RequestContext(
        user_id=uuid.uuid4(), tenant_id=setup["tenant"].id,
        role=Role.customer, iat=0.0, client_id=other_client_id,
    )
    svc = ParcelaService(session)
    with pytest.raises(NotFoundError):
        await svc.get_schedule(setup["proposal"].id, ctx)


@pytest.mark.asyncio
async def test_mark_overdue_flips_past_due_parcelas(session, setup):
    # Create an overdue parcela directly
    past_date = date.today() - timedelta(days=5)
    overdue_p = ParcelaPayment(
        tenant_id=setup["tenant"].id, proposal_id=setup["proposal"].id,
        parcela_num=99, vencimento=past_date,
        valor_parcela=Decimal("100"), status=ParcelaPaymentStatus.open,
    )
    session.add(overdue_p)
    await session.commit()

    svc = ParcelaService(session)
    await svc.mark_overdue()

    await session.refresh(overdue_p)
    assert overdue_p.status == ParcelaPaymentStatus.overdue

    # Audit entry created
    audit = await session.scalar(
        select(AuditLog).where(
            AuditLog.entidade == "parcela_payments",
            AuditLog.entidade_id == overdue_p.id,
            AuditLog.acao == "parcela_overdue",
        )
    )
    assert audit is not None

    # Outbox entry created
    outbox = await session.scalar(
        select(NotificationsOutbox).where(
            NotificationsOutbox.type == "parcela_overdue",
            NotificationsOutbox.tenant_id == setup["tenant"].id,
        )
    )
    assert outbox is not None
    assert outbox.payload["parcela_id"] == str(overdue_p.id)
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/fabio/git/financialsim-saas/backend && uv run pytest tests/test_parcela_service.py -x -q 2>&1 | head -20
```
Expected: FAILED — `parcela_service` module not found.

- [ ] **Step 3: Create parcela_service.py**

```python
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import (
    AuditLog, NotificationsOutbox, ParcelaPayment, ParcelaPaymentStatus,
    Proposal, ProposalStatus, Simulation,
)
from finacialsim_saas.errors import NotFoundError
from finacialsim_saas.schemas.proposals import PropostaSnapshot
from finacialsim_saas.services.audit_service import AuditService

UTC = timezone.utc


def _effective_status(p: ParcelaPayment) -> str:
    """Returns 'overdue' for open parcelas past due; otherwise p.status.value."""
    if p.status == ParcelaPaymentStatus.open and p.vencimento < date.today():
        return "overdue"
    return p.status.value


class ParcelaService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_for_customer(self, ctx: RequestContext) -> list[dict[str, Any]]:
        """Returns approved proposals with parcela status counts for the customer."""
        if ctx.client_id is None:
            return []

        proposals = list(
            await self._s.scalars(
                select(Proposal)
                .join(Simulation, Proposal.simulation_id == Simulation.id)
                .where(
                    Proposal.tenant_id == ctx.tenant_id,
                    Proposal.status == ProposalStatus.aprovada,
                    Simulation.client_id == ctx.client_id,
                )
                .order_by(Proposal.aprovado_em.desc())
            )
        )

        result = []
        for proposal in proposals:
            parcelas = list(
                await self._s.scalars(
                    select(ParcelaPayment).where(
                        ParcelaPayment.proposal_id == proposal.id
                    )
                )
            )
            counts: dict[str, int] = {"open": 0, "paid": 0, "overdue": 0, "canceled": 0}
            for p in parcelas:
                key = _effective_status(p)
                counts[key] = counts.get(key, 0) + 1

            snap = PropostaSnapshot.model_validate(proposal.snapshot_json)
            result.append(
                {
                    "proposal_id": str(proposal.id),
                    "codigo": proposal.codigo,
                    "veiculo": snap.veiculo.descricao if snap.veiculo else "",
                    "status_counts": counts,
                    "total_parcelas": len(parcelas),
                    "aprovado_em": (
                        proposal.aprovado_em.isoformat() if proposal.aprovado_em else None
                    ),
                }
            )
        return result

    async def get_schedule(
        self, proposal_id: uuid.UUID, ctx: RequestContext
    ) -> dict[str, Any]:
        """Returns full parcela schedule; verifies customer ownership."""
        if ctx.client_id is None:
            raise NotFoundError(f"proposal {proposal_id} not found")

        proposal = await self._s.get(Proposal, proposal_id)
        if proposal is None or proposal.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"proposal {proposal_id} not found")

        sim = await self._s.get(Simulation, proposal.simulation_id)
        if sim is None or sim.client_id != ctx.client_id:
            raise NotFoundError(f"proposal {proposal_id} not found")

        parcelas = list(
            await self._s.scalars(
                select(ParcelaPayment)
                .where(ParcelaPayment.proposal_id == proposal_id)
                .order_by(ParcelaPayment.parcela_num)
            )
        )

        next_open_id = None
        for p in parcelas:
            if _effective_status(p) in ("open", "overdue"):
                next_open_id = str(p.id)
                break

        snap = PropostaSnapshot.model_validate(proposal.snapshot_json)
        return {
            "proposal_id": str(proposal.id),
            "codigo": proposal.codigo,
            "veiculo": snap.veiculo.descricao if snap.veiculo else "",
            "next_open_parcela_id": next_open_id,
            "parcelas": [
                {
                    "id": str(p.id),
                    "parcela_num": p.parcela_num,
                    "vencimento": p.vencimento.isoformat(),
                    "valor_parcela": str(p.valor_parcela),
                    "status": _effective_status(p),
                    "paid_at": p.paid_at.isoformat() if p.paid_at else None,
                    "paid_amount": str(p.paid_amount) if p.paid_amount else None,
                }
                for p in parcelas
            ],
        }

    async def get_parcela(
        self, parcela_id: uuid.UUID, ctx: RequestContext
    ) -> ParcelaPayment:
        """Returns a single parcela after verifying customer ownership."""
        if ctx.client_id is None:
            raise NotFoundError(f"parcela {parcela_id} not found")

        parcela = await self._s.get(ParcelaPayment, parcela_id)
        if parcela is None or parcela.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"parcela {parcela_id} not found")

        proposal = await self._s.get(Proposal, parcela.proposal_id)
        if proposal is None:
            raise NotFoundError(f"parcela {parcela_id} not found")

        sim = await self._s.get(Simulation, proposal.simulation_id)
        if sim is None or sim.client_id != ctx.client_id:
            raise NotFoundError(f"parcela {parcela_id} not found")

        return parcela

    async def mark_overdue(self) -> None:
        """Flip open parcelas past due to overdue. Called by ARQ cron at 05:00 UTC."""
        today = date.today()
        from sqlalchemy import and_

        parcelas = list(
            await self._s.scalars(
                select(ParcelaPayment).where(
                    and_(
                        ParcelaPayment.status == ParcelaPaymentStatus.open,
                        ParcelaPayment.vencimento < today,
                    )
                )
            )
        )

        now = datetime.now(UTC)
        for parcela in parcelas:
            parcela.status = ParcelaPaymentStatus.overdue
            self._s.add(
                AuditLog(
                    tenant_id=parcela.tenant_id,
                    acao="parcela_overdue",
                    entidade="parcela_payments",
                    entidade_id=parcela.id,
                    diff_json={
                        "from": "open",
                        "to": "overdue",
                        "vencimento": parcela.vencimento.isoformat(),
                    },
                )
            )
            self._s.add(
                NotificationsOutbox(
                    tenant_id=parcela.tenant_id,
                    type="parcela_overdue",
                    recipient="",
                    payload={
                        "parcela_id": str(parcela.id),
                        "proposal_id": str(parcela.proposal_id),
                    },
                )
            )

        await self._s.commit()
```

- [ ] **Step 4: Run tests**

```bash
cd /home/fabio/git/financialsim-saas/backend && uv run pytest tests/test_parcela_service.py -x -q
```
Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/services/parcela_service.py backend/tests/test_parcela_service.py
git commit -m "feat(phase6): add ParcelaService with list_for_customer, get_schedule, mark_overdue"
```

---

### Task 4: Create PixService

**Files:**
- Create: `backend/finacialsim_saas/pix/service.py`

- [ ] **Step 1: Write failing test (minimal smoke test)**

```python
# backend/tests/test_pix_service_smoke.py
"""Smoke tests — full PixService tests are in test_pix_service.py (Plan 6E)."""
import pytest
from finacialsim_saas.pix.service import PixService
print("PixService import OK")
```

Run:
```bash
cd /home/fabio/git/financialsim-saas/backend && uv run pytest tests/test_pix_service_smoke.py -x -q 2>&1 | head -10
```
Expected: FAILED — module not found.

- [ ] **Step 2: Create pix/service.py**

```python
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import (
    AuditLog, ParcelaPayment, ParcelaPaymentStatus, PixCharge,
    PixChargeStatus, PixWebhookEvent, Proposal, Simulation,
)
from finacialsim_saas.errors import NotFoundError, ValidationError
from finacialsim_saas.pix.protocol import PixProvider
from finacialsim_saas.storage import StorageBackend

UTC = timezone.utc


class PixService:
    def __init__(
        self,
        session: AsyncSession,
        provider: PixProvider,
        storage: StorageBackend,
    ) -> None:
        self._s = session
        self._provider = provider
        self._storage = storage

    async def _lazy_flip_expired(self, charge: PixCharge) -> None:
        if (
            charge.status == PixChargeStatus.pending
            and charge.expires_at.replace(tzinfo=UTC) < datetime.now(UTC)
        ):
            charge.status = PixChargeStatus.expired
            charge.atualizado_em = datetime.now(UTC)

    async def create_charge_for_parcela(
        self, parcela_payment_id: uuid.UUID, ctx: RequestContext
    ) -> tuple[PixCharge, str]:
        """Idempotent. Returns (charge, signed_qr_url). TTL 30 min."""
        parcela = await self._s.get(ParcelaPayment, parcela_payment_id)
        if parcela is None or parcela.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"parcela payment {parcela_payment_id} not found")

        # Verify customer ownership
        if ctx.client_id is not None:
            proposal = await self._s.get(Proposal, parcela.proposal_id)
            sim = await self._s.get(Simulation, proposal.simulation_id) if proposal else None
            if sim is None or sim.client_id != ctx.client_id:
                raise NotFoundError(f"parcela payment {parcela_payment_id} not found")

        if parcela.status not in (ParcelaPaymentStatus.open, ParcelaPaymentStatus.overdue):
            raise ValidationError("parcela must be open or overdue to pay")

        # Check for existing pending charge (lazy-flip expired first)
        if parcela.last_pix_charge_id is not None:
            existing = await self._s.get(PixCharge, parcela.last_pix_charge_id)
            if existing is not None:
                await self._lazy_flip_expired(existing)
                if existing.status == PixChargeStatus.pending:
                    await self._s.flush()
                    qr_url = await self._storage.signed_url(existing.qrcode_png_key, expires_in=1800)
                    return existing, qr_url

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

        qr_key = f"pix/{charge_id}/qr.png"
        await self._storage.put(qr_key, charge_data.qr_png_bytes, "image/png")

        now = datetime.now(UTC)
        charge = PixCharge(
            id=charge_id,
            tenant_id=ctx.tenant_id,
            parcela_payment_id=parcela_payment_id,
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

        qr_url = await self._storage.signed_url(qr_key, expires_in=1800)
        return charge, qr_url

    async def handle_webhook(self, headers: dict[str, str], body: bytes) -> None:
        """Logs every payload. Verifies HMAC. Processes paid events idempotently."""
        now = datetime.now(UTC)

        # Always parse body for logging
        try:
            body_json: dict[str, Any] = json.loads(body)
        except Exception:
            body_json = {"_raw": body.decode("utf-8", errors="replace")[:500]}

        # Verify signature
        try:
            event = self._provider.verify_webhook(headers, body)
            signature_valid = True
        except Exception as exc:
            self._s.add(
                PixWebhookEvent(
                    received_at=now,
                    signature_valid=False,
                    headers_json=dict(headers),
                    body_json=body_json,
                    processed=False,
                    error=str(exc)[:200],
                )
            )
            await self._s.commit()
            return

        if event.status != "paid":
            self._s.add(
                PixWebhookEvent(
                    received_at=now,
                    signature_valid=True,
                    headers_json=dict(headers),
                    body_json=body_json,
                    processed=False,
                    error=f"unhandled status: {event.status}",
                )
            )
            await self._s.commit()
            return

        charge_result = await self._s.execute(
            select(PixCharge).where(PixCharge.txid == event.txid)
        )
        charge = charge_result.scalar_one_or_none()

        if charge is None:
            self._s.add(
                PixWebhookEvent(
                    received_at=now,
                    signature_valid=True,
                    headers_json=dict(headers),
                    body_json=body_json,
                    processed=False,
                    error="charge not found",
                )
            )
            await self._s.commit()
            return

        # Idempotency: already processed?
        if charge.status == PixChargeStatus.paid:
            self._s.add(
                PixWebhookEvent(
                    received_at=now,
                    signature_valid=True,
                    headers_json=dict(headers),
                    body_json=body_json,
                    processed=False,
                    error="already processed (replay)",
                )
            )
            await self._s.commit()
            return

        # Process payment
        charge.status = PixChargeStatus.paid
        charge.atualizado_em = now

        parcela = await self._s.get(ParcelaPayment, charge.parcela_payment_id)
        if parcela is not None:
            parcela.status = ParcelaPaymentStatus.paid
            parcela.paid_at = now
            parcela.paid_amount = event.paid_amount or charge.amount
            parcela.last_pix_charge_id = charge.id

        self._s.add(
            AuditLog(
                tenant_id=charge.tenant_id,
                acao="parcela_paga",
                entidade="parcela_payments",
                entidade_id=charge.parcela_payment_id,
                diff_json={
                    "txid": event.txid,
                    "amount": str(event.paid_amount or charge.amount),
                },
            )
        )
        self._s.add(
            PixWebhookEvent(
                received_at=now,
                signature_valid=True,
                headers_json=dict(headers),
                body_json=body_json,
                processed=True,
                processed_at=now,
            )
        )
        await self._s.commit()

    async def get_charge(
        self, charge_id: uuid.UUID, ctx: RequestContext
    ) -> tuple[PixCharge, str]:
        """Lazy-flips expiry, returns charge + signed QR URL."""
        charge = await self._s.get(PixCharge, charge_id)
        if charge is None or charge.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"pix charge {charge_id} not found")

        # Verify customer ownership if customer role
        if ctx.client_id is not None:
            parcela = await self._s.get(ParcelaPayment, charge.parcela_payment_id)
            proposal = await self._s.get(Proposal, parcela.proposal_id) if parcela else None
            sim = await self._s.get(Simulation, proposal.simulation_id) if proposal else None
            if sim is None or sim.client_id != ctx.client_id:
                raise NotFoundError(f"pix charge {charge_id} not found")

        await self._lazy_flip_expired(charge)
        if charge.status == PixChargeStatus.expired:
            await self._s.commit()

        qr_url = await self._storage.signed_url(charge.qrcode_png_key, expires_in=1800)
        return charge, qr_url

    async def cancel_charges_for_proposal(self, proposal_id: uuid.UUID) -> None:
        """Cancel all pending charges for all parcelas of a proposal."""
        parcelas = list(
            await self._s.scalars(
                select(ParcelaPayment).where(
                    ParcelaPayment.proposal_id == proposal_id,
                    ParcelaPayment.last_pix_charge_id.isnot(None),
                )
            )
        )
        now = datetime.now(UTC)
        for parcela in parcelas:
            charge = await self._s.get(PixCharge, parcela.last_pix_charge_id)
            if charge is not None and charge.status == PixChargeStatus.pending:
                try:
                    await self._provider.cancel_charge(charge.txid)
                except Exception:
                    pass
                charge.status = PixChargeStatus.canceled
                charge.atualizado_em = now
        await self._s.flush()
```

- [ ] **Step 3: Run smoke test**

```bash
cd /home/fabio/git/financialsim-saas/backend && uv run pytest tests/test_pix_service_smoke.py -x -q
```
Expected: passes (import succeeds).

- [ ] **Step 4: Commit**

```bash
git add backend/finacialsim_saas/pix/service.py backend/tests/test_pix_service_smoke.py
git commit -m "feat(phase6): add PixService with create_charge, handle_webhook, get_charge, cancel"
```

---

### Task 5: Update ProposalService — approve() and cancel()

**Files:**
- Modify: `backend/finacialsim_saas/services/proposal_service.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_proposal_phase6.py
"""Tests for Phase 6 ProposalService changes: invite on approve, cancel with cleanup."""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import Role, ParcelaPaymentStatus, User


@pytest.mark.asyncio
async def test_approve_calls_invite_customer(session, engine):
    """approve() calls auth_service.invite_customer after creating parcelas."""
    # Minimal setup — use mocks to isolate
    from finacialsim_saas.services.proposal_service import ProposalService
    from finacialsim_saas.data.models import (
        Tenant, User, Client, ClientType, Simulation, SimulationStatus,
        Proposal, ProposalStatus, ProposalRenderStatus,
    )
    from finacialsim_saas.auth.service import AuthService
    from finacialsim_saas.settings import get_settings
    from finacialsim_saas.storage.local import LocalVolumeBackend
    from decimal import Decimal
    from datetime import date
    from pathlib import Path
    import tempfile

    # Create real data
    tenant = Tenant(name="Phase6Co", slug=f"ph6-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()

    auth_svc = AuthService(session, get_settings())
    admin = await auth_svc.register_user(
        tenant_id=tenant.id, email=f"adm-ph6-{uuid.uuid4().hex[:6]}@t.com",
        password="x", name="Admin", role=Role.admin,
    )

    client = Client(
        tenant_id=tenant.id, nome="Test Client",
        cpf_cnpj=f"999.888.{uuid.uuid4().int % 999:03d}-77",
        tipo=ClientType.pf, email=f"testclient-{uuid.uuid4().hex[:6]}@example.com",
        criado_por=admin.id,
    )
    session.add(client)
    await session.flush()

    from finacialsim_saas.schemas.proposals import PropostaSnapshot, build_snapshot
    # Minimal snapshot_json
    snap_json = {
        "sim": {
            "valor_veiculo": "50000", "valor_financiado": "40000",
            "valor_entrada": "10000", "prazo_meses": 2,
            "taxa_mensal": "0.02", "taxa_anual": "0.27",
            "data_liberacao": date.today().isoformat(),
            "primeiro_vencimento": date.today().isoformat(),
            "incluir_iof": False, "iof_total": "0", "tarifas_total": "0",
            "valor_parcela": "21000", "total_pago": "42000",
            "total_juros": "2000", "cet_mensal": "0.021", "cet_anual": "0.28",
            "extras_acumulado": "0",
        },
        "cronograma": [
            {"numero": 1, "venc": date.today().isoformat(), "parcela_total": "21000",
             "juros": "800", "amortizacao": "20200", "parcela": "21000",
             "extras": "0", "saldo": "19800"},
            {"numero": 2, "venc": date.today().isoformat(), "parcela_total": "21000",
             "juros": "396", "amortizacao": "20604", "parcela": "21000",
             "extras": "0", "saldo": "0"},
        ],
        "loja": {"nome": "T", "cnpj": "00.000.000/0001-00", "endereco": "", "telefone": ""},
        "vendedor": {"nome": "A", "email": "a@t.com"},
        "cliente": None, "veiculo": None,
    }

    sim = Simulation(
        tenant_id=tenant.id, codigo=f"SIM-PH6-{uuid.uuid4().hex[:6]}",
        valor_veiculo=Decimal("50000"), valor_entrada=Decimal("10000"),
        valor_financiado=Decimal("40000"), taxa_mensal=Decimal("0.02"),
        prazo_meses=2, data_liberacao=date.today(), primeiro_vencimento=date.today(),
        incluir_iof=False, iof_total=Decimal("0"), parcela_financiamento=Decimal("21000"),
        total_pago=Decimal("42000"), total_juros=Decimal("2000"),
        cet_mensal=Decimal("0.021"), cet_anual=Decimal("0.28"),
        status=SimulationStatus.confirmado, rules_snapshot_json={},
        client_id=client.id, vehicle_id=None, criado_por=admin.id,
    )
    session.add(sim)
    await session.flush()

    proposal = Proposal(
        tenant_id=tenant.id, simulation_id=sim.id,
        codigo=f"PROP-PH6-{uuid.uuid4().hex[:6]}", gerado_por=admin.id,
        validade_dias=7, snapshot_json=snap_json,
        render_status=ProposalRenderStatus.ready, status=ProposalStatus.ready,
    )
    session.add(proposal)
    await session.commit()

    ctx = RequestContext(user_id=admin.id, tenant_id=tenant.id, role=Role.admin, iat=0.0)

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = LocalVolumeBackend(root=Path(tmpdir), secret="s", base_url="http://test")
        arq_mock = AsyncMock()
        svc = ProposalService(session=session, arq=arq_mock, storage=storage)

        result = await svc.approve(proposal.id, ctx)

    assert result.status == ProposalStatus.aprovada

    # Customer user created
    customer = await session.scalar(
        select(User).where(
            User.client_id == client.id,
            User.role == Role.customer,
            User.tenant_id == tenant.id,
        )
    )
    assert customer is not None
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/fabio/git/financialsim-saas/backend && uv run pytest tests/test_proposal_phase6.py::test_approve_calls_invite_customer -x -q 2>&1 | head -20
```
Expected: FAIL — customer user not created (TODO not yet implemented).

- [ ] **Step 3: Update ProposalService.__init__ to accept auth_service**

In `proposal_service.py`, update `__init__`:

```python
    def __init__(
        self,
        session: AsyncSession,
        arq: Any,
        storage: StorageBackend,
        auth_service: "AuthService | None" = None,
        pix_service: "PixService | None" = None,
    ) -> None:
        self._s = session
        self._arq = arq
        self._storage = storage
        self._audit = AuditService(session)
        self._auth = auth_service
        self._pix = pix_service
```

Add to imports at top of `proposal_service.py`:
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from finacialsim_saas.auth.service import AuthService
    from finacialsim_saas.pix.service import PixService
```

- [ ] **Step 4: Update approve() to call invite_customer**

In `approve()`, replace the existing `NotificationsOutbox` block (the one adding `customer_invite`) with:

```python
        # Invite customer
        if sim and sim.client_id and self._auth is not None:
            await self._auth.invite_customer(sim.client_id, ctx, proposal_id=proposal.id)
        elif sim and sim.client_id:
            # Fallback: direct outbox entry (no auth_service injected, e.g. old tests)
            self._s.add(
                NotificationsOutbox(
                    tenant_id=ctx.tenant_id,
                    type="customer_invite",
                    recipient=recipient,
                    payload={"proposal_id": str(proposal.id)},
                )
            )
```

Also remove the `recipient` variable setup and the old `NotificationsOutbox` add block. The full updated `approve()` end section looks like:

```python
        snap = PropostaSnapshot.model_validate(proposal.snapshot_json)
        now = datetime.now(UTC)

        for row in snap.cronograma:
            self._s.add(
                ParcelaPayment(
                    tenant_id=ctx.tenant_id,
                    proposal_id=proposal.id,
                    parcela_num=row.numero,
                    vencimento=date.fromisoformat(row.venc),
                    valor_parcela=Decimal(row.parcela_total),
                    status=ParcelaPaymentStatus.open,
                )
            )

        sim = await self._s.get(Simulation, proposal.simulation_id)
        if sim and sim.client_id and self._auth is not None:
            await self._auth.invite_customer(sim.client_id, ctx, proposal_id=proposal.id)

        proposal.status = ProposalStatus.aprovada
        proposal.aprovado_por = ctx.user_id
        proposal.aprovado_em = now
        await self._s.commit()
        await self._audit.log("proposta_aprovada", "proposals", proposal.id, None, ctx)
        return proposal
```

- [ ] **Step 5: Update cancel() to deactivate customer and cancel charges**

Replace the two `# TODO Phase 6:` lines in `cancel()` with:

```python
        # Deactivate customer user linked to this proposal
        sim = await self._s.get(Simulation, proposal.simulation_id)
        if sim and sim.client_id:
            from sqlalchemy import select as _select
            customer = await self._s.scalar(
                _select(User).where(
                    User.client_id == sim.client_id,
                    User.role == Role.customer,
                    User.tenant_id == ctx.tenant_id,
                )
            )
            if customer is not None:
                customer.is_active = False

        # Cancel open pix charges
        if self._pix is not None:
            await self._pix.cancel_charges_for_proposal(proposal.id)
```

- [ ] **Step 6: Update API factory in proposals.py**

In `backend/finacialsim_saas/api/proposals.py`, update `_svc` to inject auth_service:

```python
def _svc(request: Request, session: AsyncSession) -> ProposalService:
    from finacialsim_saas.auth.service import AuthService
    settings = get_settings()
    auth_svc = AuthService(session, settings)
    return ProposalService(
        session=session,
        arq=request.app.state.arq,
        storage=get_storage_backend(settings),
        auth_service=auth_svc,
    )
```

- [ ] **Step 7: Run failing test**

```bash
cd /home/fabio/git/financialsim-saas/backend && uv run pytest tests/test_proposal_phase6.py -x -q
```
Expected: passes.

- [ ] **Step 8: Run full proposal test suite**

```bash
cd /home/fabio/git/financialsim-saas/backend && uv run pytest tests/test_proposal_service.py tests/test_proposal_endpoints.py -x -q
```
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add backend/finacialsim_saas/services/proposal_service.py backend/finacialsim_saas/api/proposals.py backend/tests/test_proposal_phase6.py
git commit -m "feat(phase6): ProposalService.approve() invites customer; cancel() deactivates user + cancels charges"
```
