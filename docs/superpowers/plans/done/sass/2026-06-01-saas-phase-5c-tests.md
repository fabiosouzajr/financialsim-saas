# Phase 5C — Integration Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Full integration test coverage for the proposal lifecycle, API tenant isolation, and storage contract test (Local + MinIO).

**Architecture:** Tests use testcontainers (Postgres + Redis already wired in conftest). Storage contract test adds a MinIO testcontainer. All tests exercise real DB via session fixture.

**Tech Stack:** pytest, pytest-asyncio, testcontainers, httpx (ASGI), MinIO via testcontainers S3

**Prerequisite:** Phase 5A + 5B complete and all unit tests green.

---

## Task 9: Integration tests — ProposalService

**Files:**
- Test: `backend/tests/test_proposal_service.py`

Note: these tests hit a real Postgres (via testcontainers). They reuse the `db_url`, `engine`, `session_factory` fixtures from `conftest.py`.

- [ ] **Step 9.1 — Write tests**

Create `backend/tests/test_proposal_service.py`:
```python
"""Integration tests for ProposalService against a real Postgres."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.models import (
    AmortizationRow, NotificationsOutbox, ParcelaPayment, ParcelaPaymentStatus,
    Proposal, ProposalRenderStatus, ProposalStatus, Role, Simulation,
    SimulationStatus, Tenant,
)
from finacialsim_saas.errors import ConflictError, NotFoundError, ValidationError
from finacialsim_saas.services.proposal_service import ProposalService
from finacialsim_saas.storage.local import LocalVolumeBackend


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
async def tenant(session_factory) -> Tenant:
    async with session_factory() as s:
        t = Tenant(name="Loja Teste", slug=f"loja-{uuid.uuid4().hex[:6]}")
        s.add(t)
        await s.commit()
        await s.refresh(t)
        return t


@pytest.fixture
async def ctx_and_session(tenant, session_factory):
    """Returns (ctx, session) for a vendedor user in the test tenant."""
    async with session_factory() as s:
        svc = AuthService(s)
        email = f"v-{uuid.uuid4().hex[:8]}@test.com"
        user = await svc.register_user(
            tenant_id=tenant.id, email=email, name="Vendedor", password="pw123", role=Role.user
        )
        await s.commit()
        await s.refresh(user)
        ctx = RequestContext(
            user_id=user.id, tenant_id=tenant.id, role=Role.user, iat=0.0
        )
        return ctx, s


@pytest.fixture
async def admin_ctx(tenant, session_factory):
    async with session_factory() as s:
        svc = AuthService(s)
        email = f"a-{uuid.uuid4().hex[:8]}@test.com"
        user = await svc.register_user(
            tenant_id=tenant.id, email=email, name="Admin", password="pw123", role=Role.admin
        )
        await s.commit()
        await s.refresh(user)
        return RequestContext(
            user_id=user.id, tenant_id=tenant.id, role=Role.admin, iat=0.0
        )


async def _seed_simulation(session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID) -> Simulation:
    from finacialsim_saas.data.models import BusinessRule, SimulationCounter
    # Minimal simulation with 3 amortization rows
    sim = Simulation(
        tenant_id=tenant_id,
        codigo=f"SIM-{uuid.uuid4().hex[:6]}",
        valor_veiculo=Decimal("85000.00"),
        valor_entrada=Decimal("17000.00"),
        valor_financiado=Decimal("68000.00"),
        taxa_mensal=Decimal("0.012900"),
        prazo_meses=48,
        data_liberacao=date(2026, 6, 1),
        primeiro_vencimento=date(2026, 7, 1),
        incluir_iof=True,
        iof_total=Decimal("1224.00"),
        parcela_financiamento=Decimal("1987.34"),
        total_pago=Decimal("95392.32"),
        total_juros=Decimal("27392.32"),
        cet_mensal=Decimal("0.013500"),
        cet_anual=Decimal("0.174500"),
        status=SimulationStatus.confirmado,
        rules_snapshot_json={},
        criado_por=user_id,
    )
    session.add(sim)
    await session.flush()
    for i in range(1, 4):
        session.add(AmortizationRow(
            simulation_id=sim.id,
            tenant_id=tenant_id,
            numero_parcela=i,
            data_vencimento=date(2026, 6 + i, 1),
            dias_periodo=30,
            saldo_anterior=Decimal("68000.00") - (i - 1) * Decimal("1110.14"),
            juros=Decimal("877.20"),
            amortizacao=Decimal("1110.14"),
            parcela=Decimal("1987.34"),
            saldo_devedor=Decimal("68000.00") - i * Decimal("1110.14"),
            extras_total=Decimal("0.00"),
            parcela_total=Decimal("1987.34"),
            ajuste_arredondamento=Decimal("0.00"),
        ))
    await session.commit()
    await session.refresh(sim)
    return sim


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_proposal_returns_pending(ctx_and_session, session_factory, tmp_path):
    ctx, session = ctx_and_session
    sim = await _seed_simulation(session, ctx.tenant_id, ctx.user_id)
    arq = AsyncMock()
    storage = LocalVolumeBackend(root=tmp_path, secret="s", base_url="http://localhost:8000")

    svc = ProposalService(session, arq, storage)
    proposal = await svc.create(sim.id, ctx)

    assert proposal.render_status == ProposalRenderStatus.pending
    assert proposal.status == ProposalStatus.rascunho
    assert proposal.codigo.startswith("PROP-2026-")
    arq.enqueue_job.assert_called_once_with("render_proposta_pdf", str(proposal.id))


@pytest.mark.asyncio
async def test_create_proposal_duplicate_raises_409(ctx_and_session, session_factory, tmp_path):
    ctx, session = ctx_and_session
    sim = await _seed_simulation(session, ctx.tenant_id, ctx.user_id)
    arq = AsyncMock()
    storage = LocalVolumeBackend(root=tmp_path, secret="s", base_url="http://localhost:8000")

    svc = ProposalService(session, arq, storage)
    await svc.create(sim.id, ctx)
    with pytest.raises(ConflictError):
        await svc.create(sim.id, ctx)


@pytest.mark.asyncio
async def test_create_proposal_rascunho_sim_raises(ctx_and_session, session_factory, tmp_path):
    ctx, session = ctx_and_session
    sim = await _seed_simulation(session, ctx.tenant_id, ctx.user_id)
    sim.status = SimulationStatus.rascunho
    await session.commit()

    arq = AsyncMock()
    storage = LocalVolumeBackend(root=tmp_path, secret="s", base_url="http://localhost:8000")
    svc = ProposalService(session, arq, storage)
    with pytest.raises(ValidationError):
        await svc.create(sim.id, ctx)


@pytest.mark.asyncio
async def test_approve_generates_parcela_payments(ctx_and_session, session_factory, tmp_path):
    ctx, session = ctx_and_session
    sim = await _seed_simulation(session, ctx.tenant_id, ctx.user_id)
    arq = AsyncMock()
    storage = LocalVolumeBackend(root=tmp_path, secret="s", base_url="http://localhost:8000")

    svc = ProposalService(session, arq, storage)
    proposal = await svc.create(sim.id, ctx)

    # Simulate worker setting status=ready
    proposal.render_status = ProposalRenderStatus.ready
    proposal.status = ProposalStatus.ready
    await session.commit()

    await svc.approve(proposal.id, ctx)

    payments = list(await session.scalars(
        select(ParcelaPayment).where(ParcelaPayment.proposal_id == proposal.id)
    ))
    assert len(payments) == 3  # 3 amortization rows
    assert all(p.status == ParcelaPaymentStatus.pending for p in payments)


@pytest.mark.asyncio
async def test_approve_writes_customer_invite_outbox(ctx_and_session, session_factory, tmp_path):
    ctx, session = ctx_and_session
    sim = await _seed_simulation(session, ctx.tenant_id, ctx.user_id)
    arq = AsyncMock()
    storage = LocalVolumeBackend(root=tmp_path, secret="s", base_url="http://localhost:8000")

    svc = ProposalService(session, arq, storage)
    proposal = await svc.create(sim.id, ctx)
    proposal.render_status = ProposalRenderStatus.ready
    proposal.status = ProposalStatus.ready
    await session.commit()
    await svc.approve(proposal.id, ctx)

    outbox = list(await session.scalars(
        select(NotificationsOutbox)
        .where(NotificationsOutbox.tenant_id == ctx.tenant_id)
        .where(NotificationsOutbox.type == "customer_invite")
    ))
    assert len(outbox) == 1
    assert outbox[0].payload["proposal_id"] == str(proposal.id)


@pytest.mark.asyncio
async def test_cancel_cascades_parcela_payments(ctx_and_session, session_factory, tmp_path):
    ctx, session = ctx_and_session
    sim = await _seed_simulation(session, ctx.tenant_id, ctx.user_id)
    arq = AsyncMock()
    storage = LocalVolumeBackend(root=tmp_path, secret="s", base_url="http://localhost:8000")

    svc = ProposalService(session, arq, storage)
    proposal = await svc.create(sim.id, ctx)
    proposal.render_status = ProposalRenderStatus.ready
    proposal.status = ProposalStatus.ready
    await session.commit()
    await svc.approve(proposal.id, ctx)
    await svc.cancel(proposal.id, ctx)

    payments = list(await session.scalars(
        select(ParcelaPayment).where(ParcelaPayment.proposal_id == proposal.id)
    ))
    assert all(p.status == ParcelaPaymentStatus.canceled for p in payments)
    assert proposal.status == ProposalStatus.cancelada


@pytest.mark.asyncio
async def test_create_carne_rejects_non_aprovada(ctx_and_session, session_factory, tmp_path):
    ctx, session = ctx_and_session
    sim = await _seed_simulation(session, ctx.tenant_id, ctx.user_id)
    arq = AsyncMock()
    storage = LocalVolumeBackend(root=tmp_path, secret="s", base_url="http://localhost:8000")

    svc = ProposalService(session, arq, storage)
    proposal = await svc.create(sim.id, ctx)  # status=rascunho

    with pytest.raises(ValidationError, match="approved"):
        await svc.create_carne(proposal.id, ctx)
```

