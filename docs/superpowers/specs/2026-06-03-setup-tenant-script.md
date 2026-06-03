# Setup Tenant Script — Design Spec

**Date:** 2026-06-03  
**Status:** Approved

## Problem

First-time deployers (dev and ops) must manually run 3+ CLI commands with flags to get a working tenant. There is no single entry point that validates the environment, starts containers, migrates the DB, and creates the first tenant interactively.

## Solution

A single `setup-tenant.sh` bash wrapper at the repo root. Idempotent, friendly, styled like `dev.sh`.

## File

`setup-tenant.sh` — repo root, executable.

## Invocation

```bash
./setup-tenant.sh                                           # fully interactive
./setup-tenant.sh --name "Acme" --slug acme --admin-email admin@acme.com  # pre-fill flags
```

Any omitted flag falls back to an interactive prompt. `--admin-password` is always prompted (hidden, confirmed) — never accepted as a flag for security.

## Steps (in order)

### 1. Env check
- Source `.env` from repo root if it exists (`set -a; source .env; set +a`).
- Verify `DATABASE_URL` is set. If missing, print a clear error with instructions and exit 1.
- No other env vars are required to proceed (uses Docker Compose defaults for the rest).

### 2. Container readiness
- Run `docker compose ps --services --filter status=running` and check if `api` is in the list.
- If not running: run `docker compose up -d` then poll `docker compose ps api` every 3 s, up to 60 s, until the health check shows `healthy`. Timeout → exit 1 with message.
- If already running: print "API container already up — skipping start" and continue.

### 3. Migrations
- Run: `docker compose exec -T api python -m finacialsim_saas.cli.main db migrate`
- Alembic is idempotent — "already up to date" is not an error.
- Any non-zero exit from this step → print error and exit 1.

### 4. Tenant creation
- Prompt for (if not supplied via flag):
  - **Tenant name** — free text, e.g. "Acme Financiadora"
  - **Slug** — auto-suggest `$(echo "$name" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | sed 's/^-//;s/-$//')`, user can accept or override
  - **Admin email** — validated against `*@*.*` pattern in bash
  - **Admin password** — read with `read -rs`, confirmed (re-prompted), minimum 8 chars
- Run: `docker compose exec -T api python -m finacialsim_saas.cli.main tenant create --name "$name" --slug "$slug" --admin-email "$email" --admin-password "$password"`
- If CLI stderr contains "already exists": print friendly "Tenant slug already taken — choose a different slug" and re-prompt slug (loop, max 3 attempts).
- Any other non-zero exit → print raw stderr and exit 1.

### 5. Success summary
Print a box:
```
╔══════════════════════════════════════════╗
║  Tenant created successfully!            ║
║                                          ║
║  Name:   Acme Financiadora               ║
║  Slug:   acme-financiadora               ║
║  Admin:  admin@acme.com                  ║
║  URL:    http://localhost                ║
╚══════════════════════════════════════════╝
```
URL is read from `$FRONTEND_BASE_URL` env var, defaulting to `http://localhost`.

## Style / UX

- Color palette and helper functions (`info`, `ok`, `warn`, `die`, `section`) copied from `dev.sh`.
- Each phase opens with a `section "Step N/4: ..."` header.
- All user-facing messages in Portuguese (consistent with the app's locale) or English — **English** (the existing `dev.sh` uses English).

## Error handling

| Scenario | Behaviour |
|---|---|
| `DATABASE_URL` missing | die with setup instructions |
| Docker not installed | die "Docker not found — install Docker Desktop or Docker Engine" |
| Container fails to become healthy in 60 s | die with `docker compose logs api --tail 30` hint |
| Migration fails | print stderr, exit 1 |
| Slug already exists (attempt 1–3) | re-prompt slug |
| Slug already exists (attempt 4) | die "Too many attempts — run `finacialsim tenant create` manually" |
| Other CLI failure | print raw stderr, exit 1 |

## Out of scope

- `.env` generation wizard (not needed — docker-compose has sane defaults for local dev)
- Non-Docker invocation (uv run / bare metal) — deferred
- Multiple tenants in one run — deferred
