# FinacialSim SaaS

Web-accessible vehicle financing simulation platform for Brazilian dealerships —
migrated from the desktop [`finacialsim`](../finacialsim) app.

**Roadmap:** `docs/superpowers/specs/2026-05-28-saas-roadmap.md`

---

## First-time setup

**1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)** (Python package manager):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**2. Install [Docker Engine](https://docs.docker.com/engine/install/)** (Linux) or Docker Desktop.

**3. Install Node 20+** for frontend development.

---

## Local dev (no Docker required)

```bash
# Install all Python deps via uv workspace
uv sync

# Backend — copy and edit .env first
cp .env.example .env
# Edit DATABASE_URL to point at a local Postgres instance

cd backend
uv run uvicorn finacialsim_saas.main:app --reload
# → http://localhost:8000/healthz

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
# → http://localhost:5173
# Requests to /api/* are proxied automatically to FastAPI — no CORS config needed
```

---

## Full stack via Docker Compose

```bash
cp .env.example .env          # review and adjust if needed
cd ops
docker compose run --rm migrate   # apply DB migrations
docker compose up
# → http://localhost  (Caddy routes /api/* to FastAPI, everything else to React)
```

---

## Tests

```bash
# Backend (testcontainers auto-starts Postgres + Redis — requires Docker)
cd backend && uv run pytest

# Vendored core
cd packages/finacialsim_core && uv run pytest

# Frontend
cd frontend && npm test -- --run
```

---

## Sync vendored core from the desktop repo

When `app/core/` or `app/integrations/` change in the desktop repo:

```bash
FINACIALSIM_DESKTOP_PATH=/path/to/finacialsim python scripts/sync_core.py
```

Run this, verify the tests still pass, then commit.

---
