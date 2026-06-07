# Admin Dashboard — Design Spec

**Date:** 2026-06-03
**Status:** Approved (post-grill)

---

## Overview

A unified admin dashboard at `/admin` with a left sidebar covering 7 sections. Absorbs the existing `/admin/users` page. Admin role only.

---

## Scope

| Section | API | Editable |
|---|---|---|
| Business Rules | existing `GET/PUT /api/v1/business-rules/{chave}` | yes — inline per field |
| Indicators | existing `GET /api/v1/indicators`, `POST /api/v1/indicators/refresh` | refresh only |
| Audit Log | existing `GET /api/v1/audit-log` | no |
| System Health | new `GET /api/v1/admin/health` | no |
| SMTP Settings | new `GET/PUT /api/v1/admin/settings/{key}` | yes — inline per field |
| Pix Settings | env read-only via `GET /api/v1/admin/settings` | **no** — display only |
| User Management | existing `/api/v1/users` | yes — existing logic |

---

## Architecture

### Routing

```
/admin              → redirect to /admin/regras
/admin/regras       → Business Rules
/admin/indicadores  → Indicators
/admin/auditoria    → Audit Log
/admin/saude        → System Health
/admin/smtp         → SMTP Settings
/admin/pix          → Pix Settings (read-only)
/admin/users        → User Management
```

`AdminLayout` wraps all sub-routes with `<Outlet>`. `App.tsx` nests these under:
```tsx
<Route path="/admin" element={<RequireRole roles={["admin"]}><AdminLayout /></RequireRole>}>
  <Route index element={<Navigate to="regras" replace />} />
  ...sub-routes...
</Route>
```
Existing flat `/admin/users` route in `App.tsx` is removed and replaced by this block.

`Index.tsx` dashboard card "Usuários" → renamed "Administração", href `/admin`.

### Frontend Files

```
frontend/src/
  components/
    EditableField.tsx          ← new: shared inline-edit component
  routes/admin/
    AdminLayout.tsx            ← new: sidebar + <Outlet> + back-link to /
    BusinessRules.tsx          ← new
    Indicators.tsx             ← new
    AuditLog.tsx               ← new
    SystemHealth.tsx           ← new
    SmtpSettings.tsx           ← new
    PixSettings.tsx            ← new (read-only display)
    Users.tsx                  ← existing, no changes
  lib/
    admin-settings.ts          ← new: getAdminSettings(), updateAdminSetting()
    audit-log.ts               ← new: listAuditLog(params)
```

### Backend Files (new)

```
backend/alembic/versions/009_system_settings.py
backend/finacialsim_saas/
  data/models.py                    ← add SystemSetting model
  notifications/channel.py          ← refactor: accept individual kwargs, not Settings
  services/settings_service.py      ← new
  api/admin_settings.py             ← GET + PUT /api/v1/admin/settings
  api/admin_health.py               ← GET /api/v1/admin/health (admin-only)
  schemas/admin_settings.py         ← new
  workers/notifications.py          ← wire to SettingsService instead of get_settings()
  tests/test_admin_settings.py      ← new integration tests
```

---

## Backend: `system_settings` Table (global, no tenant)

```sql
system_settings (
  key          VARCHAR PRIMARY KEY,
  value        TEXT NOT NULL,
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_by   VARCHAR                            -- user email, for audit trail
)
```

**Scope: platform-global.** No `tenant_id` — SMTP is infrastructure-level config shared across the deployment. The notification worker reads one SMTP config for all tenants.

**Fallback:** `SettingsService.get_all()` reads from DB; any missing key falls back to the equivalent `Settings` env value. No seeding — lazy fallback is sufficient.

### Writable Keys

`smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `smtp_tls`, `smtp_from`, `email_provider`

### Read-Only (env-only) Keys

`pix_provider`, `pix_webhook_secret` — the Pix webhook has no JWT/tenant context, so these cannot be DB-driven. The `GET /api/v1/admin/settings` response includes them sourced from env with a `"source": "env"` flag. `PUT` rejects writes to these keys (422).

### API Endpoints

```
GET  /api/v1/admin/settings          → dict[str, SettingItem]  (admin only)
PUT  /api/v1/admin/settings/{key}    → 204                      (admin only)
     body: { value: str }
     rejects non-writable keys with 422
```

---

## Backend: `EmailChannel` Refactor

`EmailChannel.__init__` changes from accepting `Settings` to individual kwargs:

```python
class EmailChannel:
    def __init__(self, *, smtp_host, smtp_port, smtp_user, smtp_password, smtp_tls, smtp_from):
        ...
