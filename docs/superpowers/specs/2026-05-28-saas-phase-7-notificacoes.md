# Phase 7 — Notificações (email) + polish

> Real email delivery for the outbox accumulated in earlier phases, observability polish (structured JSON logs + healthcheck extension), and a final UX pass across the staff app and customer portal so v1 is ready to put in front of a real loja.
>
> **Roadmap:** `2026-05-28-saas-roadmap.md`
> **Predecessor:** Phase 6 — Portal do cliente + Pix scaffold
> **Successor:** none (v1 ships; further work in a v2 roadmap)

## Goal

The five trigger events (password reset, customer welcome, Pix link, parcela due-soon, parcela paid) reliably reach the user's inbox, retried with backoff on failure. Mobile responsiveness verified on the golden flows. Structured JSON logging enriched with notification and queue context.

## In scope

### Data layer

- `notifications_outbox` (placeholder from Phase 1) finalized: `(id, tenant_id, channel email|sms|whatsapp, template_key, payload_json, target_email, target_phone, scheduled_for, attempts, status pending|sending|sent|failed|deadlettered, last_error, sent_at, criado_em)`. Index `(status, scheduled_for)`. RLS.
- `email_log` — `(id, tenant_id, outbox_id, provider_message_id, status accepted|delivered|bounced|complained, provider_payload_json, observed_at)`. Populated when provider supports delivery callbacks.

### Notification service

- `notification_service.enqueue(template_key, payload, target, scheduled_for=None, ctx)` — single entry point. Writes outbox row in the same transaction as the triggering event.
- `EmailChannel` — aiosmtplib; provider via env (`EMAIL_PROVIDER` = `smtp` | `ses` | `resend`).
- Templates in `notifications/templates/<template_key>/{subject.txt, body.html, body.txt}` rendered with Jinja2. PT-BR. Plaintext fallback always present.

### Templates wired

| `template_key` | Trigger |
|---|---|
| `auth.password_reset` | Phase 1 — password reset request |
| `auth.user_invite` | Phase 1 — staff user invite |
| `portal.customer_invite` | Phase 6 — customer invite |
| `portal.pix_link` | Phase 6 — customer Pix charge created |
| `portal.parcela_due_soon` | Phase 6 — daily job, parcelas with `due_date = today+3` |
| `portal.parcela_paid` | Phase 6 — webhook paid |
| `portal.parcela_overdue` | Phase 6 — overdue ARQ flipped status |

### Worker

- `drain_notifications_outbox` — every 30 s: picks `pending` AND `scheduled_for <= now` AND `attempts < 5`; sends; on success `sent`; on failure `pending` + exponential backoff (`scheduled_for = now + min(2^attempts minutes, 1h)`); after 5 attempts `deadlettered` + audit + structured error log.
- `schedule_parcela_due_reminders` — daily 08:00 BRT; enqueues `portal.parcela_due_soon` for parcelas with `due_date == today+3`. Idempotent per `(parcela_id, template_key)`.

### Observability polish

- Loguru JSON sink enriched: every log carries `request_id`, `tenant_id`, `user_id`, `route`, `latency_ms`, `status_code`, `notification_template`, `outbox_attempts` (where relevant).
- ARQ worker logs carry `job_name`, `queue_depth`, `duration_ms` per execution.
- `/healthz` extended to ping Postgres + Redis; per-component status returned in payload.

### UX polish pass

For the golden flows (`/login`, `/simulacao`, `/clientes`, `/veiculos`, `/proposals`, `/portal/login`, `/portal/financiamento/:id`):

- Empty states with helpful copy.
- Skeleton loaders on async lists.
- Error boundaries per route with retry action.
- Confirm dialogs for destructive actions.
- Mobile responsiveness: portal at 360w, staff at 768w tablet.
- Form-level error summaries focusing the first errored field.
- ARIA roles + keyboard nav on modals.
- Tab title per route.
- Favicon, social meta.

### CLI quality-of-life

```
finacialsim-saas db migrate
finacialsim-saas db reset --confirm           # dev only
finacialsim-saas notifications retry --outbox-id <id>
finacialsim-saas notifications drain          # ad-hoc
```

### Documentation

- `docs/deploy/docker-compose.md` — reference single-VPS with Caddy auto-TLS.
- `docs/deploy/cloud.md` — sketch for ECS + RDS + S3.
- `docs/runbook/incidents.md` — Pix outage, BACEN degraded, email outage, deadletter pile-up.

## Out of scope

- WhatsApp/SMS adapters (interface present via `channel`; impls deferred).
- Real-time delivery-status push to UI.
- A/B testing on template copy.
- Marketing emails.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Outbox row sent but DB transaction rolled back | Enqueue is part of the triggering transaction; rollback → no row |
| Provider down for hours | Backoff caps at 1 h; alert when `notifications_pending > 100` for > 15 min |
| Spam complaints | Per-tenant rate limit (`MAX_EMAILS_PER_TENANT_PER_HOUR`, default 1000) |
| PII in logs | Loguru pre-formatter masks `email`, `cpf_cnpj`, `password` before any sink writes |
| Deadletter pile-up | `/admin/notifications` page (admin) with retry button |

## Acceptance checklist

- [ ] All five trigger events deliver real email through the configured provider in smoke env.
- [ ] Forced provider failure → backoff → deadletter; metrics + audit entries present.
- [ ] `/healthz` per-component status; failing Redis flips overall.
- [ ] Mobile Lighthouse ≥ 85 on `/simulacao` and `/portal/financiamento/:id`.
- [ ] Tab title, favicon, social meta verified on all routes.
- [ ] Keyboard nav works on all modals; ARIA roles set.
- [ ] CLI retry/drain works against a deadlettered row.
- [ ] Runbook covers the four scenarios end-to-end.
