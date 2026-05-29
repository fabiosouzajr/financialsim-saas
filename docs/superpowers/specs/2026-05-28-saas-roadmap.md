# FinacialSim SaaS — Master Roadmap

> Refactor of the desktop FinacialSim into a web/mobile/tablet-accessible SaaS for internal modernization across 1–5 lojas, with multi-tenancy scaffolding, customer-facing portal, and Pix-scaffolded payments.
>
> **Date:** 2026-05-28
> **Predecessor:** `2026-05-23-finacialsim-design.md` (desktop spec — kept for reference; desktop app keeps running until SaaS reaches parity)
> **Target repo:** new `finacialsim-saas` (separate from this one)
> **Status:** design approved; per-phase specs in `2026-05-28-saas-phase-*.md`

---

## 1. Decisions locked

| Area | Choice |
|---|---|
| Intent | Internal modernization, web-accessible — not commercial multi-tenant SaaS |
| Backend | FastAPI modular monolith + separate ARQ worker process |
| Frontend | Full React (Vite + TS) SPA rewrite, Tailwind + shadcn/ui |
| Audience | Loja staff (`admin` / `manager` / `user`) + end customers (`customer` role) |
| Auth | Email + password, JWT access (15 min) + refresh (7 d), email-based password reset |
| JWT storage | localStorage (frontend) |
| Data migration | Green-field — desktop SQLite stays untouched; desktop app keeps running |
| Multi-tenancy | Row-level `tenant_id` on every tenant-scoped table; RLS deferred until tenant 2 onboards (app-level filtering in v1) |
| Pix | Scaffold for customer-pays-parcela flow (endpoints + webhook + UI), one in-memory fake provider in v1 |
| Notifications | Email only in v1 (transactional), outbox pattern |
| Customer scope | View carnê + active parcelas, pay parcela via Pix, download proposta/carnê PDFs |
| Deployment | On-premise server + Cloudflare Tunnel (ingress/TLS only; no Cloudflare Access policies) |
| Reverse proxy | Caddy (local, routes `/api/*` → FastAPI, everything else → React SPA) |
| Object storage | Local filesystem volume |
| Backup | Restic → Cloudflare R2 (nightly pg_dump + storage volume snapshot) |
| Email provider | Resend via SMTP (`smtp.resend.com:465`) |
| Connection pooler | None — SQLAlchemy built-in async pool only |
| CI/CD | GitHub Actions, cloud-hosted runners |
| Repo structure | Monorepo (`finacialsim-saas`) — `backend/`, `frontend/`, `packages/`, `ops/` |
| Tenant onboarding | CLI command in v1, no self-serve signup |
| Tenants at launch | 1 loja; `tenant_id` columns from day 1, full RLS before tenant 2 onboards |
| Customer portal URL | Single domain, email-based tenant resolution; add loja selector at login before tenant 2 onboards |
| Observability | loguru → JSON logs only; no Prometheus, no Sentry in v1 |

---

## 2. Architecture

### 2.1 Process layout

```text
┌───────────────────────────────────────────────────────────────┐
│ Reverse proxy (Caddy/Nginx) — TLS, gzip, static React assets │
└───────────────────────────────────────────────────────────────┘
            │                                  │
            ▼                                  ▼
┌──────────────────────┐         ┌───────────────────────────┐
│  React SPA (Vite)    │  HTTPS  │  FastAPI app (uvicorn)    │
│  - Staff routes      │ ──────▶ │  - /api/v1/* JSON         │
│  - Customer routes   │         │  - Auth, RBAC, tenant ctx │
│  - TanStack Query    │         │  - Modules (see §2.3)     │
└──────────────────────┘         └─────────────┬─────────────┘
                                               │
                                  ┌────────────┼─────────────┐
                                  ▼            ▼             ▼
                          ┌────────────┐ ┌──────────┐ ┌──────────────┐
                          │ PostgreSQL │ │  Redis   │ │ Object store │
                          │ (RLS on,   │ │  - queue │ │ (local vol   │
                          │  tenant    │ │  - cache │ │  or S3 API)  │
                          │  scoped)   │ │          │ │              │
                          └────────────┘ └──────────┘ └──────────────┘
                                               ▲
                                               │ enqueue
┌──────────────────────────────────────────────┴───────────────┐
│  Worker process (ARQ on Redis)                                │
│   - render_proposta_pdf       - render_carne_pdf              │
│   - send_email                - pix_charge_create             │
│   - pix_webhook_replay        - update_bacen_indicators       │
│   - prune_fipe_cache                                          │
└────────────────────────────────────────────────────────────────┘
```

