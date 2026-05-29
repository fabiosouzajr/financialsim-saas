# Phase 5 — Propostas + PDF/Carnê (worker-rendered)

> Generate proposta and carnê PDFs in the ARQ worker using the existing Jinja2 + WeasyPrint templates, store them through a swappable `StorageBackend`, and download them from the React app.
>
> **Roadmap:** `2026-05-28-saas-roadmap.md`
> **Predecessor:** Phase 3 — Cadastros (Phase 4 runs in parallel; does not block this phase)
> **Successor:** Phase 6 — Portal do cliente + Pix scaffold

## Goal

A staff user selects "Gerar proposta" on a saved simulação, waits a few seconds (the worker renders), then downloads a byte-for-byte match of the desktop output on the fixture cases. The same fixture later renders a carnê PDF.

> **First task of this phase:** Validate WeasyPrint renders the existing `reports/proposta.html` and `reports/carne.html` templates correctly on Linux (the desktop ran on Windows; Linux rendering is untested). Block all other Phase 5 work until confirmed — if the templates require fixes, do them before building the worker pipeline.

## In scope

### Data layer

- `proposals` — `(id, tenant_id, codigo, simulation_id, cliente_id, gerado_por, snapshot_json, pdf_key, carne_key, validade_dias, gerado_em, render_status pending|rendering|ready|failed, render_error, status rascunho|ready|aprovada|cancelada, aprovado_por, aprovado_em, cancelado_por, cancelado_em)`. Unique `(tenant_id, codigo)`. Unique `(tenant_id, simulation_id)` — one proposal per simulation. RLS.

  Status flow: `rascunho → (PDF renders) → ready → aprovada → cancelada`. `render_status` tracks the async PDF job; `status` tracks the business lifecycle. Only `aprovada` and `cancelada` are terminal business states.

### Storage abstraction

```python
class StorageBackend(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> str
    async def get(self, key: str) -> bytes
    async def signed_url(self, key: str, expires_in: int = 300) -> str
    async def delete(self, key: str) -> None
```

Implementations:

- `LocalVolumeBackend` — writes under `STORAGE_LOCAL_ROOT/<tenant_id>/proposals/<id>.pdf`; signed URL is a short-lived signed HTTP path served by the API.
- `S3Backend` — boto3 against any S3-compatible (AWS S3, MinIO, R2); signed URL is presigned.

Selected by `STORAGE_BACKEND` env. Tenant prefix is enforced by `storage_service.put`, not callers, so a misbehaving service can't write outside its tenant prefix.

### Services

- `proposal_service.create(simulation_id, ctx)` — validates sim is `finalizada` (or auto-finalizes); rejects if a proposal already exists for this simulation (`UNIQUE` constraint); creates row with `status='rascunho'`, snapshots simulation + cliente + veículo + rules + indicators, enqueues `render_proposta_pdf`, returns 202.
- `proposal_service.approve(id, ctx)` — only from `status='ready'`; ownership: vendedor approves own, manager/admin approve any in tenant. Sets `status='aprovada'`, `aprovado_por`, `aprovado_em`. In the same transaction: generates all `parcela_payments` rows for the full schedule and enqueues the customer portal invite email.
- `proposal_service.cancel(id, ctx)` — only from `status='aprovada'`; same ownership rule. Sets `status='cancelada'`. Cascade: all `parcela_payments → canceled`, open `pix_charges` canceled via `pix_service.cancel_charge()`, customer `users` row deactivated, cancellation notification enqueued.
- `proposal_service.create_carne(proposal_id, ctx)` — only if `status='aprovada'`; enqueues `render_carne_pdf`.
- `proposal_service.get(id, ctx)` — returns row incl. `render_status` and `status`.
- `proposal_service.download_pdf(id, kind, ctx)` — returns signed URL (5 min).

### Worker tasks

- `render_proposta_pdf(proposal_id)` — load snapshot, render `reports/proposta.html` via Jinja2, WeasyPrint to PDF, store via `StorageBackend`, set `pdf_key` + `render_status='ready'`. On exception: `failed` + `render_error` and audit entry. Manual re-enqueue endpoint exists.
- `render_carne_pdf(proposal_id)` — same shape, writes `carne_key`.

