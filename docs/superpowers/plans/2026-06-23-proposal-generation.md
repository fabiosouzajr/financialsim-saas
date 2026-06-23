# Proposal Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the proposal generation feature — company branding in the PDF, admin-configurable validity period and logo, two-step confirm+propose flow in the simulation UI.

**Architecture:** Extend the `Tenant` model with 5 company profile columns; wire them into the existing `PropostaSnapshot` → WeasyPrint render pipeline; add `SimulationService.confirm()` to transition `rascunho` → `confirmado`; add a Tenant Profile admin page and update `SimulacaoEdit.tsx` with a two-step confirm-then-propose UX.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic, WeasyPrint, Jinja2, React 18, TypeScript, Tailwind CSS, `@tanstack/react-query`

## Global Constraints

- Run backend tests from `backend/` dir: `uv run pytest tests/ -v`
- Run a single test: `uv run pytest tests/test_foo.py::test_name -v`
- All Python imports use `finacialsim_saas.*` (not relative)
- `ProposalStatus.pronta` (not `ready`) — already renamed in a prior commit
- Migration numbering: 013 is taken (`013_rename_proposal_status_pronta.py`); next is **014**
- CNPJ validation: use `from finacialsim_core.utils.document_validation import is_valid_cnpj`
- Logo upload size limit: **2 MB**; validity days: `ge=1, le=30`, default **15**
- Logo fetch failure in the render worker is **non-fatal** — log warning, render without logo
- `slug` on `Tenant` is **never updated** by the tenant profile endpoint

---

## File Map

**New files:**
- `backend/alembic/versions/014_tenant_profile.py` — migration adding 5 columns to `tenants`
- `backend/finacialsim_saas/api/tenant_profile.py` — GET/PUT/POST logo endpoints + Pydantic schemas
- `frontend/src/lib/tenant-profile.ts` — typed API helpers for tenant profile
- `frontend/src/routes/admin/TenantProfile.tsx` — admin "Perfil da Empresa" page

**Modified files:**
- `backend/finacialsim_saas/data/models.py` — 5 new `Tenant` columns
- `backend/finacialsim_saas/schemas/proposals.py` — `LojaSnap.logo_key`, `build_snapshot()` update
- `backend/finacialsim_saas/schemas/simulations.py` — `SimulationOut.proposal_id`
- `backend/finacialsim_saas/services/simulation_service.py` — `confirm()` method, `get()` queries proposal_id
- `backend/finacialsim_saas/api/simulations.py` — `POST /{sim_id}/confirm` endpoint
- `backend/finacialsim_saas/services/proposal_service.py` — validate client+vehicle, read validade from tenant
- `backend/finacialsim_saas/workers/tasks.py` — pre-fetch logo, update `_proposta_ctx()` signature
- `backend/finacialsim_saas/reports/proposta.html` — logo `<img>` in header
- `backend/finacialsim_saas/reports/proposta.css` — `.loja-logo` styles
- `backend/finacialsim_saas/main.py` — register `tenant_profile.router`
- `frontend/src/App.tsx` — add `/admin/perfil` route
- `frontend/src/routes/admin/AdminLayout.tsx` — add "Perfil da Empresa" nav item
- `frontend/src/routes/SimulacaoEdit.tsx` — confirm button, proposal_id on mount, ProposalSection props

---

## Task 1: DB Migration + Tenant Model

**Files:**
- Create: `backend/alembic/versions/014_tenant_profile.py`
- Modify: `backend/finacialsim_saas/data/models.py`

**Interfaces:**
- Produces: `Tenant.cnpj`, `Tenant.telefone`, `Tenant.endereco`, `Tenant.logo_key`, `Tenant.proposta_validade_dias` — used by Tasks 2, 4, 6

- [ ] **Step 1: Write the migration**

```python
# backend/alembic/versions/014_tenant_profile.py
"""add company profile columns to tenants

Revision ID: 014
Revises: 013
Create Date: 2026-06-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("cnpj", sa.String(18), nullable=True))
    op.add_column("tenants", sa.Column("telefone", sa.String(20), nullable=True))
    op.add_column("tenants", sa.Column("endereco", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("logo_key", sa.Text(), nullable=True))
    op.add_column(
        "tenants",
        sa.Column(
            "proposta_validade_dias",
            sa.Integer(),
            nullable=False,
            server_default="15",
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "proposta_validade_dias")
    op.drop_column("tenants", "logo_key")
    op.drop_column("tenants", "endereco")
    op.drop_column("tenants", "telefone")
    op.drop_column("tenants", "cnpj")
```

- [ ] **Step 2: Add the 5 columns to the Tenant SQLAlchemy model**

In `backend/finacialsim_saas/data/models.py`, find the `Tenant` class and add after the `slug` column:

```python
class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = ...
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    slug: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    # ADD THESE:
    cnpj: Mapped[str | None] = mapped_column(sa.String(18), nullable=True)
    telefone: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    endereco: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    logo_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    proposta_validade_dias: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="15"
    )
    created_at: Mapped[datetime] = ...   # keep existing columns below
```

- [ ] **Step 3: Write the migration test**

```python
# In backend/tests/test_models.py — add to the existing test or create a new assertion:
# (Find the existing test_all_phaseN_models_importable_and_tables_exist pattern)

@pytest.mark.asyncio
async def test_tenant_profile_columns_exist(db_session):
    """Migration 014 adds 5 company profile columns to Tenant."""
    from finacialsim_saas.data.models import Tenant
    from sqlalchemy import inspect, text

    async with db_session() as session:
        result = await session.execute(
            text("SELECT cnpj, telefone, endereco, logo_key, proposta_validade_dias FROM tenants LIMIT 0")
        )
        # If columns don't exist this raises ProgrammingError
    assert result is not None
```

- [ ] **Step 4: Run the migration and test**

```bash
cd backend
uv run alembic upgrade head
uv run pytest tests/test_models.py -v -k "tenant_profile"
```

