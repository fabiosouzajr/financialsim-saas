# Phase 0 — Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `finacialsim-saas` repo with FastAPI + React + Postgres + Redis + Docker + CI all wired and a vendored `finacialsim_core` package importable, so Phase 1 can begin feature work immediately.

**Architecture:** FastAPI modular monolith; React SPA served by nginx behind Caddy; ARQ worker on Redis; Postgres 16. All wired in docker-compose. In local dev, Vite dev server proxies `/api/*` directly to FastAPI — no Caddy in the dev loop. Tests use testcontainers for real Postgres and Redis instances.

**Tech Stack:** Python 3.12, uv (workspace), FastAPI, SQLAlchemy 2 async, Alembic, ARQ, pydantic-settings, loguru, testcontainers; React 18, Vite, TypeScript, Tailwind CSS (no component library yet), TanStack Query, React Router, Vitest.

> **Important:** All file paths below are relative to the root of the NEW `finacialsim-saas` repo. Work outside the current `finacialsim` repo.

---

## Grill-me decision record

| Decision | Choice |
| --- | --- |
| Repo | Monorepo `finacialsim-saas`, `fabiosouzajr` GitHub account |
| Deployment | On-premise server + Cloudflare Tunnel (ingress/TLS only) |
| Reverse proxy | Caddy — routes `/api/*` → FastAPI, rest → React SPA |
| `fipe/cache.py` | Excluded from vendored package (SQLAlchemy dep) |
| Core sync | `scripts/sync_core.py` driven by `FINACIALSIM_DESKTOP_PATH` env var |
| Package manager | `uv` workspace (first-time — README has detailed setup) |
| Object storage | Local filesystem volume |
| Backup | Restic → Cloudflare R2 (ops runbook, not Phase 0 code) |
| Email provider | Resend via SMTP (wired in Phase 1) |
| Dev proxy | Vite on 5173 proxies `/api/*` to FastAPI on 8000 |
| Frontend level | Beginner — scaffold is heavily commented |
| Component library | Plain Tailwind only; shadcn/ui deferred |
| Error classes | All 6 registered in Phase 0 |
| Tenants schema | `gen_random_uuid()`, `now()`, `slug UNIQUE` |
| Multi-tenancy | `tenant_id` columns from day 1; RLS deferred until tenant 2 |
| Python version | 3.12 |
| Redis in CI | testcontainers (same pattern as Postgres) |
| CI/CD | GitHub Actions, cloud-hosted runners |
| Import style | Flat — `from finacialsim_core.price_table import PriceTable` |
| Vite proxy | `/api/*` → FastAPI; eliminates CORS in dev |
| JWT storage | localStorage (wired in Phase 1) |
| Connection pooler | SQLAlchemy built-in async pool only (no pgBouncer) |
| Observability | loguru JSON logs only; no Prometheus, no Sentry |
| `.env.example` | `DATABASE_URL`, `REDIS_URL`, `APP_ENV`, `APP_SECRET_KEY`, `GIT_SHA`, `PDF_OUTPUT_DIR` |

---

## File Map

```text
finacialsim-saas/
├── pyproject.toml                    ← uv workspace root
├── .gitignore
├── .env.example
├── README.md
│
├── scripts/
│   └── sync_core.py                  ← copies core from FINACIALSIM_DESKTOP_PATH
│
├── packages/
│   └── finacialsim_core/
│       ├── pyproject.toml
│       ├── finacialsim_core/
│       │   ├── __init__.py
│       │   ├── price_table.py        ← flat: from app/core/ directly
│       │   ├── cet.py
│       │   ├── iof.py
│       │   ├── money.py
│       │   ├── amortization.py
│       │   ├── extras.py
│       │   ├── validators.py
│       │   ├── rate_suggestions.py
│       │   ├── integrations/         ← sub-package (fipe/cache.py excluded)
│       │   ├── reports/              ← Jinja2 templates
│       │   └── utils/
│       │       └── document_validation.py
│       └── tests/
│           └── core/                 ← ported from desktop tests/unit/core/
│
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       └── 001_create_tenants.py
│   ├── finacialsim_saas/
│   │   ├── __init__.py
│   │   ├── settings.py              ← pydantic-settings Settings
│   │   ├── errors.py                ← AppError + 6 typed subclasses
│   │   ├── main.py                  ← FastAPI app + lifespan + middlewares
│   │   ├── data/
│   │   │   ├── __init__.py
│   │   │   └── database.py          ← async engine + session factory
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── health.py            ← /healthz, /version
│   │   ├── middleware/
│   │   │   ├── __init__.py
│   │   │   └── logging.py           ← loguru JSON + request_id
│   │   └── workers/
│   │       ├── __init__.py
│   │       ├── tasks.py             ← ping() job
│   │       └── worker.py            ← WorkerSettings
│   └── tests/
│       ├── conftest.py              ← testcontainers Postgres + Redis
│       ├── test_settings.py
│       ├── test_errors.py
│       ├── test_database.py
│       ├── test_health.py
│       ├── test_worker.py           ← unit: ping() returns pong
│       └── test_worker_integration.py ← testcontainers Redis + burst worker
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts               ← /api proxy + Vitest config
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx                  ← React Router + TanStack Query provider
│       ├── lib/
│       │   └── api.ts               ← axios, baseURL: "/api"
│       ├── routes/
│       │   ├── Index.tsx            ← Tailwind button demo
│       │   └── Health.tsx           ← calls /healthz, shows JSON
│       └── tests/
│           ├── setup.ts
│           └── App.test.tsx
│
└── ops/
    ├── Dockerfile.api
    ├── Dockerfile.worker
    ├── Dockerfile.web
    ├── nginx.conf
    ├── Caddyfile
    └── docker-compose.yml
```

