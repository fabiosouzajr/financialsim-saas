# Phase 6C — API Endpoints + Worker Cron Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add portal API endpoints, webhook endpoint, staff Pix admin endpoints, client invite endpoint. Register all in `main.py`. Add `mark_overdue_parcelas` ARQ cron job at 05:00 UTC.

**Architecture:** Three new API modules (`portal.py`, `webhooks.py`, `pix_admin.py`). One endpoint added to `clients.py`. Worker gains a `mark_overdue_parcelas` cron function and `pix_provider` in startup context.

**Tech Stack:** FastAPI, arq, SQLAlchemy async.

**Prerequisite:** Plans 6A + 6B complete (models, pix module, all services created).

---

## Task 1: Create api/portal.py

**Files:**

- Create: `backend/finacialsim_saas/api/portal.py`

- [ ] **Step 1: Create portal.py**

```python
"""Portal API endpoints — customer-facing (role=customer JWT required)."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_db_session, require_role
from finacialsim_saas.data.models import User
from finacialsim_saas.pix.deps import get_pix_provider
from finacialsim_saas.services.parcela_service import ParcelaService
from finacialsim_saas.services.proposal_service import ProposalService
from finacialsim_saas.settings import get_settings
from finacialsim_saas.storage.deps import get_storage_backend

router = APIRouter(prefix="/api/v1/portal", tags=["portal"])

_CustomerCtx = Annotated[RequestContext, Depends(require_role("customer"))]
_Session = Annotated[AsyncSession, Depends(get_db_session)]


def _parcela_svc(session: AsyncSession) -> ParcelaService:
    return ParcelaService(session)


def _pix_svc(request: Request, session: AsyncSession):
    from finacialsim_saas.pix.service import PixService
    settings = get_settings()
    return PixService(session, get_pix_provider(settings), get_storage_backend(settings))


def _proposal_svc(request: Request, session: AsyncSession) -> ProposalService:
    settings = get_settings()
    return ProposalService(
        session=session,
        arq=request.app.state.arq,
        storage=get_storage_backend(settings),
    )


@router.get("/me")
async def get_portal_me(
    ctx: _CustomerCtx,
    session: _Session,
) -> dict:
    user = await session.get(User, ctx.user_id)
    if user is None:
        from finacialsim_saas.errors import NotFoundError
        raise NotFoundError("user not found")
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role.value,
        "client_id": str(user.client_id) if user.client_id else None,
    }


@router.get("/financiamentos")
async def list_financiamentos(
    ctx: _CustomerCtx,
    session: _Session,
) -> list:
    return await _parcela_svc(session).list_for_customer(ctx)


@router.get("/financiamentos/{proposal_id}")
async def get_financiamento(
    proposal_id: uuid.UUID,
    ctx: _CustomerCtx,
    session: _Session,
) -> dict:
    return await _parcela_svc(session).get_schedule(proposal_id, ctx)


@router.get("/parcelas/{parcela_id}")
async def get_parcela(
    parcela_id: uuid.UUID,
    ctx: _CustomerCtx,
    session: _Session,
) -> dict:
    svc = _parcela_svc(session)
    p = await svc.get_parcela(parcela_id, ctx)
    return {
        "id": str(p.id),
        "parcela_num": p.parcela_num,
        "vencimento": p.vencimento.isoformat(),
        "valor_parcela": str(p.valor_parcela),
        "status": p.status.value,
        "paid_at": p.paid_at.isoformat() if p.paid_at else None,
        "paid_amount": str(p.paid_amount) if p.paid_amount else None,
    }


@router.post("/parcelas/{parcela_id}/pix-charge", status_code=201)
async def create_pix_charge(
    parcela_id: uuid.UUID,
    request: Request,
    ctx: _CustomerCtx,
    session: _Session,
) -> dict:
    svc = _pix_svc(request, session)
    charge, qr_url = await svc.create_charge_for_parcela(parcela_id, ctx)
    return {
        "charge_id": str(charge.id),
        "brcode": charge.brcode,
        "qr_url": qr_url,
        "expires_at": charge.expires_at.isoformat(),
    }


@router.get("/pix-charges/{charge_id}")
async def get_pix_charge(
    charge_id: uuid.UUID,
    request: Request,
    ctx: _CustomerCtx,
    session: _Session,
) -> dict:
    svc = _pix_svc(request, session)
    charge, qr_url = await svc.get_charge(charge_id, ctx)
    return {
        "charge_id": str(charge.id),
        "status": charge.status.value,
        "brcode": charge.brcode,
        "qr_url": qr_url,
        "expires_at": charge.expires_at.isoformat(),
    }


@router.get("/proposals/{proposal_id}/download")
async def download_portal_proposal(
    proposal_id: uuid.UUID,
    request: Request,
    ctx: _CustomerCtx,
    session: _Session,
    kind: str = Query(default="proposta"),
) -> RedirectResponse:
    svc = _proposal_svc(request, session)
    url = await svc.download_pdf(proposal_id, kind, ctx)
    return RedirectResponse(url, status_code=302)
```

