# Phase 6 — Portal do cliente + Pix scaffold

> Customer-facing portal where the end client logs in, sees their carnê and parcelas, pays a parcela via Pix, and downloads PDFs. Pix is scaffolded behind a `PixProvider` interface; v1 ships an in-memory fake provider with a staff-side "mark paid" button to exercise the whole flow end-to-end.
>
> **Roadmap:** `2026-05-28-saas-roadmap.md`
> **Predecessor:** Phase 5 — Propostas + PDF/Carnê
> **Successor:** Phase 7 — Notificações + polish

## Design decisions (grill session 2026-06-02)

| # | Decision | Choice |
|---|---|---|
| 1 | `parcela_payments` key | Keep `proposal_id + parcela_num` (Phase 5 landed; no migration) |
| 2 | `ParcelaPaymentStatus` enum | Rename `pending→open`, add `overdue`; new migration |
| 3 | Customer account creation timing | Eager in `proposal_service.approve()` |
| 4 | Customer login endpoint | Reuse `/api/v1/auth/login`; frontend redirects by role |
| 5 | Invite/password-set mechanism | Reuse `PasswordResetToken` (72h TTL) |
| 6 | Fake Pix QR code | Real PNG via `qrcode` library stored in storage backend |
| 7 | Column rename | `pix_charge_id → last_pix_charge_id` on `parcela_payments` |
| 8 | Overdue cron schedule | ARQ cron at 05:00 UTC hardcoded (02:00 BRT) |
| 9 | Portal frontend | Same React app; `PortalLayout` for `/portal/...` routes |
| 10 | Pix modal polling | Fixed 3s `refetchInterval` via React Query |
| 11 | Webhook HMAC secret | Single `PIX_WEBHOOK_SECRET` env var |
| 12 | Tenant isolation | Application-level `tenant_id` check; no Postgres RLS |
| 13 | Webhook idempotency logging | Always log to `pix_webhook_events`, including replays |
| 14 | Portal PDF download | New portal endpoint; same `ProposalService.download_pdf()` |
| 15 | Customer auth service | Methods `invite_customer` + `re_invite` on existing `AuthService` |
| 16 | PixProvider location | New `pix/` module (mirrors `storage/` pattern) |
| 17 | Parcela lifecycle service | New `ParcelaService` (not bolted onto `ProposalService`) |
| 18 | `mark-paid` endpoint auth | `manager + admin` (not admin-only) |
| 19 | Portal frontend state | React Query (`useQuery`, `refetchInterval`) |
| 20 | Playwright E2E | Deferred to Phase 7 (invite email not wired until then) |
| 21 | Invite outbox payload | `{"proposal_id": "...", "user_id": "..."}` — no raw token |
| 22 | QR signed URL TTL | 30 min (matches charge expiry); not refreshed on each poll |
| 23 | `cancel()` Phase 6 TODOs | Implement both: deactivate customer user + cancel open pix charges |
| 24 | `/portal/financiamentos` shape | Proposal-centric; snapshot data — no live simulation join |
| 25 | `/portal/me` response | User fields only (`id`, `email`, `name`, `role`, `client_id`) |
| 26 | `mark_overdue` outbox | Creates `NotificationsOutbox` entry now; Phase 7 processes it |
| 27 | StubExternalPixProvider | Included; selected by `PIX_PROVIDER=external`, raises `NotImplementedError` |
| 28 | QR storage key | `pix/{charge_id}/qr.png` |
| 29 | Pix charge expiry | Lazy flip on read in `pix_service`; no dedicated cron |
| 30 | Portal route guard | Router-level redirect: `role=customer` + non-portal path → `/portal/` |
| 31 | Re-invite token handling | Invalidate existing active token, issue fresh one |
| 32 | Customer JWT | Includes `client_id` claim (null for staff) |
| 33 | `pix_charges.status` enum | `pending\|paid\|expired\|canceled` (drop `created`) |
| 34 | Phase 6 migration | Single `007` migration for all schema changes |

## Goal

End-to-end demo: customer invited via email → sets a password → logs into `/portal/login` → sees financiamento with parcelas in status (paga/aberta/atrasada) → clicks "Pagar com Pix" on the next open parcela → gets QR + copy-paste → staff clicks "Marcar como paga" in the fake-provider admin view → customer sees parcela flip to `paga` within their next poll.

## In scope

### Data layer

Migration `007` covers all of the following:

- **`parcela_payments`** (existing table — alter only):
  - `ALTER TYPE parcela_payment_status RENAME VALUE 'pending' TO 'open'`
  - `ALTER TYPE parcela_payment_status ADD VALUE 'overdue'`
  - `ALTER TABLE parcela_payments RENAME COLUMN pix_charge_id TO last_pix_charge_id`
  - Add `paid_amount NUMERIC(18,2)` nullable column
