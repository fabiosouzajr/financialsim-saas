# Phase 5B — Services + Worker + API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the storage abstraction, ProposalService (full lifecycle), arq worker render tasks, and all API endpoints. This is the core of Phase 5.

**Architecture:** `StorageBackend` Protocol + `LocalVolumeBackend` (HMAC-SHA256 signed URLs). `ProposalService` injected with `(session, arq)`. Worker tasks registered with 120s timeout. All 8 proposal endpoints in `api/proposals.py`.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, arq, WeasyPrint, Jinja2, hmac/hashlib (stdlib)

**Prerequisite:** Phase 5A complete and tests green.

---

## Task 5: Storage abstraction

**Files:**
- Create: `backend/finacialsim_saas/storage/__init__.py`
- Create: `backend/finacialsim_saas/storage/local.py`
- Create: `backend/finacialsim_saas/storage/deps.py`
- Create: `backend/finacialsim_saas/api/storage.py`
- Test: `backend/tests/test_storage_local.py`

- [ ] **Step 5.1 — Write the failing test**

Create `backend/tests/test_storage_local.py`:
```python
import hashlib
import hmac
import time
import urllib.parse
from pathlib import Path

import pytest

from finacialsim_saas.storage.local import LocalVolumeBackend


@pytest.fixture
def storage(tmp_path: Path) -> LocalVolumeBackend:
    return LocalVolumeBackend(
        root=tmp_path,
        secret="test-secret",
        base_url="http://localhost:8000",
    )


@pytest.mark.asyncio
async def test_put_and_get(storage: LocalVolumeBackend):
    key = "tenant-1/proposals/abc/proposta.pdf"
    data = b"%PDF-1.4 test content"
    await storage.put(key, data, "application/pdf")
    result = await storage.get(key)
    assert result == data


@pytest.mark.asyncio
async def test_signed_url_structure(storage: LocalVolumeBackend):
    key = "tenant-1/proposals/abc/proposta.pdf"
    url = await storage.signed_url(key, expires_in=300)
    assert url.startswith("http://localhost:8000/api/v1/storage/serve?")
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    assert "key" in params
    assert "expires" in params
    assert "sig" in params
    assert params["key"][0] == key


@pytest.mark.asyncio
async def test_signed_url_valid_hmac(storage: LocalVolumeBackend):
    key = "tenant-1/proposals/abc/proposta.pdf"
    url = await storage.signed_url(key, expires_in=300)
    params = dict(urllib.parse.parse_qs(urllib.parse.urlparse(url).query))
    expires = int(params["expires"][0])
    sig = params["sig"][0]
    msg = f"{key}:{expires}".encode()
    expected = hmac.new(b"test-secret", msg, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(expected, sig)


@pytest.mark.asyncio
async def test_delete(storage: LocalVolumeBackend, tmp_path: Path):
    key = "tenant-1/proposals/abc/proposta.pdf"
    await storage.put(key, b"data", "application/pdf")
    assert (tmp_path / key).exists()
    await storage.delete(key)
    assert not (tmp_path / key).exists()


@pytest.mark.asyncio
async def test_delete_nonexistent_is_silent(storage: LocalVolumeBackend):
    await storage.delete("does/not/exist.pdf")  # must not raise
```

- [ ] **Step 5.2 — Run to verify failure**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_storage_local.py -v
```
Expected: `ImportError` — `storage/` package doesn't exist.

- [ ] **Step 5.3 — Create storage package**

Create `backend/finacialsim_saas/storage/__init__.py`:
```python
"""StorageBackend Protocol. Implementations: local.LocalVolumeBackend, s3.S3Backend."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> str: ...
    async def get(self, key: str) -> bytes: ...
    async def signed_url(self, key: str, expires_in: int = 300) -> str: ...
    async def delete(self, key: str) -> None: ...
```

- [ ] **Step 5.4 — Create LocalVolumeBackend**

Create `backend/finacialsim_saas/storage/local.py`:
```python
"""LocalVolumeBackend — stores files on disk; signs URLs with HMAC-SHA256."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from pathlib import Path