- [ ] **Step 2: Verify import**

```bash
cd /home/fabio/git/financialsim-saas && uv run --directory backend python -c "from finacialsim_saas.api.portal import router; print('OK', len(router.routes), 'routes')"
```

Expected: `OK 7 routes`

- [ ] **Step 3: Commit**

```bash
git add backend/finacialsim_saas/api/portal.py
git commit -m "feat(phase6): add portal API (me, financiamentos, parcelas, pix-charge)"
```

---

### Task 2: Create api/webhooks.py

**Files:**

- Create: `backend/finacialsim_saas/api/webhooks.py`

- [ ] **Step 1: Create webhooks.py**

```python
"""PSP webhook endpoints — no JWT auth; HMAC-SHA256 verified per provider."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import get_db_session
from finacialsim_saas.pix.deps import get_pix_provider
from finacialsim_saas.pix.service import PixService
from finacialsim_saas.settings import get_settings
from finacialsim_saas.storage.deps import get_storage_backend

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

_Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.post("/pix")
async def pix_webhook(request: Request, session: _Session) -> dict:
    """Receives Pix PSP callbacks. Always returns 200. Logs everything."""
    body = await request.body()
    headers = dict(request.headers)
    settings = get_settings()
    svc = PixService(session, get_pix_provider(settings), get_storage_backend(settings))
    await svc.handle_webhook(headers, body)
    return {"ok": True}
```

- [ ] **Step 2: Verify import**

```bash
cd /home/fabio/git/financialsim-saas && uv run --directory backend python -c "from finacialsim_saas.api.webhooks import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/finacialsim_saas/api/webhooks.py
git commit -m "feat(phase6): add POST /webhooks/pix endpoint"
```

---

### Task 3: Create api/pix_admin.py

**Files:**

- Create: `backend/finacialsim_saas/api/pix_admin.py`

- [ ] **Step 1: Create pix_admin.py**

```python
"""Staff Pix admin endpoints — manager|admin only."""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_db_session, require_role
from finacialsim_saas.data.models import PixCharge, PixChargeStatus
from finacialsim_saas.pix.deps import get_pix_provider
from finacialsim_saas.pix.service import PixService
from finacialsim_saas.settings import get_settings
from finacialsim_saas.storage.deps import get_storage_backend

router = APIRouter(prefix="/api/v1/admin/pix", tags=["pix-admin"])

_StaffCtx = Annotated[RequestContext, Depends(require_role("manager", "admin"))]
_Session = Annotated[AsyncSession, Depends(get_db_session)]


def _pix_svc(request: Request, session: AsyncSession) -> PixService:
    settings = get_settings()
    return PixService(session, get_pix_provider(settings), get_storage_backend(settings))


@router.post("/fake/mark-paid/{txid}")
async def mark_paid(
    txid: str,
    request: Request,
    ctx: _StaffCtx,
    session: _Session,
) -> dict:
    """Fake-provider only: triggers webhook path to mark a charge as paid."""
    settings = get_settings()
    if settings.pix_provider == "external":
        raise HTTPException(status_code=501, detail="mark-paid not available for external provider")

    # Look up charge to get amount
    charge = await session.scalar(
        select(PixCharge).where(
            PixCharge.txid == txid,
            PixCharge.tenant_id == ctx.tenant_id,
        )
    )
    if charge is None:
        raise HTTPException(status_code=404, detail=f"charge with txid {txid!r} not found")
    if charge.status != PixChargeStatus.pending:
        raise HTTPException(
            status_code=409,
            detail=f"charge status is {charge.status.value}, cannot mark paid",
        )

    # Build webhook payload
    body_dict = {
        "pix": [
            {
                "txid": txid,
                "status": "paid",
                "valor": str(charge.amount),
            }
        ]
    }
    body = json.dumps(body_dict).encode()

    # Sign with PIX_WEBHOOK_SECRET
    if settings.pix_webhook_secret:
        sig = hmac.new(
            settings.pix_webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        headers = {"X-Pix-Signature": f"sha256={sig}", "Content-Type": "application/json"}
    else:
        headers = {"Content-Type": "application/json"}

    svc = _pix_svc(request, session)
    await svc.handle_webhook(headers, body)
    return {"txid": txid, "status": "paid"}


@router.get("/charges")
async def list_pix_charges(
    ctx: _StaffCtx,
    session: _Session,
    status: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
) -> dict:
    """List pix charges for this tenant with cursor pagination."""
    import base64

    q = select(PixCharge).where(PixCharge.tenant_id == ctx.tenant_id)
    if status:
        q = q.where(PixCharge.status == PixChargeStatus(status))
    if cursor:
        cur = json.loads(base64.b64decode(cursor))
        q = q.where(PixCharge.criado_em < cur["ts"])
    q = q.order_by(PixCharge.criado_em.desc()).limit(limit + 1)

    results = list(await session.scalars(q))
    has_more = len(results) > limit
    items = results[:limit]

    next_cursor = None
    if has_more:
        next_cursor = base64.b64encode(
            json.dumps({"ts": items[-1].criado_em.isoformat()}).encode()
        ).decode()

    return {
        "items": [
            {
                "id": str(c.id),
                "txid": c.txid,
                "status": c.status.value,
                "amount": str(c.amount),
                "expires_at": c.expires_at.isoformat(),
                "parcela_payment_id": str(c.parcela_payment_id),
            }
            for c in items
        ],
        "next_cursor": next_cursor,
    }
```

