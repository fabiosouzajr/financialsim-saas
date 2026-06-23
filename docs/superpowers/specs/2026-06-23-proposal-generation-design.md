# Proposal Generation from Simulation — Design Spec

**Date:** 2026-06-23  
**Approach:** B — Extend Tenant model; single "Perfil da Empresa" admin page

---

## Overview

Generate a print-ready PDF proposal from a confirmed simulation. The proposal is populated with data from `cliente`, `veiculo`, and `simulacao`. Company branding (name, CNPJ, phone, address, logo) and proposal validity period are admin-configurable per tenant.

The infrastructure (ProposalService, PropostaSnapshot, WeasyPrint render worker, proposta.html template, PropostasPage list) already exists and is ~80% wired. This spec covers the remaining gaps.

---

## Scope

### In scope
- Extend `Tenant` model with company info + validity days
- Wire company info + logo into the snapshot and PDF render
- Combined "confirm + create proposal" action on the simulation page
- Polling status indicator + download link on the simulation page
- Admin page "Perfil da Empresa" for company settings and logo upload

### Out of scope
- Proposal detail page / approve / cancel UI (already exists; not modified)
- Carnê PDF generation
- Portal do cliente changes

---

## 1. Data Layer

### Migration (new file: `013_tenant_profile.py`)

Add columns to the `tenants` table:

| Column | Type | Nullable | Default |
|---|---|---|---|
| `cnpj` | VARCHAR(18) | yes | — |
| `telefone` | VARCHAR(20) | yes | — |
| `endereco` | TEXT | yes | — |
| `logo_key` | TEXT | yes | — |
| `proposta_validade_dias` | INTEGER | no | 15 |

`logo_key` is a storage path (`{tenant_id}/logo/{filename}`), not a URL. The render worker resolves it to bytes and embeds as a base64 data URI so the PDF is fully self-contained.

### Model (`data/models.py`)

Add the five mapped columns to the `Tenant` SQLAlchemy model.

---

## 2. Backend

### 2a. Schemas

**`LojaSnap`** (`schemas/proposals.py`) — add one field:
- `logo_key: str | None = None`

`logo_data_uri` is NOT a snapshot field — the render worker resolves `logo_key` → base64 string and injects it directly into the Jinja2 context dict; it is never stored in the sealed JSON snapshot.

**`build_snapshot()`** — populate `LojaSnap` from the extended tenant:
```python
loja=LojaSnap(
    nome=tenant.name,
    cnpj=tenant.cnpj,
    telefone=tenant.telefone,
    endereco=tenant.endereco,
    logo_key=tenant.logo_key,
)
```

### 2b. SimulationService — new `confirm()` method

Add `SimulationService.confirm(simulation_id, ctx)`:
- Loads the simulation (tenant-scoped)
- Raises `ValidationError` if `status != rascunho` (already `confirmado` or `arquivado`)
- Sets `status = confirmado`, commits, writes audit log entry `simulacao_confirmada`

New endpoint: `POST /api/v1/simulations/{id}/confirm` (auth: any authenticated user, same as create).

### 2c. ProposalService

`ProposalService.create()` changes:
1. Keep the `status == confirmado` guard — proposal creation requires an explicitly confirmed simulation.
2. Read `validade_dias` from `tenant.proposta_validade_dias` instead of hardcoded `7`.
3. Validate that sim has `client_id` and `vehicle_id` set before accepting.

### 2d. Render Worker (`workers/tasks.py`)

`_proposta_ctx()` stays synchronous. In `render_proposta_pdf`, pre-fetch the logo inside the existing async block **before** calling `_proposta_ctx()`, then pass it as a parameter:

```python
logo_data_uri = None
if snap.loja.logo_key:
    try:
        logo_bytes = await storage.get(snap.loja.logo_key)
        b64 = base64.b64encode(logo_bytes).decode()
        ext = snap.loja.logo_key.rsplit(".", 1)[-1].lower()
        mime = "image/png" if ext == "png" else "image/jpeg"
        logo_data_uri = f"data:{mime};base64,{b64}"
    except Exception:
        logger.warning(f"render_proposta_pdf: logo fetch failed for key {snap.loja.logo_key!r}, rendering without logo")
        logo_data_uri = None

html_str = _jinja.get_template("proposta.html").render(
    **_proposta_ctx(snap, proposal, logo_data_uri=logo_data_uri)
)
```

`_proposta_ctx()` gains an optional `logo_data_uri: str | None = None` parameter and injects it into the `loja` dict. The async boundary stays in `render_proposta_pdf` where it belongs.

### 2e. PDF Template (`reports/proposta.html`)

Add to header section:
```html
{% if loja.logo_data_uri %}
<img src="{{ loja.logo_data_uri }}" class="loja-logo" alt="{{ loja.nome }}">
{% endif %}
```

Add `.loja-logo` styling to `proposta.css` (max-height ~60px, float right or centered).

### 2f. New API: Tenant Profile

**File:** `backend/finacialsim_saas/api/tenant_profile.py`  
**Router prefix:** `/api/v1/admin/tenant-profile`  
**Auth:** `require_role("admin")`

#### `GET /api/v1/admin/tenant-profile`
Returns current tenant company fields.

**Response schema (`TenantProfileOut`):**
```python
class TenantProfileOut(BaseModel):
    nome: str
    cnpj: str | None
    telefone: str | None
    endereco: str | None
    logo_url: str | None   # signed URL, 1h TTL; None if no logo set
    proposta_validade_dias: int
```

#### `PUT /api/v1/admin/tenant-profile`
Updates company text fields + validity days.