### 2.2 Modules

```text
finacialsim_saas/
├── api/                 — FastAPI routers, request/response schemas
│   ├── auth/
│   ├── tenants/
│   ├── simulations/
│   ├── clients/
│   ├── vehicles/
│   ├── proposals/
│   ├── indicators/
│   ├── rules/
│   ├── audit/
│   ├── portal/          — customer-facing endpoints
│   ├── pix/
│   └── webhooks/
├── services/            — orchestration, transactional boundaries
├── data/                — SQLAlchemy models, repositories, Alembic migrations
├── workers/             — ARQ task functions
├── storage/             — StorageBackend protocol + Local/S3 impls
├── secrets/             — SecretsBackend protocol + env/docker/cloud impls
├── notifications/       — channel abstraction (Email in v1)
├── core/                — vendored from finacialsim (pure Decimal math)
├── integrations/        — vendored from finacialsim (FIPE, BACEN chains)
├── reports/             — vendored from finacialsim (Jinja2 + WeasyPrint templates)
└── settings.py          — pydantic-settings Settings model
```

### 2.3 Request flow — create simulation

```text
1. React POST /api/v1/simulations + Bearer JWT
2. Middleware: verify JWT → load user → request.state.ctx = RequestContext(user, tenant_id, role)
3. TenantSession middleware: SET LOCAL app.tenant_id = '<uuid>' on the SQLA session
4. RBAC dependency: role ∈ {admin, manager, user}
5. simulations.router → simulation_service.create(payload, ctx)
6. core/ math: PV → IOF iter → Price schedule → CET — unchanged from desktop
7. Persist simulations + amortization_rows + simulation_extras with tenant_id
8. audit_service.log("sim_criada", diff, ctx)
9. 201 Created + Location header
```

---

## 3. Multi-tenancy model

### 3.1 Boundary

**Tenant-scoped tables** (every row has `tenant_id UUID NOT NULL`, indexed, RLS-policied):

```
users, clients, vehicles, simulations, simulation_fees,
simulation_extras, amortization_rows, extraordinary_amortizations,
proposals, comparisons, business_rules, audit_log,
pix_charges, parcela_payments, notifications_outbox
```

**Global tables** (no tenant_id):

```
tenants, indicators_history, indicator_sources, fipe_cache, alembic_version
```

`fipe_cache` is global: FIPE data is entirely public; sharing the cache across tenants reduces redundant API calls and is not a privacy concern.

### 3.2 Context propagation

- JWT carries `sub` (user_id) and `tenant_id`.
- `get_current_ctx()` dependency builds `RequestContext(user, tenant_id, role)`.
- `TenantSession` middleware issues `SET LOCAL app.tenant_id = '<uuid>'` at request start; RLS policies read it via `current_setting('app.tenant_id')`.
- Repositories take `ctx` explicitly; raw SQL is forbidden outside `data/`.
- **Connection pooling:** SQLAlchemy's built-in async pool is used directly — no external pooler (pgBouncer, etc.) in v1. ARQ worker jobs must explicitly issue `SET LOCAL app.tenant_id` at the start of their own session — they do not inherit request context. If a pooler is ever added, it must operate in **session mode**; transaction mode silently bypasses RLS.

### 3.2.1 Email uniqueness

- **Staff roles** (`admin`, `manager`, `user`): email is globally unique across the platform. One login, one account. Staff always belong to exactly one tenant.
- **Customer role**: email is unique per tenant — `UNIQUE(tenant_id, email)`. The same person can be a client at multiple lojas with the same email, each with a separate customer account accessed via that loja's portal URL.

### 3.3 RBAC

| Role | Capability |
|---|---|
| `admin` | Full tenant control: users, business_rules |
| `manager` | All staff features, no user/rule edits |
| `user` | Own simulations + clients + dashboards |
| `customer` | Own carnê + Pix pay + PDF download (scoped to `clients.id`) |

The `customer` JWT carries `client_id`; backend resolves `tenant_id` from `clients.tenant_id`.

