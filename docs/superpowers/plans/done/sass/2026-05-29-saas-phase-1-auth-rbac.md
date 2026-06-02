# Phase 1 — Auth + RBAC + Tenant Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Staff users can log in with email/password, receive JWT sessions, hit role-protected endpoints, and be isolated per tenant at the application layer; password reset flows to a dev maildir sink; CLI onboards tenants.

**Architecture:** FastAPI dependency injection for session management and auth; PyJWT + bcrypt for tokens; SQLAlchemy async ORM with Alembic migration; `require_role` dependency factory for RBAC; React AuthContext + axios 401-queue interceptor for the frontend.

**Tech Stack:** PyJWT ≥ 2.8, bcrypt ≥ 4.1 (direct, rounds=12), Typer ≥ 0.12, SQLAlchemy 2 async, Alembic, React 19, react-hook-form, zod, axios

---

## File Map

```text
backend/
├── pyproject.toml                        ← ADD PyJWT, bcrypt, typer; [project.scripts] CLI entry
├── finacialsim_saas/
│   ├── settings.py                       ← ADD jwt_secret_key, access_token_expire_minutes,
│   │                                         refresh_token_expire_days, frontend_base_url, maildir_path
│   ├── main.py                           ← ADD app.state.session_factory in lifespan; include auth + users routers
│   ├── data/
│   │   └── models.py                     ← CREATE: Tenant, User, PasswordResetToken, RefreshToken,
│   │                                         AuditLog, NotificationsOutbox ORM models
│   ├── auth/
│   │   ├── __init__.py                   ← CREATE: empty
│   │   ├── schemas.py                    ← CREATE: Pydantic request/response schemas
│   │   ├── service.py                    ← CREATE: AuthService (register_user, authenticate,
│   │   │                                     issue_tokens, rotate_refresh, revoke_all,
│   │   │                                     request_password_reset, confirm_password_reset, write_audit)
│   │   └── deps.py                       ← CREATE: RequestContext dataclass, _parse_bearer,
│   │                                         get_db_session, get_current_ctx, require_role
│   ├── api/
│   │   ├── auth.py                       ← CREATE: login, refresh, logout, password-reset/* endpoints
│   │   └── users.py                      ← CREATE: GET /me, GET/POST /users, PATCH /users/{id}
│   ├── cli/
│   │   ├── __init__.py                   ← CREATE: empty
│   │   └── main.py                       ← CREATE: Typer CLI — tenant create, user create, user reset-password
│   └── workers/
│       └── maildir.py                    ← CREATE: MaildirChannel + drain_outbox ARQ task
├── alembic/versions/
│   └── 002_auth_tables.py                ← CREATE: citext ext + userrole enum + all Phase 1 tables
└── tests/
    ├── conftest.py                       ← MODIFY: enable citext in engine, add shared client fixture
    ├── test_auth_service.py              ← CREATE
    ├── test_auth_endpoints.py            ← CREATE
    ├── test_users_endpoints.py           ← CREATE
    ├── test_tenant_isolation.py          ← CREATE
    └── test_cli.py                       ← CREATE

frontend/
├── package.json                          ← ADD react-hook-form, zod, @hookform/resolvers
├── src/
│   ├── context/AuthContext.tsx           ← CREATE
│   ├── components/RequireRole.tsx        ← CREATE
│   ├── lib/api.ts                        ← MODIFY: add 401-queue interceptor + token refresh
│   ├── routes/
│   │   ├── Login.tsx                     ← CREATE
│   │   ├── ForgotPassword.tsx            ← CREATE
│   │   ├── ResetPassword.tsx             ← CREATE
│   │   └── admin/Users.tsx               ← CREATE
│   └── App.tsx                           ← MODIFY: wrap with AuthProvider, add all routes
```

---

## Task 1: Add backend dependencies

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Edit `backend/pyproject.toml`**

Add to `[project] dependencies` array:
```toml
"PyJWT>=2.8.0",
"bcrypt>=4.1.0",
"typer>=0.12.0",
```

Add new section after `[project.optional-dependencies]`:
```toml
[project.scripts]
finacialsim-saas = "finacialsim_saas.cli.main:app"
```

- [ ] **Step 2: Sync**

```bash
uv sync --extra dev
```

Expected: packages installed, no errors.

- [ ] **Step 3: Verify imports**

```bash
cd backend && uv run python -c "import jwt; import bcrypt; import typer; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml
git commit -m "feat(deps): add PyJWT, bcrypt, typer for Phase 1 auth"
```

---

## Task 2: ORM models + conftest CITEXT patch

**Files:**
- Create: `backend/finacialsim_saas/data/models.py`
- Modify: `backend/tests/conftest.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_models.py`:
```python
import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_all_phase1_models_importable_and_tables_exist(session):
    from finacialsim_saas.data.models import (
        AuditLog, NotificationsOutbox, PasswordResetToken,
        RefreshToken, Tenant, User,
    )
    for Model in (Tenant, User, PasswordResetToken, RefreshToken, AuditLog, NotificationsOutbox):
        result = await session.execute(select(Model))
        assert result.scalars().all() == []
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd backend && uv run pytest tests/test_models.py -v
```

Expected: `ImportError` — `User` does not exist yet.

- [ ] **Step 3: Create `backend/finacialsim_saas/data/models.py`**

```python
import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from finacialsim_saas.data.database import Base


class Role(enum.Enum):
    admin = "admin"
    manager = "manager"
    user = "user"
    customer = "customer"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    slug: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(sa.Text, nullable=False)
    role: Mapped[Role] = mapped_column(
        sa.Enum(Role, name="userrole", native_enum=True), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    tokens_revoked_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        sa.Index(
            "uq_users_email_staff", "email",
            unique=True, postgresql_where=sa.text("role != 'customer'"),
        ),
        sa.Index(
            "uq_users_tenant_email_customer", "tenant_id", "email",
            unique=True, postgresql_where=sa.text("role = 'customer'"),
        ),
    )


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    acao: Mapped[str] = mapped_column(sa.Text, nullable=False)
    entidade: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    entidade_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    diff_json: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    hostname: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    __table_args__ = (
        sa.Index("ix_audit_log_tenant_timestamp", "tenant_id", "timestamp"),
        sa.Index("ix_audit_log_tenant_entidade", "tenant_id", "entidade", "entidade_id"),
    )


class NotificationsOutbox(Base):
    __tablename__ = "notifications_outbox"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    recipient: Mapped[str] = mapped_column(sa.Text, nullable=False)
    payload: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    processed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    attempts: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
```

- [ ] **Step 4: Patch `backend/tests/conftest.py` — enable CITEXT before create_all**

Replace the `engine` fixture:
```python
@pytest.fixture(scope="session")
def engine(db_url: str) -> AsyncEngine:
    """Sync fixture: enables citext extension, then creates schema."""
    from sqlalchemy import text as _text

    eng = create_async_engine(db_url, poolclass=NullPool)

    async def _create_schema() -> None:
        async with eng.begin() as conn:
            await conn.execute(_text("CREATE EXTENSION IF NOT EXISTS citext"))
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create_schema())
    yield eng
    asyncio.run(eng.dispose())
```

