# Phase 7 — Notificações + Polish — Plan Index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-28-saas-phase-7-notificacoes.md`
**Predecessor:** Phase 6 complete (all 6A–6E sub-plans done)

---

## Sub-plans

| Plan | Scope | Depends On |
|------|-------|------------|
| [7A — Data Layer](2026-06-02-saas-phase-7a-data.md) | Migration 008: new outbox schema + email_log, update models | Phase 6 complete |
| [7B — Notification Service](2026-06-02-saas-phase-7b-notification-service.md) | NotificationService, EmailChannel (aiosmtplib), Jinja2 templates, SMTP settings | 7A |
| [7C — Worker + Wiring](2026-06-02-saas-phase-7c-worker.md) | drain job (30s), schedule_due_reminders, wire 6 trigger sites, delete maildir | 7B |
| [7D — Observability](2026-06-02-saas-phase-7d-observability.md) | /healthz Redis check, JSON logging, PII masking, contextvars enrichment | 7A |
| [7E — CLI](2026-06-02-saas-phase-7e-cli.md) | `db migrate/reset`, `notifications retry/drain` sub-commands | 7B |
| [7F — UX Polish](2026-06-02-saas-phase-7f-ux-polish.md) | Tab titles, favicon, social meta, confirm dialogs, form errors (staff app) | None |
| [7G — Docs](2026-06-02-saas-phase-7g-docs.md) | Full runbook (4 scenarios), deploy stubs | None |

## Execution Order

```
7A → 7B → 7C
               → 7E
7D  (parallel with 7A–7C)
7F  (parallel — frontend only)
7G  (parallel — docs only)
```

7D can start once 7A migration is applied (needs updated models).
7F and 7G have no backend dependencies.

## Key Decisions (grilling session 2026-06-02)

| Topic | Decision |
|-------|----------|
| Outbox schema | Clean drop/recreate in migration 008 |
| Email delivery | smtp + Mailpit for dev/smoke; `EMAIL_PROVIDER=smtp\|ses\|resend` selects prod adapter |
| maildir.py | Deleted entirely when 7C lands |
| Templates directory | Nested: `notifications/templates/auth/password_reset/`, `portal/pix_link/`, etc. |
| Idempotency | `idempotency_key TEXT UNIQUE` on outbox; `INSERT ... ON CONFLICT DO NOTHING` |
| RLS | Application-level tenant filtering (consistent with rest of codebase) |
| Drain interval | 30s cron + Redis lock guard (25s TTL) |
| /healthz shape | 503 on failure; flat `{"status","postgres","redis"}` |
| Structured logging | `contextvars` binding in middleware; patcher + regex for PII masking |
| UX polish scope | Must-have only: tab titles, favicon, confirm dialogs, form errors, portal mobile |
| CLI structure | Split sub-modules: `cli/db.py`, `cli/notifications_cli.py` |
| email_log | Table created in migration 008; write path stubbed (no delivery callbacks in Phase 7) |
| NotificationService | Class with instance methods; session passed per call |
| Rate limit | `MAX_EMAILS_PER_TENANT_PER_HOUR=1000` setting added; enforcement deferred to v2 |
| Timezone | 11:00 UTC hardcoded (= BRT 08:00; DST drift ±1h accepted) |
| Docs | Runbook full; `docker-compose.md` + `cloud.md` as stubs |
| Tests | Split: `test_notification_templates.py`, `test_notification_service.py`, `test_drain_outbox.py` |
| `sending` status | Implemented; stuck-row recovery at 60s via `updated_at` column |
| Non-email channels | Skip with `logger.warning`, leave `pending` |
| Trigger sites | All 6 wired atomically in 7C (single atomic swap, old maildir path deleted) |

## Acceptance Checklist (from spec)

- [ ] All 5 trigger events (password_reset, customer_invite, pix_link, parcela_due_soon, parcela_paid) deliver real email in smoke env
- [ ] Forced provider failure → backoff → deadletter after 5 attempts; audit entries present
- [ ] `/healthz` returns per-component status; failing Redis → 503
- [ ] Tab title, favicon, social meta verified on all staff routes
- [ ] Confirm dialogs on all destructive actions
- [ ] Form-level error summaries focus first errored field
- [ ] CLI `notifications retry/drain` works against a deadlettered row
- [ ] Runbook covers 4 scenarios end-to-end