- [ ] **Step 2: Verify import**

```bash
cd /home/fabio/git/financialsim-saas && uv run --directory backend python -c "from finacialsim_saas.api.pix_admin import router; print('OK', len(router.routes), 'routes')"
```

Expected: `OK 2 routes`

- [ ] **Step 3: Commit**

```bash
git add backend/finacialsim_saas/api/pix_admin.py
git commit -m "feat(phase6): add pix admin endpoints (mark-paid, list charges)"
```

---

### Task 4: Add invite endpoint to api/clients.py

**Files:**

- Modify: `backend/finacialsim_saas/api/clients.py`

- [ ] **Step 1: Read current clients.py to understand structure**

```bash
cd /home/fabio/git/financialsim-saas && head -20 backend/finacialsim_saas/api/clients.py
```

- [ ] **Step 2: Add invite endpoint**

Append to the end of `backend/finacialsim_saas/api/clients.py`:

```python
@router.post("/{client_id}/invite", status_code=200)
async def invite_client_customer(
    client_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(require_role("manager", "admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    """Create or re-invite the customer user for a client. Invalidates old token."""
    from finacialsim_saas.auth.service import AuthService
    from finacialsim_saas.settings import get_settings
    from finacialsim_saas.errors import NotFoundError

    svc = AuthService(session, get_settings())

    # Try re-invite first (user may already exist)
    from finacialsim_saas.data.models import User, Role
    from sqlalchemy import select

    existing = await session.scalar(
        select(User).where(
            User.client_id == client_id,
            User.role == Role.customer,
            User.tenant_id == ctx.tenant_id,
        )
    )
    if existing is not None:
        user = await svc.re_invite(client_id, ctx)
    else:
        user = await svc.invite_customer(client_id, ctx)
    await session.commit()

    return {"user_id": str(user.id), "email": user.email, "status": "invited"}
```

Also add `uuid` import if not already present. Check the current imports at the top of clients.py.

- [ ] **Step 3: Verify import**

```bash
cd /home/fabio/git/financialsim-saas && uv run --directory backend python -c "from finacialsim_saas.api.clients import router; routes = [r.path for r in router.routes]; print(routes)"
```

Expected: includes `/{client_id}/invite`.

- [ ] **Step 4: Commit**

```bash
git add backend/finacialsim_saas/api/clients.py
git commit -m "feat(phase6): add POST /clients/{id}/invite endpoint"
```

---

### Task 5: Update main.py — register new routers

**Files:**

- Modify: `backend/finacialsim_saas/main.py`

- [ ] **Step 1: Add router imports and include calls**

After the existing `from finacialsim_saas.api.proposals import router as proposals_router` line, add:

```python
from finacialsim_saas.api.portal import router as portal_router                          # noqa: E402
from finacialsim_saas.api.webhooks import router as webhooks_router                      # noqa: E402
from finacialsim_saas.api.pix_admin import router as pix_admin_router                    # noqa: E402
```

After the existing `app.include_router(proposals_router)` line, add:

```python
app.include_router(portal_router)
app.include_router(webhooks_router)
app.include_router(pix_admin_router)
```

- [ ] **Step 2: Verify app starts without errors**

```bash
cd /home/fabio/git/financialsim-saas && uv run --directory backend python -c "from finacialsim_saas.main import app; print('routes:', len(app.routes))"
```