class LocalVolumeBackend:
    def __init__(self, root: Path, secret: str, base_url: str) -> None:
        self._root = root
        self._secret = secret.encode()
        self._base_url = base_url.rstrip("/")

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        dest = self._root / key
        await asyncio.to_thread(dest.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(dest.write_bytes, data)
        return key

    async def get(self, key: str) -> bytes:
        path = self._root / key
        return await asyncio.to_thread(path.read_bytes)

    async def signed_url(self, key: str, expires_in: int = 300) -> str:
        expires_at = int(time.time()) + expires_in
        msg = f"{key}:{expires_at}".encode()
        sig = hmac.new(self._secret, msg, hashlib.sha256).hexdigest()
        import urllib.parse
        params = urllib.parse.urlencode({"key": key, "expires": expires_at, "sig": sig})
        return f"{self._base_url}/api/v1/storage/serve?{params}"

    async def delete(self, key: str) -> None:
        path = self._root / key
        try:
            await asyncio.to_thread(path.unlink)
        except FileNotFoundError:
            pass
```

- [ ] **Step 5.5 — Create storage deps**

Create `backend/finacialsim_saas/storage/deps.py`:
```python
"""FastAPI dependency: build storage backend from settings."""
from __future__ import annotations

from pathlib import Path

from finacialsim_saas.settings import Settings
from finacialsim_saas.storage import StorageBackend
from finacialsim_saas.storage.local import LocalVolumeBackend


def get_storage_backend(settings: Settings) -> StorageBackend:
    if settings.storage_backend == "local":
        return LocalVolumeBackend(
            root=Path(settings.storage_local_root),
            secret=settings.storage_hmac_secret,
            base_url=settings.storage_base_url,
        )
    raise ValueError(f"Unknown storage backend: {settings.storage_backend!r}")
```

- [ ] **Step 5.6 — Create storage serve endpoint**

Create `backend/finacialsim_saas/api/storage.py`:
```python
"""Storage serve endpoint — validates HMAC token and streams the file."""
from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from finacialsim_saas.settings import get_settings
from finacialsim_saas.storage.deps import get_storage_backend

router = APIRouter(prefix="/api/v1/storage", tags=["storage"])


@router.get("/serve")
async def serve_storage_file(
    key: str = Query(...),
    expires: int = Query(...),
    sig: str = Query(...),
) -> StreamingResponse:
    settings = get_settings()
    secret = settings.storage_hmac_secret.encode()
    msg = f"{key}:{expires}".encode()
    expected = hmac.new(secret, msg, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(status_code=403, detail="invalid signature")
    if time.time() > expires:
        raise HTTPException(status_code=410, detail="link expired")

    storage = get_storage_backend(settings)
    data = await storage.get(key)
    filename = key.rsplit("/", 1)[-1]
    return StreamingResponse(
        iter([data]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 5.7 — Run storage tests**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_storage_local.py -v
```
Expected: all 5 tests PASS.

- [ ] **Step 5.8 — Commit**

```bash
git add backend/finacialsim_saas/storage/ \
        backend/finacialsim_saas/api/storage.py \
        backend/tests/test_storage_local.py
git commit -m "feat(phase5): StorageBackend protocol + LocalVolumeBackend + serve endpoint"
```

---

## Task 6: ProposalService — create, get, download_pdf

**Files:**
- Create: `backend/finacialsim_saas/services/proposal_service.py`
- Test: `backend/tests/test_proposal_service_unit.py`

- [ ] **Step 6.1 — Write the failing tests**

Create `backend/tests/test_proposal_service_unit.py`:
```python
"""Unit tests for ProposalService using mocked session + arq."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import (
    AmortizationRow, Client, Role, Simulation, SimulationStatus,
    Tenant, User,
)
from finacialsim_saas.errors import ConflictError, NotFoundError, ValidationError
from finacialsim_saas.schemas.proposals import PropostaSnapshot
from finacialsim_saas.services.proposal_service import ProposalService


def _ctx(role: Role = Role.user) -> RequestContext:
    return RequestContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        role=role,
        iat=0.0,
    )


def _make_sim(tenant_id: uuid.UUID, status=SimulationStatus.confirmado) -> MagicMock:
    s = MagicMock(spec=Simulation)
    s.id = uuid.uuid4()
    s.tenant_id = tenant_id
    s.client_id = None
    s.vehicle_id = None
    s.status = status
    s.valor_veiculo = Decimal("85000.00")
    s.valor_entrada = Decimal("17000.00")
    s.valor_financiado = Decimal("68000.00")
    s.taxa_mensal = Decimal("0.012900")
    s.prazo_meses = 48
    s.data_liberacao = date(2026, 6, 1)
    s.primeiro_vencimento = date(2026, 7, 1)
    s.incluir_iof = True
    s.iof_total = Decimal("1224.00")
    s.parcela_financiamento = Decimal("1987.34")
    s.total_pago = Decimal("95392.32")
    s.total_juros = Decimal("27392.32")
    s.cet_mensal = Decimal("0.013500")
    s.cet_anual = Decimal("0.174500")
    return s


@pytest.mark.asyncio
async def test_create_rejects_wrong_tenant():
    ctx = _ctx()
    sim = _make_sim(tenant_id=uuid.uuid4())  # different tenant
    session = AsyncMock()
    session.get = AsyncMock(return_value=sim)
    arq = AsyncMock()
    svc = ProposalService(session, arq)
    with pytest.raises(NotFoundError):
        await svc.create(sim.id, ctx)


@pytest.mark.asyncio
async def test_create_rejects_non_confirmado():
    ctx = _ctx()
    sim = _make_sim(tenant_id=ctx.tenant_id, status=SimulationStatus.rascunho)
    session = AsyncMock()
    session.get = AsyncMock(return_value=sim)
    arq = AsyncMock()
    svc = ProposalService(session, arq)
    with pytest.raises(ValidationError, match="confirmado"):
        await svc.create(sim.id, ctx)


@pytest.mark.asyncio
async def test_get_cross_tenant_raises():
    ctx = _ctx()
    from finacialsim_saas.data.models import Proposal, ProposalStatus, ProposalRenderStatus
    proposal = MagicMock(spec=Proposal)
    proposal.tenant_id = uuid.uuid4()  # different tenant
    session = AsyncMock()
    session.get = AsyncMock(return_value=proposal)
    arq = AsyncMock()
    svc = ProposalService(session, arq)
    with pytest.raises(NotFoundError):
        await svc.get(proposal.id, ctx)
```

- [ ] **Step 6.2 — Run to verify failure**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_proposal_service_unit.py -v
```
Expected: `ImportError` — `proposal_service.py` doesn't exist.

- [ ] **Step 6.3 — Create proposal_service.py**

Create `backend/finacialsim_saas/services/proposal_service.py`:
```python
"""ProposalService — manages the full proposal lifecycle."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select, update  # update kept for parcela_payments cascade
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import (
    AmortizationRow, Client, NotificationsOutbox, ParcelaPayment,
    ParcelaPaymentStatus, Proposal, ProposalRenderStatus, ProposalStatus,
    Role, Simulation, SimulationExtra, SimulationFee, SimulationStatus,
    Tenant, User, Vehicle,
)
from finacialsim_saas.errors import ConflictError, NotFoundError, TenantAccessError, ValidationError
from finacialsim_saas.schemas.proposals import (
    ProposalListPage, ProposalListItem, ProposalOut, PropostaSnapshot, build_snapshot,
)
from finacialsim_saas.services.audit_service import AuditService
from finacialsim_saas.storage import StorageBackend

UTC = timezone.utc


class ProposalService:
    def __init__(self, session: AsyncSession, arq: object, storage: StorageBackend) -> None:
        self._s = session
        self._arq = arq
        self._storage = storage
        self._audit = AuditService(session)

    # ── Helpers ──────────────────────────────────────────────────────────────

    async def _get_proposal_owned(self, proposal_id: uuid.UUID, ctx: RequestContext) -> Proposal:
        proposal = await self._s.get(Proposal, proposal_id)
        if proposal is None or proposal.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"proposal {proposal_id} not found")
        return proposal

    def _can_act_on(self, proposal: Proposal, ctx: RequestContext) -> bool:
        """Vendedor can act on own proposals; manager/admin can act on any in tenant."""
        if ctx.role in (Role.admin, Role.manager):
            return True
        return proposal.gerado_por == ctx.user_id

    # ── create ───────────────────────────────────────────────────────────────

    async def create(self, simulation_id: uuid.UUID, ctx: RequestContext) -> Proposal:
        sim = await self._s.get(Simulation, simulation_id)
        if sim is None or sim.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"simulation {simulation_id} not found")
        if sim.status != SimulationStatus.confirmado:
            raise ValidationError("simulation must be confirmado to generate a proposal")

        existing = await self._s.scalar(
            select(Proposal).where(
                Proposal.tenant_id == ctx.tenant_id,
                Proposal.simulation_id == simulation_id,
            )
        )
        if existing is not None:
            raise ConflictError("a proposal already exists for this simulation")

        fees = list(
            await self._s.scalars(
                select(SimulationFee).where(SimulationFee.simulation_id == simulation_id)
            )
        )
        extras = list(
            await self._s.scalars(
                select(SimulationExtra)
                .where(SimulationExtra.simulation_id == simulation_id)
                .order_by(SimulationExtra.ordem)
            )
        )
        rows = list(
            await self._s.scalars(
                select(AmortizationRow)
                .where(AmortizationRow.simulation_id == simulation_id)
                .order_by(AmortizationRow.numero_parcela)
            )
        )
        client = await self._s.get(Client, sim.client_id) if sim.client_id else None
        vehicle = await self._s.get(Vehicle, sim.vehicle_id) if sim.vehicle_id else None
        tenant = await self._s.get(Tenant, ctx.tenant_id)
        user = await self._s.get(User, ctx.user_id)

        snapshot = build_snapshot(sim, fees, extras, rows, client, vehicle, tenant, user)

        year = date.today().year
        count = await self._s.scalar(
            select(func.count(Proposal.id)).where(
                Proposal.tenant_id == ctx.tenant_id,
                Proposal.codigo.like(f"PROP-{year}-%"),
            )
        ) or 0
        codigo = f"PROP-{year}-{count + 1:05d}"

        proposal = Proposal(
            tenant_id=ctx.tenant_id,
            simulation_id=simulation_id,
            codigo=codigo,
            gerado_por=ctx.user_id,
            validade_dias=7,
            snapshot_json=snapshot.model_dump(),
            render_status=ProposalRenderStatus.pending,
            status=ProposalStatus.rascunho,
        )
        self._s.add(proposal)
        await self._s.flush()
        await self._arq.enqueue_job("render_proposta_pdf", str(proposal.id))
        await self._s.commit()
        await self._audit.log("proposta_criada", "proposals", proposal.id, ctx)
        return proposal

    # ── get ──────────────────────────────────────────────────────────────────

    async def get(self, proposal_id: uuid.UUID, ctx: RequestContext) -> Proposal:
        return await self._get_proposal_owned(proposal_id, ctx)

    # ── list ─────────────────────────────────────────────────────────────────

    async def list(
        self,
        ctx: RequestContext,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> ProposalListPage:
        q = select(Proposal).where(Proposal.tenant_id == ctx.tenant_id)
        if status:
            q = q.where(Proposal.status == ProposalStatus(status))
        if cursor:
            import base64, json
            cur = json.loads(base64.b64decode(cursor))
            q = q.where(Proposal.gerado_em < cur["ts"])
        q = q.order_by(Proposal.gerado_em.desc()).limit(limit + 1)
        results = list(await self._s.scalars(q))
        has_more = len(results) > limit
        items = results[:limit]
        next_cursor = None
        if has_more:
            import base64, json
            next_cursor = base64.b64encode(
                json.dumps({"ts": items[-1].gerado_em.isoformat()}).encode()
            ).decode()
        return ProposalListPage(
            items=[
                ProposalListItem(
                    id=p.id,
                    codigo=p.codigo,
                    simulation_id=p.simulation_id,
                    render_status=p.render_status.value,
                    status=p.status.value,
                    gerado_em=p.gerado_em,
                )
                for p in items
            ],
            next_cursor=next_cursor,
        )

    # ── download_pdf ─────────────────────────────────────────────────────────

    async def download_pdf(
        self, proposal_id: uuid.UUID, kind: str, ctx: RequestContext
    ) -> str:
        proposal = await self._get_proposal_owned(proposal_id, ctx)
        key = proposal.pdf_key if kind == "proposta" else proposal.carne_key
        if key is None:
            raise ValidationError(f"{kind} PDF not available yet")
        return await self._storage.signed_url(key, expires_in=300)

    # ── approve ──────────────────────────────────────────────────────────────

    async def approve(self, proposal_id: uuid.UUID, ctx: RequestContext) -> Proposal:
        proposal = await self._get_proposal_owned(proposal_id, ctx)
        if proposal.status != ProposalStatus.ready:
            raise ValidationError("proposal must be ready to approve")
        if not self._can_act_on(proposal, ctx):
            raise TenantAccessError("insufficient permissions to approve this proposal")

        snap = PropostaSnapshot.model_validate(proposal.snapshot_json)
        now = datetime.now(UTC)

        # Generate parcela_payments from snapshot cronograma
        from datetime import date as _date
        for row in snap.cronograma:
            self._s.add(
                ParcelaPayment(
                    tenant_id=ctx.tenant_id,
                    proposal_id=proposal.id,
                    parcela_num=row.numero,
                    vencimento=_date.fromisoformat(row.venc),
                    valor_parcela=Decimal(row.parcela_total),
                    status=ParcelaPaymentStatus.pending,
                )
            )

        # Enqueue customer invite (email address may be None — Phase 6 handles it)
        recipient = ""
        if snap.cliente and snap.cliente.cpf_cnpj:
            # Look up client email from DB
            sim = await self._s.get(Simulation, proposal.simulation_id)
            if sim and sim.client_id:
                client = await self._s.get(Client, sim.client_id)
                recipient = client.email or ""
        self._s.add(
            NotificationsOutbox(
                tenant_id=ctx.tenant_id,
                type="customer_invite",
                recipient=recipient,
                payload={"proposal_id": str(proposal.id)},
            )
        )

        proposal.status = ProposalStatus.aprovada
        proposal.aprovado_por = ctx.user_id
        proposal.aprovado_em = now
        await self._s.commit()
        await self._audit.log("proposta_aprovada", "proposals", proposal.id, ctx)
        return proposal

    # ── cancel ───────────────────────────────────────────────────────────────

    async def cancel(self, proposal_id: uuid.UUID, ctx: RequestContext) -> Proposal:
        proposal = await self._get_proposal_owned(proposal_id, ctx)
        if proposal.status != ProposalStatus.aprovada:
            raise ValidationError("only approved proposals can be cancelled")
        if not self._can_act_on(proposal, ctx):
            raise TenantAccessError("insufficient permissions to cancel this proposal")

        now = datetime.now(UTC)

        # Cascade: cancel all parcela_payments
        await self._s.execute(
            update(ParcelaPayment)
            .where(ParcelaPayment.proposal_id == proposal.id)
            .values(status=ParcelaPaymentStatus.canceled)
        )

        # TODO Phase 6: deactivate customer User row linked to this proposal
        # (customer portal + customer users don't exist until Phase 6)

        # TODO Phase 6: cancel open pix_charges via pix_service.cancel_charge()

        # Cancellation notification outbox
        self._s.add(
            NotificationsOutbox(
                tenant_id=ctx.tenant_id,
                type="proposal_cancelled",
                recipient="",
                payload={"proposal_id": str(proposal.id)},
            )
        )

        proposal.status = ProposalStatus.cancelada
        proposal.cancelado_por = ctx.user_id
        proposal.cancelado_em = now
        await self._s.commit()
        await self._audit.log("proposta_cancelada", "proposals", proposal.id, ctx)
        return proposal

    # ── create_carne ─────────────────────────────────────────────────────────

    async def create_carne(self, proposal_id: uuid.UUID, ctx: RequestContext) -> Proposal:
        proposal = await self._get_proposal_owned(proposal_id, ctx)
        if proposal.status != ProposalStatus.aprovada:
            raise ValidationError("carnê can only be generated for approved proposals")
        await self._arq.enqueue_job("render_carne_pdf", str(proposal.id))
        return proposal

    # ── re_render ────────────────────────────────────────────────────────────

    async def re_render(
        self, proposal_id: uuid.UUID, kind: str, ctx: RequestContext
    ) -> Proposal:
        if ctx.role != Role.admin:
            raise TenantAccessError("only admins can re-render proposals")
        proposal = await self._get_proposal_owned(proposal_id, ctx)
        if kind == "proposta":
            proposal.render_status = ProposalRenderStatus.pending
            proposal.render_error = None
            await self._s.commit()
            await self._arq.enqueue_job("render_proposta_pdf", str(proposal.id))
        else:
            await self._arq.enqueue_job("render_carne_pdf", str(proposal.id))
        return proposal
```

- [ ] **Step 6.4 — Run unit tests**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_proposal_service_unit.py -v
```
Expected: all 3 tests PASS.

- [ ] **Step 6.5 — Commit**

```bash
git add backend/finacialsim_saas/services/proposal_service.py \
        backend/tests/test_proposal_service_unit.py
git commit -m "feat(phase5): ProposalService (create/get/list/download/approve/cancel/carne/re-render)"
```

---

## Task 7: Worker render tasks

**Files:**
- Modify: `backend/finacialsim_saas/workers/tasks.py`
- Modify: `backend/finacialsim_saas/workers/worker.py`
- Test: `backend/tests/test_render_tasks.py`

- [ ] **Step 7.1 — Write the failing tests**

Create `backend/tests/test_render_tasks.py`:
```python
"""Worker render task tests — WeasyPrint is mocked."""
import uuid
from decimal import Decimal
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from finacialsim_saas.data.models import (
    Proposal, ProposalRenderStatus, ProposalStatus,
)
from finacialsim_saas.schemas.proposals import (
    PropostaSnapshot, LojaSnap, VendedorSnap, SimSnap,
)
from finacialsim_saas.workers.tasks import render_proposta_pdf, render_carne_pdf


def _make_snap() -> dict:
    return PropostaSnapshot(
        loja=LojaSnap(nome="Loja Teste"),
        vendedor=VendedorSnap(nome="Vendedor"),
        cliente=None,
        veiculo=None,
        sim=SimSnap(
            valor_veiculo="85000.00",
            valor_entrada="17000.00",
            valor_financiado="68000.00",
            prazo_meses=48,
            taxa_mensal="0.012900",
            taxa_anual="0.163000",
            incluir_iof=True,
            iof_total="1224.00",
            tarifas_total="500.00",
            valor_parcela="1987.34",
            total_pago="95392.32",
            total_juros="27392.32",
            cet_mensal="0.013500",
            cet_anual="0.174500",
            extras_acumulado="0.00",
        ),
        extras=[],
        cronograma=[],
    ).model_dump()


def _make_proposal(tenant_id: uuid.UUID) -> MagicMock:
    p = MagicMock(spec=Proposal)
    p.id = uuid.uuid4()
    p.tenant_id = tenant_id
    p.codigo = "PROP-2026-00001"
    p.gerado_em = datetime(2026, 6, 1, tzinfo=timezone.utc)
    p.validade_dias = 7
    p.snapshot_json = _make_snap()
    p.render_status = ProposalRenderStatus.pending
    p.status = ProposalStatus.rascunho
    return p


@pytest.mark.asyncio
async def test_render_proposta_sets_ready():
    tenant_id = uuid.uuid4()
    proposal = _make_proposal(tenant_id)
    session = AsyncMock()
    session.get = AsyncMock(return_value=proposal)
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    storage = AsyncMock()
    storage.put = AsyncMock(return_value=f"{tenant_id}/proposals/{proposal.id}/proposta.pdf")

    ctx = {"session_factory": session_factory, "storage_backend": storage}

    with patch("finacialsim_saas.workers.tasks.HTML") as mock_html:
        mock_html.return_value.write_pdf.return_value = b"%PDF-1.4 fake"
        await render_proposta_pdf(ctx, str(proposal.id))

    assert proposal.render_status == ProposalRenderStatus.ready
    assert proposal.status == ProposalStatus.ready
    assert proposal.pdf_key is not None
    storage.put.assert_called_once()


@pytest.mark.asyncio
async def test_render_proposta_sets_failed_on_exception():
    tenant_id = uuid.uuid4()
    proposal = _make_proposal(tenant_id)
    session = AsyncMock()
    session.get = AsyncMock(return_value=proposal)
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    ctx = {"session_factory": session_factory, "storage_backend": AsyncMock()}

    with patch("finacialsim_saas.workers.tasks.HTML") as mock_html:
        mock_html.return_value.write_pdf.side_effect = RuntimeError("render boom")
        await render_proposta_pdf(ctx, str(proposal.id))

    assert proposal.render_status == ProposalRenderStatus.failed
    assert proposal.render_error is not None
    assert "render boom" in proposal.render_error


@pytest.mark.asyncio
async def test_render_proposta_not_found_is_silent():
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    ctx = {"session_factory": session_factory, "storage_backend": AsyncMock()}
    # Must not raise
    await render_proposta_pdf(ctx, str(uuid.uuid4()))
```

- [ ] **Step 7.2 — Run to verify failure**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_render_tasks.py -v
```
Expected: `ImportError` — `render_proposta_pdf` not in `tasks.py` yet.

- [ ] **Step 7.3 — Add render tasks to workers/tasks.py**

Append to `backend/finacialsim_saas/workers/tasks.py`:
```python
import uuid as _uuid
from pathlib import Path as _Path

from jinja2 import Environment as _Env, FileSystemLoader as _FSL
from weasyprint import CSS as _CSS, HTML as _HTML

from finacialsim_saas.data.models import (
    Proposal as _Proposal,
    ProposalRenderStatus as _PRS,
    ProposalStatus as _PS,
)
from finacialsim_saas.schemas.proposals import PropostaSnapshot as _Snap
from finacialsim_saas.storage import StorageBackend as _SB
from finacialsim_saas.utils.br_format import (
    format_brl as _fbrl, format_date_br as _fdate,
    format_pct as _fpct, format_cpf_cnpj as _fcpf,
)

_REPORTS = _Path(__file__).resolve().parents[1] / "reports"
_jinja = _Env(loader=_FSL(str(_REPORTS)), autoescape=True)

_MODALIDADE_LABEL = {
    "mensal_continuo": "Mensal contínuo",
    "rateio_meses": "Rateio em meses",
    "unico_inicial": "Único (1ª parcela)",
}


def _proposta_ctx(snap: _Snap, proposal: _Proposal) -> dict:
    from decimal import Decimal
    from datetime import date

    def _d(s: object) -> Decimal:
        return Decimal(str(s))

    s = snap.sim
    rows = snap.cronograma
    n = len(rows)
    pt1 = _d(rows[0].parcela_total) if rows else Decimal("0")
    pta = _d(rows[min(11, n - 1)].parcela_total) if rows else Decimal("0")
    pct_e = _d(s.valor_entrada) / _d(s.valor_veiculo) if _d(s.valor_veiculo) else Decimal("0")
    pct_j = _d(s.total_juros) / _d(s.valor_financiado) if _d(s.valor_financiado) else Decimal("0")
    total_cliente = _d(s.total_pago) + _d(s.extras_acumulado)

    return {
        "loja": snap.loja.model_dump(),
        "vendedor": snap.vendedor.model_dump(),
        "proposal": {
            "codigo": proposal.codigo,
            "gerado_em_br": _fdate(proposal.gerado_em.date()),
            "validade_dias": proposal.validade_dias,
        },
        "cliente": {
            "nome": snap.cliente.nome if snap.cliente else "",
            "tipo": snap.cliente.tipo if snap.cliente else "PF",
            "cpf_cnpj_fmt": _fcpf(snap.cliente.cpf_cnpj, snap.cliente.tipo) if snap.cliente else "",
            "telefone": snap.cliente.telefone if snap.cliente else None,
        },
        "veiculo": {
            "marca": snap.veiculo.marca if snap.veiculo else "",
            "modelo": snap.veiculo.modelo if snap.veiculo else "",
            "ano_modelo": snap.veiculo.ano_modelo if snap.veiculo else 0,
            "codigo_fipe": snap.veiculo.codigo_fipe if snap.veiculo else None,
            "mes_referencia_fipe": snap.veiculo.mes_referencia_fipe if snap.veiculo else None,
        },
        "sim": {
            "valor_veiculo_brl": _fbrl(_d(s.valor_veiculo)),
            "valor_financiado_brl": _fbrl(_d(s.valor_financiado)),
            "valor_entrada_brl": _fbrl(_d(s.valor_entrada)),
            "pct_entrada_pct": _fpct(pct_e),
            "prazo_meses": s.prazo_meses,
            "taxa_juros_mes_pct": _fpct(_d(s.taxa_mensal), 4),
            "taxa_juros_ano_pct": _fpct(_d(s.taxa_anual), 2),
            "cet_mes_pct": _fpct(_d(s.cet_mensal), 4),
            "cet_ano_pct": _fpct(_d(s.cet_anual), 2),
            "incluir_iof": s.incluir_iof,
            "iof_total_brl": _fbrl(_d(s.iof_total)),
            "tarifas_total_brl": _fbrl(_d(s.tarifas_total)),
            "valor_parcela_brl": _fbrl(_d(s.valor_parcela)),
            "parcela_total_1ano_brl": _fbrl(pt1),
            "parcela_total_apos_brl": _fbrl(pta),
            "total_pago_brl": _fbrl(_d(s.total_pago)),
            "total_juros_brl": _fbrl(_d(s.total_juros)),
            "pct_juros_pct": _fpct(pct_j),
            "total_pago_cliente_brl": _fbrl(total_cliente),
        },
        "extras": [
            {
                "nome": e.nome,
                "modalidade_label": _MODALIDADE_LABEL.get(e.modalidade, e.modalidade),
                "valor_total_brl": _fbrl(_d(e.valor_total)),
                "duracao_meses": e.duracao_meses,
                "valor_por_parcela_brl": _fbrl(_d(e.valor_por_parcela)),
            }
            for e in snap.extras
        ],
        "cronograma": [
            {
                "numero": r.numero,
                "venc": _fdate(date.fromisoformat(r.venc)),
                "juros_brl": _fbrl(_d(r.juros)),
                "amortizacao_brl": _fbrl(_d(r.amortizacao)),
                "parcela_brl": _fbrl(_d(r.parcela)),
                "extras_brl": _fbrl(_d(r.extras)),
                "parcela_total_brl": _fbrl(_d(r.parcela_total)),
                "saldo_brl": _fbrl(_d(r.saldo)),
            }
            for r in snap.cronograma
        ],
    }


def _carne_ctx(snap: _Snap, proposal: _Proposal) -> dict:
    from decimal import Decimal
    from datetime import date

    def _d(s: object) -> Decimal:
        return Decimal(str(s))

    total = len(snap.cronograma)
    return {
        "loja": snap.loja.model_dump(),
        "proposal": {"codigo": proposal.codigo},
        "cliente": {
            "nome": snap.cliente.nome if snap.cliente else "",
            "cpf_cnpj_fmt": _fcpf(snap.cliente.cpf_cnpj, snap.cliente.tipo)
            if snap.cliente else "",
        },
        "veiculo": {
            "descricao": snap.veiculo.descricao if snap.veiculo else "",
            "placa": snap.veiculo.placa if snap.veiculo else None,
        },
        "parcelas": [
            {
                "numero": r.numero,
                "total": total,
                "vencimento_br": _fdate(date.fromisoformat(r.venc)),
                "valor_total_brl": _fbrl(_d(r.parcela_total)),
            }
            for r in snap.cronograma
        ],
    }


async def render_proposta_pdf(ctx: dict, proposal_id: str) -> None:
    session_factory = ctx["session_factory"]
    storage: _SB = ctx["storage_backend"]

    async with session_factory() as session:
        proposal = await session.get(_Proposal, _uuid.UUID(proposal_id))
        if proposal is None:
            logger.error(f"render_proposta_pdf: proposal {proposal_id} not found")
            return

        proposal.render_status = _PRS.rendering
        await session.commit()

        try:
            snap = _Snap.model_validate(proposal.snapshot_json)
            html_str = _jinja.get_template("proposta.html").render(**_proposta_ctx(snap, proposal))
            css_path = _REPORTS / "proposta.css"
            stylesheets = [_CSS(filename=str(css_path))] if css_path.exists() else []
            pdf = _HTML(string=html_str).write_pdf(stylesheets=stylesheets)

            key = f"{proposal.tenant_id}/proposals/{proposal.id}/proposta.pdf"
            await storage.put(key, pdf, "application/pdf")

            proposal.pdf_key = key
            proposal.render_status = _PRS.ready
            proposal.status = _PS.ready
            await session.commit()
            logger.info(f"render_proposta_pdf: {proposal_id} → {len(pdf):,} bytes")

        except Exception as exc:
            logger.exception(f"render_proposta_pdf: {proposal_id} failed")
            proposal.render_status = _PRS.failed
            proposal.render_error = str(exc)[:1000]
            await session.commit()


async def render_carne_pdf(ctx: dict, proposal_id: str) -> None:
    session_factory = ctx["session_factory"]
    storage: _SB = ctx["storage_backend"]

    async with session_factory() as session:
        proposal = await session.get(_Proposal, _uuid.UUID(proposal_id))
        if proposal is None:
            return

        try:
            snap = _Snap.model_validate(proposal.snapshot_json)
            html_str = _jinja.get_template("carne.html").render(**_carne_ctx(snap, proposal))
            css_path = _REPORTS / "carne.css"
            stylesheets = [_CSS(filename=str(css_path))] if css_path.exists() else []
            pdf = _HTML(string=html_str).write_pdf(stylesheets=stylesheets)

            key = f"{proposal.tenant_id}/proposals/{proposal.id}/carne.pdf"
            await storage.put(key, pdf, "application/pdf")

            proposal.carne_key = key
            await session.commit()
            logger.info(f"render_carne_pdf: {proposal_id} → {len(pdf):,} bytes")

        except Exception as exc:
            logger.exception(f"render_carne_pdf: {proposal_id} failed")
            proposal.render_error = f"carne: {str(exc)[:990]}"
            await session.commit()
```

- [ ] **Step 7.4 — Update WorkerSettings**

Edit `backend/finacialsim_saas/workers/worker.py`. Add imports and update `startup` + `WorkerSettings`:

```python
from arq import func  # add to imports

# In startup():
from finacialsim_saas.settings import get_settings as _get_settings
from finacialsim_saas.storage.deps import get_storage_backend as _get_storage

async def startup(ctx: dict) -> None:
    settings = get_settings()
    engine = build_engine(str(settings.database_url))
    ctx["engine"] = engine
    ctx["session_factory"] = build_session_factory(engine)
    ctx["http_client"] = httpx.AsyncClient(timeout=10.0)
    ctx["bacen_chain"] = ProviderChain([
        BcbSgsProvider(ctx["http_client"]),
        BrasilApiBacenProvider(ctx["http_client"]),
    ])
    ctx["storage_backend"] = _get_storage(settings)
```

In `WorkerSettings`:
```python
from finacialsim_saas.workers.tasks import (
    ping, prune_fipe_cache, update_bacen_indicators,
    verify_provider_health, render_proposta_pdf, render_carne_pdf,
)

class WorkerSettings:
    functions = [
        ping,
        func(render_proposta_pdf, timeout=120),
        func(render_carne_pdf, timeout=120),
    ]
    # ... rest unchanged
```

- [ ] **Step 7.5 — Run render task tests**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_render_tasks.py -v
```
Expected: all 3 tests PASS.

- [ ] **Step 7.6 — Commit**

```bash
git add backend/finacialsim_saas/workers/tasks.py \
        backend/finacialsim_saas/workers/worker.py \
        backend/tests/test_render_tasks.py
git commit -m "feat(phase5): add render_proposta_pdf + render_carne_pdf worker tasks (120s timeout)"
```

---

## Task 8: API endpoints

**Files:**
- Create: `backend/finacialsim_saas/api/proposals.py`
- Modify: `backend/finacialsim_saas/main.py`

- [ ] **Step 8.1 — Create proposals router**

Create `backend/finacialsim_saas/api/proposals.py`:
```python
"""Proposal API endpoints."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_current_ctx, get_db_session, require_role
from finacialsim_saas.data.models import Role
from finacialsim_saas.schemas.proposals import ProposalCreate, ProposalListPage, ProposalOut
from finacialsim_saas.services.proposal_service import ProposalService
from finacialsim_saas.settings import get_settings
from finacialsim_saas.storage.deps import get_storage_backend

router = APIRouter(prefix="/api/v1/proposals", tags=["proposals"])


def _svc(request: Request, session: AsyncSession) -> ProposalService:
    settings = get_settings()
    return ProposalService(
        session=session,
        arq=request.app.state.arq,
        storage=get_storage_backend(settings),
    )


@router.post("", status_code=202, response_model=ProposalOut)
async def create_proposal(
    body: ProposalCreate,
    request: Request,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProposalOut:
    svc = _svc(request, session)
    proposal = await svc.create(body.simulation_id, ctx)
    return ProposalOut(
        id=proposal.id,
        tenant_id=proposal.tenant_id,
        simulation_id=proposal.simulation_id,
        codigo=proposal.codigo,
        gerado_por=proposal.gerado_por,
        gerado_em=proposal.gerado_em,
        validade_dias=proposal.validade_dias,
        render_status=proposal.render_status.value,
        render_error=proposal.render_error,
        status=proposal.status.value,
        pdf_key=proposal.pdf_key,
        carne_key=proposal.carne_key,
        aprovado_por=proposal.aprovado_por,
        aprovado_em=proposal.aprovado_em,
        cancelado_por=proposal.cancelado_por,
        cancelado_em=proposal.cancelado_em,
    )


@router.get("", response_model=ProposalListPage)
async def list_proposals(
    request: Request,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    status: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
) -> ProposalListPage:
    return await _svc(request, session).list(ctx, status=status, cursor=cursor, limit=limit)


@router.get("/{proposal_id}", response_model=ProposalOut)
async def get_proposal(
    proposal_id: uuid.UUID,
    request: Request,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProposalOut:
    p = await _svc(request, session).get(proposal_id, ctx)
    return ProposalOut(
        id=p.id, tenant_id=p.tenant_id, simulation_id=p.simulation_id,
        codigo=p.codigo, gerado_por=p.gerado_por, gerado_em=p.gerado_em,
        validade_dias=p.validade_dias, render_status=p.render_status.value,
        render_error=p.render_error, status=p.status.value,
        pdf_key=p.pdf_key, carne_key=p.carne_key,
        aprovado_por=p.aprovado_por, aprovado_em=p.aprovado_em,
        cancelado_por=p.cancelado_por, cancelado_em=p.cancelado_em,
    )


@router.post("/{proposal_id}/approve", response_model=ProposalOut)
async def approve_proposal(
    proposal_id: uuid.UUID,
    request: Request,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProposalOut:
    p = await _svc(request, session).approve(proposal_id, ctx)
    return ProposalOut(
        id=p.id, tenant_id=p.tenant_id, simulation_id=p.simulation_id,
        codigo=p.codigo, gerado_por=p.gerado_por, gerado_em=p.gerado_em,
        validade_dias=p.validade_dias, render_status=p.render_status.value,
        render_error=p.render_error, status=p.status.value,
        pdf_key=p.pdf_key, carne_key=p.carne_key,
        aprovado_por=p.aprovado_por, aprovado_em=p.aprovado_em,
        cancelado_por=p.cancelado_por, cancelado_em=p.cancelado_em,
    )


@router.post("/{proposal_id}/cancel", response_model=ProposalOut)
async def cancel_proposal(
    proposal_id: uuid.UUID,
    request: Request,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProposalOut:
    p = await _svc(request, session).cancel(proposal_id, ctx)
    return ProposalOut(
        id=p.id, tenant_id=p.tenant_id, simulation_id=p.simulation_id,
        codigo=p.codigo, gerado_por=p.gerado_por, gerado_em=p.gerado_em,
        validade_dias=p.validade_dias, render_status=p.render_status.value,
        render_error=p.render_error, status=p.status.value,
        pdf_key=p.pdf_key, carne_key=p.carne_key,
        aprovado_por=p.aprovado_por, aprovado_em=p.aprovado_em,
        cancelado_por=p.cancelado_por, cancelado_em=p.cancelado_em,
    )


@router.post("/{proposal_id}/render-carne", status_code=202, response_model=ProposalOut)
async def render_carne(
    proposal_id: uuid.UUID,
    request: Request,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProposalOut:
    p = await _svc(request, session).create_carne(proposal_id, ctx)
    return ProposalOut(
        id=p.id, tenant_id=p.tenant_id, simulation_id=p.simulation_id,
        codigo=p.codigo, gerado_por=p.gerado_por, gerado_em=p.gerado_em,
        validade_dias=p.validade_dias, render_status=p.render_status.value,
        render_error=p.render_error, status=p.status.value,
        pdf_key=p.pdf_key, carne_key=p.carne_key,
        aprovado_por=p.aprovado_por, aprovado_em=p.aprovado_em,
        cancelado_por=p.cancelado_por, cancelado_em=p.cancelado_em,
    )


@router.get("/{proposal_id}/download")
async def download_proposal(
    proposal_id: uuid.UUID,
    request: Request,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    kind: str = Query(default="proposta"),
) -> RedirectResponse:
    url = await _svc(request, session).download_pdf(proposal_id, kind, ctx)
    return RedirectResponse(url, status_code=302)


@router.post("/{proposal_id}/re-render")
async def re_render(
    proposal_id: uuid.UUID,
    request: Request,
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    kind: str = Query(default="proposta"),
) -> ProposalOut:
    p = await _svc(request, session).re_render(proposal_id, kind, ctx)
    return ProposalOut(
        id=p.id, tenant_id=p.tenant_id, simulation_id=p.simulation_id,
        codigo=p.codigo, gerado_por=p.gerado_por, gerado_em=p.gerado_em,
        validade_dias=p.validade_dias, render_status=p.render_status.value,
        render_error=p.render_error, status=p.status.value,
        pdf_key=p.pdf_key, carne_key=p.carne_key,
        aprovado_por=p.aprovado_por, aprovado_em=p.aprovado_em,
        cancelado_por=p.cancelado_por, cancelado_em=p.cancelado_em,
    )
```

- [ ] **Step 8.2 — Register routers in main.py**

Edit `backend/finacialsim_saas/main.py`. Add at the bottom (following existing pattern):
```python
from finacialsim_saas.api.proposals import router as proposals_router  # noqa: E402
from finacialsim_saas.api.storage import router as storage_router      # noqa: E402

app.include_router(proposals_router)
app.include_router(storage_router)
```

- [ ] **Step 8.3 — Run lint check**

```bash
cd /home/fj/git/financialsim-saas
uv run ruff check backend/
```
Expected: no errors.

- [ ] **Step 8.4 — Commit**

```bash
git add backend/finacialsim_saas/api/proposals.py \
        backend/finacialsim_saas/main.py
git commit -m "feat(phase5): proposals API endpoints (create/get/list/approve/cancel/carne/download/re-render)"
```

---

## Phase 5B complete

All services, worker tasks, and API endpoints are in place. Proceed to `2026-06-01-saas-phase-5c-tests.md`.