Also add a shared `client` fixture at the bottom of conftest (used by endpoint tests):
```python
@pytest_asyncio.fixture
async def client(engine: AsyncEngine):
    """Shared HTTP test client. Lifespan uses DATABASE_URL set by db_url fixture."""
    from httpx import ASGITransport, AsyncClient
    from finacialsim_saas.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

- [ ] **Step 5: Run test — expect PASS**

```bash
cd backend && uv run pytest tests/test_models.py -v
```

Expected: PASS

- [ ] **Step 6: Confirm existing tests still pass**

```bash
cd backend && uv run pytest tests/ -v --ignore=tests/test_models.py
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add backend/finacialsim_saas/data/models.py backend/tests/test_models.py backend/tests/conftest.py
git commit -m "feat(models): ORM models for users, tokens, audit_log, outbox; enable citext in test engine"
```

---

## Task 3: Alembic migration 002

**Files:**
- Create: `backend/alembic/versions/002_auth_tables.py`

This migration targets production via `alembic upgrade head`. Tests use `Base.metadata.create_all` (see conftest), so this file is not exercised in the test suite directly — but it must produce an identical schema to the ORM models.

- [ ] **Step 1: Create `backend/alembic/versions/002_auth_tables.py`**

```python
"""auth tables — users, password_reset_tokens, refresh_tokens, audit_log, notifications_outbox

Revision ID: 002
Revises: 001
Create Date: 2026-05-29
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import CITEXT, UUID

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute(
        "CREATE TYPE userrole AS ENUM ('admin', 'manager', 'user', 'customer')"
    )

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("email", CITEXT, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("role", sa.Enum(name="userrole", create_type=False), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("tokens_revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_users_email_staff ON users (email) WHERE role != 'customer'"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_users_tenant_email_customer"
        " ON users (tenant_id, email) WHERE role = 'customer'"
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text, nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text, nullable=False, unique=True),
        sa.Column("family_id", UUID(as_uuid=True), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("usuario_id", UUID(as_uuid=True), nullable=True),
        sa.Column("acao", sa.Text, nullable=False),
        sa.Column("entidade", sa.Text, nullable=True),
        sa.Column("entidade_id", UUID(as_uuid=True), nullable=True),
        sa.Column("diff_json", sa.JSON, nullable=True),
        sa.Column("ip", sa.Text, nullable=True),
        sa.Column("hostname", sa.Text, nullable=True),
    )
    op.create_index("ix_audit_log_tenant_timestamp", "audit_log", ["tenant_id", "timestamp"])
    op.create_index(
        "ix_audit_log_tenant_entidade", "audit_log",
        ["tenant_id", "entidade", "entidade_id"],
    )

    op.create_table(
        "notifications_outbox",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("recipient", sa.Text, nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_table("notifications_outbox")
    op.drop_table("audit_log")
    op.drop_table("refresh_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_table("users")
    op.execute("DROP TYPE userrole")
```

- [ ] **Step 2: Verify migration parses (import check)**

```bash
cd backend && uv run python -c "from alembic.versions import 002_auth_tables; print('ok')"
```

Note: if the file name causes import issues, check via alembic:
```bash
cd backend && uv run alembic check
```

Expected: no import errors.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/002_auth_tables.py
git commit -m "feat(migrations): 002 auth tables — citext, userrole enum, users, tokens, audit_log, outbox"
```

---

## Task 4: Expand settings

**Files:**
- Modify: `backend/finacialsim_saas/settings.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_settings.py`:
```python
def test_settings_has_jwt_and_phase1_fields(monkeypatch):
    import os
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    os.environ["JWT_SECRET_KEY"] = "test-jwt-secret"
    from importlib import reload
    import finacialsim_saas.settings as _m
    reload(_m)
    s = _m.Settings()
    assert s.jwt_secret_key == "test-jwt-secret"
    assert s.access_token_expire_minutes == 15
    assert s.refresh_token_expire_days == 7
    assert s.frontend_base_url == "http://localhost:5173"
    assert s.maildir_path == "./dev-mail"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd backend && uv run pytest tests/test_settings.py::test_settings_has_jwt_and_phase1_fields -v
```

Expected: `AttributeError`

- [ ] **Step 3: Replace `backend/finacialsim_saas/settings.py`**

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

    database_url: PostgresDsn

    redis_url: RedisDsn = "redis://localhost:6379/0"  # type: ignore[assignment]

    app_env: Literal["development", "production", "test"] = "development"
    app_secret_key: str = "change-me-in-production"

    git_sha: str = "dev"
    build_time: str = ""

    pdf_output_dir: str = "/tmp/finacialsim-pdfs"

    jwt_secret_key: str = "change-jwt-secret-in-production"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    frontend_base_url: str = "http://localhost:5173"
    maildir_path: str = "./dev-mail"


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run — expect PASS**

```bash
cd backend && uv run pytest tests/test_settings.py -v
```

Expected: all PASS.

- [ ] **Step 5: Add to `.env.example`**

Append to the root `.env.example` file:
```
JWT_SECRET_KEY=change-me-in-production
FRONTEND_BASE_URL=http://localhost:5173
MAILDIR_PATH=./dev-mail
```

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/settings.py .env.example
git commit -m "feat(settings): jwt_secret_key, token expiry, frontend_base_url, maildir_path"
```

---

## Task 5: Auth service

**Files:**
- Create: `backend/finacialsim_saas/auth/__init__.py`
- Create: `backend/finacialsim_saas/auth/service.py`
- Create: `backend/tests/test_auth_service.py`

- [ ] **Step 1: Create `backend/finacialsim_saas/auth/__init__.py`**

Empty file.

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_auth_service.py`:
```python
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.data.models import Role, Tenant
from finacialsim_saas.settings import Settings


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        jwt_secret_key="unit-test-secret",
    )


@pytest.fixture
async def tenant(session: AsyncSession) -> Tenant:
    t = Tenant(name="SvcTest", slug=f"svc-{uuid.uuid4().hex[:6]}")
    session.add(t)
    await session.flush()
    return t


@pytest.mark.asyncio
async def test_register_and_authenticate(session: AsyncSession, tenant: Tenant):
    from finacialsim_saas.auth.service import AuthService
    svc = AuthService(session, _settings())
    user = await svc.register_user(
        tenant_id=tenant.id, email="a@test.com", password="secret",
        name="A", role=Role.admin,
    )
    await session.flush()
    assert user.id is not None
    assert user.password_hash != "secret"
    authed = await svc.authenticate("a@test.com", "secret")
    assert authed.id == user.id


@pytest.mark.asyncio
async def test_authenticate_wrong_password_raises(session: AsyncSession, tenant: Tenant):
    from finacialsim_saas.auth.service import AuthService
    from finacialsim_saas.errors import AuthError
    svc = AuthService(session, _settings())
    await svc.register_user(
        tenant_id=tenant.id, email="b@test.com", password="correct",
        name="B", role=Role.user,
    )
    await session.flush()
    with pytest.raises(AuthError):
        await svc.authenticate("b@test.com", "wrong")


@pytest.mark.asyncio
async def test_issue_tokens_returns_valid_jwt(session: AsyncSession, tenant: Tenant):
    import jwt as pyjwt
    from finacialsim_saas.auth.service import AuthService
    settings = _settings()
    svc = AuthService(session, settings)
    user = await svc.register_user(
        tenant_id=tenant.id, email="c@test.com", password="pw",
        name="C", role=Role.manager,
    )
    await session.flush()
    access, refresh = await svc.issue_tokens(user)
    payload = pyjwt.decode(access, settings.jwt_secret_key, algorithms=["HS256"])
    assert payload["sub"] == str(user.id)
    assert payload["tenant_id"] == str(tenant.id)
    assert payload["role"] == "manager"
    assert len(refresh) > 20


@pytest.mark.asyncio
async def test_rotate_refresh_issues_new_tokens(session: AsyncSession, tenant: Tenant):
    from finacialsim_saas.auth.service import AuthService
    svc = AuthService(session, _settings())
    user = await svc.register_user(
        tenant_id=tenant.id, email="d@test.com", password="pw", name="D", role=Role.user,
    )
    await session.flush()
    _, refresh1 = await svc.issue_tokens(user)
    await session.flush()
    returned_user, access2, refresh2 = await svc.rotate_refresh(refresh1)
    assert returned_user.id == user.id
    assert access2 != ""
    assert refresh2 != refresh1


@pytest.mark.asyncio
async def test_rotate_refresh_reuse_revokes_family(session: AsyncSession, tenant: Tenant):
    from finacialsim_saas.auth.service import AuthService
    from finacialsim_saas.errors import AuthError
    svc = AuthService(session, _settings())
    user = await svc.register_user(
        tenant_id=tenant.id, email="e@test.com", password="pw", name="E", role=Role.user,
    )
    await session.flush()
    _, refresh1 = await svc.issue_tokens(user)
    await session.flush()
    await svc.rotate_refresh(refresh1)   # first use — ok
    await session.flush()
    with pytest.raises(AuthError):
        await svc.rotate_refresh(refresh1)   # reuse → AuthError + family revoked


@pytest.mark.asyncio
async def test_revoke_all_sets_tokens_revoked_at(session: AsyncSession, tenant: Tenant):
    from finacialsim_saas.auth.service import AuthService
    svc = AuthService(session, _settings())
    user = await svc.register_user(
        tenant_id=tenant.id, email="f@test.com", password="pw", name="F", role=Role.user,
    )
    await session.flush()
    assert user.tokens_revoked_at is None
    await svc.revoke_all(user)
    assert user.tokens_revoked_at is not None
```

- [ ] **Step 3: Run — expect FAIL**

```bash
cd backend && uv run pytest tests/test_auth_service.py -v
```

Expected: `ModuleNotFoundError: finacialsim_saas.auth.service`

- [ ] **Step 4: Create `backend/finacialsim_saas/auth/service.py`**

```python
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.data.models import (
    AuditLog, NotificationsOutbox, PasswordResetToken,
    RefreshToken, Role, User,
)
from finacialsim_saas.errors import AuthError, ConflictError
from finacialsim_saas.settings import Settings


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._s = session
        self._cfg = settings

    # ── internal helpers ──────────────────────────────────────────────────────

    def _hash_pw(self, pw: str) -> str:
        return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=12)).decode()

    def _check_pw(self, pw: str, hashed: str) -> bool:
        return bcrypt.checkpw(pw.encode(), hashed.encode())

    def _hash_token(self, raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    def _make_access_jwt(self, user: User) -> str:
        now = datetime.now(timezone.utc)
        payload: dict = {
            "sub": str(user.id),
            "tenant_id": str(user.tenant_id),
            "role": user.role.value,
            "iat": now,
            "exp": now + timedelta(minutes=self._cfg.access_token_expire_minutes),
        }
        if user.client_id is not None:
            payload["client_id"] = str(user.client_id)
        return jwt.encode(payload, self._cfg.jwt_secret_key, algorithm="HS256")

    # ── public API ────────────────────────────────────────────────────────────

    async def register_user(
        self, *, tenant_id: uuid.UUID, email: str, password: str, name: str, role: Role
    ) -> User:
        existing = await self._s.execute(
            select(User).where(User.email == email, User.role != Role.customer)
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictError(f"Email {email!r} already registered")
        user = User(
            tenant_id=tenant_id, email=email, name=name,
            password_hash=self._hash_pw(password), role=role,
        )
        self._s.add(user)
        return user

    async def authenticate(self, email: str, password: str) -> User:
        result = await self._s.execute(
            select(User).where(User.email == email, User.role != Role.customer)
        )
        user = result.scalar_one_or_none()
        if user is None or not self._check_pw(password, user.password_hash):
            raise AuthError("Invalid credentials")
        if not user.is_active:
            raise AuthError("Account disabled")
        return user

    async def issue_tokens(
        self, user: User, family_id: uuid.UUID | None = None
    ) -> tuple[str, str]:
        raw = secrets.token_urlsafe(32)
        rt = RefreshToken(
            user_id=user.id,
            tenant_id=user.tenant_id,
            token_hash=self._hash_token(raw),
            family_id=family_id or uuid.uuid4(),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=self._cfg.refresh_token_expire_days),
        )
        self._s.add(rt)
        return self._make_access_jwt(user), raw

    async def rotate_refresh(self, raw_token: str) -> tuple[User, str, str]:
        th = self._hash_token(raw_token)
        result = await self._s.execute(
            select(RefreshToken).where(RefreshToken.token_hash == th)
        )
        rt = result.scalar_one_or_none()
        if rt is None:
            raise AuthError("Invalid refresh token")

        now = datetime.now(timezone.utc)

        if rt.revoked_at is not None:
            await self._s.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == rt.family_id)
                .values(revoked_at=now)
            )
            raise AuthError("Refresh token reuse detected — session revoked")

        if rt.expires_at.replace(tzinfo=timezone.utc) < now:
            raise AuthError("Refresh token expired")

        user_result = await self._s.execute(select(User).where(User.id == rt.user_id))
        user = user_result.scalar_one_or_none()
        if user is None or not user.is_active:
            raise AuthError("User not found or inactive")

        rt.revoked_at = now
        new_access, new_refresh = await self.issue_tokens(user, family_id=rt.family_id)
        return user, new_access, new_refresh

    async def revoke_all(self, user: User) -> None:
        user.tokens_revoked_at = datetime.now(timezone.utc)

    async def request_password_reset(self, email: str) -> None:
        result = await self._s.execute(
            select(User).where(User.email == email, User.role != Role.customer)
        )
        user = result.scalar_one_or_none()
        if user is None:
            return  # silent — don't leak user existence

        now = datetime.now(timezone.utc)
        await self._s.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=now)
        )

        raw = secrets.token_urlsafe(32)
        prt = PasswordResetToken(
            user_id=user.id,
            tenant_id=user.tenant_id,
            token_hash=self._hash_token(raw),
            expires_at=now + timedelta(minutes=30),
        )
        self._s.add(prt)

        reset_url = f"{self._cfg.frontend_base_url}/reset-password/{raw}"
        self._s.add(
            NotificationsOutbox(
                tenant_id=user.tenant_id,
                type="password_reset",
                recipient=user.email,
                payload={"reset_url": reset_url, "user_name": user.name},
            )
        )

    async def confirm_password_reset(self, raw_token: str, new_password: str) -> None:
        th = self._hash_token(raw_token)
        result = await self._s.execute(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == th)
        )
        prt = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)

        if prt is None or prt.used_at is not None:
            raise AuthError("Invalid or already-used reset token")
        if prt.expires_at.replace(tzinfo=timezone.utc) < now:
            raise AuthError("Reset token expired")

        user_result = await self._s.execute(select(User).where(User.id == prt.user_id))
        user = user_result.scalar_one()
        user.password_hash = self._hash_pw(new_password)
        user.tokens_revoked_at = now
        prt.used_at = now

    async def write_audit(
        self,
        *,
        tenant_id: uuid.UUID,
        usuario_id: uuid.UUID | None,
        acao: str,
        entidade: str | None = None,
        entidade_id: uuid.UUID | None = None,
        diff_json: dict | None = None,
    ) -> None:
        self._s.add(
            AuditLog(
                tenant_id=tenant_id,
                usuario_id=usuario_id,
                acao=acao,
                entidade=entidade,
                entidade_id=entidade_id,
                diff_json=diff_json,
            )
        )
```

- [ ] **Step 5: Run — expect PASS**

```bash
cd backend && uv run pytest tests/test_auth_service.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/auth/ backend/tests/test_auth_service.py
git commit -m "feat(auth): AuthService — register, authenticate, tokens, rotation, reset, audit"
```

---

## Task 6: FastAPI auth dependencies

**Files:**
- Create: `backend/finacialsim_saas/auth/deps.py`
- Create: `backend/tests/test_deps.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_deps.py`:
```python
import uuid
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import jwt


def _token(user_id: str, tenant_id: str, role: str, secret: str = "test-secret") -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": user_id, "tenant_id": tenant_id, "role": role,
         "iat": now, "exp": now + timedelta(minutes=15)},
        secret, algorithm="HS256",
    )


@pytest.mark.asyncio
async def test_parse_bearer_valid_token(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
    from finacialsim_saas.auth.deps import _parse_bearer
    uid, tid = str(uuid.uuid4()), str(uuid.uuid4())
    req = MagicMock()
    req.headers = {"Authorization": f"Bearer {_token(uid, tid, 'admin')}"}
    ctx = await _parse_bearer(req)
    assert ctx is not None and str(ctx.user_id) == uid


@pytest.mark.asyncio
async def test_parse_bearer_no_header_returns_none(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
    from finacialsim_saas.auth.deps import _parse_bearer
    req = MagicMock()
    req.headers = {}
    assert await _parse_bearer(req) is None


@pytest.mark.asyncio
async def test_require_role_wrong_role_raises():
    from finacialsim_saas.auth.deps import RequestContext, require_role
    from finacialsim_saas.data.models import Role
    from finacialsim_saas.errors import TenantAccessError
    ctx = RequestContext(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role=Role.user, iat=0.0)
    with pytest.raises(TenantAccessError):
        await require_role("admin")(ctx)


@pytest.mark.asyncio
async def test_require_role_correct_role_passes():
    from finacialsim_saas.auth.deps import RequestContext, require_role
    from finacialsim_saas.data.models import Role
    ctx = RequestContext(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role=Role.admin, iat=0.0)
    result = await require_role("admin")(ctx)
    assert result.role == Role.admin
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd backend && uv run pytest tests/test_deps.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `backend/finacialsim_saas/auth/deps.py`**

```python
import uuid
from dataclasses import dataclass
from datetime import timezone
from typing import Annotated, AsyncGenerator

import jwt
from fastapi import Depends, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.data.models import Role, User
from finacialsim_saas.errors import AuthError, TenantAccessError
from finacialsim_saas.settings import get_settings


@dataclass
class RequestContext:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: Role
    iat: float


async def _parse_bearer(request: Request) -> RequestContext | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(
            auth[7:], get_settings().jwt_secret_key, algorithms=["HS256"]
        )
    except jwt.PyJWTError:
        return None
    return RequestContext(
        user_id=uuid.UUID(payload["sub"]),
        tenant_id=uuid.UUID(payload["tenant_id"]),
        role=Role(payload["role"]),
        iat=float(payload["iat"]),
    )


async def get_db_session(
    request: Request,
    ctx: Annotated[RequestContext | None, Depends(_parse_bearer)],
) -> AsyncGenerator[AsyncSession, None]:
    factory = request.app.state.session_factory
    async with factory() as session:
        if ctx is not None:
            await session.execute(
                text(f"SET LOCAL app.tenant_id = '{ctx.tenant_id}'")
            )
        yield session


async def get_current_ctx(
    ctx: Annotated[RequestContext | None, Depends(_parse_bearer)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RequestContext:
    if ctx is None:
        raise AuthError("Not authenticated")
    result = await session.execute(select(User).where(User.id == ctx.user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthError("User not found or inactive")
    if str(user.tenant_id) != str(ctx.tenant_id):
        raise AuthError("Token tenant mismatch")
    if user.tokens_revoked_at is not None:
        revoked_ts = user.tokens_revoked_at.replace(tzinfo=timezone.utc).timestamp()
        if ctx.iat <= revoked_ts:
            raise AuthError("Token revoked")
    return ctx


def require_role(*allowed_roles: str):
    async def _inner(
        ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    ) -> RequestContext:
        if ctx.role.value not in allowed_roles:
            raise TenantAccessError("Insufficient permissions")
        return ctx
    return _inner
```

- [ ] **Step 4: Run — expect PASS**

```bash
cd backend && uv run pytest tests/test_deps.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/auth/deps.py backend/tests/test_deps.py
git commit -m "feat(auth): FastAPI deps — RequestContext, get_db_session, get_current_ctx, require_role"
```

---

## Task 7: Auth schemas

**Files:**
- Create: `backend/finacialsim_saas/auth/schemas.py`

Schemas are pure Pydantic — tested indirectly by endpoint tests in Task 9.

- [ ] **Step 1: Create `backend/finacialsim_saas/auth/schemas.py`**

```python
import uuid
from datetime import datetime
from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access: str
    refresh: str


class RefreshRequest(BaseModel):
    refresh: str


class PasswordResetRequestBody(BaseModel):
    email: str


class PasswordResetConfirmBody(BaseModel):
    token: str
    password: str


class UserMeResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    name: str
    role: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class UserListItem(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime


class CreateUserRequest(BaseModel):
    email: str
    name: str
    password: str
    role: str


class PatchUserRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
```

- [ ] **Step 2: Commit**

```bash
git add backend/finacialsim_saas/auth/schemas.py
git commit -m "feat(auth): Pydantic schemas for auth and user endpoints"
```

---

## Task 8: Wire main.py

**Files:**
- Modify: `backend/finacialsim_saas/main.py`

Adds `session_factory` to `app.state` (needed by `get_db_session`) and registers the auth + users routers (created in Tasks 9 + 10).

- [ ] **Step 1: Update `backend/finacialsim_saas/main.py`**

Replace the full file with:
```python
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from finacialsim_saas.data.database import build_engine, build_session_factory
from finacialsim_saas.errors import AppError
from finacialsim_saas.middleware.logging import configure_logging
from finacialsim_saas.settings import get_settings

app_state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.app_env)
    engine = build_engine(str(settings.database_url))
    app_state["engine"] = engine
    app.state.session_factory = build_session_factory(engine)
    logger.info("startup", env=settings.app_env, sha=settings.git_sha)
    yield
    await engine.dispose()
    logger.info("shutdown")


app = FastAPI(title="FinacialSim SaaS", lifespan=lifespan)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
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
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


from finacialsim_saas.api.health import router as health_router   # noqa: E402
from finacialsim_saas.api.auth import router as auth_router        # noqa: E402
from finacialsim_saas.api.users import router as users_router      # noqa: E402

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(users_router)
```

Note: `api/auth.py` and `api/users.py` don't exist yet. Create empty stub files now to avoid import errors:

`backend/finacialsim_saas/api/auth.py` (stub):
```python
from fastapi import APIRouter
router = APIRouter()
```

`backend/finacialsim_saas/api/users.py` (stub):
```python
from fastapi import APIRouter
router = APIRouter()
```

- [ ] **Step 2: Verify existing tests still pass**

```bash
cd backend && uv run pytest tests/ -v
```

Expected: all existing tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/finacialsim_saas/main.py backend/finacialsim_saas/api/auth.py backend/finacialsim_saas/api/users.py
git commit -m "feat(main): add session_factory to app.state; stub auth + users routers"
```

---

## Task 9: Auth router + integration tests

**Files:**
- Modify: `backend/finacialsim_saas/api/auth.py` (replace stub)
- Create: `backend/tests/test_auth_endpoints.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_auth_endpoints.py`:
```python
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.data.models import Role, Tenant
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.settings import Settings


def _svc_settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        jwt_secret_key="test-secret",
    )


@pytest.fixture
async def seed(session: AsyncSession):
    t = Tenant(name="Auth EP", slug=f"auth-ep-{uuid.uuid4().hex[:6]}")
    session.add(t)
    await session.flush()
    svc = AuthService(session, _svc_settings())
    user = await svc.register_user(
        tenant_id=t.id, email="ep@test.com", password="pass123",
        name="EP User", role=Role.admin,
    )
    await session.commit()
    return t, user


@pytest.mark.asyncio
async def test_login_returns_tokens(client, seed):
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "ep@test.com", "password": "pass123"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access" in data and "refresh" in data


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client, seed):
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "ep@test.com", "password": "wrong"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_returns_new_tokens(client, seed):
    login = await client.post(
        "/api/v1/auth/login", json={"email": "ep@test.com", "password": "pass123"}
    )
    r1 = login.json()["refresh"]
    resp = await client.post("/api/v1/auth/refresh", json={"refresh": r1})
    assert resp.status_code == 200
    assert resp.json()["refresh"] != r1


@pytest.mark.asyncio
async def test_refresh_reuse_returns_401(client, seed):
    login = await client.post(
        "/api/v1/auth/login", json={"email": "ep@test.com", "password": "pass123"}
    )
    r1 = login.json()["refresh"]
    await client.post("/api/v1/auth/refresh", json={"refresh": r1})
    resp = await client.post("/api/v1/auth/refresh", json={"refresh": r1})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_returns_204(client, seed):
    login = await client.post(
        "/api/v1/auth/login", json={"email": "ep@test.com", "password": "pass123"}
    )
    access = login.json()["access"]
    resp = await client.post(
        "/api/v1/auth/logout", headers={"Authorization": f"Bearer {access}"}
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_password_reset_request_always_202(client, seed):
    for email in ("ep@test.com", "nobody@example.com"):
        resp = await client.post(
            "/api/v1/auth/password-reset/request", json={"email": email}
        )
        assert resp.status_code == 202
```

- [ ] **Step 2: Run — expect FAIL (stub router returns 404)**

```bash
cd backend && uv run pytest tests/test_auth_endpoints.py -v
```

Expected: 404 errors.

- [ ] **Step 3: Replace `backend/finacialsim_saas/api/auth.py` with full implementation**

```python
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_current_ctx, get_db_session
from finacialsim_saas.auth.schemas import (
    LoginRequest, PasswordResetConfirmBody, PasswordResetRequestBody,
    RefreshRequest, TokenResponse,
)
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.models import User
from finacialsim_saas.settings import get_settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _svc(session: AsyncSession) -> AuthService:
    return AuthService(session, get_settings())


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    svc = _svc(session)
    user = await svc.authenticate(body.email, body.password)
    access, refresh = await svc.issue_tokens(user)
    user.last_login_at = datetime.now(timezone.utc)
    await svc.write_audit(tenant_id=user.tenant_id, usuario_id=user.id, acao="login")
    await session.commit()
    return TokenResponse(access=access, refresh=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    body: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    svc = _svc(session)
    _, access, refresh = await svc.rotate_refresh(body.refresh)
    await session.commit()
    return TokenResponse(access=access, refresh=refresh)


@router.post("/logout", status_code=204)
async def logout(
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    svc = _svc(session)
    result = await session.execute(select(User).where(User.id == ctx.user_id))
    user = result.scalar_one()
    await svc.revoke_all(user)
    await svc.write_audit(tenant_id=ctx.tenant_id, usuario_id=ctx.user_id, acao="logout")
    await session.commit()
    return Response(status_code=204)


@router.post("/password-reset/request", status_code=202)
async def password_reset_request(
    body: PasswordResetRequestBody,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    svc = _svc(session)
    await svc.request_password_reset(body.email)
    await session.commit()
    return Response(status_code=202)


@router.post("/password-reset/confirm", status_code=204)
async def password_reset_confirm(
    body: PasswordResetConfirmBody,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    svc = _svc(session)
    await svc.confirm_password_reset(body.token, body.password)
    await session.commit()
    return Response(status_code=204)
```

- [ ] **Step 4: Run — expect PASS**

```bash
cd backend && uv run pytest tests/test_auth_endpoints.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/api/auth.py backend/tests/test_auth_endpoints.py
git commit -m "feat(api): auth endpoints — login, refresh, logout, password-reset"
```

---

## Task 10: Users router + integration tests

**Files:**
- Modify: `backend/finacialsim_saas/api/users.py` (replace stub)
- Create: `backend/tests/test_users_endpoints.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_users_endpoints.py`:
```python
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.data.models import Role, Tenant
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.settings import Settings


def _ss() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        jwt_secret_key="test-secret",
    )


@pytest.fixture
async def setup(session: AsyncSession):
    t = Tenant(name="Users EP", slug=f"users-ep-{uuid.uuid4().hex[:6]}")
    session.add(t)
    await session.flush()
    svc = AuthService(session, _ss())
    admin = await svc.register_user(
        tenant_id=t.id, email="admin@users.com", password="pass",
        name="Admin", role=Role.admin,
    )
    member = await svc.register_user(
        tenant_id=t.id, email="member@users.com", password="pass",
        name="Member", role=Role.user,
    )
    await session.commit()
    return t, admin, member


async def _login(client, email: str) -> str:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "pass"}
    )
    return resp.json()["access"]


@pytest.mark.asyncio
async def test_get_me(client, setup):
    _, admin, _ = setup
    token = await _login(client, "admin@users.com")
    resp = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "admin@users.com"
    assert resp.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_get_users_as_admin_returns_staff_only(client, setup):
    token = await _login(client, "admin@users.com")
    resp = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    emails = [u["email"] for u in resp.json()]
    assert "admin@users.com" in emails
    assert "member@users.com" in emails


@pytest.mark.asyncio
async def test_get_users_as_user_role_returns_403(client, setup):
    token = await _login(client, "member@users.com")
    resp = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_post_users_creates_user(client, setup):
    t, _, _ = setup
    token = await _login(client, "admin@users.com")
    resp = await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "new@users.com", "name": "New", "password": "pw123", "role": "user"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_patch_user_role(client, setup):
    t, _, member = setup
    token = await _login(client, "admin@users.com")
    resp = await client.patch(
        f"/api/v1/users/{member.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "manager"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "manager"


@pytest.mark.asyncio
async def test_get_me_unauthenticated_returns_401(client, setup):
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd backend && uv run pytest tests/test_users_endpoints.py -v
```

Expected: 404 errors (stub router).

- [ ] **Step 3: Replace `backend/finacialsim_saas/api/users.py`**

```python
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_current_ctx, get_db_session, require_role
from finacialsim_saas.auth.schemas import (
    CreateUserRequest, PatchUserRequest, UserListItem, UserMeResponse,
)
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.models import NotificationsOutbox, Role, User
from finacialsim_saas.errors import NotFoundError, TenantAccessError
from finacialsim_saas.settings import get_settings

router = APIRouter(prefix="/api/v1", tags=["users"])


def _svc(session: AsyncSession) -> AuthService:
    return AuthService(session, get_settings())


@router.get("/me", response_model=UserMeResponse)
async def get_me(
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserMeResponse:
    result = await session.execute(select(User).where(User.id == ctx.user_id))
    user = result.scalar_one()
    return UserMeResponse(
        id=user.id, tenant_id=user.tenant_id, email=user.email, name=user.name,
        role=user.role.value, is_active=user.is_active,
        last_login_at=user.last_login_at, created_at=user.created_at,
    )


@router.get("/users", response_model=list[UserListItem])
async def list_users(
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[UserListItem]:
    result = await session.execute(
        select(User).where(
            User.tenant_id == ctx.tenant_id,
            User.role != Role.customer,
        )
    )
    return [
        UserListItem(
            id=u.id, email=u.email, name=u.name,
            role=u.role.value, is_active=u.is_active, created_at=u.created_at,
        )
        for u in result.scalars().all()
    ]


@router.post("/users", response_model=UserListItem, status_code=201)
async def create_user(
    body: CreateUserRequest,
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserListItem:
    svc = _svc(session)
    user = await svc.register_user(
        tenant_id=ctx.tenant_id, email=body.email, password=body.password,
        name=body.name, role=Role(body.role),
    )
    await session.flush()
    session.add(
        NotificationsOutbox(
            tenant_id=ctx.tenant_id,
            type="user_invite",
            recipient=user.email,
            payload={"user_name": user.name},
        )
    )
    await svc.write_audit(
        tenant_id=ctx.tenant_id, usuario_id=ctx.user_id,
        acao="user_create", entidade="user", entidade_id=user.id,
    )
    await session.commit()
    await session.refresh(user)
    return UserListItem(
        id=user.id, email=user.email, name=user.name,
        role=user.role.value, is_active=user.is_active, created_at=user.created_at,
    )


@router.patch("/users/{user_id}", response_model=UserListItem)
async def patch_user(
    user_id: uuid.UUID,
    body: PatchUserRequest,
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserListItem:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundError(f"User {user_id} not found")
    if str(user.tenant_id) != str(ctx.tenant_id):
        raise TenantAccessError("Cannot modify users from another tenant")

    before: dict = {"role": user.role.value, "is_active": user.is_active}
    if body.role is not None:
        user.role = Role(body.role)
    if body.is_active is not None:
        user.is_active = body.is_active
    after: dict = {"role": user.role.value, "is_active": user.is_active}

    svc = _svc(session)
    await svc.write_audit(
        tenant_id=ctx.tenant_id, usuario_id=ctx.user_id,
        acao="user_patch", entidade="user", entidade_id=user.id,
        diff_json={"before": before, "after": after},
    )
    await session.commit()
    await session.refresh(user)
    return UserListItem(
        id=user.id, email=user.email, name=user.name,
        role=user.role.value, is_active=user.is_active, created_at=user.created_at,
    )
```

- [ ] **Step 4: Run — expect PASS**

```bash
cd backend && uv run pytest tests/test_users_endpoints.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/api/users.py backend/tests/test_users_endpoints.py
git commit -m "feat(api): users endpoints — /me, GET/POST /users, PATCH /users/{id}"
```

---

## Task 11: MaildirChannel + outbox drain task

**Files:**
- Create: `backend/finacialsim_saas/workers/maildir.py`

- [ ] **Step 1: Write the test**

Create `backend/tests/test_maildir.py`:
```python
import json
import pytest
from pathlib import Path


def test_deliver_writes_eml_file(tmp_path):
    from finacialsim_saas.workers.maildir import MaildirChannel
    ch = MaildirChannel(str(tmp_path))
    ch.deliver(to="user@test.com", subject="Test", body="Hello")
    files = list(tmp_path.iterdir())
    assert len(files) == 1
    content = files[0].read_text()
    assert "To: user@test.com" in content
    assert "Hello" in content
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd backend && uv run pytest tests/test_maildir.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `backend/finacialsim_saas/workers/maildir.py`**

```python
from datetime import datetime, timezone
from pathlib import Path


class MaildirChannel:
    def __init__(self, maildir_path: str) -> None:
        self._path = Path(maildir_path)
        self._path.mkdir(parents=True, exist_ok=True)

    def deliver(self, *, to: str, subject: str, body: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        safe_to = to.replace("@", "_at_").replace("/", "_")
        filename = self._path / f"{ts}-{safe_to}.eml"
        filename.write_text(
            f"To: {to}\nSubject: {subject}\n\n{body}", encoding="utf-8"
        )


async def drain_outbox(ctx) -> None:  # noqa: ANN001 — ARQ context
    """ARQ task: reads pending notifications_outbox rows, writes to MaildirChannel."""
    from datetime import timezone
    from sqlalchemy import select, update

    from finacialsim_saas.data.database import build_session_factory
    from finacialsim_saas.data.models import NotificationsOutbox
    from finacialsim_saas.settings import get_settings

    settings = get_settings()
    channel = MaildirChannel(settings.maildir_path)
    engine = ctx.get("engine")  # set by WorkerSettings.on_startup
    factory = build_session_factory(engine)

    async with factory() as session:
        now = datetime.now(timezone.utc)
        result = await session.execute(
            select(NotificationsOutbox).where(
                NotificationsOutbox.processed_at.is_(None),
                NotificationsOutbox.failed_at.is_(None),
            ).limit(50)
        )
        rows = result.scalars().all()

        for row in rows:
            try:
                _render_and_deliver(channel, row)
                row.processed_at = now
            except Exception as exc:
                row.attempts += 1
                row.failed_at = now
                row.error = str(exc)

        await session.commit()


def _render_and_deliver(channel: MaildirChannel, row) -> None:  # noqa: ANN001
    if row.type == "password_reset":
        subject = "Redefinição de senha — FinacialSim"
        body = (
            f"Olá {row.payload.get('user_name', '')},\n\n"
            f"Clique no link para redefinir sua senha:\n{row.payload['reset_url']}\n\n"
            "Link válido por 30 minutos."
        )
    elif row.type == "user_invite":
        subject = "Bem-vindo ao FinacialSim"
        body = (
            f"Olá {row.payload.get('user_name', '')},\n\n"
            "Sua conta foi criada. Use as credenciais fornecidas pelo administrador."
        )
    else:
        subject = f"Notificação: {row.type}"
        body = str(row.payload)
    channel.deliver(to=row.recipient, subject=subject, body=body)
```

- [ ] **Step 4: Run — expect PASS**

```bash
cd backend && uv run pytest tests/test_maildir.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/workers/maildir.py backend/tests/test_maildir.py
git commit -m "feat(workers): MaildirChannel + drain_outbox ARQ task for dev email sink"
```

---

## Task 12: CLI

**Files:**
- Create: `backend/finacialsim_saas/cli/__init__.py`
- Create: `backend/finacialsim_saas/cli/main.py`
- Create: `backend/tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_cli.py`:
```python
import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


def test_tenant_create_and_user_create(runner, engine):
    """CLI creates tenant and user in the testcontainer DB."""
    import os
    # DATABASE_URL is already set by db_url fixture (engine depends on db_url)
    from finacialsim_saas.cli.main import app

    result = runner.invoke(
        app,
        ["tenant", "create",
         "--name", "CLI Loja",
         "--slug", "cli-loja",
         "--admin-email", "cli-admin@loja.com",
         "--admin-password", "cli-pass123"],
    )
    assert result.exit_code == 0, result.output
    assert "created" in result.output.lower()

    result2 = runner.invoke(
        app,
        ["user", "create",
         "--tenant-slug", "cli-loja",
         "--email", "cli-user@loja.com",
         "--role", "user",
         "--password", "userpass"],
    )
    assert result2.exit_code == 0, result2.output
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd backend && uv run pytest tests/test_cli.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `backend/finacialsim_saas/cli/__init__.py`**

Empty file.

- [ ] **Step 4: Create `backend/finacialsim_saas/cli/main.py`**

```python
import asyncio
from typing import Annotated

import typer
from sqlalchemy import select

from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.database import build_engine, build_session_factory
from finacialsim_saas.data.models import Role, Tenant
from finacialsim_saas.settings import get_settings

app = typer.Typer(name="finacialsim-saas", help="FinacialSim SaaS management CLI")
tenant_app = typer.Typer()
user_app = typer.Typer()
app.add_typer(tenant_app, name="tenant")
app.add_typer(user_app, name="user")


def _run(coro):
    return asyncio.run(coro)


@tenant_app.command("create")
def tenant_create(
    name: Annotated[str, typer.Option("--name")],
    slug: Annotated[str, typer.Option("--slug")],
    admin_email: Annotated[str, typer.Option("--admin-email")],
    admin_password: Annotated[str, typer.Option(
        "--admin-password", prompt=True, hide_input=True
    )],
):
    async def _create():
        settings = get_settings()
        engine = build_engine(str(settings.database_url))
        factory = build_session_factory(engine)
        async with factory() as session:
            existing = await session.execute(select(Tenant).where(Tenant.slug == slug))
            if existing.scalar_one_or_none() is not None:
                typer.echo(f"Error: tenant slug '{slug}' already exists.", err=True)
                raise typer.Exit(1)
            tenant = Tenant(name=name, slug=slug)
            session.add(tenant)
            await session.flush()
            svc = AuthService(session, settings)
            await svc.register_user(
                tenant_id=tenant.id,
                email=admin_email,
                password=admin_password,
                name=admin_email,
                role=Role.admin,
            )
            await session.commit()
            typer.echo(f"Tenant '{name}' (slug={slug}) created. Admin: {admin_email}")
        await engine.dispose()

    _run(_create())


@user_app.command("create")
def user_create(
    tenant_slug: Annotated[str, typer.Option("--tenant-slug")],
    email: Annotated[str, typer.Option("--email")],
    role: Annotated[str, typer.Option("--role")],
    password: Annotated[str, typer.Option(
        "--password", prompt=True, hide_input=True
    )],
):
    async def _create():
        settings = get_settings()
        engine = build_engine(str(settings.database_url))
        factory = build_session_factory(engine)
        async with factory() as session:
            t_result = await session.execute(
                select(Tenant).where(Tenant.slug == tenant_slug)
            )
            tenant = t_result.scalar_one_or_none()
            if tenant is None:
                typer.echo(f"Error: tenant '{tenant_slug}' not found.", err=True)
                raise typer.Exit(1)
            svc = AuthService(session, settings)
            await svc.register_user(
                tenant_id=tenant.id, email=email, password=password,
                name=email, role=Role(role),
            )
            await session.commit()
            typer.echo(f"User '{email}' ({role}) created in tenant '{tenant_slug}'.")
        await engine.dispose()

    _run(_create())


@user_app.command("reset-password")
def user_reset_password(
    tenant_slug: Annotated[str, typer.Option("--tenant-slug")],
    email: Annotated[str, typer.Option("--email")],
):
    async def _reset():
        settings = get_settings()
        engine = build_engine(str(settings.database_url))
        factory = build_session_factory(engine)
        async with factory() as session:
            svc = AuthService(session, settings)
            await svc.request_password_reset(email)
            await session.commit()
            typer.echo(f"Password reset enqueued for {email} (check dev-mail/).")
        await engine.dispose()

    _run(_reset())


if __name__ == "__main__":
    app()
```

- [ ] **Step 5: Run — expect PASS**

```bash
cd backend && uv run pytest tests/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/cli/ backend/tests/test_cli.py
git commit -m "feat(cli): Typer CLI — tenant create, user create, user reset-password"
```

---

## Task 13: Cross-tenant isolation tests

**Files:**
- Create: `backend/tests/test_tenant_isolation.py`

- [ ] **Step 1: Create `backend/tests/test_tenant_isolation.py`**

```python
"""
Verifies that every role under tenant A cannot read tenant B's resources,
even when authenticated. Tests app-level tenant_id filtering (no RLS in Phase 1).
"""
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.data.models import Role, Tenant
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.settings import Settings

_ROLES = [Role.admin, Role.manager, Role.user]


def _ss() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        jwt_secret_key="test-secret",
    )


@pytest.fixture(scope="module")
async def two_tenants(engine):
    from finacialsim_saas.data.database import build_session_factory
    factory = build_session_factory(engine)
    async with factory() as session:
        ta = Tenant(name="Tenant A", slug=f"tenant-a-{uuid.uuid4().hex[:6]}")
        tb = Tenant(name="Tenant B", slug=f"tenant-b-{uuid.uuid4().hex[:6]}")
        session.add_all([ta, tb])
        await session.flush()

        svc = AuthService(session, _ss())
        users_a = {}
        users_b = {}
        for r in _ROLES:
            ua = await svc.register_user(
                tenant_id=ta.id, email=f"{r.value}_a@iso.com",
                password="pass", name=f"{r.value} A", role=r,
            )
            ub = await svc.register_user(
                tenant_id=tb.id, email=f"{r.value}_b@iso.com",
                password="pass", name=f"{r.value} B", role=r,
            )
            users_a[r] = ua
            users_b[r] = ub
        await session.commit()
        yield ta, tb, users_a, users_b


@pytest.mark.asyncio
@pytest.mark.parametrize("role", _ROLES)
async def test_get_users_returns_only_own_tenant(client, two_tenants, role):
    ta, tb, users_a, _ = two_tenants
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": f"{role.value}_a@iso.com", "password": "pass"},
    )
    if role != Role.admin:
        # Non-admin gets 403 on /users — that's the expected isolation behavior
        token = login.json()["access"]
        resp = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403
        return

    token = login.json()["access"]
    resp = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    emails = [u["email"] for u in resp.json()]
    # Only tenant A emails returned
    assert all("_a@iso.com" in e for e in emails)
    assert not any("_b@iso.com" in e for e in emails)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", _ROLES)
async def test_get_me_returns_own_tenant(client, two_tenants, role):
    ta, _, users_a, _ = two_tenants
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": f"{role.value}_a@iso.com", "password": "pass"},
    )
    token = login.json()["access"]
    resp = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == str(ta.id)


@pytest.mark.asyncio
async def test_patch_user_cross_tenant_returns_403_or_404(client, two_tenants):
    ta, tb, users_a, users_b = two_tenants
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin_a@iso.com", "password": "pass"},
    )
    token = login.json()["access"]
    # Admin A tries to patch a user from Tenant B
    resp = await client.patch(
        f"/api/v1/users/{users_b[Role.user].id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "manager"},
    )
    assert resp.status_code in (403, 404)
```

- [ ] **Step 2: Run — expect PASS**

```bash
cd backend && uv run pytest tests/test_tenant_isolation.py -v
```

Expected: all PASS.

- [ ] **Step 3: Run full backend test suite**

```bash
cd backend && uv run pytest tests/ -v
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_tenant_isolation.py
git commit -m "test: cross-tenant isolation — every role × every endpoint × two tenants"
```

---

## Task 14: Frontend dependencies + AuthContext

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/context/AuthContext.tsx`

- [ ] **Step 1: Add frontend deps**

```bash
cd frontend && npm install react-hook-form zod @hookform/resolvers
```

- [ ] **Step 2: Create `frontend/src/context/AuthContext.tsx`**

```tsx
import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api } from "../lib/api";

interface AuthTokens {
  access: string;
  refresh: string;
}

interface AuthContextValue {
  tokens: AuthTokens | null;
  login: (tokens: AuthTokens) => void;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [tokens, setTokens] = useState<AuthTokens | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("auth_tokens");
    if (stored) {
      const parsed: AuthTokens = JSON.parse(stored);
      // Re-hydrate access token via refresh on page reload
      api
        .post<AuthTokens>("/v1/auth/refresh", { refresh: parsed.refresh })
        .then((r) => {
          const fresh = r.data;
          localStorage.setItem("auth_tokens", JSON.stringify(fresh));
          setTokens(fresh);
        })
        .catch(() => {
          localStorage.removeItem("auth_tokens");
        })
        .finally(() => setReady(true));
    } else {
      setReady(true);
    }
  }, []);

  const login = (t: AuthTokens) => {
    localStorage.setItem("auth_tokens", JSON.stringify(t));
    setTokens(t);
  };

  const logout = () => {
    if (tokens) {
      api
        .post("/v1/auth/logout", null, {
          headers: { Authorization: `Bearer ${tokens.access}` },
        })
        .catch(() => {});
    }
    localStorage.removeItem("auth_tokens");
    setTokens(null);
  };

  if (!ready) return null;

  return (
    <AuthContext.Provider
      value={{ tokens, login, logout, isAuthenticated: tokens !== null }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
```

- [ ] **Step 3: Commit**

```bash
cd ..
git add frontend/package.json frontend/package-lock.json frontend/src/context/AuthContext.tsx
git commit -m "feat(frontend): AuthContext with localStorage token management + refresh on reload"
```

---

## Task 15: Axios 401 interceptor

**Files:**
- Modify: `frontend/src/lib/api.ts`

The interceptor must handle concurrent 401s: only one refresh fires, others queue and replay when the new token arrives.

- [ ] **Step 1: Replace `frontend/src/lib/api.ts`**

```typescript
import axios, { AxiosRequestConfig } from "axios";

// In dev: Vite proxy forwards /api/* → http://localhost:8000/*
// In prod: Caddy routes /api/* → api:8000/*
export const api = axios.create({
  baseURL: "/api",
  withCredentials: true,
});

let isRefreshing = false;
let waitQueue: Array<{ resolve: (token: string) => void; reject: (err: unknown) => void }> = [];

function processQueue(error: unknown, token: string | null) {
  waitQueue.forEach((p) => (error ? p.reject(error) : p.resolve(token!)));
  waitQueue = [];
}

api.interceptors.request.use((config) => {
  const stored = localStorage.getItem("auth_tokens");
  if (stored) {
    const { access } = JSON.parse(stored) as { access: string; refresh: string };
    config.headers = config.headers ?? {};
    config.headers["Authorization"] = `Bearer ${access}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config as AxiosRequestConfig & { _retry?: boolean };
    if (error.response?.status !== 401 || original._retry) {
      return Promise.reject(error);
    }
    original._retry = true;

    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        waitQueue.push({
          resolve: (token) => {
            original.headers = original.headers ?? {};
            original.headers["Authorization"] = `Bearer ${token}`;
            resolve(api(original));
          },
          reject,
        });
      });
    }

    isRefreshing = true;
    const stored = localStorage.getItem("auth_tokens");
    if (!stored) {
      isRefreshing = false;
      window.location.href = "/login";
      return Promise.reject(error);
    }

    const { refresh } = JSON.parse(stored) as { access: string; refresh: string };
    try {
      const { data } = await api.post<{ access: string; refresh: string }>(
        "/v1/auth/refresh",
        { refresh }
      );
      localStorage.setItem("auth_tokens", JSON.stringify(data));
      processQueue(null, data.access);
      original.headers = original.headers ?? {};
      original.headers["Authorization"] = `Bearer ${data.access}`;
      return api(original);
    } catch (refreshError) {
      processQueue(refreshError, null);
      localStorage.removeItem("auth_tokens");
      window.location.href = "/login";
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }
);
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(frontend): axios 401-queue interceptor with token refresh and redirect"
```

---

## Task 16: Login, ForgotPassword, ResetPassword pages

**Files:**
- Create: `frontend/src/routes/Login.tsx`
- Create: `frontend/src/routes/ForgotPassword.tsx`
- Create: `frontend/src/routes/ResetPassword.tsx`

- [ ] **Step 1: Create `frontend/src/routes/Login.tsx`**

```tsx
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";

const schema = z.object({
  email: z.string().email("Email inválido"),
  password: z.string().min(1, "Senha obrigatória"),
});
type FormData = z.infer<typeof schema>;

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: FormData) => {
    try {
      const res = await api.post<{ access: string; refresh: string }>(
        "/v1/auth/login",
        data
      );
      login(res.data);
      navigate("/");
    } catch {
      setError("root", { message: "Email ou senha inválidos." });
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm rounded-lg bg-white p-8 shadow">
        <h1 className="mb-6 text-2xl font-bold text-gray-900">FinacialSim</h1>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Email
            </label>
            <input
              type="email"
              {...register("email")}
              className="w-full rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            {errors.email && (
              <p className="mt-1 text-xs text-red-600">{errors.email.message}</p>
            )}
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Senha
            </label>
            <input
              type="password"
              {...register("password")}
              className="w-full rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            {errors.password && (
              <p className="mt-1 text-xs text-red-600">{errors.password.message}</p>
            )}
          </div>
          {errors.root && (
            <p className="text-sm text-red-600">{errors.root.message}</p>
          )}
          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-lg bg-blue-600 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {isSubmitting ? "Entrando..." : "Entrar"}
          </button>
        </form>
        <Link
          to="/forgot-password"
          className="mt-4 block text-center text-sm text-blue-600 hover:underline"
        >
          Esqueceu a senha?
        </Link>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create `frontend/src/routes/ForgotPassword.tsx`**

```tsx
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useState } from "react";

const schema = z.object({ email: z.string().email("Email inválido") });
type FormData = z.infer<typeof schema>;

export default function ForgotPassword() {
  const [sent, setSent] = useState(false);
  const { register, handleSubmit, formState: { errors, isSubmitting } } =
    useForm<FormData>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: FormData) => {
    await api.post("/v1/auth/password-reset/request", data).catch(() => {});
    setSent(true);
  };

  if (sent) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <div className="max-w-sm rounded-lg bg-white p-8 shadow text-center">
          <p className="text-gray-700">Se o email existir, você receberá um link em breve.</p>
          <Link to="/login" className="mt-4 block text-sm text-blue-600 hover:underline">
            Voltar ao login
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm rounded-lg bg-white p-8 shadow">
        <h1 className="mb-4 text-xl font-bold text-gray-900">Redefinir senha</h1>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Email</label>
            <input
              type="email"
              {...register("email")}
              className="w-full rounded border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            {errors.email && <p className="mt-1 text-xs text-red-600">{errors.email.message}</p>}
          </div>
          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-lg bg-blue-600 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {isSubmitting ? "Enviando..." : "Enviar link"}
          </button>
        </form>
        <Link to="/login" className="mt-4 block text-center text-sm text-blue-600 hover:underline">
          Voltar
        </Link>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create `frontend/src/routes/ResetPassword.tsx`**

```tsx
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useState } from "react";

const schema = z.object({
  password: z.string().min(6, "Mínimo 6 caracteres"),
  confirm: z.string(),
}).refine((d) => d.password === d.confirm, {
  message: "Senhas não conferem",
  path: ["confirm"],
});
type FormData = z.infer<typeof schema>;

export default function ResetPassword() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const [done, setDone] = useState(false);
  const { register, handleSubmit, setError, formState: { errors, isSubmitting } } =
    useForm<FormData>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: FormData) => {
    try {
      await api.post("/v1/auth/password-reset/confirm", { token, password: data.password });
      setDone(true);
      setTimeout(() => navigate("/login"), 2000);
    } catch {
      setError("root", { message: "Token inválido ou expirado." });
    }
  };

  if (done) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <p className="text-gray-700">Senha redefinida! Redirecionando...</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm rounded-lg bg-white p-8 shadow">
        <h1 className="mb-4 text-xl font-bold text-gray-900">Nova senha</h1>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Nova senha</label>
            <input
              type="password"
              {...register("password")}
              className="w-full rounded border px-3 py-2 text-sm"
            />
            {errors.password && <p className="mt-1 text-xs text-red-600">{errors.password.message}</p>}
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Confirmar senha</label>
            <input
              type="password"
              {...register("confirm")}
              className="w-full rounded border px-3 py-2 text-sm"
            />
            {errors.confirm && <p className="mt-1 text-xs text-red-600">{errors.confirm.message}</p>}
          </div>
          {errors.root && <p className="text-sm text-red-600">{errors.root.message}</p>}
          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-lg bg-blue-600 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {isSubmitting ? "Salvando..." : "Redefinir senha"}
          </button>
        </form>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/Login.tsx frontend/src/routes/ForgotPassword.tsx frontend/src/routes/ResetPassword.tsx
git commit -m "feat(frontend): Login, ForgotPassword, ResetPassword pages with react-hook-form + zod"
```

---

## Task 17: RequireRole + Admin Users page + wire App.tsx

**Files:**
- Create: `frontend/src/components/RequireRole.tsx`
- Create: `frontend/src/routes/admin/Users.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create `frontend/src/components/RequireRole.tsx`**

```tsx
import { Navigate } from "react-router-dom";
import { ReactNode } from "react";
import { useAuth } from "../context/AuthContext";

interface Props {
  roles: string[];
  children: ReactNode;
}

export default function RequireRole({ roles, children }: Props) {
  const { tokens, isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;

  // Decode role from JWT payload (base64 middle segment)
  try {
    const payload = JSON.parse(atob(tokens!.access.split(".")[1]));
    if (!roles.includes(payload.role)) return <Navigate to="/" replace />;
  } catch {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
```

- [ ] **Step 2: Create `frontend/src/routes/admin/Users.tsx`**

```tsx
import { useEffect, useState } from "react";
import { api } from "../../lib/api";

interface UserItem {
  id: string;
  email: string;
  name: string;
  role: string;
  is_active: boolean;
}

export default function AdminUsers() {
  const [users, setUsers] = useState<UserItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<UserItem[]>("/v1/users")
      .then((r) => setUsers(r.data))
      .catch(() => setError("Erro ao carregar usuários."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-8 text-gray-500">Carregando...</div>;
  if (error) return <div className="p-8 text-red-600">{error}</div>;

  return (
    <div className="p-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Usuários</h1>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-gray-500">
            <th className="pb-2 pr-4">Email</th>
            <th className="pb-2 pr-4">Nome</th>
            <th className="pb-2 pr-4">Perfil</th>
            <th className="pb-2">Ativo</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} className="border-b last:border-0">
              <td className="py-3 pr-4 text-gray-900">{u.email}</td>
              <td className="py-3 pr-4 text-gray-700">{u.name}</td>
              <td className="py-3 pr-4">
                <span className="rounded bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800">
                  {u.role}
                </span>
              </td>
              <td className="py-3">
                {u.is_active ? (
                  <span className="text-green-600">✓</span>
                ) : (
                  <span className="text-gray-400">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 3: Replace `frontend/src/App.tsx`**

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Health from "./routes/Health";
import Index from "./routes/Index";
import Login from "./routes/Login";
import ForgotPassword from "./routes/ForgotPassword";
import ResetPassword from "./routes/ResetPassword";
import AdminUsers from "./routes/admin/Users";
import RequireRole from "./components/RequireRole";

const queryClient = new QueryClient();

function ProtectedIndex() {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <Index />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/" element={<ProtectedIndex />} />
            <Route path="/login" element={<Login />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password/:token" element={<ResetPassword />} />
            <Route path="/healthz" element={<Health />} />
            <Route
              path="/admin/users"
              element={
                <RequireRole roles={["admin"]}>
                  <AdminUsers />
                </RequireRole>
              }
            />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
```

- [ ] **Step 4: TypeScript check**

```bash
cd frontend && npm run build
```

Expected: no TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/RequireRole.tsx frontend/src/routes/admin/Users.tsx frontend/src/App.tsx
git commit -m "feat(frontend): RequireRole guard, Admin Users page, wire all routes in App.tsx"
```

---

## Self-Review Checklist

### Spec coverage

| Requirement | Task |
|---|---|
| Users/password_reset_tokens/refresh_tokens/audit_log/notifications_outbox tables | Task 2 + 3 |
| CITEXT extension, UNIQUE(email) staff, UNIQUE(tenant_id, email) customer | Task 2 + 3 |
| register_user, authenticate, issue_tokens, rotate_refresh, revoke_all | Task 5 |
| JWT claims: sub, tenant_id, role, iat, exp; access 15 min, refresh 7 d | Task 5 |
| POST /auth/login, /auth/refresh, /auth/logout | Task 9 |
| POST /auth/password-reset/request (always 202), /confirm | Task 9 |
| GET /me, GET/POST /users (admin), PATCH /users/{id} (role + is_active only) | Task 10 |
| get_db_session: SET LOCAL app.tenant_id | Task 6 |
| get_current_ctx: revocation check vs tokens_revoked_at | Task 6 |
| require_role dependency factory | Task 6 |
| audit_log writes: login, logout, user_create, user_patch | Task 9 + 10 |
| notifications_outbox rows: password_reset, user_invite | Task 5 + 10 |
| MaildirChannel drain worker | Task 11 |
| CLI: tenant create, user create, user reset-password | Task 12 |
| Cross-tenant isolation tests under every role | Task 13 |
| /login, /forgot-password, /reset-password/:token pages | Task 16 |
| AuthContext + localStorage tokens + refresh on reload | Task 14 |
| axios interceptor: 401-queue pattern | Task 15 |
| RequireRole guard + /admin/users admin-only page | Task 17 |
| GET /users filters role != 'customer' | Task 10 (list_users query) |
| Password reset: invalidate previous tokens on new request | Task 5 (request_password_reset) |
| Refresh reuse: full family revocation | Task 5 (rotate_refresh) |

### Type consistency

All method signatures introduced in Task 5 (`AuthService`) are called identically in Tasks 9, 10, 12, 13:
- `svc.register_user(tenant_id=..., email=..., password=..., name=..., role=...)` — keyword-only
- `svc.issue_tokens(user)` → `(str, str)`
- `svc.rotate_refresh(raw_token)` → `(User, str, str)`
- `svc.revoke_all(user)` → `None`
- `svc.write_audit(tenant_id=..., usuario_id=..., acao=..., ...)` — keyword-only

`RequestContext` dataclass defined in Task 6, used in Tasks 9, 10, 13, 17 — same fields: `user_id`, `tenant_id`, `role`, `iat`.

`require_role(*allowed_roles)` returns a callable in Task 6, used as `Depends(require_role("admin"))` in Task 10 — consistent.
