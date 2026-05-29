# Phase 1 — Auth + RBAC + Tenant management

> Email/password authentication with JWT sessions, role-based access control for staff (`admin`/`manager`/`user`), tenant scaffolding (CLI-driven onboarding), and Postgres RLS as the multi-tenant guardrail.
>
> **Roadmap:** `2026-05-28-saas-roadmap.md`
> **Predecessor:** Phase 0 — Foundations
> **Successor:** Phase 2 — Core domain port + Simulação

## Goal

A staff user from tenant A can log in, refresh, and hit a placeholder authenticated endpoint. A user from tenant B cannot read tenant A's user list under any role, including admin. Password reset works end-to-end via a captured email sink (no real SMTP yet).

## In scope

### Data layer

Alembic migrations:

- `users` — id UUID PK, tenant_id UUID FK NOT NULL, email CITEXT, name, password_hash bcrypt, role ENUM(`admin`,`manager`,`user`,`customer`), is_active, tokens_revoked_at, created_at, updated_at, last_login_at, client_id UUID nullable (customer role only).
  - Staff roles (`admin`, `manager`, `user`): `UNIQUE(email)` globally — one account per email across the platform.
  - Customer role: `UNIQUE(tenant_id, email)` — same email may exist as a customer at multiple lojas.
- `password_reset_tokens` — id UUID PK, user_id, tenant_id, token_hash, expires_at, used_at.
- `refresh_tokens` — id UUID PK, user_id, tenant_id, token_hash, family_id UUID, issued_at, expires_at, revoked_at (rotation with reuse detection).
- `audit_log` — `(id, tenant_id, timestamp, usuario_id, acao, entidade, entidade_id, diff_json, ip, hostname)`. Indexes `(tenant_id, timestamp DESC)`, `(tenant_id, entidade, entidade_id)`. Table created here; wired from Phase 2; browsable UI in Phase 4.
- No Postgres RLS policies in v1 — tenant isolation via app-level `tenant_id` filtering in every query. RLS policies added before tenant 2 onboards. `TenantSessionMiddleware` still issues `SET LOCAL app.tenant_id` (laying the foundation for future RLS).

### Auth core

- `auth_service.register_user(tenant_id, email, password, role)` — admin-only path; CLI uses the same.
- `auth_service.authenticate(email, password)`.
- `auth_service.issue_tokens(user)` → `(access_jwt, refresh_jwt)`.
- `auth_service.rotate_refresh(refresh_jwt)` — invalidates the old family entry; reuse triggers full-family revocation.
- `auth_service.revoke_all(user)` — bumps `tokens_revoked_at`.

JWT claims: `sub`, `tenant_id`, `role`, `iat`, `exp`. Access 15 min, refresh 7 d. Customer JWTs also carry `client_id`.

### API endpoints

```text
POST   /api/v1/auth/login                  { email, password } → { access, refresh }
POST   /api/v1/auth/refresh                { refresh }         → { access, refresh }
POST   /api/v1/auth/logout                 (auth)              → 204
POST   /api/v1/auth/password-reset/request { email }           → 202 (always)
POST   /api/v1/auth/password-reset/confirm { token, password } → 204
GET    /api/v1/me                          (auth)              → user payload
GET    /api/v1/users                       (admin)             → tenant's users
POST   /api/v1/users                       (admin)             → create user (invite enqueued)
PATCH  /api/v1/users/{id}                  (admin)             → role/active toggle
```

### Middleware & dependencies

- `JWTMiddleware`: verifies bearer; rejects revoked tokens (compare `iat` against `users.tokens_revoked_at`).
- `get_current_ctx()`: returns `RequestContext(user, tenant_id, role)`.
- `TenantSessionMiddleware`: opens SQLAlchemy session, issues `SET LOCAL app.tenant_id = '<uuid>'`.
- `require_role("admin", "manager", "user")`: dependency factory.

### CLI

```text
finacialsim-saas tenant create --name "Loja X" --slug loja-x --admin-email admin@loja-x.com
finacialsim-saas user create --tenant-slug loja-x --email u@x.com --role user
finacialsim-saas user reset-password --tenant-slug loja-x --email u@x.com
```

Implemented via Typer; commands call the same services as the API.

### Notifications (stub for this phase)

- Password reset and user-invite emails are written to a `notifications_outbox` table (created here as a placeholder for Phase 7).
- The worker drains them to a file-based `MaildirChannel` in dev.

### Frontend

- `/login`, `/forgot-password`, `/reset-password/:token` (react-hook-form + zod).
- `AuthContext`: both access token and refresh token stored in `localStorage`. On page reload, `AuthContext` reads the refresh token from `localStorage` and calls `/auth/refresh` to re-hydrate the access token.
- axios interceptor: silent refresh on 401 once, then redirect to `/login`.
- `<RequireRole roles=["admin"]>` guards.
- `/admin/users` page (admin only) listing tenant users + create/edit modal.

## Out of scope

- Real SMTP delivery (Phase 7).
- Customer login flow (Phase 6) — schema exists for it, no UX.
- SSO, 2FA, social login.
- Self-serve tenant signup (CLI only).

## Risks & mitigations

| Risk | Mitigation |
| --- | --- |
| App-level filtering gap allows cross-tenant read | Two-tenant fixture; cross-tenant suite under every role verifies `tenant_id` WHERE clause enforced |
| Refresh token replay | Rotation with family revocation on reuse |
| Password reset token brute force | 256-bit URL-safe random, hashed, one-time, 30 min expiry |
| Tenant lookup on login | Staff: look up by global-unique email. Customer: look up by tenant (from portal URL slug) + email. |

## Acceptance checklist

- [ ] CLI: create tenants A and B with admin users.
- [ ] Login with A admin returns access + refresh; JWT decodes with `tenant_id` = A.
- [ ] `GET /me` returns the right user.
- [ ] `GET /users` as A admin returns only A's users; B admin returns only B's.
- [ ] `GET /users` as A `user` role returns 403.
- [ ] Refresh rotates the token; using an old refresh family member revokes the whole family.
- [ ] Password reset request enqueues outbox row; confirm with the token logs in with the new password.
- [ ] Playwright E2E: login → `/me` → logout.
- [ ] Cross-tenant app-level isolation verified: every endpoint × every role × cross-tenant (app-level `tenant_id` filtering, no RLS in v1).