### 3.4 Cross-tenant safeguards

- Composite FKs `(tenant_id, id)` between dependent tables.
- Audit log records `tenant_id` on every entry.
- Two-tenant integration fixture asserts cross-tenant reads return 404 under every role, including admin.

---

## 4. Stack

| Function | Choice | Notes |
|---|---|---|
| API framework | FastAPI 0.110+ | Uvicorn workers, async-first |
| ORM | SQLAlchemy 2.x + Alembic | Async sessions, `NUMERIC(18,4)` for money |
| Validation | Pydantic v2 | `Decimal` fields, JSON-as-string for money |
| DB | PostgreSQL 16 | RLS enabled, B-tree on `(tenant_id, …)` |
| Queue | ARQ on Redis 7 | Same Redis used as lightweight cache |
| Auth | Custom JWT (PyJWT) + bcrypt | Refresh rotation; revocation via `users.tokens_revoked_at` |
| HTTP client | httpx + tenacity | Reused from existing `app/integrations/http.py` |
| PDF | WeasyPrint + Jinja2 | Rendered in worker, never in API |
| Email | aiosmtplib + Jinja2 templates | Provider via SMTP env (SES/Resend/generic) |
| Logging | loguru → JSON | `request_id`, `tenant_id`, `user_id`, `route`, `latency_ms` |
| Frontend | React 18 + Vite + TS | Tailwind + shadcn/ui, TanStack Query, React Router |
| Forms | react-hook-form + zod | Schemas mirror Pydantic |
| Charts | Recharts | Lightweight; Plotly is heavy for SPA |
| API client | axios + openapi-typescript | Types generated from FastAPI's OpenAPI in CI |
| E2E | Playwright | Golden paths only |
| Testing (be) | pytest + hypothesis + testcontainers | Real Postgres in CI |
| Testing (fe) | Vitest | Components + hooks |
| Container | Docker + docker-compose | Multi-stage builds; api, worker, web, db, redis |

---

## 5. Vendored modules from desktop repo

Copied wholesale into `finacialsim_core/`:

- `app/core/*` — Decimal money, Price table, IOF, CET, amortization, extras, validators
- `app/integrations/fipe/*` — providers; `cache.py` rewritten to use Postgres-backed cache
- `app/integrations/bacen/*` — providers; same cache treatment
- `app/integrations/http.py`, `base.py`, `factory.py` — providers chain abstraction
- `app/reports/*.html` and `*.css` — Jinja2 templates for proposta and carnê
- `app/utils/document_validation.py` — CPF/CNPJ mod-11 validation
- All tests under `tests/unit/core/` and `tests/unit/integrations/`

Tests are the contract that protects the math IP. Vendored copy fixes drift; future fixes that matter for both repos are manually back-ported.

---

## 6. Cross-cutting concerns

### 6.1 Error handling

- Single FastAPI exception handler → `{code, message, details, request_id}`.
- Typed domain errors: `ValidationError`, `NotFoundError`, `ConflictError`, `AuthError`, `TenantAccessError`, `ExternalProviderError`.
- `ProviderChain` `Err` translates to `ExternalProviderError(degraded=True)` — UI renders a yellow badge.
- Pix webhook returns 200 on malformed input (logged drop, no PSP retry-storm); 5xx only on real internal failures.
- React axios interceptor: 401 → silent refresh once → redirect; 403 → toast; 4xx with `details` → form errors; 5xx → toast + Sentry breadcrumb.

### 6.2 Testing

- `finacialsim_core` test suite ported as-is (the math regression net).
- Backend: pytest + testcontainers Postgres. Two-tenant fixture in every service test that touches tenant-scoped tables.
- Auth/RLS suite: every role × every endpoint × cross-tenant.
- Frontend: Vitest units, Playwright on the golden flows.
- OpenAPI: published from FastAPI; frontend types generated in CI; drift fails the build.
- Coverage: 80% on backend services + core; UI covered by E2E, no number target.

### 6.3 Observability

- Structured JSON logs, stdout in containers (loguru, `serialize=True` in production).
- Log fields: `request_id`, `tenant_id`, `user_id`, `route`, `latency_ms`.
- Audit log = business event of record; logs = operational.
- No Prometheus, no Sentry in v1. Add when a second tenant onboards and operational dashboards become justified.

### 6.4 Config & secrets