- **`pix_charges`** (new): `(id, tenant_id, parcela_payment_id FK, txid TEXT UNIQUE, brcode TEXT, qrcode_png_key TEXT, amount NUMERIC(18,2), expires_at TIMESTAMPTZ, status pending|paid|expired|canceled, provider_payload_json JSON, criado_em, atualizado_em)`. Application-level tenant isolation.
- **`pix_webhook_events`** (new): `(id, received_at, signature_valid BOOL, headers_json JSON, body_json JSON, processed BOOL, processed_at TIMESTAMPTZ, error TEXT)`. Append-only audit of every inbound PSP callback including malformed and replayed ones.
- **`users`**: `client_id` nullable FK and `customer` role already present from Phase 5. No migration needed.

### Pix abstraction (`backend/finacialsim_saas/pix/`)

Mirrors the `storage/` module structure:

```
pix/
  __init__.py      — exports PixProvider protocol, PixCharge, WebhookEvent
  protocol.py      — Protocol + dataclasses
  fake.py          — InMemoryFakePixProvider
  stub.py          — StubExternalPixProvider (raises NotImplementedError)
  service.py       — PixService
  deps.py          — get_pix_provider() reads PIX_PROVIDER env var
```

```python
class PixProvider(Protocol):
    name: str
    async def create_charge(self, *, txid, amount, expires_in, description, payer) -> PixCharge
    async def cancel_charge(self, txid: str) -> None
    def verify_webhook(self, headers: dict, body: bytes) -> WebhookEvent
```

- `InMemoryFakePixProvider` — generates real QR PNG via `qrcode` library stored at `pix/{charge_id}/qr.png`. Deterministic `txid`. `verify_webhook` always returns valid for its own payloads.
- `StubExternalPixProvider` — all methods raise `NotImplementedError`. Selected by `PIX_PROVIDER=external`.
- Default: `PIX_PROVIDER=fake`.

### Settings additions

```python
PIX_PROVIDER: str = "fake"
PIX_WEBHOOK_SECRET: str = ""   # HMAC-SHA256 key for webhook verification
```

### Services

- **`ParcelaService`** (new `services/parcela_service.py`):
  - `list_for_customer(client_id, ctx)` — returns approved proposals with parcela status counts and next open parcela; overdue computed on-the-fly from `vencimento < today`.
  - `get_parcela(parcela_id, ctx)` — single parcela detail, customer-owned check.
  - `mark_overdue(ctx)` — ARQ cron job (05:00 UTC daily); flips `open` parcelas past due to `overdue`; writes audit entry + `NotificationsOutbox(type="parcela_overdue")` per flip.

- **`PixService`** (new `pix/service.py`):
  - `create_charge_for_parcela(parcela_payment_id, ctx)` — idempotent: returns existing `pending` charge if one exists, else creates new via provider. Stores QR PNG at `pix/{charge_id}/qr.png`. Returns signed URL (30-min TTL matching charge expiry). Lazy-flips `expired` charges before checking for existing open one.
  - `handle_webhook(headers, body)` — always logs to `pix_webhook_events`; verifies HMAC; idempotent by `(txid, status)`; on `paid` → updates `pix_charges` + `parcela_payments(status=paid, paid_at, paid_amount, last_pix_charge_id)` + audit.
  - `get_charge(charge_id, ctx)` — lazy-flips expiry; returns charge with fresh signed `qr_url`.
  - `cancel_charges_for_proposal(proposal_id)` — cancels all `pending` charges for a proposal's parcelas (called by `proposal_service.cancel()`).

- **`AuthService`** additions:
  - `invite_customer(client_id, ctx)` — creates `User(role=customer, client_id=...)` with unusable password hash if not exists; invalidates any existing active `PasswordResetToken` for the user; issues new `PasswordResetToken` (72h TTL); writes `NotificationsOutbox(type="customer_invite", payload={"proposal_id": ..., "user_id": ...})`.
  - `re_invite(client_id, ctx)` — calls `invite_customer` for an existing customer user (same logic: invalidate old token, issue new).

- **`ProposalService`** changes:
  - `approve()` — after creating `ParcelaPayment` rows, calls `auth_service.invite_customer(sim.client_id, ctx)`.
  - `cancel()` — implement both Phase 6 TODOs: deactivate customer `User(is_active=False)` linked to this proposal; call `pix_service.cancel_charges_for_proposal(proposal.id)`.

- **`AuthService.issue_tokens()`** — include `client_id` in JWT payload (null for staff).

### API endpoints

```
# Customer-scoped (role=customer JWT required)
GET    /api/v1/portal/me                                  → {id, email, name, role, client_id}
GET    /api/v1/portal/financiamentos                      → list of proposals with parcela status counts
GET    /api/v1/portal/financiamentos/{proposal_id}        → full parcela schedule
GET    /api/v1/portal/parcelas/{id}                       → single parcela detail
POST   /api/v1/portal/parcelas/{id}/pix-charge            → 201 { brcode, qr_url, expires_at }
GET    /api/v1/portal/pix-charges/{id}                    → { status, brcode, qr_url, expires_at } (polling)
GET    /api/v1/portal/proposals/{id}/download?kind=…      → 302 signed URL (own proposals only)

# PSP webhook (no JWT; HMAC-SHA256 verified via PIX_WEBHOOK_SECRET)
POST   /api/v1/webhooks/pix                               → 200 always; all payloads logged to pix_webhook_events

# Staff
POST   /api/v1/clients/{id}/invite                        (manager|admin)
POST   /api/v1/admin/pix/fake/mark-paid/{txid}            (manager|admin; fake provider only — 501 if PIX_PROVIDER=external)
GET    /api/v1/pix-charges                                ?status,?cursor (manager|admin)
```