- [ ] **Step 9.2 — Run tests**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_proposal_service.py -v
```
Expected: all 7 tests PASS.

- [ ] **Step 9.3 — Commit**

```bash
git add backend/tests/test_proposal_service.py
git commit -m "test(phase5): ProposalService integration tests (create/approve/cancel/carne)"
```

---

## Task 10: Integration tests — Proposals API + tenant isolation

**Files:**
- Test: `backend/tests/test_proposal_endpoints.py`

These tests use httpx + ASGI transport against a real DB (same pattern as `test_simulation_endpoints.py`).

- [ ] **Step 10.1 — Write tests**

Create `backend/tests/test_proposal_endpoints.py`:
```python
"""Integration tests for proposal API endpoints."""
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from finacialsim_saas.data.models import (
    AmortizationRow, ProposalRenderStatus, ProposalStatus,
    Role, Simulation, SimulationStatus, Tenant,
)
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.main import app


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _login(client: AsyncClient, email: str, password: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


async def _seed_tenant_user_sim(session_factory) -> tuple:
    """Returns (tenant, token, sim_id) for a fresh vendedor."""
    async with session_factory() as s:
        t = Tenant(name="TenantAPI", slug=f"api-{uuid.uuid4().hex[:6]}")
        s.add(t)
        await s.flush()
        svc = AuthService(s)
        email = f"v-{uuid.uuid4().hex[:8]}@test.com"
        user = await svc.register_user(
            tenant_id=t.id, email=email, name="Vend", password="pw123", role=Role.user
        )
        await s.flush()
        sim = Simulation(
            tenant_id=t.id,
            codigo=f"SIM-{uuid.uuid4().hex[:6]}",
            valor_veiculo=Decimal("85000.00"),
            valor_entrada=Decimal("17000.00"),
            valor_financiado=Decimal("68000.00"),
            taxa_mensal=Decimal("0.012900"),
            prazo_meses=48,
            data_liberacao=date(2026, 6, 1),
            primeiro_vencimento=date(2026, 7, 1),
            incluir_iof=True,
            iof_total=Decimal("1224.00"),
            parcela_financiamento=Decimal("1987.34"),
            total_pago=Decimal("95392.32"),
            total_juros=Decimal("27392.32"),
            cet_mensal=Decimal("0.013500"),
            cet_anual=Decimal("0.174500"),
            status=SimulationStatus.confirmado,
            rules_snapshot_json={},
            criado_por=user.id,
        )
        s.add(sim)
        await s.flush()
        for i in range(1, 4):
            s.add(AmortizationRow(
                simulation_id=sim.id, tenant_id=t.id,
                numero_parcela=i, data_vencimento=date(2026, 6 + i, 1),
                dias_periodo=30,
                saldo_anterior=Decimal("68000.00") - (i - 1) * Decimal("1110.14"),
                juros=Decimal("877.20"), amortizacao=Decimal("1110.14"),
                parcela=Decimal("1987.34"),
                saldo_devedor=Decimal("68000.00") - i * Decimal("1110.14"),
                extras_total=Decimal("0.00"), parcela_total=Decimal("1987.34"),
                ajuste_arredondamento=Decimal("0.00"),
            ))
        await s.commit()
        return t, email, user.id, str(sim.id)


@pytest.fixture
async def client(session_factory, engine):
    app.state.session_factory = session_factory
    from arq import create_pool
    from arq.connections import RedisSettings
    from finacialsim_saas.settings import get_settings
    settings = get_settings()
    app.state.arq = await create_pool(RedisSettings.from_dsn(str(settings.redis_url)))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    await app.state.arq.aclose()


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_proposal_returns_202(client, session_factory):
    _, email, _, sim_id = await _seed_tenant_user_sim(session_factory)
    token = await _login(client, email, "pw123")
    with patch("finacialsim_saas.workers.tasks.HTML"):
        r = await client.post(
            "/api/v1/proposals",
            json={"simulation_id": sim_id},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 202
    body = r.json()
    assert body["render_status"] == "pending"
    assert body["status"] == "rascunho"
    assert body["codigo"].startswith("PROP-")


@pytest.mark.asyncio
async def test_duplicate_proposal_returns_409(client, session_factory):
    _, email, _, sim_id = await _seed_tenant_user_sim(session_factory)
    token = await _login(client, email, "pw123")
    headers = {"Authorization": f"Bearer {token}"}
    r1 = await client.post("/api/v1/proposals", json={"simulation_id": sim_id}, headers=headers)
    assert r1.status_code == 202
    r2 = await client.post("/api/v1/proposals", json={"simulation_id": sim_id}, headers=headers)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_cross_tenant_get_returns_404(client, session_factory):
    """Tenant A cannot read tenant B's proposal."""
    _, email_a, _, sim_a = await _seed_tenant_user_sim(session_factory)
    _, email_b, _, _ = await _seed_tenant_user_sim(session_factory)
    token_a = await _login(client, email_a, "pw123")
    token_b = await _login(client, email_b, "pw123")

    r = await client.post(
        "/api/v1/proposals",
        json={"simulation_id": sim_a},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    proposal_id = r.json()["id"]

    r2 = await client.get(
        f"/api/v1/proposals/{proposal_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_get_proposal_returns_render_status(client, session_factory):
    _, email, _, sim_id = await _seed_tenant_user_sim(session_factory)
    token = await _login(client, email, "pw123")
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post("/api/v1/proposals", json={"simulation_id": sim_id}, headers=headers)
    proposal_id = r.json()["id"]

    r2 = await client.get(f"/api/v1/proposals/{proposal_id}", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["render_status"] in ("pending", "rendering", "ready", "failed")


@pytest.mark.asyncio
async def test_approve_requires_ready_status(client, session_factory):
    """Approval rejected if render_status != ready."""
    _, email, _, sim_id = await _seed_tenant_user_sim(session_factory)
    token = await _login(client, email, "pw123")
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post("/api/v1/proposals", json={"simulation_id": sim_id}, headers=headers)
    proposal_id = r.json()["id"]

    r2 = await client.post(f"/api/v1/proposals/{proposal_id}/approve", headers=headers)
    assert r2.status_code == 422  # not ready yet
```

- [ ] **Step 10.2 — Run tests**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_proposal_endpoints.py -v
```
Expected: all 5 tests PASS.

- [ ] **Step 10.3 — Commit**

```bash
git add backend/tests/test_proposal_endpoints.py
git commit -m "test(phase5): proposal API integration tests + cross-tenant isolation"
```

---

## Task 11: Storage contract test (Local + MinIO)

**Files:**
- Test: `backend/tests/test_storage_contract.py`

This test uses `testcontainers` to spin up a real MinIO instance. If MinIO is unavailable in the test environment, the S3 test is skipped via `pytest.mark.skip`.

- [ ] **Step 11.1 — Add S3Backend stub**

Create `backend/finacialsim_saas/storage/s3.py`:
```python
"""S3Backend — boto3 against any S3-compatible endpoint (AWS S3, MinIO, R2)."""
from __future__ import annotations

import time
import hashlib
import hmac

import boto3
from botocore.config import Config


class S3Backend:
    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        region: str = "us-east-1",
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            config=Config(signature_version="s3v4"),
        )

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        import asyncio
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket, Key=key, Body=data, ContentType=content_type,
        )
        return key

    async def get(self, key: str) -> bytes:
        import asyncio
        resp = await asyncio.to_thread(
            self._client.get_object, Bucket=self._bucket, Key=key
        )
        return resp["Body"].read()

    async def signed_url(self, key: str, expires_in: int = 300) -> str:
        import asyncio
        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    async def delete(self, key: str) -> None:
        import asyncio
        await asyncio.to_thread(
            self._client.delete_object, Bucket=self._bucket, Key=key
        )
```

- [ ] **Step 11.2 — Write the contract test**

Create `backend/tests/test_storage_contract.py`:
```python
"""
Storage backend contract test — same assertions pass both Local and S3 (MinIO).

The S3 fixture spins up MinIO via testcontainers. It is skipped if Docker is
unavailable (e.g. in some CI environments). Local always runs.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from finacialsim_saas.storage.local import LocalVolumeBackend

KEY = "tenant-abc/proposals/123/proposta.pdf"
DATA = b"%PDF-1.4 contract test content"
CONTENT_TYPE = "application/pdf"


@pytest.fixture
def local_backend(tmp_path: Path) -> LocalVolumeBackend:
    return LocalVolumeBackend(
        root=tmp_path, secret="contract-secret", base_url="http://localhost:8000"
    )


@pytest.fixture
def s3_backend():
    """MinIO via testcontainers — skipped if Docker unavailable."""
    try:
        from testcontainers.minio import MinioContainer
    except ImportError:
        pytest.skip("testcontainers[minio] not installed")

    try:
        minio = MinioContainer()
        minio.start()
    except Exception:
        pytest.skip("Docker unavailable — skipping MinIO contract test")

    import boto3
    client = boto3.client(
        "s3",
        endpoint_url=minio.get_url(),
        aws_access_key_id=minio.access_key,
        aws_secret_access_key=minio.secret_key,
        region_name="us-east-1",
    )
    client.create_bucket(Bucket="test-bucket")

    from finacialsim_saas.storage.s3 import S3Backend
    backend = S3Backend(
        bucket="test-bucket",
        endpoint_url=minio.get_url(),
        aws_access_key_id=minio.access_key,
        aws_secret_access_key=minio.secret_key,
    )
    yield backend
    minio.stop()


# ── Contract assertions ───────────────────────────────────────────────────────

async def _run_contract(backend) -> None:
    returned_key = await backend.put(KEY, DATA, CONTENT_TYPE)
    assert returned_key == KEY

    retrieved = await backend.get(KEY)
    assert retrieved == DATA

    url = await backend.signed_url(KEY, expires_in=300)
    assert isinstance(url, str)
    assert len(url) > 0

    await backend.delete(KEY)

    # Delete non-existent must be silent
    await backend.delete("does/not/exist.pdf")


@pytest.mark.asyncio
async def test_contract_local(local_backend):
    await _run_contract(local_backend)


@pytest.mark.asyncio
async def test_contract_s3(s3_backend):
    await _run_contract(s3_backend)
```

- [ ] **Step 11.3 — Add boto3 to dev deps**

Edit `backend/pyproject.toml`. Add to `[project.optional-dependencies] dev`:
```toml
"boto3>=1.34.0",
```

Run:
```bash
cd /home/fj/git/financialsim-saas
uv sync --extra dev
```

- [ ] **Step 11.4 — Run contract tests (local only — S3 skipped without Docker)**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_storage_contract.py -v
```
Expected:
- `test_contract_local` → PASS
- `test_contract_s3` → SKIPPED (if Docker Hub unreachable, as per WSL2 constraints) or PASS

- [ ] **Step 11.5 — Run full test suite**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/ -v --tb=short 2>&1 | tail -30
```
Expected: all tests PASS (no regressions from Phases 0–4).

- [ ] **Step 11.6 — Commit**

```bash
git add backend/finacialsim_saas/storage/s3.py \
        backend/tests/test_storage_contract.py \
        backend/pyproject.toml
git commit -m "test(phase5): storage contract test (Local + MinIO/S3); add S3Backend stub"
```

---

## Task 12: Lint + type-check pass

- [ ] **Step 12.1 — Run ruff**

```bash
cd /home/fj/git/financialsim-saas
uv run ruff check backend/
```
Fix any reported issues.

- [ ] **Step 12.2 — Run mypy**

```bash
cd /home/fj/git/financialsim-saas
uv run mypy backend/finacialsim_saas
```
Fix any type errors. Common expected issue: `StorageBackend` Protocol needs `@runtime_checkable` — already set in Phase 5B.

- [ ] **Step 12.3 — Commit fixes if any**

```bash
git add -u
git commit -m "fix(phase5): lint + type-check corrections"
```

---

## Phase 5C complete

All backend tests pass. Proceed to `2026-06-01-saas-phase-5d-frontend.md`.
