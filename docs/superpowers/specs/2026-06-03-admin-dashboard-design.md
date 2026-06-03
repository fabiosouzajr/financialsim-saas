# Admin Dashboard — Design Spec

**Date:** 2026-06-03  
**Status:** Approved  

---

## Overview

A unified admin dashboard accessible at `/admin` with a left sidebar navigation covering 7 sections. Replaces the standalone `/admin/users` page by absorbing it into the new layout.

**Access:** admin role only (enforced at route level via `RequireRole` and at API level via `require_role("admin")`).

---

## Scope

| Section | API | Editable |
|---|---|---|
| Business Rules | existing `GET/PUT /api/v1/business-rules/{chave}` | yes |
| Indicators | existing `GET /api/v1/indicators`, `POST /api/v1/indicators/refresh` | refresh only |
| Audit Log | existing `GET /api/v1/audit-log` | no (read-only) |
| System Health | existing `GET /api/v1/healthz` | no (read-only) |
| SMTP Settings | new `GET/PUT /api/v1/admin/settings/{key}` | yes |
| Pix Settings | new `GET/PUT /api/v1/admin/settings/{key}` | yes |
| User Management | existing `/api/v1/users` | yes (existing logic) |

---

## Architecture

### Routing

```
/admin                → redirect to /admin/regras
/admin/regras         → Business Rules
/admin/indicadores    → Indicators
/admin/auditoria      → Audit Log
/admin/saude          → System Health
/admin/smtp           → SMTP Settings
/admin/pix            → Pix Settings
/admin/users          → User Management
```

`AdminLayout` wraps all sub-routes: renders the sidebar on the left and `<Outlet>` on the right. `App.tsx` nests these routes under a single `<Route path="/admin" element={<AdminLayout />}>` block.

### Frontend Files

```
frontend/src/routes/admin/
  AdminLayout.tsx        — sidebar + <Outlet>, handles active nav state
  BusinessRules.tsx      — inline-edit rules panel
  Indicators.tsx         — BACEN indicator cards + refresh
  AuditLog.tsx           — paginated, filterable audit log table
  SystemHealth.tsx       — provider/infra health status rows
  SmtpSettings.tsx       — inline-edit SMTP fields
  PixSettings.tsx        — inline-edit Pix fields
  Users.tsx              — existing component, no changes

frontend/src/lib/
  admin-settings.ts      — getAdminSettings(), updateAdminSetting(key, value)
  audit-log.ts           — listAuditLog(params)
```

### Backend Files (new)

```
backend/alembic/versions/009_system_settings.py
backend/finacialsim_saas/data/models.py           — add SystemSetting model
backend/finacialsim_saas/services/settings_service.py
backend/finacialsim_saas/api/admin_settings.py
backend/finacialsim_saas/schemas/admin_settings.py
```

---

## Backend: `system_settings` Table

```sql
system_settings (
  tenant_id        UUID NOT NULL REFERENCES tenants(id),
  key              VARCHAR NOT NULL,
  value            TEXT NOT NULL,
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_by_id    UUID REFERENCES users(id),
  PRIMARY KEY (tenant_id, key)
)
```

Seed defaults on first read (if key missing, fall back to `Settings` env value). No secrets encryption in v1 — masked in UI only.

### API Endpoints

```
GET  /api/v1/admin/settings          → dict[str, str]  (admin only)
PUT  /api/v1/admin/settings/{key}    → 204              (admin only)
     body: { value: str }
```

Keys managed: `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `smtp_tls`, `smtp_from`, `email_provider`, `pix_provider`, `pix_webhook_secret`.

`SettingsService.get_all(tenant_id)` reads from DB, falls back to env for any missing key. `SettingsService.update(tenant_id, key, value, ctx)` upserts and writes an audit log entry.

---

## Frontend: Panel Designs

### Business Rules (`/admin/regras`)

Grouped into 4 collapsible sections:
- **Financiamento** — `entrada_minima_pct`, `prazo_minimo_meses`, `prazo_maximo_meses`, `valor_minimo_financiado`
- **Taxas** — `taxa_minima_mes`, `taxa_maxima_mes`, `taxa_por_prazo_curva` (read-only table, editable in future)
- **IOF** — `iof_fixo_pct`, `iof_diario_pct`, `iof_diario_max_dias`, `incluir_iof_default`
- **Padrões** — `dias_max_carencia`, `rateio_ipva_meses_default`, `rateio_emplacamento_meses_default`

**Edit interaction:** click pencil icon on any row → row expands inline showing an input + optional `motivo` field + ✓/✕ buttons. Fires `PUT /api/v1/business-rules/{chave}`. One field editable at a time.

### Indicators (`/admin/indicadores`)

Three cards: SELIC · CDI · IPCA — each shows current value + last-updated timestamp. "Atualizar agora" button fires `POST /api/v1/indicators/refresh` (enqueues ARQ job), shows a loading state, then refetches after 2 s.

### Audit Log (`/admin/auditoria`)

Paginated table columns: `timestamp | usuário | ação | entidade | diff`. Filter dropdown by `ação` (all / create / update / delete). Uses `GET /api/v1/audit-log` with cursor pagination. Read-only.

### System Health (`/admin/saude`)

Status rows: Postgres · Redis · FIPE provider · BACEN provider. Green/yellow/red status pill per service, sourced from `GET /api/v1/healthz`. Auto-refreshes every 30 s with a last-checked timestamp.

### SMTP Settings (`/admin/smtp`)

Fields: `email_provider` (select), `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password` (masked — shows `••••••` until edit mode), `smtp_tls` (toggle), `smtp_from`. Same inline-edit UX as business rules.

### Pix Settings (`/admin/pix`)

Fields: `pix_provider` (select: fake | external), `pix_webhook_secret` (masked). Same inline-edit UX.

### User Management (`/admin/users`)

Existing `Users.tsx` component, rendered inside `AdminLayout`. No code changes to `Users.tsx`.

---

## Edit Interaction Pattern (shared)

Used by Business Rules, SMTP, and Pix panels:

1. Each setting displayed as: `label | current value | pencil icon`
2. Click pencil → row transitions to edit mode: input pre-filled + ✓ (save) + ✕ (cancel)
3. Business Rules rows also show optional `motivo` text input
4. Save fires the relevant PUT endpoint; on success row returns to display mode and value updates
5. Error from API shown inline below the input
6. Only one row editable at a time per panel

---

## Non-Scope (v1)

- Rate curve (`taxa_por_prazo_curva`) editing — shown read-only
- Secrets encryption at rest
- SMTP "send test email" button
- Per-tenant indicator override
- Role: manager can view but not edit (future)