Expected: migration applies cleanly, test passes.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/014_tenant_profile.py backend/finacialsim_saas/data/models.py backend/tests/test_models.py
git commit -m "feat(data): add company profile columns to Tenant model (migration 014)"
```

---

## Task 2: LojaSnap + build_snapshot + SimulationOut.proposal_id

**Files:**
- Modify: `backend/finacialsim_saas/schemas/proposals.py`
- Modify: `backend/finacialsim_saas/schemas/simulations.py`
- Modify: `backend/finacialsim_saas/services/simulation_service.py`

**Interfaces:**
- Consumes: `Tenant.cnpj`, `Tenant.telefone`, `Tenant.endereco`, `Tenant.logo_key` (Task 1)
- Produces:
  - `LojaSnap.logo_key: str | None` — used by Task 5 (render worker)
  - `build_snapshot(sim, fees, extras, rows, client, vehicle, tenant, user) -> PropostaSnapshot` — unchanged signature
  - `SimulationOut.proposal_id: uuid.UUID | None` — used by Task 8 (frontend)

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_proposal_snapshot.py — add to existing file

def test_build_snapshot_includes_logo_key(make_snapshot_deps):
    """build_snapshot copies logo_key from Tenant into LojaSnap."""
    sim, fees, extras, rows, client, vehicle, tenant, user = make_snapshot_deps
    tenant.logo_key = "abc-tenant-id/logo/logo.png"
    tenant.cnpj = "12.345.678/0001-90"
    tenant.telefone = "11 99999-0000"
    tenant.endereco = "Rua Teste, 123"

    snap = build_snapshot(sim, fees, extras, rows, client, vehicle, tenant, user)

    assert snap.loja.logo_key == "abc-tenant-id/logo/logo.png"
    assert snap.loja.cnpj == "12.345.678/0001-90"
    assert snap.loja.telefone == "11 99999-0000"
    assert snap.loja.endereco == "Rua Teste, 123"


def test_build_snapshot_logo_key_none_when_unset(make_snapshot_deps):
    """logo_key is None when tenant has no logo."""
    sim, fees, extras, rows, client, vehicle, tenant, user = make_snapshot_deps
    tenant.logo_key = None
    snap = build_snapshot(sim, fees, extras, rows, client, vehicle, tenant, user)
    assert snap.loja.logo_key is None
```

You will need to check if `make_snapshot_deps` fixture exists. If not, look at how `test_proposal_snapshot.py` currently seeds its data and add a `tenant.logo_key = None` attribute to its tenant object (since migration 014 adds this column, the in-memory object needs it too).

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend
uv run pytest tests/test_proposal_snapshot.py -v -k "logo_key"
```

Expected: `AttributeError` or `ValidationError` — `logo_key` not yet on `LojaSnap`.

- [ ] **Step 3: Update LojaSnap and build_snapshot**

In `backend/finacialsim_saas/schemas/proposals.py`:

```python
class LojaSnap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str
    cnpj: str | None = None
    telefone: str | None = None
    endereco: str | None = None
    logo_key: str | None = None          # NEW
```

In `build_snapshot()`, replace the `loja=LojaSnap(nome=tenant.name)` line with:

```python
    return PropostaSnapshot(
        loja=LojaSnap(
            nome=tenant.name,
            cnpj=tenant.cnpj,
            telefone=tenant.telefone,
            endereco=tenant.endereco,
            logo_key=tenant.logo_key,
        ),
        ...  # rest unchanged
    )
```

- [ ] **Step 4: Run tests**

```bash
cd backend
uv run pytest tests/test_proposal_snapshot.py -v
```

Expected: all pass.

- [ ] **Step 5: Write failing test for SimulationOut.proposal_id**

```python
# backend/tests/test_simulation_endpoints.py — add:

@pytest.mark.asyncio
async def test_get_simulation_includes_proposal_id_none(client, seed_simulation):
    """GET /simulations/{id} returns proposal_id=null when no proposal exists."""
    r = await client.get(f"/api/v1/simulations/{seed_simulation.id}")
    assert r.status_code == 200
    assert r.json()["proposal_id"] is None


@pytest.mark.asyncio
async def test_get_simulation_includes_proposal_id_when_exists(client, seed_simulation_with_proposal):
    """GET /simulations/{id} returns the proposal UUID when a proposal exists."""
    sim, proposal = seed_simulation_with_proposal
    r = await client.get(f"/api/v1/simulations/{sim.id}")
    assert r.status_code == 200
    assert r.json()["proposal_id"] == str(proposal.id)
```

Check `conftest.py` and `test_simulation_endpoints.py` for existing fixture patterns to make `seed_simulation` and `seed_simulation_with_proposal`. Follow the same async session + `RequestContext` pattern used elsewhere in the test suite.

- [ ] **Step 6: Add proposal_id to SimulationOut schema**

In `backend/finacialsim_saas/schemas/simulations.py`, add to `SimulationOut`:

```python
class SimulationOut(BaseModel):
    ...
    summary: SimulationSummary | None = None
    proposal_id: uuid.UUID | None = None     # NEW — populated by SimulationService.get()
```

- [ ] **Step 7: Update SimulationService.get() to query proposal_id**

In `backend/finacialsim_saas/services/simulation_service.py`, add an import and a subquery inside `get()`, then pass it to `SimulationOut`:

```python
# At top of file, ensure Proposal is imported:
from finacialsim_saas.data.models import (
    ..., Proposal,
)

# Inside get(), after loading rows, add:
proposal_id = await self._s.scalar(
    select(Proposal.id).where(
        Proposal.simulation_id == sim_id,
        Proposal.tenant_id == ctx.tenant_id,
    )
)

# In the SimulationOut(...) call, add:
return SimulationOut(
    ...
    summary=summary,
    proposal_id=proposal_id,   # NEW
)
```

- [ ] **Step 8: Run tests**

```bash
cd backend
uv run pytest tests/test_simulation_endpoints.py -v -k "proposal_id"
```

Expected: both pass.

- [ ] **Step 9: Commit**

```bash
git add backend/finacialsim_saas/schemas/proposals.py \
        backend/finacialsim_saas/schemas/simulations.py \
        backend/finacialsim_saas/services/simulation_service.py \
        backend/tests/test_proposal_snapshot.py \
        backend/tests/test_simulation_endpoints.py