```

`drain_notifications_outbox` worker reads settings from `SettingsService` (DB + env fallback) and constructs `EmailChannel` with those values. `EmailChannel` is only constructed in one place — the notification worker.

---

## Backend: `/api/v1/admin/health`

Admin-only endpoint (JWT required). Returns combined health:

```json
{
  "postgres": "ok",
  "redis": "ok",
  "providers": {
    "fipe_parallelum": { "success": true, "latency_ms": 120, "checked_at": "..." },
    "bacen_sgs":       { "success": false, "error": "timeout", "checked_at": "..." }
  }
}
```

Sources: Postgres + Redis checked live (same logic as public `/healthz`). Provider health read from latest `provider_health` row per `provider_name`. Public `/healthz` unchanged.

---

## Backend: `AuditLogItem` Enrichment

Add `usuario_email: str | None` to `AuditLogItem` schema. `AuditService.list()` LEFT JOINs `users` on `usuario_id` to populate it. Displayed in the audit log table as the "Usuário" column instead of the raw UUID.

---

## Frontend: `EditableField` Component

Shared component used by Business Rules, SMTP panels:

```tsx
<EditableField
  label="Entrada mínima (%)"
  value="20"
  type="number" | "text" | "password" | "select" | "toggle"
  onSave={(value: string) => Promise<void>}
  motivo={true}          // shows motivo field (Business Rules only)
  options={[...]}        // for select type
/>
```

- `toggle` type: renders `<Switch>` directly in the row — no pencil, fires `onSave` on change immediately
- `password` type: masked display; input shown only in edit mode
- Only one field editable at a time per panel
- Errors shown inline below the input

Boolean fields (`incluir_iof_default`, `smtp_tls`): use `toggle` type — no pencil icon, instant save.

---

## Frontend: Panel Designs

### Business Rules (`/admin/regras`)

Grouped into 4 sections (open by default):

| Group | Keys |
|---|---|
| Financiamento | `entrada_minima_pct`, `prazo_minimo_meses`, `prazo_maximo_meses`, `valor_minimo_financiado` |
| Taxas | `taxa_minima_mes`, `taxa_maxima_mes`, `taxa_por_prazo_curva` (read-only table) |
| IOF | `iof_fixo_pct`, `iof_diario_pct`, `iof_diario_max_dias`, `incluir_iof_default` (toggle) |
| Padrões | `dias_max_carencia`, `rateio_ipva_meses_default`, `rateio_emplacamento_meses_default` |

All fields use `<EditableField motivo={true}>` except `incluir_iof_default` (toggle). Rate curve shown as read-only table — no edit.

### Indicators (`/admin/indicadores`)

Three cards: SELIC · CDI · IPCA — value + last-updated timestamp. "Atualizar agora" button → `POST /api/v1/indicators/refresh`, loading state, refetches after 2 s. Stale data is acceptable if job hasn't completed — `checked_at` timestamp communicates freshness.

### Audit Log (`/admin/auditoria`)

Paginated table: `timestamp | usuário (email) | ação | entidade | diff`. Filter by `ação` (all / create / update / delete). "Ver detalhes" expand button per row shows `diff_json` as formatted JSON in a `<pre>`. CSV export button (proxies `?format=csv`).

### System Health (`/admin/saude`)

Status rows from `GET /api/v1/admin/health`: Postgres · Redis · FIPE providers · BACEN providers. Green/red pill + latency for providers, ok/error for infra. Auto-refreshes every 30 s with last-checked timestamp.

### SMTP Settings (`/admin/smtp`)

`EditableField` rows: `email_provider` (select), `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password` (password type), `smtp_tls` (toggle), `smtp_from`. No motivo field.

### Pix Settings (`/admin/pix`)

Display-only. Shows `pix_provider` and masked `pix_webhook_secret` from env. Badge: "Configurado via variável de ambiente". No pencil icons.

### User Management (`/admin/users`)

Existing `Users.tsx` unchanged, rendered inside `AdminLayout`.

---

## Tests (`test_admin_settings.py`)

Minimum viable — follows existing integration test patterns:

1. `GET /api/v1/admin/settings` returns env defaults when table is empty
2. `PUT` + `GET` round-trip persists value
3. Non-admin `PUT` returns 403
4. `PUT` to a read-only key (`pix_provider`) returns 422

---

## Non-Scope (v1)

- Rate curve (`taxa_por_prazo_curva`) editing
- Secrets encryption at rest
- SMTP "send test email" button
- Per-tenant SMTP or Pix overrides
- Manager read-only view of admin panel
