# Phase 0 — Foundations

> Stand up the new `finacialsim-saas` repo with every cross-cutting primitive in place so later phases can focus on features, not plumbing.
>
> **Roadmap:** `2026-05-28-saas-roadmap.md`
> **Predecessor:** none (first phase)
> **Successor:** Phase 1 — Auth + RBAC + Tenant management

## Goal

A `docker-compose up` developer experience that brings api + worker + postgres + redis + react online with healthchecks green, lint/type/test/build all wired in CI, and the `finacialsim_core` package vendored and importable.

## In scope

### Repo skeleton

- New repo `finacialsim-saas`, MIT license, README pointing at this spec.
- `pyproject.toml` with `uv`-managed deps; ruff + mypy + pytest configured.
- Top-level layout:
  ```
  backend/   — FastAPI app + ARQ worker + Alembic
  frontend/  — Vite + React + TS
  packages/finacialsim_core/  — vendored from desktop repo
  ops/       — Dockerfiles, compose, CI scripts
  docs/      — this and other specs (copied)
  ```

### Backend skeleton

- FastAPI app exposing `/healthz` (DB ping) and `/version` (git SHA + build time).
- `Settings` model via pydantic-settings reading every env from `.env.example`.
- Structured logging: loguru sink emitting JSON with `request_id` middleware.
- Async SQLAlchemy engine; first Alembic migration creates `tenants` (id UUID PK, name, slug UNIQUE, created_at) and Alembic's own version table.
- ARQ worker scaffolded with one job `ping()` that logs and returns.
- Single FastAPI exception handler emitting `{code, message, details, request_id}`; typed error classes registered (`ValidationError`, `NotFoundError`, `ConflictError`, `AuthError`, `TenantAccessError`, `ExternalProviderError`).

### Vendored core

- Copy `app/core/`, `app/integrations/`, `app/reports/`, `app/utils/document_validation.py` into `packages/finacialsim_core/`.
- Strip any imports that touch SQLAlchemy/NiceGUI; the package is pure.
- Port matching test suite under `packages/finacialsim_core/tests/`; runs in CI.
- Backend `pyproject.toml` declares `finacialsim_core` as a local path dependency.

### Frontend skeleton

- Vite + React 18 + TS template.
- Tailwind initialized; one demo button component rendered on the index route.
- React Router with two empty routes: `/` and `/healthz` (calls backend `/healthz`).
- TanStack Query provider; axios client with base URL from `VITE_API_URL`.
- ESLint + Prettier configured; `npm test` runs Vitest.

### Docker + compose

- `ops/Dockerfile.api` (multi-stage: builder → slim runtime; non-root user).
- `ops/Dockerfile.worker` (shares builder layer with api).
- `ops/Dockerfile.web` (multi-stage: Node build → nginx static serve).
- `ops/docker-compose.yml`: services `api`, `worker`, `web`, `db` (postgres:16), `redis` (redis:7-alpine), `proxy` (Caddy).
- Named volumes for postgres data and a placeholder `object-store` volume.

### CI

- GitHub Actions on push/PR:
  - Backend: ruff, mypy, pytest (testcontainers Postgres), coverage.
  - Frontend: ESLint, `tsc --noEmit`, Vitest.
  - Docker: build all three images, tag with SHA.
- Fail-fast.

### Documentation

- `README.md`: one-paragraph product summary + `docker-compose up` quickstart.
- `.env.example` documents every env var with a short comment.

## Out of scope

- Authentication or tenancy enforcement at the data layer (Phase 1).
- Business endpoints beyond `/healthz` and `/version`.
- Production deployment.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| `finacialsim_core` carries hidden imports of SQLAlchemy/NiceGUI | CI grep on the package directory rejects offending imports |
| Mac/Windows dev parity with WeasyPrint native deps | Pin WeasyPrint to a version with prebuilt wheels; document system packages in README |
| ARQ worker fails to pick up tasks (redis URL mismatch) | Integration test: api enqueues `ping`; worker processes it within 5s |

## Acceptance checklist

- [ ] `docker-compose up` brings every service to healthy status within 60s on a clean machine.
- [ ] `curl localhost/healthz` → 200 with DB-OK payload.
- [ ] `curl localhost/version` → 200 with git SHA.
- [ ] React `/` route renders the shadcn `Button`; `/healthz` page calls the backend and shows OK.
- [ ] `pytest` passes in `backend/` (including the vendored `finacialsim_core` suite).
- [ ] `npm test` passes in `frontend/`.
- [ ] CI workflow green on a freshly pushed branch.
- [ ] Worker processes a `ping` job enqueued by an integration test.