- `Settings` pydantic-settings model validates every env var at boot.
- `.env.example` lists every key with a comment; nothing committed.
- `SecretsBackend` protocol with `env`, `docker-secrets`, `aws-secretsmanager`, `gcp-secret-manager` impls, picked by `SECRETS_BACKEND` env.

### 6.5 Data integrity

- `NUMERIC(18,4)` for every money field.
- Pydantic `Decimal` fields with `json_encoders={Decimal: str}` to avoid float on the wire.
- Composite unique on `(tenant_id, codigo)` for `simulations` and `proposals`.
- FK actions: `ON DELETE RESTRICT` everywhere except `audit_log → users` which is `SET NULL`.
- Notifications use the **outbox pattern**: write row to `notifications_outbox` in the same transaction as the triggering business event; worker drains and sends.

### 6.6 Performance budgets

| Endpoint / page | p95 target |
|---|---|
| `POST /simulations` (create + persist) | < 250 ms |
| `POST /simulations/preview` (compute only) | < 150 ms |
| `GET /portal/carnes/{id}` | < 200 ms |
| Worker `render_proposta_pdf` | < 4 s |
| React initial JS bundle (gzipped) | < 350 KB |

### 6.7 Internationalization

- PT-BR hard-coded in v1 (R$, dd/mm/yyyy, vírgula).
- UI strings in `i18n/pt-br.json` so future locales are mechanical.
- Backend speaks Decimal + ISO-8601 dates on the wire; no localization there.

---

## 7. Phase decomposition

| # | Phase | Spec | Notes |
|---|---|---|---|
| 0 | Foundations | `2026-05-28-saas-phase-0-foundations.md` | Critical path |
| 1 | Auth + RBAC + Tenant management | `2026-05-28-saas-phase-1-auth-rbac.md` | Critical path; `audit_log` table created here |
| 2 | Core domain port + Simulação | `2026-05-28-saas-phase-2-simulacao.md` | Critical path; `audit_service.log()` wired silently |
| 3 | Cadastros (Clientes + Veículos + FIPE) | `2026-05-28-saas-phase-3-cadastros.md` | Critical path |
| 5 | Propostas + PDF/Carnê (worker-rendered) | `2026-05-28-saas-phase-5-propostas-pdf.md` | Critical path; **loja switches here**; first task: validate WeasyPrint on Linux |
| 4 | Indicadores + Business Rules UI + Scheduler + Audit log UI | `2026-05-28-saas-phase-4-indicadores-rules.md` | After loja switch; Phase 5 does not depend on Phase 4 |
| 6 | Portal do cliente + Pix scaffold | `2026-05-28-saas-phase-6-portal-cliente-pix.md` | Second rollout; after Phase 5 is stable |
| 7 | Notificações (email) + polish | `2026-05-28-saas-phase-7-notificacoes.md` | Final polish |

**Critical path:** 0 → 1 → 2 → 3 → 5. Each phase is "done" only when its acceptance checks pass.

**Phase 4 note:** Proposal creation does not fail if business rules are unconfigured or BACEN data is unavailable — Phase 4 is not a blocker for Phase 5.

**WeasyPrint risk:** The desktop PDF templates were developed on Windows. The SaaS renders PDFs via WeasyPrint on Linux inside a container. Validate template rendering on Linux as the first task of Phase 5 — font and layout differences are a known risk.

---

## 8. Out of scope for v1

- Comparativo (two-simulation side-by-side)
- Amortização extraordinária UI (math already in `core/`, just no UI)
- Dashboard with KPIs/charts beyond simulação's own
- WhatsApp/SMS channels
- Self-serve tenant signup + billing portal
- Customer self-service simulação or financing request
- Real Pix PSP wiring (scaffold uses an in-memory fake provider)
- Native mobile apps (responsive web only)
- SSO / 2FA

---

## 9. Migration of users (operational)

Phases 0–7 deliver the SaaS. Once Phase 5 ships (proposta PDF parity), the loja can run both desktop and SaaS in parallel for a transition window. After Phase 7, the desktop app is frozen for new features and kept available for read-only access to historical data until the user retires it.

No automated data migration is built in v1; if a need arises later, a dedicated `Phase 8 — Data import` spec can be added that reads the desktop SQLite and inserts into the SaaS Postgres under tenant 1.