Renders read from `snapshot_json` only — never re-queries — so a proposta from 2026 renders identically in 2027.

### API endpoints

```
POST   /api/v1/proposals                                { simulation_id } → 202 + { id, status }
GET    /api/v1/proposals/{id}                           → row incl. render_status + status
POST   /api/v1/proposals/{id}/approve                   (own or manager/admin) → 200
POST   /api/v1/proposals/{id}/cancel                    (own or manager/admin) → 200
POST   /api/v1/proposals/{id}/render-carne              (aprovada only) → 202
GET    /api/v1/proposals/{id}/download?kind=proposta    → 302 to signed URL
GET    /api/v1/proposals/{id}/download?kind=carne       → 302 to signed URL
POST   /api/v1/proposals/{id}/re-render?kind=…          (admin) → re-enqueue
GET    /api/v1/proposals                                ?simulation_id,?cliente_id,?status,?cursor
```

### Frontend

- On `/simulacao/:id`: "Gerar proposta" → `POST /proposals`; render-status pill polled every 2s (pending → rendering → ready / failed).
- When `status='ready'`: "Baixar proposta (PDF)" + "Aprovar proposta" buttons visible to staff with ownership.
- "Aprovar proposta" → `POST /proposals/{id}/approve` → success toast; parcela_payments generated + customer invite sent automatically.
- When `status='aprovada'`: "Gerar carnê" button appears; "Cancelar proposta" button visible.
- "Cancelar proposta" → confirmation dialog → `POST /proposals/{id}/cancel`.
- Failure: error message + admin-only "Re-renderizar".
- `/propostas` list page: paginated, filter by cliente, status (rascunho/ready/aprovada/cancelada), date.

### Tests

- Storage backend contract test parametrized for Local + MinIO (S3) — same assertions pass both.
- WeasyPrint render: extract text via pdfminer, compare against golden file. No chart in Phase 5 — proposta PDF ships with a data table instead; chart added in a later polish phase.
- Worker task: success path, exception path sets `failed`, re-enqueue resets status.
- Cross-tenant: tenant A cannot download tenant B's proposta (404); direct key forgery rejected.
- Reproducibility: two renders byte-identical after `/CreationDate` and `/ID` normalization.
- Frontend: pill state transitions; download click hits signed URL.

## Out of scope

- WhatsApp/email delivery of PDF (Phase 7 emails the link).
- Customer-side download (Phase 6 portal).
- Bulk operations.
- E-signature.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| WeasyPrint native deps drift | Pin version; document system packages in Dockerfile.worker |
| Reproducibility broken by PDF metadata | Normalize `/CreationDate` and `/ID` post-render |
| Snapshot bloat | Include only rendered fields; reject extras at snapshot-builder boundary |
| Misforged storage key | Enforce tenant prefix in `storage_service.put`; tests assert |
| Render queue backlog | Per-tenant rate limit on `POST /proposals` (10/min, env-tunable) |

## Acceptance checklist

- [ ] `POST /proposals` → 202 with status URL.
- [ ] Second `POST /proposals` for same simulation → 409 (UNIQUE constraint enforced).
- [ ] Polling shows `pending → rendering → ready` within 4 s on fixture.
- [ ] Download signed URL serves the PDF; text extraction matches desktop golden (data table, no chart).
- [ ] `POST /proposals/{id}/approve` → `status='aprovada'`; `parcela_payments` rows exist for every amortization row; customer invite outbox row exists.
- [ ] Vendedor cannot approve another vendedor's proposal; manager/admin can.
- [ ] `POST /proposals/{id}/cancel` from `aprovada` → cascade: `parcela_payments` all `canceled`, customer account deactivated, audit entry present.
- [ ] Carnê render only possible when `status='aprovada'`; rejected otherwise.
- [ ] Two renders of the same proposal are byte-identical after metadata normalization.
- [ ] Storage contract test passes both `local` and `s3` (MinIO).
- [ ] Tenant A cannot download tenant B's proposta (incl. direct key forgery).
- [ ] Failed render surfaces error; admin re-render works.