Expected: routes count increases (no ImportError).

- [ ] **Step 3: Commit**

```bash
git add backend/finacialsim_saas/main.py
git commit -m "feat(phase6): register portal, webhooks, pix_admin routers in main.py"
```

---

### Task 6: Add mark_overdue_parcelas cron to worker

**Files:**

- Modify: `backend/finacialsim_saas/workers/tasks.py`
- Modify: `backend/finacialsim_saas/workers/worker.py`

- [ ] **Step 1: Add mark_overdue_parcelas task to tasks.py**

Append to the end of `tasks.py`:

```python
# ── Phase 6: Parcela overdue cron ─────────────────────────────────────────────


async def mark_overdue_parcelas(ctx: dict) -> None:
    """Daily cron at 05:00 UTC: flip open parcelas past due to overdue."""
    from finacialsim_saas.services.parcela_service import ParcelaService

    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        svc = ParcelaService(session)
        await svc.mark_overdue()
    logger.info("mark_overdue_parcelas: complete")
```

- [ ] **Step 2: Register cron in worker.py**

In `worker.py`, add `mark_overdue_parcelas` import:

```python
from finacialsim_saas.workers.tasks import (
    mark_overdue_parcelas,
    ping,
    prune_fipe_cache,
    render_carne_pdf,
    render_proposta_pdf,
    update_bacen_indicators,
    verify_provider_health,
)
```

Add to `cron_jobs` list in `WorkerSettings`:

```python
        cron(mark_overdue_parcelas, hour=5, minute=0),   # 02:00 BRT = 05:00 UTC
```

Also add `pix_provider` to worker startup context (needed if worker ever calls PixService directly):

```python
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
    from finacialsim_saas.storage.deps import get_storage_backend as _get_storage
    ctx["storage_backend"] = _get_storage(settings)
    from finacialsim_saas.pix.deps import get_pix_provider as _get_pix
    ctx["pix_provider"] = _get_pix(settings)
```

- [ ] **Step 3: Verify worker imports**

```bash
cd /home/fabio/git/financialsim-saas && uv run --directory backend python -c "from finacialsim_saas.workers.worker import WorkerSettings; print('crons:', len(WorkerSettings.cron_jobs))"
```

Expected: prints 4 crons (update_bacen_indicators, prune_fipe_cache, verify_provider_health, mark_overdue_parcelas).

- [ ] **Step 4: Commit**

```bash
git add backend/finacialsim_saas/workers/tasks.py backend/finacialsim_saas/workers/worker.py
git commit -m "feat(phase6): add mark_overdue_parcelas ARQ cron at 05:00 UTC"
```

---

### Task 7: Quick integration smoke test of portal endpoints

- [ ] **Step 1: Write a minimal portal endpoint test**

```python
# backend/tests/test_portal_endpoints_smoke.py
"""Smoke tests for portal API — full isolation tests are in test_portal_endpoints.py (Plan 6E)."""
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_portal_me_requires_customer_role(client: AsyncClient):
    """Without auth, /portal/me returns 401."""
    r = await client.get("/api/v1/portal/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_portal_me_staff_gets_403(client: AsyncClient, engine):
    """Staff JWT accessing /portal/me gets 403."""
    import jwt
    from finacialsim_saas.settings import get_settings
    from finacialsim_saas.main import app, app_state
    from finacialsim_saas.data.database import build_session_factory
    from unittest.mock import AsyncMock
    from httpx import ASGITransport

    cfg = get_settings()
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "tenant_id": str(uuid.uuid4()),
         "role": "admin", "iat": 0, "exp": 9999999999},
        cfg.jwt_secret_key, algorithm="HS256",
    )
    r = await client.get(
        "/api/v1/portal/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_webhook_pix_always_200(client: AsyncClient):
    """Webhook endpoint always returns 200 regardless of payload."""
    r = await client.post(
        "/api/v1/webhooks/pix",
        content=b'{"pix": []}',
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200
```

- [ ] **Step 2: Run smoke tests**

```bash
cd /home/fabio/git/financialsim-saas/backend && uv run pytest tests/test_portal_endpoints_smoke.py -x -q
```

Expected: all 3 pass.

- [ ] **Step 3: Run full backend test suite**

```bash
cd /home/fabio/git/financialsim-saas/backend && uv run pytest tests/ -x -q --ignore=tests/test_pix_service.py --ignore=tests/test_portal_endpoints.py 2>&1 | tail -10
```

Expected: all pass (the full test files for phase 6 are in Plan 6E).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_portal_endpoints_smoke.py
git commit -m "test(phase6): smoke tests for portal and webhook endpoints"
```