---

## Task 1: Repo skeleton + uv workspace

**Files:**

- Create: `pyproject.toml` (workspace root)
- Create: `.gitignore`
- Create: `backend/finacialsim_saas/__init__.py`
- Create: `backend/pyproject.toml`
- Create: `packages/finacialsim_core/pyproject.toml`
- Create: `packages/finacialsim_core/finacialsim_core/__init__.py`

- [ ] **Step 1: Bootstrap the repo**

```bash
# Run from the parent directory where you want to clone repos
mkdir finacialsim-saas && cd finacialsim-saas
git init
mkdir -p backend/finacialsim_saas \
          packages/finacialsim_core/finacialsim_core \
          packages/finacialsim_core/tests/core \
          scripts ops .github/workflows docs/superpowers/specs
```

- [ ] **Step 2: Write root `pyproject.toml` (uv workspace)**

```toml
# This file makes uv treat finacialsim-saas as a workspace.
# Run `uv sync` from here to install all members at once.
[tool.uv.workspace]
members = ["backend", "packages/finacialsim_core"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

- [ ] **Step 3: Write `backend/pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "finacialsim-saas"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.29.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "alembic>=1.13.0",
    "asyncpg>=0.29.0",
    "pydantic-settings>=2.2.0",
    "loguru>=0.7.0",
    "arq>=0.25.0",
    "finacialsim-core",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0.0",
    "httpx>=0.27.0",
    "testcontainers[postgres,redis]>=4.7.0",
    "ruff>=0.4.0",
    "mypy>=1.10.0",
]

