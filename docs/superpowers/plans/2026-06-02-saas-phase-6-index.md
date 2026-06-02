# Phase 6 — Portal do Cliente + Pix Scaffold — Plan Index

> **Spec:** `docs/superpowers/specs/2026-05-28-saas-phase-6-portal-cliente-pix.md`

This phase is split into 5 sub-plans to keep each within context window. Execute in order — each plan depends on the previous.

---

## Execution Order

| Plan | File | Focus | Prerequisite |
|------|------|-------|-------------|
| **6A** | [2026-06-02-saas-phase-6a-data-pix.md](2026-06-02-saas-phase-6a-data-pix.md) | Migration 007, models, settings, `pix/` module (protocol/fake/stub/deps) | Phase 5 done |
| **6B** | [2026-06-02-saas-phase-6b-services.md](2026-06-02-saas-phase-6b-services.md) | `RequestContext.client_id`, `AuthService.invite_customer`, `ParcelaService`, `PixService`, `ProposalService` updates | 6A |
| **6C** | [2026-06-02-saas-phase-6c-api.md](2026-06-02-saas-phase-6c-api.md) | Portal API, webhook endpoint, pix admin, client invite, worker cron, main.py | 6B |
| **6D** | [2026-06-02-saas-phase-6d-frontend.md](2026-06-02-saas-phase-6d-frontend.md) | Portal pages, PixModal, customer redirect, AuthContext role, PortalLayout | 6C |
| **6E** | [2026-06-02-saas-phase-6e-tests.md](2026-06-02-saas-phase-6e-tests.md) | Backend integration tests + Vitest PixModal tests | 6D |

---

## Key Design Decisions (from spec grill session 2026-06-02)

| # | Decision |
|---|----------|
| 2 | `ParcelaPaymentStatus` enum: `pending→open`, add `overdue` |
| 3 | Customer account created eagerly in `proposal_service.approve()` |
| 4 | Customer login reuses `/api/v1/auth/login`; frontend redirects by role |
| 6 | Real PNG via `qrcode` library; stored in storage backend at `pix/{charge_id}/qr.png` |
| 7 | Column rename: `pix_charge_id → last_pix_charge_id` |
| 8 | Overdue cron at 05:00 UTC (02:00 BRT) |
| 9 | Same React app; `PortalLayout` for `/portal/...` |
| 10 | Pix modal polls every 3s via React Query `refetchInterval` |
| 16 | `pix/` module mirrors `storage/` pattern |
| 17 | New `ParcelaService` (not bolted onto `ProposalService`) |
| 18 | `mark-paid` endpoint auth: `manager + admin` |
| 22 | QR signed URL TTL: 30 min |
| 23 | `cancel()` implements both TODO Phase 6 items |
| 29 | Pix charge expiry: lazy flip on read in `pix_service` |
| 30 | Router-level redirect: `role=customer` + non-portal path → `/portal/` |
| 34 | Single migration `007` for all schema changes |

---

## New Files Created

### Backend
```
backend/alembic/versions/007_phase6_pix.py
backend/finacialsim_saas/pix/__init__.py
backend/finacialsim_saas/pix/protocol.py
backend/finacialsim_saas/pix/fake.py
backend/finacialsim_saas/pix/stub.py
backend/finacialsim_saas/pix/deps.py
backend/finacialsim_saas/pix/service.py
backend/finacialsim_saas/services/parcela_service.py
backend/finacialsim_saas/api/portal.py
backend/finacialsim_saas/api/webhooks.py
backend/finacialsim_saas/api/pix_admin.py
backend/tests/test_pix_provider.py
backend/tests/test_pix_service.py
backend/tests/test_portal_endpoints.py
backend/tests/test_proposal_cancel_phase6.py
backend/tests/test_auth_invite.py
backend/tests/test_parcela_service.py
backend/tests/test_proposal_phase6.py
backend/tests/test_deps_client_id.py
```

### Frontend
```
frontend/src/lib/portal.ts
frontend/src/components/PortalLayout.tsx
frontend/src/routes/portal/PortalHome.tsx
frontend/src/routes/portal/PortalFinanciamento.tsx
frontend/src/routes/portal/PortalDocumentos.tsx
frontend/src/routes/portal/PixModal.tsx
frontend/src/tests/pix-modal.test.tsx
```

### Modified Files
```
backend/pyproject.toml                          (add qrcode dep)
backend/finacialsim_saas/data/models.py         (PixCharge, PixWebhookEvent, enum changes)
backend/finacialsim_saas/settings.py            (PIX_PROVIDER, PIX_WEBHOOK_SECRET)
backend/finacialsim_saas/auth/deps.py           (RequestContext.client_id)
backend/finacialsim_saas/auth/service.py        (invite_customer, re_invite, authenticate)
backend/finacialsim_saas/services/proposal_service.py  (approve, cancel, constructor)
backend/finacialsim_saas/api/proposals.py       (inject auth_service into ProposalService)
backend/finacialsim_saas/api/clients.py         (add /invite endpoint)
backend/finacialsim_saas/main.py                (register 3 new routers)
backend/finacialsim_saas/workers/tasks.py       (add mark_overdue_parcelas)
backend/finacialsim_saas/workers/worker.py      (cron + pix_provider in ctx)
frontend/src/context/AuthContext.tsx            (expose role)
frontend/src/App.tsx                            (portal routes, CustomerGuard)
```