git commit -m "feat(schemas): extend LojaSnap with logo_key+company fields; add proposal_id to SimulationOut"
```

---

## Task 3: SimulationService.confirm() + API Endpoint

**Files:**
- Modify: `backend/finacialsim_saas/services/simulation_service.py`
- Modify: `backend/finacialsim_saas/api/simulations.py`

**Interfaces:**
- Consumes: `SimulationStatus.rascunho`, `SimulationStatus.confirmado` from `data/models.py`
- Produces: `SimulationService.confirm(sim_id: uuid.UUID, ctx: RequestContext) -> SimulationOut`
- Produces: `POST /api/v1/simulations/{sim_id}/confirm` → `SimulationOut` (200)

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_simulation_service.py — add:

@pytest.mark.asyncio
async def test_confirm_transitions_rascunho_to_confirmado(ctx_and_session):
    """confirm() sets a rascunho simulation to confirmado."""
    ctx, session = ctx_and_session
    # Seed a rascunho simulation (clone pattern sets rascunho)
    svc = SimulationService(session)
    # First create a confirmado sim, then clone it to get a rascunho
    base = await _seed_simulation(session, ctx.tenant_id, ctx.user_id)
    await session.commit()
    clone_out = await svc.clone(base.id, ctx)
    await session.commit()

    result = await svc.confirm(clone_out.id, ctx)
    await session.commit()

    assert result.status == "confirmado"


@pytest.mark.asyncio
async def test_confirm_rejects_already_confirmado(ctx_and_session):
    """confirm() raises ValidationError when simulation is already confirmado."""
    from finacialsim_saas.errors import ValidationError
    ctx, session = ctx_and_session
    svc = SimulationService(session)
    sim_out = await _seed_simulation(session, ctx.tenant_id, ctx.user_id)
    await session.commit()

    with pytest.raises(ValidationError):
        await svc.confirm(sim_out.id, ctx)
```

Look at `test_simulation_service.py` for the `_seed_simulation` helper and `ctx_and_session` fixture.

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend
uv run pytest tests/test_simulation_service.py -v -k "confirm"
```

Expected: `AttributeError: 'SimulationService' object has no attribute 'confirm'`

- [ ] **Step 3: Implement SimulationService.confirm()**

In `backend/finacialsim_saas/services/simulation_service.py`, add the method (follow the `archive()` method pattern for structure):

```python
async def confirm(self, sim_id: uuid.UUID, ctx: RequestContext) -> SimulationOut:
    result = await self._s.execute(
        select(Simulation).where(
            Simulation.id == sim_id,
            Simulation.tenant_id == ctx.tenant_id,
        )
    )
    sim = result.scalar_one_or_none()
    if sim is None:
        raise NotFoundError(f"Simulation {sim_id} not found")
    if sim.status != SimulationStatus.rascunho:
        raise ValidationError("Only rascunho simulations can be confirmed")
    before_status = sim.status.value
    sim.status = SimulationStatus.confirmado
    await self._s.flush()
    from finacialsim_saas.services.audit_service import AuditService
    await AuditService(self._s).log(
        "simulacao_confirmada", "simulation", sim.id,
        {"before": {"status": before_status}, "after": {"status": sim.status.value}},
        ctx,
    )
    return await self.get(sim.id, ctx)
```

- [ ] **Step 4: Run tests**

```bash
cd backend
uv run pytest tests/test_simulation_service.py -v -k "confirm"
```

Expected: both pass.

- [ ] **Step 5: Write failing endpoint test**

```python
# backend/tests/test_simulation_endpoints.py — add:

@pytest.mark.asyncio
async def test_confirm_simulation_endpoint(client, seed_rascunho_simulation):
    """POST /simulations/{id}/confirm transitions status to confirmado."""
    r = await client.post(f"/api/v1/simulations/{seed_rascunho_simulation.id}/confirm")
    assert r.status_code == 200
    assert r.json()["status"] == "confirmado"


@pytest.mark.asyncio
async def test_confirm_simulation_already_confirmado_returns_422(client, seed_simulation):
    """POST /simulations/{id}/confirm on confirmado sim returns 422."""
    r = await client.post(f"/api/v1/simulations/{seed_simulation.id}/confirm")
    assert r.status_code == 422