# Resolves finacialsim-core from the uv workspace (sibling package)
[tool.uv.sources]
finacialsim-core = { workspace = true }

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.mypy]
python_version = "3.12"
strict = true
ignore_missing_imports = true
```

- [ ] **Step 4: Write `packages/finacialsim_core/pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "finacialsim-core"
version = "0.1.0"
requires-python = ">=3.12"
# Pure financial math — no SQLAlchemy, no NiceGUI
dependencies = [
    "pydantic>=2.0.0",
    "httpx>=0.27.0",
    "tenacity>=8.0.0",
    "jinja2>=3.1.0",
    "weasyprint>=62.0",
    "python-dateutil>=2.9",
    "babel>=2.15",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "hypothesis>=6.0.0",
    "respx>=0.21",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 5: Write `backend/finacialsim_saas/__init__.py`**

```python
"""FinacialSim SaaS backend."""
```

- [ ] **Step 6: Write `packages/finacialsim_core/finacialsim_core/__init__.py`**

```python
"""Pure financial math library — no SQLAlchemy, no NiceGUI."""
```

- [ ] **Step 7: Write `.gitignore`**

```gitignore
__pycache__/
*.py[cod]
.venv/
.env
*.egg-info/
dist/
.mypy_cache/
.ruff_cache/
.pytest_cache/
htmlcov/
node_modules/
.DS_Store
*.local
uv.lock
```

- [ ] **Step 8: Install the workspace**

```bash
# From the repo root
uv sync
```

Expected: uv creates a shared `.venv/` and resolves both members. If `finacialsim_core` has no source files yet, that's fine — it resolves as an empty package.

- [ ] **Step 9: Commit**

```bash
git add .
git commit -m "chore: initialize finacialsim-saas uv workspace skeleton"
```

---

## Task 2: Sync script + vendor finacialsim_core

**Files:**

- Create: `scripts/sync_core.py`
- Create: `packages/finacialsim_core/finacialsim_core/*.py` (from desktop)
- Create: `packages/finacialsim_core/finacialsim_core/integrations/` (from desktop, cache.py excluded)
- Create: `packages/finacialsim_core/tests/core/` (from desktop)

- [ ] **Step 1: Write `scripts/sync_core.py`**

```python
#!/usr/bin/env python3
"""Sync finacialsim_core from the desktop repo.

Usage:
    FINACIALSIM_DESKTOP_PATH=/path/to/finacialsim python scripts/sync_core.py
"""
import os
import shutil
from pathlib import Path

desktop = Path(os.environ["FINACIALSIM_DESKTOP_PATH"]).resolve()
dest = Path(__file__).parent.parent / "packages" / "finacialsim_core" / "finacialsim_core"

# Files excluded from the vendored package
EXCLUDED = {"cache.py", "__pycache__"}


def _ensure_init(directory: Path) -> None:
    init = directory / "__init__.py"
    if not init.exists():
        init.write_text("")


def sync_flat(src_dir: Path, dst_dir: Path) -> None:
    """Copy *.py files from src_dir directly into dst_dir (no subdirectory)."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    for f in src_dir.iterdir():
        if f.is_file() and f.name not in EXCLUDED and not f.name.startswith("."):
            shutil.copy2(f, dst_dir / f.name)
            print(f"  {f.name}")


def sync_tree(src_dir: Path, dst_dir: Path) -> None:
    """Recursively copy a directory, skipping EXCLUDED files."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    _ensure_init(dst_dir)
    for item in src_dir.iterdir():
        if item.name in EXCLUDED or item.name.startswith("."):
            continue
        if item.is_dir():
            sync_tree(item, dst_dir / item.name)
        else:
            shutil.copy2(item, dst_dir / item.name)
            print(f"  {item.relative_to(src_dir.parent)}")


print("=== Syncing finacialsim_core ===")

# 1. Core math — flat into finacialsim_core/ root
print("\n[core] flat files:")
sync_flat(desktop / "app" / "core", dest)

# 2. Integrations — keep subdirectory structure, cache.py excluded by EXCLUDED set
print("\n[integrations]:")
sync_tree(desktop / "app" / "integrations", dest / "integrations")

# 3. Report templates
print("\n[reports]:")
sync_tree(desktop / "app" / "reports", dest / "reports")

# 4. document_validation utility
print("\n[utils]:")
(dest / "utils").mkdir(exist_ok=True)
_ensure_init(dest / "utils")
src_dv = desktop / "app" / "utils" / "document_validation.py"
if src_dv.exists():
    shutil.copy2(src_dv, dest / "utils" / "document_validation.py")
    print(f"  document_validation.py")

# 5. Port core unit tests
print("\n[tests/core]:")
tests_dst = Path(__file__).parent.parent / "packages" / "finacialsim_core" / "tests" / "core"
sync_tree(desktop / "tests" / "unit" / "core", tests_dst)
_ensure_init(tests_dst.parent)

print("\n=== Done ===")
print(f"Destination: {dest}")
```

- [ ] **Step 2: Run the sync script**

```bash
FINACIALSIM_DESKTOP_PATH=/path/to/finacialsim python scripts/sync_core.py
```

Replace `/path/to/finacialsim` with the actual path to the desktop repo on your machine.

Expected: lists copied files with no errors.

- [ ] **Step 3: Verify no forbidden imports**

```bash
grep -rn "nicegui\|from app\.data\|from app\.ui\|^from sqlalchemy\|^import sqlalchemy" \
  packages/finacialsim_core/finacialsim_core/ || echo "CLEAN"
```

Expected: `CLEAN`. The only SQLAlchemy file (`fipe/cache.py`) was excluded by the sync script.

- [ ] **Step 4: Install and run core tests**

```bash
cd packages/finacialsim_core
uv sync
uv run pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: all tests from the desktop repo pass unchanged. Fix any import path issues (e.g., `from app.core.price_table` → `from finacialsim_core.price_table`) if the ported tests used absolute imports.

- [ ] **Step 5: Verify importable from backend**

```bash
# From repo root
uv run python -c "from finacialsim_core.price_table import build_schedule; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "feat: sync script + vendor finacialsim_core with core test suite"
```

---

## Task 3: Settings model + `.env.example`

**Files:**

- Create: `backend/finacialsim_saas/settings.py`
- Create: `.env.example`
- Create: `backend/tests/test_settings.py`

- [ ] **Step 1: Write `backend/finacialsim_saas/settings.py`**

```python
from typing import Literal
from pydantic import PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database — required, no default
    database_url: PostgresDsn

    # Redis
    redis_url: RedisDsn = "redis://localhost:6379/0"  # type: ignore[assignment]

    # App
    app_env: Literal["development", "production", "test"] = "development"
    app_secret_key: str = "change-me-in-production"

    # Build info — injected at Docker build time; "dev" locally
    git_sha: str = "dev"
    build_time: str = ""

    # PDF output — local filesystem path written by the ARQ worker
    pdf_output_dir: str = "/tmp/finacialsim-pdfs"


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 2: Write `backend/tests/test_settings.py`**

```python
import pytest
from finacialsim_saas.settings import Settings


def test_settings_loads_with_valid_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    s = Settings()
    assert s.app_env == "development"
    assert s.git_sha == "dev"
    assert s.pdf_output_dir == "/tmp/finacialsim-pdfs"


def test_settings_missing_database_url_raises(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(Exception):
        Settings(_env_file=None)  # type: ignore[call-arg]
```

- [ ] **Step 3: Run tests**

```bash
cd backend
uv run pytest tests/test_settings.py -v
```

Expected: `2 passed`

- [ ] **Step 4: Write `.env.example`**

```dotenv
# ── Database ──────────────────────────────────────────────────────────────────
# asyncpg driver required. In compose this points to the `db` service.
DATABASE_URL=postgresql+asyncpg://finacialsim:changeme@db:5432/finacialsim

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_URL=redis://redis:6379/0

# ── App ───────────────────────────────────────────────────────────────────────
APP_ENV=development
# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
APP_SECRET_KEY=change-me-in-production

# ── Build info (injected at Docker build time — leave blank for local dev) ────
GIT_SHA=dev
BUILD_TIME=

# ── PDF output ────────────────────────────────────────────────────────────────
# Worker writes rendered PDFs here. Mount a volume at this path in compose.
PDF_OUTPUT_DIR=/var/lib/finacialsim/pdfs
```

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: Settings model + .env.example"
```

---

## Task 4: Typed error classes

**Files:**

- Create: `backend/finacialsim_saas/errors.py`
- Create: `backend/tests/test_errors.py`

- [ ] **Step 1: Write `backend/finacialsim_saas/errors.py`**

```python
from typing import Any


class AppError(Exception):
    """Base class for all domain errors. Maps to a structured JSON response."""

    code: str = "app_error"
    status_code: int = 500

    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ValidationError(AppError):
    code = "validation_error"
    status_code = 422


class NotFoundError(AppError):
    code = "not_found"
    status_code = 404


class ConflictError(AppError):
    code = "conflict"
    status_code = 409


class AuthError(AppError):
    """Raised when the caller is not authenticated. Used from Phase 1 onward."""

    code = "auth_error"
    status_code = 401


class TenantAccessError(AppError):
    """Raised when the caller tries to access another tenant's data. Used from Phase 1 onward."""

    code = "tenant_access_error"
    status_code = 403


class ExternalProviderError(AppError):
    """Raised when an external API (FIPE, BACEN) fails or is degraded."""

    code = "external_provider_error"
    status_code = 502

    def __init__(self, message: str, details: Any = None, degraded: bool = False) -> None:
        super().__init__(message, details)
        self.degraded = degraded
```

- [ ] **Step 2: Write `backend/tests/test_errors.py`**

```python
from finacialsim_saas.errors import (
    AppError,
    AuthError,
    ConflictError,
    ExternalProviderError,
    NotFoundError,
    TenantAccessError,
    ValidationError,
)


def test_not_found_code_and_status():
    err = NotFoundError("simulation not found")
    assert err.code == "not_found"
    assert err.status_code == 404
    assert err.message == "simulation not found"
    assert err.details is None


def test_external_provider_degraded_flag():
    err = ExternalProviderError("FIPE unreachable", degraded=True)
    assert err.degraded is True
    assert err.status_code == 502


def test_all_six_errors_are_app_errors():
    for cls in [
        ValidationError,
        NotFoundError,
        ConflictError,
        AuthError,
        TenantAccessError,
        ExternalProviderError,
    ]:
        assert issubclass(cls, AppError), f"{cls.__name__} must extend AppError"
```

- [ ] **Step 3: Run tests**

```bash
cd backend
uv run pytest tests/test_errors.py -v
```

Expected: `3 passed`

- [ ] **Step 4: Commit**

```bash
git add .
git commit -m "feat: all 6 typed domain error classes"
```

---

## Task 5: Async database engine + testcontainers fixture

**Files:**

- Create: `backend/finacialsim_saas/data/__init__.py`
- Create: `backend/finacialsim_saas/data/database.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_database.py`

- [ ] **Step 1: Write `backend/finacialsim_saas/data/database.py`**

```python
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy declarative base. All ORM models inherit from this."""
    pass


def build_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def check_db(engine: AsyncEngine) -> bool:
    """Ping the database. Raises if the connection is broken."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return True
```

- [ ] **Step 2: Write `backend/tests/conftest.py`**

```python
import pytest
import pytest_asyncio
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from finacialsim_saas.data.database import Base, build_engine, build_session_factory


# ── Postgres ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def postgres_container():
    """Starts a real Postgres 16 container for the test session."""
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def db_url(postgres_container) -> str:
    url = postgres_container.get_connection_url()
    # testcontainers returns a psycopg2 URL; we need asyncpg
    return url.replace("psycopg2", "asyncpg").replace("postgresql://", "postgresql+asyncpg://")


@pytest_asyncio.fixture(scope="session")
async def engine(db_url: str) -> AsyncEngine:
    eng = build_engine(db_url)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncSession:
    factory = build_session_factory(engine)
    async with factory() as s:
        yield s
        await s.rollback()


# ── Redis ─────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def redis_container():
    """Starts a real Redis 7 container for the test session."""
    with RedisContainer("redis:7-alpine") as r:
        yield r


@pytest.fixture(scope="session")
def redis_url(redis_container) -> str:
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}"
```

- [ ] **Step 3: Write `backend/tests/test_database.py`**

```python
import pytest
from sqlalchemy import text

