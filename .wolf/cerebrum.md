# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-05-29

## User Preferences

- User copies desktop `app/` folder directly into the saas repo root for sync script access rather than keeping a separate path.
- Caveman mode active — terse communication preferred.

## Key Learnings

- **Project:** financialsim-saas — FastAPI + React + Postgres + Redis + Docker monorepo.
- **Repo layout:** `backend/` (FastAPI, uv workspace member), `packages/finacialsim_core/` (vendored pure math), `frontend/` (Vite+React), `ops/` (Docker), `.github/workflows/` (CI).
- **uv workspace:** Root `pyproject.toml` declares members. Run `uv sync --extra dev` from root to install all deps including dev.
- **Running tests:** Must `cd backend` before `uv run pytest tests/` (pytest `testpaths = ["tests"]` is relative to backend/).
- **testcontainers Redis:** WSL2 can't pull `redis:7-alpine` from Docker Hub (intermittent). Use `redis:7` locally; CI uses `-alpine` fine.
- **pytest-asyncio + SQLAlchemy async:** Session-scoped async fixtures + asyncpg = event loop mismatch. Fix: make `engine` a sync fixture with `asyncio.run()` + `NullPool`, add `asyncio_default_test_loop_scope = "session"` to pytest config.
- **bacen/cached.py exclusion:** `sync_core.py` EXCLUDED set must include both `cache.py` (fipe) and `cached.py` (bacen) to avoid SQLAlchemy forbidden imports.
- **DATABASE_URL in tests:** Session fixtures that set env vars (like `db_url`) must also set `os.environ["DATABASE_URL"]` since route handlers call `get_settings()` which reads env vars at call time.
- **git data/ ignore:** Root `.gitignore` has `data/` rule. Any new `data/` source dir (like `backend/finacialsim_saas/data/`) needs explicit exception: `!backend/.../data/` + `!backend/.../data/**`.
- **Docker builds local:** Docker Hub unreachable in WSL2. `python:3.12-slim`, `node:20-alpine`, `nginx:alpine` not available locally. Docker build tasks must be verified in CI, not locally.
- **CI install:** Use `uv sync --extra dev` from repo root (not `uv pip install` from backend/) to resolve workspace deps like `finacialsim-core`.
- **Phase 3 architecture:** `clients`, `vehicles`, `fipe_cache` tables added. `Simulation` gains nullable FK `client_id`/`vehicle_id` in DB but required in the API (SimulationCreate). SimulationService.create denormalizes client name and vehicle description at save time.
- **RequestContext requires iat:** `RequestContext(tenant_id=..., user_id=..., role=..., iat=0.0)` — the `iat` field is required.
- **Test token issuance pattern:** In integration tests, issue JWT directly via `AuthService.issue_tokens(user)` rather than calling the login endpoint. The login endpoint returns KeyError on `access_token` in tests due to session isolation issues.
- **FipeCache mock objects:** Don't use `ModelClass.__new__(ModelClass)` for mock objects — SQLAlchemy descriptors break. Use `types.SimpleNamespace` instead.
- **VehicleService.refresh_fipe order:** Check `fonte == "manual"` BEFORE checking `self._fipe is None`, so manual vehicle raises ValidationError even without fipe_chain injected.
- **PostgresFipeCache session_factory usage:** Uses `async with self._sf() as s:` — the `async_sessionmaker` is callable and returns a session context manager.
- **AuthService takes 2 args:** `AuthService(session, get_settings())` — always pass settings as second arg.
- **TokenResponse key is `access`, not `access_token`:** The login endpoint returns `{"access": ..., "refresh": ...}`. Use `r.json()["access"]`. Or better: use `AuthService.issue_tokens(user)` directly in tests (per existing learning).
- **conftest has no `session_factory` fixture:** Tests that need a factory call `build_session_factory(engine)` themselves with the `engine` fixture.

- **qrcode PIL factory:** `qrcode` package uses `PilImage` (from `qrcode.image.pil`), NOT `PyPNGImage` (requires separate `pypng` package). Call `img.save(buf, format="PNG")` for PIL. Pillow is already installed as a transitive dep.
- **Phase 6A enums:** `ParcelaPaymentStatus` now has `open` (not `pending`) + `overdue`. `PixChargeStatus` has `pending/paid/expired/canceled`. Tests asserting `.pending` must be updated to `.open`.

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->

- [2026-05-29] Don't use session-scoped `@pytest_asyncio.fixture` for SQLAlchemy engine — use sync fixture with `asyncio.run()` + `NullPool`. See bug-002.
- [2026-05-29] Don't add `await s.rollback()` inside `async with factory() as s:` — the context manager handles teardown. See bug-003.
- [2026-05-29] Don't commit with `git add .` from subdirectory — use `git -C /repo/root add <specific-paths>` to avoid path resolution issues.
- [2026-05-29] Don't use `!path/to/data/**` gitignore exceptions without also excluding `__pycache__` subdirs — or committed .pyc files slip through.
- [2026-05-29] Don't rely on lifespan for test client session_factory — `ASGITransport` doesn't trigger FastAPI lifespan. Always manually inject `app.state.session_factory = build_session_factory(engine)` and `app_state["engine"] = engine` in test client fixtures. See bug-009.
- [2026-05-29] Don't use fixed emails in seed fixtures that commit to a shared DB — subsequent test runs hit unique constraint. Use `f"ep-{uuid4().hex[:8]}@test.com"` pattern and return email from fixture. See bug-010.
- [2026-06-07] Repo had NO `.dockerignore` anywhere — `COPY frontend/ .` in `ops/Dockerfile.web` overwrote freshly-`npm ci`'d musl `node_modules` with host's glibc-built one, breaking rolldown's native binding (cryptic `Cannot convert undefined or null to object` from vite.config bundling). Added root `.dockerignore` (build context for all services is `..`, not the per-service dir) excluding `frontend/node_modules`, `frontend/dist`, `backend/.venv`, `**/__pycache__`. Also: don't run `npm install` locally with a different npm major (11 vs lockfile's 10) — corrupts `package-lock.json` (adds spurious `"peer": true`, version bumps) and breaks `npm ci` in Docker; `git checkout -- frontend/package-lock.json` to revert.
- [2026-06-07] `docker compose -f ops/docker-compose.yml up` host port 5432 conflicts with this machine's system Postgres (also serves other local projects like `gozap`) — remapped compose `db` to `"5433:5432"` (in-container `db:5432` traffic between services is unaffected by host port mapping).
- [2026-06-07] Local dev `.env` is gitignored and not auto-created — `cp .env.example .env` first, or `Settings()` raises `database_url Field required`. Also: `.env.example` REDIS_URL uses compose hostname `redis://redis:...` which doesn't resolve outside Docker — change to `redis://localhost:6379/0`. The local Postgres cluster (port 5432, role `fj` is superuser) does NOT have the `finacialsim` role/db by default — create with `CREATE ROLE finacialsim WITH LOGIN PASSWORD 'changeme'; CREATE DATABASE finacialsim OWNER finacialsim;` to match `.env.example` creds, then `uv run alembic upgrade head`. Redis itself also isn't running locally — start one with `docker run -d --name finacialsim_redis -p 6379:6379 redis:7`. See bug-008.

## Decision Log

- **2026-05-29:** Used `redis:7` (not `redis:7-alpine`) in testcontainers for local dev due to WSL2 Docker Hub connectivity; CI workflow still targets `redis:7-alpine` since GitHub Actions runners have full internet.
- **2026-05-29:** `asyncio_default_test_loop_scope = "session"` added to backend pytest config — required to share event loop between async tests and session-scoped sync fixtures using asyncpg connections.
