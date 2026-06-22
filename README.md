# FinacialSim SaaS

Multi-tenant web platform for Brazilian vehicle financing dealerships — simulations, proposals, PDF carnês, customer portal, and Pix payment integration.

Migrated from the desktop [`finacialsim`](../finacialsim) app.

---

## Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + SQLAlchemy 2 (asyncpg) + Alembic |
| Worker | ARQ (Redis-backed cron + task queue) |
| Frontend | React 18 + Vite + Tailwind + shadcn/ui |
| Database | PostgreSQL 16 |
| Email | aiosmtplib → SMTP / SES / Resend |
| Storage | Local volume or S3-compatible |
| Pix | Pluggable provider (fake for dev, external for prod) |
| Proxy | Caddy (auto-TLS) |

---

## First-time setup

**1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**2. Install [Docker Engine](https://docs.docker.com/engine/install/)** (or Docker Desktop) — required for running tests.

**3. Install Node 20+** for frontend development.

---

## Local dev (no Docker required for the app)

```bash
# Install all Python deps
uv sync

# Copy and edit environment
cp .env.example .env
# Edit DATABASE_URL to point at a local Postgres instance

# Run backend
cd backend
uv run uvicorn finacialsim_saas.main:app --reload
# → http://localhost:8000/healthz

# Run frontend (separate terminal)
cd frontend
npm install && npm run dev
# → http://localhost:5173  (proxies /api/* to FastAPI automatically)

# Run ARQ worker (separate terminal, optional)
cd backend
uv run arq finacialsim_saas.workers.worker.WorkerSettings
```

### Email in dev — Mailpit

The worker sends real email via SMTP. For local dev, use [Mailpit](https://github.com/axllent/mailpit) as a local SMTP catch-all:

```bash
docker run -d -p 1025:1025 -p 8025:8025 axllent/mailpit
# Web UI: http://localhost:8025
```

The `.env.example` defaults (`SMTP_HOST=localhost`, `SMTP_PORT=1025`) already point at Mailpit.

---

## Full stack via Docker Compose

```bash
cp .env.example .env          # review and adjust
docker compose -f ops/docker-compose.yml up
# → http://localhost  (Caddy routes /api/* → FastAPI, everything else → React)
```

```bash
docker compose -f ops/docker-compose.yml up --build
```

Migrations run automatically via the `migrate` service on startup.

---

## First tenant setup

After the database is running, create your first tenant and admin user:

```bash
cd backend
uv run finacialsim-saas tenant create \
  --name "Minha Loja" \
  --slug "minha-loja" \
  --admin-email admin@example.com \
  --admin-password   # prompted
```

---

## CLI reference

```bash
finacialsim-saas tenant create     # create tenant + seed business rules
finacialsim-saas user create       # add staff user to a tenant
finacialsim-saas user reset-password

finacialsim-saas db migrate        # run Alembic upgrade head
finacialsim-saas db reset --confirm  # drop + remigrate (dev only)

finacialsim-saas notifications drain              # ad-hoc outbox drain
finacialsim-saas notifications retry --outbox-id <uuid>  # retry deadlettered row
```

---

## Tests

```bash
# Backend — requires Docker (testcontainers auto-starts Postgres + Redis)
cd backend && uv run pytest

# Vendored core
cd packages/finacialsim_core && uv run pytest

# Frontend
cd frontend && npm test -- --run
```

---

## Project structure

```
backend/
  finacialsim_saas/
    api/           — FastAPI routers (auth, clients, vehicles, proposals, portal, webhooks, …)
    auth/          — JWT auth, RBAC, password reset, customer invite
    data/          — SQLAlchemy models, Alembic migrations
    notifications/ — NotificationService, EmailChannel, Jinja2 templates (PT-BR)
    pix/           — Pix charge protocol + fake/stub providers
    services/      — Business logic (simulation, proposals, clients, vehicles, …)
    storage/       — Local volume + S3 backends
    workers/       — ARQ tasks (PDF render, BACEN indicators, notifications drain, …)
    cli/           — Typer CLI (tenant, user, db, notifications)
  alembic/         — 008 migrations (001 tenants → … → 008 notifications)
  tests/           — Integration tests (testcontainers Postgres + Redis)

frontend/
  src/
    routes/        — Staff app pages (login, simulação, clientes, veículos, propostas)
    components/    — Shared components (FormErrorSummary, RequireRole, shadcn/ui)
    lib/           — API clients, formatters

packages/
  finacialsim_core/  — Pure financial math (vendored from desktop repo)

ops/
  docker-compose.yml  — Full stack (db, redis, migrate, api, worker, web, proxy)
  Dockerfile.api / .worker / .web
  Caddyfile
```

---

## Key environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | — | PostgreSQL asyncpg URL (required) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL |
| `APP_ENV` | `development` | `development` \| `production` \| `test` |
| `JWT_SECRET_KEY` | — | JWT signing secret (required in prod) |
| `SMTP_HOST` | `localhost` | SMTP server hostname |
| `SMTP_PORT` | `1025` | SMTP port (1025 = Mailpit, 587 = TLS, 465 = SSL) |
| `SMTP_FROM` | `noreply@finacialsim.local` | Sender address |
| `EMAIL_PROVIDER` | `smtp` | `smtp` \| `ses` \| `resend` |
| `PIX_PROVIDER` | `fake` | `fake` (dev) \| `external` (prod) |
| `STORAGE_BACKEND` | `local` | `local` \| `s3` |

See `.env.example` for the full list.

---

## Docs

- `docs/runbook/incidents.md` — Pix outage, BACEN degraded, email outage, deadletter pile-up
- `docs/deploy/docker-compose.md` — Single-VPS deploy guide
- `docs/deploy/cloud.md` — AWS ECS + RDS sketch
- `docs/superpowers/specs/2026-05-28-saas-roadmap.md` — Full roadmap

---

## Sync vendored core from the desktop repo

When `app/core/` or `app/integrations/` change in the desktop repo:

```bash
FINACIALSIM_DESKTOP_PATH=/path/to/finacialsim python scripts/sync_core.py
```

Run this, verify the tests still pass, then commit.