```

Add a `seed_rascunho_simulation` fixture that clones an existing simulation (clones start as `rascunho`).

- [ ] **Step 6: Add the endpoint to api/simulations.py**

```python
@router.post("/simulations/{sim_id}/confirm", response_model=SimulationOut)
async def confirm_simulation(
    sim_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SimulationOut:
    svc = SimulationService(session)
    result = await svc.confirm(sim_id, ctx)
    await session.commit()
    return result
```

- [ ] **Step 7: Run tests**

```bash
cd backend
uv run pytest tests/test_simulation_endpoints.py -v -k "confirm"
```

Expected: both pass.

- [ ] **Step 8: Commit**

```bash
git add backend/finacialsim_saas/services/simulation_service.py \
        backend/finacialsim_saas/api/simulations.py \
        backend/tests/test_simulation_service.py \
        backend/tests/test_simulation_endpoints.py
git commit -m "feat(simulation): add confirm() method and POST /simulations/{id}/confirm endpoint"
```

---

## Task 4: ProposalService.create() — validate client+vehicle, read validade from tenant

**Files:**
- Modify: `backend/finacialsim_saas/services/proposal_service.py`

**Interfaces:**
- Consumes: `Tenant.proposta_validade_dias` (Task 1), `Simulation.client_id`, `Simulation.vehicle_id`
- Produces: `ProposalService.create()` — unchanged signature, new validation + validade behaviour

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_proposal_service.py — add:

@pytest.mark.asyncio
async def test_create_rejects_sim_without_client(ctx_and_session, tmp_path):
    """create() raises ValidationError when simulation has no client_id."""
    from finacialsim_saas.errors import ValidationError
    ctx, session = ctx_and_session
    # Seed a simulation without client_id — use _seed_simulation with client_id=None
    sim = await _seed_simulation(session, ctx.tenant_id, ctx.user_id, client_id=None)
    await session.commit()
    svc = _make_svc(session, tmp_path)
    with pytest.raises(ValidationError, match="client"):
        await svc.create(sim.id, ctx)


@pytest.mark.asyncio
async def test_create_rejects_sim_without_vehicle(ctx_and_session, tmp_path):
    """create() raises ValidationError when simulation has no vehicle_id."""
    from finacialsim_saas.errors import ValidationError
    ctx, session = ctx_and_session
    sim = await _seed_simulation(session, ctx.tenant_id, ctx.user_id, vehicle_id=None)
    await session.commit()
    svc = _make_svc(session, tmp_path)
    with pytest.raises(ValidationError, match="vehicle"):
        await svc.create(sim.id, ctx)


@pytest.mark.asyncio
async def test_create_reads_validade_from_tenant(ctx_and_session, tmp_path):
    """create() uses tenant.proposta_validade_dias instead of hardcoded 7."""
    ctx, session = ctx_and_session
    tenant = await session.get(Tenant, ctx.tenant_id)
    tenant.proposta_validade_dias = 20
    await session.flush()
    sim = await _seed_simulation(session, ctx.tenant_id, ctx.user_id)
    await session.commit()
    svc = _make_svc(session, tmp_path)
    proposal = await svc.create(sim.id, ctx)
    assert proposal.validade_dias == 20
```

Check that `_seed_simulation` supports `client_id=None` and `vehicle_id=None` — if not, add those kwargs.

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend
uv run pytest tests/test_proposal_service.py -v -k "rejects_sim_without or validade_from_tenant"
```

Expected: the first two tests pass (no validation yet → no error raised where expected), validade test fails (gets 7 not 20).

- [ ] **Step 3: Update ProposalService.create()**

In `backend/finacialsim_saas/services/proposal_service.py`, inside `create()`, after loading `sim` and before building the snapshot, add:

```python
        # Validate client and vehicle are linked
        if sim.client_id is None:
            raise ValidationError("simulation must have a client to generate a proposal")
        if sim.vehicle_id is None:
            raise ValidationError("simulation must have a vehicle to generate a proposal")
```

Then replace the hardcoded `validade_dias=7` with:

```python
        proposal = Proposal(
            ...
            validade_dias=tenant.proposta_validade_dias,   # was: validade_dias=7
            ...
        )
```

- [ ] **Step 4: Run tests**

```bash
cd backend
uv run pytest tests/test_proposal_service.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/services/proposal_service.py \
        backend/tests/test_proposal_service.py
git commit -m "feat(proposal): validate client+vehicle on create; read validade_dias from tenant"
```

---

## Task 5: Render Worker Logo + PDF Template

**Files:**
- Modify: `backend/finacialsim_saas/workers/tasks.py`
- Modify: `backend/finacialsim_saas/reports/proposta.html`
- Modify: `backend/finacialsim_saas/reports/proposta.css`

**Interfaces:**
- Consumes: `LojaSnap.logo_key` (Task 2), `StorageBackend.get(key) -> bytes` (protocol, already exists)
- `_proposta_ctx(snap, proposal, logo_data_uri: str | None = None) -> dict` — gains one param

- [ ] **Step 1: Write failing test for logo embedding**

```python
# backend/tests/test_render_tasks.py — add:

@pytest.mark.asyncio
async def test_render_proposta_embeds_logo(proposal_with_logo, ctx):
    """render_proposta_pdf embeds logo as base64 data URI when logo_key is set."""
    from finacialsim_saas.workers.tasks import render_proposta_pdf
    from unittest.mock import AsyncMock, patch, MagicMock

    proposal, session_factory, storage = proposal_with_logo
    # storage.get should return PNG bytes
    storage.get = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n")  # minimal PNG header

    fake_pdf = b"%PDF-1.4 fake"
    with patch("finacialsim_saas.workers.tasks.HTML") as mock_html:
        mock_html.return_value.write_pdf.return_value = fake_pdf
        await render_proposta_pdf(
            {"session_factory": session_factory, "storage_backend": storage},
            str(proposal.id),
        )

    # HTML() was called with a string containing data:image/png;base64
    html_arg = mock_html.call_args[1]["string"]
    assert "data:image/png;base64" in html_arg


@pytest.mark.asyncio
async def test_render_proposta_continues_without_logo_on_storage_error(proposal_with_logo, ctx):
    """render_proposta_pdf succeeds even when logo storage.get() raises."""
    from finacialsim_saas.workers.tasks import render_proposta_pdf
    from unittest.mock import AsyncMock, patch

    proposal, session_factory, storage = proposal_with_logo
    storage.get = AsyncMock(side_effect=Exception("S3 error"))

    fake_pdf = b"%PDF-1.4 fake"
    with patch("finacialsim_saas.workers.tasks.HTML") as mock_html:
        mock_html.return_value.write_pdf.return_value = fake_pdf
        await render_proposta_pdf(
            {"session_factory": session_factory, "storage_backend": storage},
            str(proposal.id),
        )

    # PDF was still produced despite storage error
    assert proposal.render_status.value == "ready"
```

Look at the existing `test_render_tasks.py` for the existing fixture pattern and extend it to produce a `proposal_with_logo` fixture where `snap.loja.logo_key` is set.

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend
uv run pytest tests/test_render_tasks.py -v -k "logo"
```

Expected: `AssertionError` — no `data:image/png;base64` in the rendered HTML yet.

- [ ] **Step 3: Update _proposta_ctx() and render_proposta_pdf()**

In `backend/finacialsim_saas/workers/tasks.py`:

**a)** Add `import base64` to the top-level imports (if not already present — it's stdlib).

**b)** Change `_proposta_ctx` signature:

```python
def _proposta_ctx(snap: _Snap, proposal: _Proposal, logo_data_uri: str | None = None) -> dict:
    ...
    return {
        "loja": {
            **snap.loja.model_dump(),
            "logo_data_uri": logo_data_uri,   # ADD THIS KEY
        },
        ...  # rest unchanged
    }
```

**c)** In `render_proposta_pdf`, add logo pre-fetch **before** the `_proposta_ctx()` call:

```python
        try:
            snap = _Snap.model_validate(proposal.snapshot_json)

            # Pre-fetch logo (non-fatal if missing)
            logo_data_uri: str | None = None
            if snap.loja.logo_key:
                try:
                    logo_bytes = await storage.get(snap.loja.logo_key)
                    b64 = base64.b64encode(logo_bytes).decode()
                    ext = snap.loja.logo_key.rsplit(".", 1)[-1].lower()
                    mime = "image/png" if ext == "png" else "image/jpeg"
                    logo_data_uri = f"data:{mime};base64,{b64}"
                except Exception:
                    logger.warning(
                        f"render_proposta_pdf: logo fetch failed for key "
                        f"{snap.loja.logo_key!r}, rendering without logo"
                    )

            html_str = _jinja.get_template("proposta.html").render(
                **_proposta_ctx(snap, proposal, logo_data_uri=logo_data_uri)
            )
```

- [ ] **Step 4: Run tests**

```bash
cd backend
uv run pytest tests/test_render_tasks.py -v
```

Expected: all pass.

- [ ] **Step 5: Update proposta.html — add logo to header**

In `backend/finacialsim_saas/reports/proposta.html`, add inside `<body>` before the `<h1>`:

```html
<body>
    <div class="header">
        {% if loja.logo_data_uri %}
        <img src="{{ loja.logo_data_uri }}" class="loja-logo" alt="{{ loja.nome }}">
        {% endif %}
        <h1>{{ loja.nome }} — Proposta de financiamento</h1>
        {% if loja.cnpj %}<p class="loja-info">CNPJ: {{ loja.cnpj }}</p>{% endif %}
        {% if loja.telefone %}<p class="loja-info">Tel.: {{ loja.telefone }}</p>{% endif %}
        {% if loja.endereco %}<p class="loja-info">{{ loja.endereco }}</p>{% endif %}
    </div>
```

- [ ] **Step 6: Update proposta.css — add logo styles**

In `backend/finacialsim_saas/reports/proposta.css`, add:

```css
.header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 1.5rem;
    border-bottom: 1px solid #e5e7eb;
    padding-bottom: 1rem;
}

.loja-logo {
    max-height: 60px;
    max-width: 200px;
    object-fit: contain;
}

.loja-info {
    font-size: 0.8rem;
    color: #6b7280;
    margin: 0.1rem 0;
}
```

- [ ] **Step 7: Commit**

```bash
git add backend/finacialsim_saas/workers/tasks.py \
        backend/finacialsim_saas/reports/proposta.html \
        backend/finacialsim_saas/reports/proposta.css \
        backend/tests/test_render_tasks.py
git commit -m "feat(worker): pre-fetch logo for PDF render; graceful degradation on storage error"
```

---

## Task 6: Tenant Profile API

**Files:**
- Create: `backend/finacialsim_saas/api/tenant_profile.py`
- Modify: `backend/finacialsim_saas/main.py`

**Interfaces:**
- Consumes: `Tenant` model (Task 1), `StorageBackend.put()`, `StorageBackend.signed_url()`
- Produces:
  - `GET /api/v1/admin/tenant-profile` → `TenantProfileOut`
  - `PUT /api/v1/admin/tenant-profile` → `TenantProfileOut`
  - `POST /api/v1/admin/tenant-profile/logo` → `TenantProfileOut`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_tenant_profile.py  (new file)

import pytest
import uuid
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_tenant_profile_returns_defaults(client_admin):
    """GET /admin/tenant-profile returns tenant fields; proposta_validade_dias defaults to 15."""
    r = await client_admin.get("/api/v1/admin/tenant-profile")
    assert r.status_code == 200
    body = r.json()
    assert "nome" in body
    assert body["proposta_validade_dias"] == 15
    assert body["cnpj"] is None
    assert body["logo_url"] is None