**Request schema (`TenantProfileIn`):**
```python
class TenantProfileIn(BaseModel):
    nome: str
    cnpj: str | None = None
    telefone: str | None = None
    endereco: str | None = None
    proposta_validade_dias: int = Field(ge=1, le=30)
```

Note: `nome` updates `tenant.name`. `logo_key` is NOT updated here — logo has its own upload endpoint.

#### `POST /api/v1/admin/tenant-profile/logo`
Multipart file upload. Stores to `StorageBackend`, writes `logo_key` to tenant.

**Constraints enforced at API layer:**
- `Content-Type` must be `image/png` or `image/jpeg`
- File size ≤ 2MB (rejected with HTTP 422 before hitting storage)

**Storage key:** `{tenant_id}/logo/{uuid4()}.{ext}`  
Previous logo key is overwritten on the tenant (old file is orphaned in storage — acceptable, logos change rarely).

**Response:** `TenantProfileOut` (with fresh signed URL for the new logo).

### 2g. Wire into `main.py`

Register `tenant_profile.router` in the FastAPI app.

---

## 3. Frontend

### 3a. New admin page: `TenantProfile.tsx`

**Route:** `/admin/perfil`  
**File:** `frontend/src/routes/admin/TenantProfile.tsx`

Layout:
- **Company info card** — fields: Nome, CNPJ, Telefone, Endereço, Validade da proposta (dias). Save button calls `PUT /api/v1/admin/tenant-profile`.
- **Logo card** — shows current logo thumbnail (from `logo_url`); file input (PNG/JPG only, 2MB max enforced client-side); "Enviar logo" button calls `POST .../logo` as `multipart/form-data`.

Add to `AdminLayout.tsx` nav: `{ label: "Perfil da Empresa", path: "/admin/perfil" }`.

Add to `frontend/src/lib/` — `tenant-profile.ts` with typed API helpers.

### 3b. `SimulacaoEdit.tsx` changes

**Two-step flow** — `SimulacaoEdit.tsx` renders different controls depending on simulation status:

1. **`status == rascunho`** — shows "Confirmar simulação" button. On click: `POST /api/v1/simulations/{id}/confirm`. On success, simulation status updates to `confirmado` in local state. "Gerar Proposta" then becomes available.
2. **`status == confirmado`, no proposal yet** — shows "Gerar Proposta" button.
3. **`status == confirmado`, proposal exists** — shows proposal section (polling / ready / failed).

To avoid a separate API call on mount, extend `SimulationOut` (backend `schemas/simulations.py`) to include `proposal_id: uuid.UUID | None` — populated by a subquery when loading the simulation. `SimulacaoEdit.tsx` reads this to determine initial state.

**Proposal state machine (local to the component):**

```
idle → creating → polling → pronta
                          → failed
```

- `idle`: "Gerar Proposta" button shown
- `creating`: `POST /api/v1/proposals` in flight; button disabled, "Aguarde…"
- `polling`: proposal created; poll `GET /api/v1/proposals/{proposal_id}` every 2s. Stops when `render_status === "ready"` or `render_status === "failed"`.
- `pronta`: "✓ Proposta pronta" + "Baixar PDF" + "Aprovar" buttons
- `failed`: "Erro ao gerar PDF" + "Tentar novamente" (calls `POST /api/v1/proposals/{id}/re-render`)

Poll cleanup: `clearInterval` on unmount. On return to page, `proposal_id` in `SimulationOut` resumes from correct state.

---

## 4. Key Pitfalls

| Risk | Mitigation |
|---|---|
| Large logo balloons PDF memory | 2MB cap enforced at API + client; CSS caps render size at 60px height |
| Poll runs forever if worker crashes | `failed` state stops poll; worker writes `render_status = failed` on exception |
| Combined confirm+create called twice (double-click) | Button disabled immediately on first click; server-side `ConflictError` if proposal already exists for simulation |
| Logo key orphaned on re-upload | Acceptable — logos change rarely; a future cleanup job can prune orphans |
| `sim.status` confirmation skips validation | `ProposalService.create()` should still validate that sim has `client_id` and `vehicle_id` before confirming |

---

## 5. Files Changed

**Backend:**
- `backend/alembic/versions/013_tenant_profile.py` ← new migration
- `backend/finacialsim_saas/data/models.py` ← 5 new Tenant columns
- `backend/finacialsim_saas/schemas/proposals.py` ← extend LojaSnap (add logo_key), update build_snapshot
- `backend/finacialsim_saas/schemas/simulations.py` ← add proposal_id to SimulationOut
- `backend/finacialsim_saas/services/simulation_service.py` ← add `confirm()` method
- `backend/finacialsim_saas/api/simulations.py` ← add `POST /{id}/confirm` endpoint
- `backend/finacialsim_saas/services/proposal_service.py` ← read validade from tenant, validate client_id+vehicle_id
- `backend/finacialsim_saas/workers/tasks.py` ← logo → base64 in _proposta_ctx
- `backend/finacialsim_saas/reports/proposta.html` ← logo img tag
- `backend/finacialsim_saas/reports/proposta.css` ← .loja-logo styles
- `backend/finacialsim_saas/api/tenant_profile.py` ← new file
- `backend/finacialsim_saas/main.py` ← register new router

**Frontend:**
- `frontend/src/routes/admin/TenantProfile.tsx` ← new page
- `frontend/src/routes/admin/AdminLayout.tsx` ← add nav item
- `frontend/src/lib/tenant-profile.ts` ← new API helpers
- `frontend/src/routes/simulacao/SimulacaoEdit.tsx` ← Gerar Proposta button + polling
- `frontend/src/App.tsx` ← add `/admin/perfil` route