from finacialsim_saas.data.database import check_db


@pytest.mark.asyncio
async def test_db_ping(engine):
    result = await check_db(engine)
    assert result is True


@pytest.mark.asyncio
async def test_session_can_execute_query(session):
    result = await session.execute(text("SELECT 42 AS answer"))
    row = result.fetchone()
    assert row is not None
    assert row.answer == 42
```

- [ ] **Step 4: Run tests**

```bash
cd backend
uv run pytest tests/test_database.py -v
```

Expected: `2 passed` (testcontainers downloads `postgres:16-alpine` on first run — takes ~30s)

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: async SQLAlchemy engine + testcontainers session/Redis fixtures"
```

---

## Task 6: Alembic + tenants migration

**Files:**

- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/001_create_tenants.py`

- [ ] **Step 1: Initialize Alembic**

```bash
cd backend
uv run alembic init alembic
```

This creates `alembic.ini` and `alembic/`. You will overwrite `env.py` in the next step.

- [ ] **Step 2: Replace `backend/alembic/env.py` with async version**

```python
import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from finacialsim_saas.data.database import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return os.environ["DATABASE_URL"]


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = get_url()
    connectable = async_engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: Write `backend/alembic/versions/001_create_tenants.py`**

```python
"""create tenants table

Revision ID: 001
Revises:
Create Date: 2026-05-28
"""
import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )


def downgrade() -> None:
    op.drop_table("tenants")
```

- [ ] **Step 4: Smoke-test the migration against a temporary Postgres**

```bash
docker run -d --name pg-test \
  -e POSTGRES_PASSWORD=test -e POSTGRES_DB=fsim \
  -p 5433:5432 postgres:16-alpine
sleep 3
cd backend
DATABASE_URL=postgresql+asyncpg://postgres:test@localhost:5433/fsim \
  uv run alembic upgrade head
docker stop pg-test && docker rm pg-test
```

