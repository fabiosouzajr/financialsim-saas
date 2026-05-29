# Phase 6 — Portal do cliente + Pix scaffold

> Customer-facing portal where the end client logs in, sees their carnê and parcelas, pays a parcela via Pix, and downloads PDFs. Pix is scaffolded behind a `PixProvider` interface; v1 ships an in-memory fake provider with a staff-side "mark paid" button to exercise the whole flow end-to-end.
>
> **Roadmap:** `2026-05-28-saas-roadmap.md`
> **Predecessor:** Phase 5 — Propostas + PDF/Carnê
> **Successor:** Phase 7 — Notificações + polish

## Goal

End-to-end demo: customer invited via email → sets a password → logs into `/portal/login` → sees financiamento with parcelas in status (paga/aberta/atrasada) → clicks "Pagar com Pix" on the next open parcela → gets QR + copy-paste → staff clicks "Marcar como paga" in the fake-provider admin view → customer sees parcela flip to `paga` within their next poll.

## In scope

### Data layer

- Extend `users` for `customer` role (`client_id` FK, nullable for staff). Customer account created automatically when a proposal is approved (see Phase 5 `proposal_service.approve`). Staff can manually re-invite via `POST /api/v1/clients/{id}/invite` if the customer lost the invite email.
- `pix_charges` — `(id, tenant_id, parcela_payment_id, txid TEXT UNIQUE, brcode TEXT, qrcode_png_key, amount NUMERIC(18,2), expires_at, status created|pending|paid|expired|canceled, provider_payload_json, criado_em, atualizado_em)`. RLS.
- `parcela_payments` — `(id, tenant_id, simulation_id, amortization_row_id, due_date, expected_amount, paid_amount, paid_at, status open|paid|overdue|canceled, last_pix_charge_id)`. Unique `(simulation_id, amortization_row_id)`. Generated eagerly when a proposal transitions to `aprovada` — never lazy.
- `pix_webhook_events` — `(id, received_at, signature_valid, headers_json, body_json, processed, processed_at, error)`. Audit of every PSP callback incl. malformed ones.

### Pix abstraction

```python
class PixProvider(Protocol):
    name: str
    async def create_charge(self, *, txid, amount, expires_in, description, payer) -> PixCharge
    async def cancel_charge(self, txid: str) -> None
    def verify_webhook(self, headers: dict, body: bytes) -> WebhookEvent
```

Implementations:

- `InMemoryFakePixProvider` (v1) — deterministic txid + dummy brcode + placeholder QR PNG. Staff-only `POST /admin/pix/fake/mark-paid/{txid}` synthesizes a webhook through the production code path.
- `StubExternalPixProvider` — interface only, raises `NotImplementedError`. Selected by `PIX_PROVIDER=external` so real wiring is a future drop-in.

### Services

- `parcela_service.list_for_customer(client_id, ctx)` — financiamentos with parcela status; computes overdue on the fly.
- `parcela_service.mark_overdue` — ARQ job daily 02:00 BRT bumps status; emits audit + outbox notification (Phase 7).
- `pix_service.create_charge_for_parcela(parcela_payment_id, ctx)` — idempotent: returns existing open charge, else creates.
- `pix_service.handle_webhook(headers, body)` — verifies signature; idempotent by `(txid, status)`; on `paid` → updates `pix_charges` + `parcela_payments` + audit + outbox notification.
- `customer_auth_service.invite(client_id, ctx)` — creates `users` row with `role='customer'` (if not exists) and enqueues invite email. Called automatically by `proposal_service.approve`; also callable directly by staff for re-invite.

### API endpoints

```
# Customer-scoped (customer JWT)
GET    /api/v1/portal/me
GET    /api/v1/portal/financiamentos                    → list with status counts
GET    /api/v1/portal/financiamentos/{simulation_id}    → full schedule
GET    /api/v1/portal/parcelas/{id}                     → details
POST   /api/v1/portal/parcelas/{id}/pix-charge          → 201 { brcode, qr_url, expires_at }
GET    /api/v1/portal/pix-charges/{id}                  → status (polling)
GET    /api/v1/portal/proposals/{id}/download?kind=…    → 302 signed URL (own only)

# PSP webhook (no auth; HMAC-verified)
POST   /api/v1/webhooks/pix                             → 200 always; rejected payloads logged

# Staff
POST   /api/v1/clients/{id}/invite                      (staff)
POST   /api/v1/admin/pix/fake/mark-paid/{txid}          (admin, fake provider only)
GET    /api/v1/pix-charges                              ?status,?cursor (manager/admin)
```

### Frontend

- `/portal/login` — customer-branded layout.
- `/portal/` — active financiamentos with status badges.
- `/portal/financiamento/:id` — schedule table with parcela chips; "Pagar com Pix" on next open.
- Pix flow modal: QR PNG + copy-paste brcode + expiry countdown + "Já paguei" (polls); auto-closes on `paid` with success animation.
- `/portal/documentos` — proposta + carnê downloads (own only).
- Mobile-first layout.

### Tests

- `InMemoryFakePixProvider` round-trip: create → mark-paid → webhook → parcela paid; audit entries each step.
- Webhook signature: valid accepted; invalid 200 with `signature_valid=false`, no state change.
- Idempotency: replay → no duplicate state, no duplicate audit.
- Customer JWT cannot access another customer's parcelas (404) or staff endpoints (403).
- Overdue job flips an expired open parcela.
- Frontend Vitest: Pix modal renders QR; polling transitions; expiry countdown.
- Playwright E2E: invite → password → login → start Pix → staff marks paid → customer sees paid.

## Out of scope

- Real PSP wiring.
- Pix Automático.
- Customer profile editing.
- Refund / chargeback.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Signature impl drift fake vs real | Shared `verify_webhook` shape; fake mirrors PSP (HMAC-SHA256, header configurable) |
| Customer accidentally exposed staff data | Distinct middleware paths; cross-path access 403 + audit |
| Double-charge for one parcela | `last_pix_charge_id` + idempotent create returns existing open charge |
| Webhook retry storms | Idempotency by `(txid, status)`; retries no-op |
| Customer abandons mid-Pix | Charge expires (default 30 min); polling stops on terminal status |

## Acceptance checklist

- [ ] Approving a proposal (Phase 5) auto-creates customer account and invite email lands in outbox.
- [ ] Staff can re-invite via `POST /clients/{id}/invite` without creating a duplicate account.
- [ ] Customer sets password and logs in.
- [ ] `/portal/` lists financiamentos with correct paid/open/overdue counts.
- [ ] "Pagar com Pix" creates a charge; modal shows QR + brcode + countdown.
- [ ] Staff `mark-paid` triggers webhook path; charge → `paid`, parcela → `paga`, audit entries present.
- [ ] Polling sees status flip within 2 polls.
- [ ] Second `mark-paid` does NOT double-update.
- [ ] Invalid webhook signature: 200, `signature_valid=false`, no state change.
- [ ] Customer A cannot read customer B (404) or staff endpoints (403).
- [ ] Cross-tenant customer isolation verified (RLS catches forged tenant claim).
- [ ] Overdue ARQ job flips expired open parcela.
- [ ] Playwright E2E green.