### Frontend

- **`PortalLayout`** — mobile-first wrapper for all `/portal/...` routes; distinct nav from staff `AppLayout`.
- **Router** — top-level redirect: authenticated `customer` role + non-`/portal` path → `/portal/`.
- **`RequireRole`** — no changes needed; portal routes use `<RequireRole roles={["customer"]}>`.
- `/portal/login` — calls existing `/api/v1/auth/login`; on success redirects `customer` → `/portal/`, staff → `/`.
- `/portal/` — lists financiamentos (proposal cards) with paid/open/overdue badge counts.
- `/portal/financiamento/:proposalId` — parcela schedule table; "Pagar com Pix" button on next open parcela.
- **Pix modal** — shows QR PNG + copy-paste brcode + expiry countdown; polls `GET /portal/pix-charges/{id}` every 3s via React Query `refetchInterval`; auto-closes on `paid` status with success animation; stops polling on terminal status (`paid|expired|canceled`).
- `/portal/documentos` — proposta + carnê PDF download links (own proposals only).

### Tests

- `InMemoryFakePixProvider` round-trip: create → mark-paid → webhook → parcela `paid`; audit + webhook event entries verified at each step.
- Webhook signature: valid HMAC accepted and processed; invalid HMAC returns 200 with `signature_valid=false`, no state change.
- Idempotency: replay same webhook → no duplicate `parcela_payments` update, no duplicate audit entry; second `pix_webhook_events` row logged with `processed=false`.
- Customer JWT cannot access another customer's parcelas (404) or staff endpoints (403).
- Cross-tenant: customer A's token cannot read tenant B's parcelas.
- Overdue ARQ job flips `open` parcelas past due to `overdue`; writes audit + outbox entry.
- `invite_customer` creates user + token; `re_invite` invalidates old token and issues new one.
- `proposal_service.cancel()` deactivates customer user and cancels open pix charges.
- Vitest: Pix modal renders QR image; polling hook transitions `pending→paid`; expiry countdown decrements.

## Out of scope

- Real PSP wiring.
- Pix Automático.
- Customer profile editing.
- Refund / chargeback.
- Playwright E2E (deferred to Phase 7 when invite email is wired).
- Postgres RLS (application-level isolation only).

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Signature impl drift fake vs real | Shared `verify_webhook` shape; fake uses HMAC-SHA256 mirroring real PSP header convention |
| Customer accidentally exposed staff data | Distinct route prefixes; `RequireRole roles=["customer"]` on all portal routes; router redirect for mis-routed staff |
| Double-charge for one parcela | `last_pix_charge_id` + idempotent create returns existing `pending` charge |
| Webhook retry storms | Idempotency by `(txid, status)`; retries logged but no-op on state |
| Customer abandons mid-Pix | Charge expires (30 min); lazy flip on next poll; polling stops on terminal status |
| Circular FK `pix_charges ↔ parcela_payments` | Insert `pix_charges` first, then update `parcela_payments.last_pix_charge_id` — no constraint issue |

## Acceptance checklist

- [ ] Approving a proposal auto-creates customer `User` row + `PasswordResetToken` (72h); outbox entry has `user_id`.
- [ ] Staff can re-invite via `POST /clients/{id}/invite`; old token invalidated, new token issued; no duplicate user.
- [ ] Customer sets password at `/reset-password?token=...` and logs in at `/portal/login`.
- [ ] Customer JWT contains `client_id` claim.
- [ ] `/portal/` lists financiamentos with correct paid/open/overdue counts from snapshot data.
- [ ] "Pagar com Pix" creates a charge; modal shows real QR PNG + brcode + countdown.
- [ ] Staff `mark-paid` (manager or admin) triggers webhook path; charge → `paid`, parcela → `paid`, audit + webhook event entries present.
- [ ] Polling sees status flip within 2 polls (3s interval).
- [ ] Second `mark-paid` does NOT double-update; second webhook event row has `processed=false`.
- [ ] Invalid webhook signature: 200, `signature_valid=false`, no state change, event logged.
- [ ] Customer A cannot read customer B's parcelas (404) or staff endpoints (403).
- [ ] Cross-tenant customer isolation verified (application-level `tenant_id` check).
- [ ] Canceling a proposal deactivates customer user and cancels open pix charges.
- [ ] Overdue ARQ job (05:00 UTC) flips expired open parcelas; outbox entry created per flip.
- [ ] `PIX_PROVIDER=external` → 501 on `mark-paid`; all other provider calls raise `NotImplementedError`.