Expected: `Running upgrade -> 001, create tenants table` with no errors.

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: Alembic setup + 001 create tenants migration"
```

---

## Task 7: FastAPI app + /healthz + /version + error handler + logging

**Files:**

- Create: `backend/finacialsim_saas/middleware/__init__.py`
- Create: `backend/finacialsim_saas/middleware/logging.py`
- Create: `backend/finacialsim_saas/api/__init__.py`
- Create: `backend/finacialsim_saas/api/health.py`
- Create: `backend/finacialsim_saas/main.py`
- Create: `backend/tests/test_health.py`

- [ ] **Step 1: Write `backend/finacialsim_saas/middleware/logging.py`**

```python
import sys
from loguru import logger


def configure_logging(app_env: str = "development") -> None:
    """Set up loguru. In production: JSON to stdout. In dev: colored human-readable."""
    logger.remove()
    if app_env == "production":
        # serialize=True emits JSON — structured logs for log aggregators
        logger.add(sys.stdout, format="{message}", serialize=True, level="INFO")
    else:
        logger.add(
            sys.stdout,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
            level="DEBUG",
            colorize=True,
        )
```

- [ ] **Step 2: Write `backend/finacialsim_saas/api/health.py`**

```python
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

router = APIRouter()


@router.get("/healthz")
async def healthz():
    """Returns 200 when the API can reach the database, 503 otherwise."""
    from finacialsim_saas.main import app_state

    try:
        async with app_state["engine"].connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok"}
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "db": str(exc)},
        )


@router.get("/version")
async def version():
    """Returns the git SHA and build timestamp baked into the Docker image."""
    from finacialsim_saas.settings import get_settings

    s = get_settings()
    return {
        "git_sha": s.git_sha,
        "build_time": s.build_time or datetime.now(timezone.utc).isoformat(),
        "app_env": s.app_env,
    }
```

- [ ] **Step 3: Write `backend/finacialsim_saas/main.py`**

```python
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from finacialsim_saas.data.database import build_engine
from finacialsim_saas.errors import AppError
from finacialsim_saas.middleware.logging import configure_logging
from finacialsim_saas.settings import get_settings

# Shared state accessed by route handlers — populated during lifespan startup
app_state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.app_env)
    engine = build_engine(str(settings.database_url))
    app_state["engine"] = engine
    logger.info("startup", env=settings.app_env, sha=settings.git_sha)
    yield
    await engine.dispose()
    logger.info("shutdown")