@pytest.mark.asyncio
async def test_put_tenant_profile_updates_fields(client_admin):
    """PUT /admin/tenant-profile updates name and validade_dias."""
    r = await client_admin.put(
        "/api/v1/admin/tenant-profile",
        json={
            "nome": "Minha Loja Atualizada",
            "cnpj": "12.345.678/0001-90",
            "telefone": "11 99999-0000",
            "endereco": "Rua Nova, 456",
            "proposta_validade_dias": 20,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["nome"] == "Minha Loja Atualizada"
    assert body["cnpj"] == "12.345.678/0001-90"
    assert body["proposta_validade_dias"] == 20

    # Verify persisted
    r2 = await client_admin.get("/api/v1/admin/tenant-profile")
    assert r2.json()["nome"] == "Minha Loja Atualizada"


@pytest.mark.asyncio
async def test_put_tenant_profile_rejects_invalid_cnpj(client_admin):
    """PUT rejects a CNPJ that fails the checksum validation."""
    r = await client_admin.put(
        "/api/v1/admin/tenant-profile",
        json={"nome": "Loja", "cnpj": "00.000.000/0000-00", "proposta_validade_dias": 15},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_put_tenant_profile_rejects_validade_over_30(client_admin):
    """PUT rejects proposta_validade_dias > 30."""
    r = await client_admin.put(
        "/api/v1/admin/tenant-profile",
        json={"nome": "Loja", "proposta_validade_dias": 31},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_logo_stores_and_returns_url(client_admin):
    """POST /admin/tenant-profile/logo stores the file and returns a logo_url."""
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # minimal valid-ish PNG
    r = await client_admin.post(
        "/api/v1/admin/tenant-profile/logo",
        files={"file": ("logo.png", png_bytes, "image/png")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["logo_url"] is not None


@pytest.mark.asyncio
async def test_post_logo_rejects_oversized_file(client_admin):
    """POST /admin/tenant-profile/logo rejects files > 2MB."""
    oversized = b"\x89PNG\r\n\x1a\n" + b"\x00" * (2 * 1024 * 1024 + 1)
    r = await client_admin.post(
        "/api/v1/admin/tenant-profile/logo",
        files={"file": ("big.png", oversized, "image/png")},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_logo_rejects_non_image(client_admin):
    """POST /admin/tenant-profile/logo rejects non-image content type."""
    r = await client_admin.post(
        "/api/v1/admin/tenant-profile/logo",
        files={"file": ("doc.pdf", b"%PDF", "application/pdf")},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_tenant_profile_requires_admin(client_user):
    """Non-admin users get 403 from tenant profile endpoints."""
    r = await client_user.get("/api/v1/admin/tenant-profile")
    assert r.status_code == 403
```

Look at existing test files (e.g. `test_admin_settings.py`) for the `client_admin` / `client_user` fixture pattern and replicate it.

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend
uv run pytest tests/test_tenant_profile.py -v
```

Expected: 404 — route does not exist yet.

- [ ] **Step 3: Create the API file**

```python
# backend/finacialsim_saas/api/tenant_profile.py
"""Tenant profile endpoints — company info and logo for the proposal PDF."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_db_session, require_role
from finacialsim_saas.data.models import Tenant
from finacialsim_saas.settings import get_settings
from finacialsim_saas.storage.deps import get_storage_backend

router = APIRouter(prefix="/api/v1/admin/tenant-profile", tags=["tenant-profile"])

_MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB
_ALLOWED_MIME = {"image/png", "image/jpeg"}


class TenantProfileOut(BaseModel):
    nome: str
    cnpj: str | None
    telefone: str | None
    endereco: str | None
    logo_url: str | None
    proposta_validade_dias: int


class TenantProfileIn(BaseModel):
    nome: str
    cnpj: str | None = None
    telefone: str | None = None
    endereco: str | None = None
    proposta_validade_dias: int = Field(default=15, ge=1, le=30)

    @model_validator(mode="after")
    def validate_cnpj(self) -> "TenantProfileIn":
        if self.cnpj is not None:
            from finacialsim_core.utils.document_validation import is_valid_cnpj
            clean = "".join(ch for ch in self.cnpj if ch.isdigit())
            if not is_valid_cnpj(clean):
                raise ValueError("CNPJ inválido")
        return self


async def _tenant_profile_out(tenant: Tenant, session: AsyncSession) -> TenantProfileOut:
    logo_url = None
    if tenant.logo_key:
        settings = get_settings()
        storage = get_storage_backend(settings)
        logo_url = await storage.signed_url(tenant.logo_key, expires_in=3600)
    return TenantProfileOut(
        nome=tenant.name,
        cnpj=tenant.cnpj,
        telefone=tenant.telefone,
        endereco=tenant.endereco,
        logo_url=logo_url,
        proposta_validade_dias=tenant.proposta_validade_dias,
    )


@router.get("", response_model=TenantProfileOut)
async def get_tenant_profile(
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TenantProfileOut:
    tenant = await session.get(Tenant, ctx.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return await _tenant_profile_out(tenant, session)


@router.put("", response_model=TenantProfileOut)
async def update_tenant_profile(
    body: TenantProfileIn,
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TenantProfileOut:
    tenant = await session.get(Tenant, ctx.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant.name = body.nome
    tenant.cnpj = body.cnpj
    tenant.telefone = body.telefone
    tenant.endereco = body.endereco
    tenant.proposta_validade_dias = body.proposta_validade_dias
    await session.commit()
    return await _tenant_profile_out(tenant, session)


@router.post("/logo", response_model=TenantProfileOut)
async def upload_logo(
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    file: UploadFile = File(...),
) -> TenantProfileOut:
    if file.content_type not in _ALLOWED_MIME:
        raise HTTPException(status_code=422, detail="Logo must be PNG or JPEG")
    data = await file.read()
    if len(data) > _MAX_LOGO_BYTES:
        raise HTTPException(status_code=422, detail="Logo must be under 2 MB")

    ext = "png" if file.content_type == "image/png" else "jpg"
    key = f"{ctx.tenant_id}/logo/{uuid.uuid4()}.{ext}"

    settings = get_settings()
    storage = get_storage_backend(settings)
    await storage.put(key, data, file.content_type)

    tenant = await session.get(Tenant, ctx.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant.logo_key = key
    await session.commit()

    return await _tenant_profile_out(tenant, session)
```

- [ ] **Step 4: Register the router in main.py**

In `backend/finacialsim_saas/main.py`, add at the bottom of the import block and `include_router` list:

```python
from finacialsim_saas.api.tenant_profile import router as tenant_profile_router   # noqa: E402

app.include_router(tenant_profile_router)
```

- [ ] **Step 5: Run tests**

```bash
cd backend
uv run pytest tests/test_tenant_profile.py -v
```

Expected: all 7 pass.

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/api/tenant_profile.py \
        backend/finacialsim_saas/main.py \
        backend/tests/test_tenant_profile.py
git commit -m "feat(api): add tenant profile endpoints — GET/PUT company info and POST logo upload"
```

---

## Task 7: Frontend — Tenant Profile Lib + Admin Page

**Files:**
- Create: `frontend/src/lib/tenant-profile.ts`
- Create: `frontend/src/routes/admin/TenantProfile.tsx`
- Modify: `frontend/src/routes/admin/AdminLayout.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `GET/PUT /api/v1/admin/tenant-profile`, `POST .../logo`
- Produces: `/admin/perfil` route, "Perfil da Empresa" nav item

- [ ] **Step 1: Create the API helpers**

```typescript
// frontend/src/lib/tenant-profile.ts
import { api } from "./api";

export interface TenantProfileOut {
  nome: string;
  cnpj: string | null;
  telefone: string | null;
  endereco: string | null;
  logo_url: string | null;
  proposta_validade_dias: number;
}

export interface TenantProfileIn {
  nome: string;
  cnpj?: string | null;
  telefone?: string | null;
  endereco?: string | null;
  proposta_validade_dias: number;
}

export async function getTenantProfile(): Promise<TenantProfileOut> {
  const { data } = await api.get<TenantProfileOut>("/v1/admin/tenant-profile");
  return data;
}

export async function updateTenantProfile(body: TenantProfileIn): Promise<TenantProfileOut> {
  const { data } = await api.put<TenantProfileOut>("/v1/admin/tenant-profile", body);
  return data;
}

export async function uploadLogo(file: File): Promise<TenantProfileOut> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<TenantProfileOut>("/v1/admin/tenant-profile/logo", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}
```

- [ ] **Step 2: Create TenantProfile.tsx admin page**

```tsx
// frontend/src/routes/admin/TenantProfile.tsx
import { useEffect, useRef, useState } from "react";
import {
  type TenantProfileOut,
  getTenantProfile,
  updateTenantProfile,
  uploadLogo,
} from "@/lib/tenant-profile";

const MAX_LOGO_BYTES = 2 * 1024 * 1024;

export default function TenantProfile() {
  useEffect(() => { document.title = "Perfil da Empresa — FinacialSim"; }, []);

  const [profile, setProfile] = useState<TenantProfileOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [logoUploading, setLogoUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [nome, setNome] = useState("");
  const [cnpj, setCnpj] = useState("");
  const [telefone, setTelefone] = useState("");
  const [endereco, setEndereco] = useState("");
  const [validadeDias, setValidadeDias] = useState(15);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void getTenantProfile().then((p) => {
      setProfile(p);
      setNome(p.nome);
      setCnpj(p.cnpj ?? "");
      setTelefone(p.telefone ?? "");
      setEndereco(p.endereco ?? "");
      setValidadeDias(p.proposta_validade_dias);
      setLoading(false);
    });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const updated = await updateTenantProfile({
        nome,
        cnpj: cnpj || null,
        telefone: telefone || null,
        endereco: endereco || null,
        proposta_validade_dias: validadeDias,
      });
      setProfile(updated);
      setSuccess("Perfil salvo com sucesso.");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao salvar perfil");
    } finally {
      setSaving(false);
    }
  };

  const handleLogoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_LOGO_BYTES) {
      setError("Logo deve ter no máximo 2 MB.");
      return;
    }
    setLogoUploading(true);
    setError(null);
    try {
      const updated = await uploadLogo(file);
      setProfile(updated);
      setSuccess("Logo enviado com sucesso.");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao enviar logo");
    } finally {
      setLogoUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  if (loading) return <div className="p-8 text-muted-foreground">Carregando…</div>;

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="text-xl font-semibold mb-6">Perfil da Empresa</h1>

      {error && <p className="mb-4 text-sm text-destructive">{error}</p>}
      {success && <p className="mb-4 text-sm text-green-600">{success}</p>}

      {/* Company info card */}
      <div className="rounded-lg border p-5 mb-6 space-y-4">
        <h2 className="text-sm font-semibold">Dados da empresa</h2>
        <div className="space-y-3">
          {(
            [
              { label: "Nome", value: nome, set: setNome, type: "text" },
              { label: "CNPJ", value: cnpj, set: setCnpj, type: "text" },
              { label: "Telefone", value: telefone, set: setTelefone, type: "text" },
              { label: "Endereço", value: endereco, set: setEndereco, type: "text" },
            ] as const
          ).map(({ label, value, set }) => (
            <div key={label}>
              <label className="block text-xs font-medium text-muted-foreground mb-1">{label}</label>
              <input
                value={value}
                onChange={(e) => set(e.target.value)}
                className="w-full rounded border px-3 py-1.5 text-sm"
              />
            </div>
          ))}
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">
              Validade da proposta (dias, máx. 30)
            </label>
            <input
              type="number"
              min={1}
              max={30}
              value={validadeDias}
              onChange={(e) => setValidadeDias(Number(e.target.value))}
              className="w-32 rounded border px-3 py-1.5 text-sm"
            />
          </div>
        </div>
        <button
          onClick={() => void handleSave()}
          disabled={saving}
          className="rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {saving ? "Salvando…" : "Salvar"}
        </button>
      </div>

      {/* Logo card */}
      <div className="rounded-lg border p-5 space-y-3">
        <h2 className="text-sm font-semibold">Logo da empresa</h2>
        {profile?.logo_url && (
          <img
            src={profile.logo_url}
            alt="Logo atual"
            className="max-h-16 object-contain border rounded p-1"
          />
        )}
        <div className="flex items-center gap-3">
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg"
            onChange={(e) => void handleLogoUpload(e)}
            className="text-sm"
          />
          {logoUploading && <span className="text-xs text-muted-foreground">Enviando…</span>}
        </div>
        <p className="text-xs text-muted-foreground">PNG ou JPEG, máx. 2 MB.</p>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add nav item to AdminLayout.tsx**

In `frontend/src/routes/admin/AdminLayout.tsx`, add to the `NAV_ITEMS` array and import `Building2` from lucide-react:

```typescript
import {
  Activity, ArrowLeft, Building2, ClipboardList, CreditCard,
  Mail, Settings, TrendingUp, Users,
} from "lucide-react";

const NAV_ITEMS = [
  { label: "Perfil da Empresa", href: "/admin/perfil", icon: Building2 },  // ADD
  { label: "Regras de Negócio", href: "/admin/regras", icon: Settings },
  { label: "Indicadores", href: "/admin/indicadores", icon: TrendingUp },
  { label: "Auditoria", href: "/admin/auditoria", icon: ClipboardList },
  { label: "Saúde do Sistema", href: "/admin/saude", icon: Activity },
  { label: "SMTP", href: "/admin/smtp", icon: Mail },
  { label: "Pix", href: "/admin/pix", icon: CreditCard },
  { label: "Usuários", href: "/admin/users", icon: Users },
];
```

- [ ] **Step 4: Add route to App.tsx**

In `frontend/src/App.tsx`:

```typescript
import TenantProfile from "./routes/admin/TenantProfile";  // ADD

// Inside the /admin Route children:
<Route path="perfil" element={<TenantProfile />} />   // ADD alongside other admin routes
```

- [ ] **Step 5: Type-check**

```bash
cd frontend
npm run build 2>&1 | head -40
```

Expected: no TypeScript errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/tenant-profile.ts \
        frontend/src/routes/admin/TenantProfile.tsx \
        frontend/src/routes/admin/AdminLayout.tsx \
        frontend/src/App.tsx
git commit -m "feat(frontend): add Perfil da Empresa admin page with company info and logo upload"
```

---

## Task 8: Frontend — SimulacaoEdit Two-Step Confirm + Propose Flow

**Files:**
- Modify: `frontend/src/routes/SimulacaoEdit.tsx`

**Interfaces:**
- Consumes: `SimulationOut.proposal_id` (Task 2), `SimulationOut.status`, existing `ProposalSection` component
- Consumes: `POST /api/v1/simulations/{id}/confirm` (Task 3)

- [ ] **Step 1: Add the confirm API call to SimulacaoEdit.tsx**

`SimulacaoEdit.tsx` already imports from `@/lib/api` and `@/lib/proposals`. Add a confirm helper at the top of the file (not in a separate lib — it's one call):

```typescript
async function confirmSimulation(id: string): Promise<void> {
  await api.post(`/v1/simulations/${id}/confirm`);
}
```

- [ ] **Step 2: Pass status and initialProposalId to ProposalSection**

`ProposalSection` currently only receives `simulationId`. Update it to also receive `simStatus` and `initialProposalId`:

Change the component signature:

```typescript
function ProposalSection({
  simulationId,
  simStatus,
  initialProposalId,
  onSimulationConfirmed,
}: {
  simulationId: string;
  simStatus: string;
  initialProposalId: string | null;
  onSimulationConfirmed: () => void;
}) {
```

- [ ] **Step 3: Add confirm-simulation state and handler inside ProposalSection**

Inside `ProposalSection`, add:

```typescript
  const [confirming, setConfirming] = useState(false);

  const handleConfirm = async () => {
    setConfirming(true);
    setError(null);
    try {
      await confirmSimulation(simulationId);
      onSimulationConfirmed();   // triggers parent to re-fetch sim
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao confirmar simulação");
    } finally {
      setConfirming(false);
    }
  };
```

- [ ] **Step 4: Initialize proposal state from initialProposalId on mount**

Replace the existing empty `useState<ProposalOut | null>(null)` with logic that pre-loads if a proposal already exists:

```typescript
  // On mount: if a proposal already exists, fetch and display it
  useEffect(() => {
    if (!initialProposalId) return;
    void getProposal(initialProposalId).then((p) => {
      setProposal(p);
      // If still rendering, start polling
      if (p.render_status === "pending" || p.render_status === "rendering") {
        startPolling(p.id);
      }
    });
  }, [initialProposalId, startPolling]);
```

- [ ] **Step 5: Update the render block to show confirm button for rascunho simulations**

Replace the existing `{!proposal && ( <button>Gerar proposta</button> )}` block with:

```tsx
      {/* Show confirm button for rascunho, propose button for confirmado */}
      {!proposal && simStatus === "rascunho" && (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">
            Confirme a simulação antes de gerar a proposta.
          </p>
          <button
            onClick={() => void handleConfirm()}
            disabled={confirming}
            className="rounded bg-yellow-500 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {confirming ? "Confirmando…" : "Confirmar simulação"}
          </button>
        </div>
      )}

      {!proposal && simStatus !== "rascunho" && simStatus !== "arquivado" && (
        <button
          onClick={() => void handleGerar()}
          disabled={loading}
          className="rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {loading ? "Gerando…" : "Gerar proposta"}
        </button>
      )}
```

- [ ] **Step 6: Update ProposalSection call-site in the parent**

In the `SimulacaoEdit` component (bottom of the file), update the `<ProposalSection>` usage:

```tsx
          <ProposalSection
            simulationId={sim.id}
            simStatus={sim.status}
            initialProposalId={sim.proposal_id ?? null}
            onSimulationConfirmed={() => qc.invalidateQueries({ queryKey: ["simulation", id] })}
          />
```

Note: `sim.proposal_id` will be `uuid.UUID | None` from the backend but arrives as `string | null` in TypeScript. Add `proposal_id: string | null` to the `SimulationOut` type in `frontend/src/routes/simulacao/types.ts`:

```typescript
// In types.ts, add to SimulationOut:
proposal_id: string | null;
```

- [ ] **Step 7: Type-check**

```bash
cd frontend
npm run build 2>&1 | head -40
```

Expected: no TypeScript errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/routes/SimulacaoEdit.tsx \
        frontend/src/routes/simulacao/types.ts
git commit -m "feat(frontend): two-step confirm+propose flow in SimulacaoEdit; resume from proposal_id on mount"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| Extend Tenant model — 5 columns | Task 1 |
| Migration 014 with default 15 days | Task 1 |
| LojaSnap.logo_key | Task 2 |
| build_snapshot populates company fields | Task 2 |
| SimulationOut.proposal_id | Task 2 |
| SimulationService.confirm() | Task 3 |
| POST /simulations/{id}/confirm | Task 3 |
| ProposalService validate client+vehicle | Task 4 |
| ProposalService read validade from tenant | Task 4 |
| Logo pre-fetch in render worker | Task 5 |
| Graceful logo degradation | Task 5 |
| proposta.html logo img | Task 5 |
| proposta.css .loja-logo | Task 5 |
| GET/PUT /admin/tenant-profile | Task 6 |
| POST /admin/tenant-profile/logo | Task 6 |
| CNPJ validation with is_valid_cnpj | Task 6 |
| 2MB limit enforced at API | Task 6 |
| ge=1, le=30 on validade_dias | Task 6 |
| Admin nav + /admin/perfil route | Task 7 |
| TenantProfile.tsx admin page | Task 7 |
| Confirm button for rascunho sims | Task 8 |
| Gerar Proposta for confirmado sims | Task 8 |
| Resume from proposal_id on mount | Task 8 |
| onSimulationConfirmed → invalidate query | Task 8 |

All requirements covered. No gaps found.

**Placeholder scan:** No TBD/TODO/implement later found. All code blocks are complete.

**Type consistency check:**
- `SimulationService.confirm(sim_id: uuid.UUID, ctx: RequestContext) -> SimulationOut` — consistent across Tasks 3 and 8
- `_proposta_ctx(snap, proposal, logo_data_uri: str | None = None) -> dict` — defined and used in Task 5 only
- `TenantProfileOut` — defined in Task 6 (`tenant_profile.py`), consumed by Task 7 (`tenant-profile.ts` mirrors the shape)
- `ProposalSection` props extended in Task 8: `simStatus: string`, `initialProposalId: string | null`, `onSimulationConfirmed: () => void` — all used in the same task