app = FastAPI(title="FinacialSim SaaS", lifespan=lifespan)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Attaches a UUID to every request and logs method, path, status, and latency."""
    import time

    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.perf_counter()
    with logger.contextualize(request_id=request_id):
        response = await call_next(request)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "request",
            method=request.method,
            path=str(request.url.path),
            status=response.status_code,
            latency_ms=latency_ms,
        )
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Converts any AppError subclass into the standard error response shape."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


from finacialsim_saas.api.health import router as health_router  # noqa: E402

app.include_router(health_router)
```

- [ ] **Step 4: Write `backend/tests/test_health.py`**

```python
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client(engine):
    """FastAPI test client wired to the testcontainers Postgres engine."""
    from finacialsim_saas.main import app, app_state

    app_state["engine"] = engine
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_healthz_returns_ok(client):
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


@pytest.mark.asyncio
async def test_version_has_expected_keys(client):
    response = await client.get("/version")
    assert response.status_code == 200
    data = response.json()
    assert "git_sha" in data
    assert "app_env" in data
    assert "build_time" in data


@pytest.mark.asyncio
async def test_app_error_handler_returns_structured_json(client):
    from fastapi import APIRouter

    from finacialsim_saas.errors import NotFoundError
    from finacialsim_saas.main import app

    test_router = APIRouter()

    @test_router.get("/_test/not-found")
    async def raise_not_found():
        raise NotFoundError("thing not found")

    app.include_router(test_router)
    response = await client.get("/_test/not-found")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "not_found"
    assert body["message"] == "thing not found"
    assert "request_id" in body
```

- [ ] **Step 5: Run tests**

```bash
cd backend
uv run pytest tests/test_health.py -v
```

Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "feat: FastAPI app with /healthz, /version, request_id middleware, AppError handler"
```

---

## Task 8: ARQ worker + ping job + integration test

**Files:**

- Create: `backend/finacialsim_saas/workers/__init__.py`
- Create: `backend/finacialsim_saas/workers/tasks.py`
- Create: `backend/finacialsim_saas/workers/worker.py`
- Create: `backend/tests/test_worker.py`
- Create: `backend/tests/test_worker_integration.py`

- [ ] **Step 1: Write `backend/finacialsim_saas/workers/tasks.py`**

```python
from loguru import logger


async def ping(ctx: dict) -> str:
    """Health-check job. Enqueue it to verify the worker is alive and Redis is reachable."""
    logger.info("ping job executed")
    return "pong"
```

- [ ] **Step 2: Write `backend/finacialsim_saas/workers/worker.py`**

```python
from arq.connections import RedisSettings

from finacialsim_saas.settings import get_settings
from finacialsim_saas.workers.tasks import ping


def get_redis_settings() -> RedisSettings:
    s = get_settings()
    return RedisSettings.from_dsn(str(s.redis_url))


class WorkerSettings:
    """ARQ reads this class to configure the worker process."""

    functions = [ping]
    redis_settings = get_redis_settings()
    max_jobs = 10
    job_timeout = 30
```

- [ ] **Step 3: Write `backend/tests/test_worker.py`**

```python
import pytest


@pytest.mark.asyncio
async def test_ping_returns_pong():
    """Unit test: the ping function works in isolation."""
    from finacialsim_saas.workers.tasks import ping

    result = await ping({})
    assert result == "pong"
```

- [ ] **Step 4: Run unit test**

```bash
cd backend
uv run pytest tests/test_worker.py -v
```

Expected: `1 passed`

- [ ] **Step 5: Write `backend/tests/test_worker_integration.py`**

```python
import pytest
from arq import Worker
from arq.connections import RedisSettings, create_pool

from finacialsim_saas.workers.tasks import ping


@pytest.mark.asyncio
async def test_ping_job_enqueue_and_process(redis_url):
    """
    Integration test: enqueue ping via ARQ, run the worker in burst mode
    (processes all pending jobs then exits), verify the result is 'pong'.
    Uses testcontainers Redis — no external Redis required.
    """
    settings = RedisSettings.from_dsn(redis_url)

    # Enqueue the job
    pool = await create_pool(settings)
    job = await pool.enqueue_job("ping")
    await pool.aclose()

    # Run the worker in burst mode: processes all pending jobs, then exits
    worker = Worker(
        functions=[ping],
        redis_settings=settings,
        burst=True,
        max_jobs=1,
    )
    await worker.main()
    await worker.close()

    # Check the job result (timeout=5 as per acceptance criteria)
    pool = await create_pool(settings)
    result = await job.result(timeout=5)
    await pool.aclose()

    assert result == "pong"
```

- [ ] **Step 6: Run integration test**

```bash
cd backend
uv run pytest tests/test_worker_integration.py -v
```

Expected: `1 passed` (testcontainers downloads `redis:7-alpine` on first run)

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "feat: ARQ worker + ping job + Redis integration test"
```

---

## Task 9: Frontend scaffold (Vite + React + TS + Tailwind)

**Files:**

- Create: `frontend/` (via `npm create vite`)
- Create: `frontend/vite.config.ts` (with `/api` proxy + Vitest)
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/routes/Index.tsx`
- Create: `frontend/src/routes/Health.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/tests/setup.ts`
- Create: `frontend/src/tests/App.test.tsx`

- [ ] **Step 1: Scaffold Vite app**

```bash
# From repo root
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install
```

- [ ] **Step 2: Install additional deps**

```bash
# Runtime deps
npm install @tanstack/react-query react-router-dom axios

# Tailwind (Vite plugin — no separate PostCSS config needed)
npm install tailwindcss @tailwindcss/vite

# Test deps
npm install -D vitest @vitest/ui @testing-library/react \
  @testing-library/jest-dom @testing-library/user-event jsdom
```

- [ ] **Step 3: Write `frontend/tailwind.config.ts`**

```typescript
import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
} satisfies Config;
```

- [ ] **Step 4: Replace `frontend/vite.config.ts`**

```typescript
import path from "path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],

  resolve: {
    // "@/" maps to "src/" — write `import X from "@/lib/api"` instead of `"../../lib/api"`
    alias: { "@": path.resolve(__dirname, "./src") },
  },

  server: {
    // In dev, Vite proxies any request starting with /api to FastAPI on port 8000.
    // This removes the need for CORS headers or a separate proxy service.
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        // Strip the /api prefix before forwarding: /api/healthz → /healthz
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },

  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/tests/setup.ts"],
  },
});
```

- [ ] **Step 5: Write `frontend/src/lib/api.ts`**

```typescript
import axios from "axios";

// In dev:  Vite proxy forwards /api/* → http://localhost:8000/*
// In prod: Caddy routes /api/* → api:8000/*
// The client always calls /api/... and never needs to know the backend URL.
export const api = axios.create({
  baseURL: "/api",
  withCredentials: true,
});
```

- [ ] **Step 6: Write `frontend/src/routes/Index.tsx`**

```typescript
// Home page — a single Tailwind-styled button as a smoke test for the UI stack.
// No component library yet; we use plain Tailwind utility classes.
export default function Index() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <button className="rounded-lg bg-blue-600 px-6 py-3 font-semibold text-white transition-colors hover:bg-blue-700">
        FinacialSim SaaS
      </button>
    </div>
  );
}
```

- [ ] **Step 7: Write `frontend/src/routes/Health.tsx`**

```typescript
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export default function Health() {
  // Calls GET /api/healthz — Vite proxy rewrites to GET /healthz on FastAPI
  const { data, isLoading, isError } = useQuery({
    queryKey: ["healthz"],
    queryFn: () => api.get("/healthz").then((r) => r.data),
  });

  if (isLoading) return <p className="p-4 text-gray-500">Checking backend…</p>;
  if (isError) return <p className="p-4 text-red-500">API unreachable</p>;

  return (
    <pre className="m-4 rounded-lg bg-gray-100 p-4 font-mono text-sm">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}
```

- [ ] **Step 8: Write `frontend/src/App.tsx`**

```typescript
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import Health from "./routes/Health";
import Index from "./routes/Index";

// One QueryClient per app. Lives outside the component so it isn't recreated on renders.
const queryClient = new QueryClient();

export default function App() {
  return (
    // QueryClientProvider makes TanStack Query available to all child components
    <QueryClientProvider client={queryClient}>
      {/* BrowserRouter enables React Router URL-based navigation */}
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Index />} />
          <Route path="/healthz" element={<Health />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
```

- [ ] **Step 9: Write `frontend/src/tests/setup.ts`**

```typescript
// Runs before every test. Adds @testing-library/jest-dom matchers
// like toBeInTheDocument(), toHaveClass(), etc. to Vitest's expect.
import "@testing-library/jest-dom";
```

- [ ] **Step 10: Write `frontend/src/tests/App.test.tsx`**

```typescript
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import Index from "../routes/Index";

// Minimal wrapper that provides the React context dependencies each route needs
function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Index route", () => {
  it("renders the FinacialSim SaaS button", () => {
    render(<Index />, { wrapper: Wrapper });
    expect(screen.getByRole("button", { name: /FinacialSim SaaS/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 11: Add Tailwind directives to `frontend/src/index.css`**

Replace the contents of `src/index.css` with:

```css
@import "tailwindcss";
```

- [ ] **Step 12: Run frontend tests**

```bash
cd frontend
npm test -- --run
```

Expected: `1 test passed`

- [ ] **Step 13: Run type-check**

```bash
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 14: Commit**

```bash
git add .
git commit -m "feat: React + Vite + Tailwind frontend scaffold with /api proxy"
```

---

## Task 10: Dockerfiles + docker-compose

**Files:**

- Create: `ops/Dockerfile.api`
- Create: `ops/Dockerfile.worker`
- Create: `ops/Dockerfile.web`
- Create: `ops/nginx.conf`
- Create: `ops/Caddyfile`
- Create: `ops/docker-compose.yml`

- [ ] **Step 1: Write `ops/Dockerfile.api`**

```dockerfile
# Stage 1: install Python deps
FROM python:3.12-slim AS builder
WORKDIR /build
RUN pip install uv
COPY backend/pyproject.toml backend/
COPY packages/ packages/
RUN cd backend && uv pip install --system --no-cache "."

# Stage 2: lean runtime image
FROM python:3.12-slim AS runtime
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn
COPY backend/ .
# Non-root user for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "finacialsim_saas.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Write `ops/Dockerfile.worker`**

```dockerfile
# Stage 1: install Python deps + WeasyPrint native libraries (needed for Phase 5 PDF jobs)
FROM python:3.12-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 libffi-dev shared-mime-info \
    && rm -rf /var/lib/apt/lists/*
RUN pip install uv
COPY backend/pyproject.toml backend/
COPY packages/ packages/
RUN cd backend && uv pip install --system --no-cache "."

# Stage 2: runtime — must also carry the native WeasyPrint libs
FROM python:3.12-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 libffi-dev shared-mime-info \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin /usr/local/bin
COPY backend/ .
RUN useradd -m appuser && chown -R appuser /app
USER appuser
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "arq", "finacialsim_saas.workers.worker.WorkerSettings"]
```

- [ ] **Step 3: Write `ops/Dockerfile.web`**

```dockerfile
# Stage 1: build the React app
FROM node:20-alpine AS builder
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
# VITE_API_URL is not set — Caddy handles /api/* routing in prod via proxy
RUN npm run build

# Stage 2: serve static files with nginx
FROM nginx:alpine AS runtime
COPY --from=builder /app/dist /usr/share/nginx/html
COPY ops/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

- [ ] **Step 4: Write `ops/nginx.conf`**

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;
    # Route all requests to index.html so React Router handles navigation client-side
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 5: Write `ops/Caddyfile`**

```caddy
:80 {
    # /api/* → FastAPI (strips the /api prefix before forwarding)
    handle /api/* {
        uri strip_prefix /api
        reverse_proxy api:8000
    }
    # Everything else → React SPA served by nginx
    handle {
        reverse_proxy web:80
    }
}
```

- [ ] **Step 6: Write `ops/docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: finacialsim
      POSTGRES_USER: finacialsim
      POSTGRES_PASSWORD: changeme
    volumes:
      - pg-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U finacialsim"]
      interval: 5s
      retries: 12

  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      retries: 12

  migrate:
    build:
      context: ..
      dockerfile: ops/Dockerfile.api
    environment:
      DATABASE_URL: postgresql+asyncpg://finacialsim:changeme@db:5432/finacialsim
      APP_SECRET_KEY: local-dev
    command: python -m alembic upgrade head
    depends_on:
      db:
        condition: service_healthy

  api:
    build:
      context: ..
      dockerfile: ops/Dockerfile.api
    environment:
      DATABASE_URL: postgresql+asyncpg://finacialsim:changeme@db:5432/finacialsim
      REDIS_URL: redis://redis:6379/0
      APP_SECRET_KEY: local-dev
      GIT_SHA: local
    depends_on:
      migrate:
        condition: service_completed_successfully
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8000/healthz || exit 1"]
      interval: 10s
      retries: 6

  worker:
    build:
      context: ..
      dockerfile: ops/Dockerfile.worker
    environment:
      DATABASE_URL: postgresql+asyncpg://finacialsim:changeme@db:5432/finacialsim
      REDIS_URL: redis://redis:6379/0
      APP_SECRET_KEY: local-dev
      PDF_OUTPUT_DIR: /var/lib/finacialsim/pdfs
    volumes:
      - pdf-store:/var/lib/finacialsim/pdfs
    depends_on:
      api:
        condition: service_healthy

  web:
    build:
      context: ..
      dockerfile: ops/Dockerfile.web

  proxy:
    image: caddy:2-alpine
    ports:
      - "80:80"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
    depends_on:
      - api
      - web

volumes:
  pg-data:
  pdf-store:
```

- [ ] **Step 7: Build images**

```bash
cd ops
docker compose build 2>&1 | tail -20
```

Expected: all three images build without error.

- [ ] **Step 8: Commit**

```bash
git add .
git commit -m "feat: Dockerfiles (api/worker/web) + docker-compose stack"
```

---

## Task 11: GitHub Actions CI

**Files:**

- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write `.github/workflows/ci.yml`**

```yaml
name: CI
on:
  push:
  pull_request:

jobs:
  # Backend: lint, type-check, pytest — testcontainers handles Postgres + Redis internally
  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install uv
      - run: uv pip install --system -e ".[dev]"
      - run: uv run ruff check .
      - run: uv run mypy finacialsim_saas
      - name: pytest (testcontainers spins up Postgres + Redis internally)
        run: uv run pytest tests/ --cov=finacialsim_saas --cov-report=term-missing -v
        env:
          # pydantic-settings validates DATABASE_URL at import time — dummy satisfies the validator.
          # The actual URL is overridden by the testcontainers fixture in conftest.py.
          DATABASE_URL: postgresql+asyncpg://dummy:dummy@localhost/dummy
          APP_SECRET_KEY: ci-secret

  # Vendored core: forbidden-import check + test suite
  vendored-core:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: packages/finacialsim_core
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install uv
      - run: uv pip install --system -e ".[dev]"
      - name: Verify no forbidden imports
        run: |
          grep -rn "nicegui\|from app\.data\|from app\.ui\|^from sqlalchemy\|^import sqlalchemy" \
            finacialsim_core/ && echo "FORBIDDEN IMPORTS FOUND" && exit 1 || echo "CLEAN"
      - run: uv run pytest tests/ -v --tb=short

  # Frontend: type-check + Vitest
  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npx tsc --noEmit
      - run: npm test -- --run

  # Docker: verify all three images build cleanly
  docker:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -f ops/Dockerfile.api -t finacialsim-saas-api .
      - run: docker build -f ops/Dockerfile.worker -t finacialsim-saas-worker .
      - run: docker build -f ops/Dockerfile.web -t finacialsim-saas-web .
```

- [ ] **Step 2: Commit**

```bash
git add .
git commit -m "ci: GitHub Actions — backend, vendored-core, frontend, docker builds"
```

---

## Task 12: README + smoke test

**Files:**

- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

````markdown
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
````

- [ ] **Step 2: Full local smoke test**

```bash
cd ops
docker compose up --build -d
# Wait for services to become healthy (up to 60s)
sleep 45
curl -s http://localhost/healthz | python3 -m json.tool
curl -s http://localhost/version | python3 -m json.tool
```

Expected:

```json
{"status": "ok", "db": "ok"}
{"git_sha": "local", "build_time": "...", "app_env": "development"}
```

- [ ] **Step 3: Verify React app loads**

Open <http://localhost> in a browser. You should see the blue "FinacialSim SaaS" button.
Open <http://localhost/healthz>. You should see `{"status": "ok", "db": "ok"}` rendered as JSON.

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "docs: README with uv first-time setup, quickstart, and sync instructions"
```

---

## Self-Review

**Spec coverage:**

| Requirement | Task |
|---|---|
| New repo `finacialsim-saas` | 1 |
| `pyproject.toml` with `uv`-managed deps; ruff + mypy + pytest configured | 1, 3 |
| `packages/finacialsim_core/` vendored + pure (no SQLAlchemy/NiceGUI) | 2 |
| Sync script (`FINACIALSIM_DESKTOP_PATH`) | 2 |
| `fipe/cache.py` excluded | 2 |
| Flat imports: `from finacialsim_core.price_table import ...` | 2 |
| `Settings` model via pydantic-settings + `.env.example` | 3 |
| All 6 typed error classes + `{code, message, details, request_id}` handler | 4, 7 |
| Async SQLAlchemy engine | 5 |
| Alembic + `tenants` migration (`gen_random_uuid`, `now()`, `slug UNIQUE`) | 6 |
| `/healthz` (DB ping) + `/version` (git SHA + build time) | 7 |
| Structured JSON logging + `request_id` middleware | 7 |
| ARQ worker + `ping()` unit test | 8 |
| Worker integration test (testcontainers Redis, burst mode, 5s) | 8 |
| Vite + React 18 + TS | 9 |
| Plain Tailwind (no component library) | 9 |
| Vite proxy `/api/*` → FastAPI | 9 |
| TanStack Query provider + axios `baseURL: "/api"` | 9 |
| React Router with `/` and `/healthz` routes | 9 |
| `Dockerfile.api`, `Dockerfile.worker`, `Dockerfile.web` | 10 |
| docker-compose: api, worker, web, db (postgres:16), redis, proxy (Caddy) | 10 |
| PDF filesystem volume (`pdf-store`) | 10 |
| CI: backend ruff + mypy + pytest (testcontainers) | 11 |
| CI: vendored-core forbidden-import check + pytest | 11 |
| CI: frontend tsc + Vitest | 11 |
| CI: docker build all three images | 11 |
| README with `uv` first-time setup + `docker compose up` quickstart | 12 |
| Smoke test: `curl localhost/healthz` → 200 | 12 |
| Smoke test: React renders in browser | 12 |

All acceptance checklist items covered. No TBDs or placeholders found.
