# Admin Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a unified `/admin` dashboard with left sidebar covering Business Rules, Indicators, Audit Log, System Health, SMTP Settings, Pix Settings, and User Management.

**Architecture:** New `system_settings` DB table (global, no tenant) stores SMTP config; `SettingsService` reads it with env fallback. `EmailChannel` refactored to accept individual kwargs so the notification worker reads live settings. Frontend uses nested React Router routes under `/admin` with a shared `EditableField` component.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic (backend); React + Vite + Tailwind + shadcn/ui + TanStack Query (frontend). All backend commands run from `backend/` with `uv run`. All frontend commands from `frontend/` with `npm`.

---

## Phase 1: Backend

### Task 1: Migration — `system_settings` table

**Files:**
- Create: `backend/alembic/versions/009_system_settings.py`

- [ ] **Step 1: Get current head revision**

```bash
cd backend && grep "^revision" alembic/versions/008_phase7_notifications.py
```

Copy the `revision = "..."` value — you'll use it as `down_revision` below.

- [ ] **Step 2: Create migration file**

```python
# backend/alembic/versions/009_system_settings.py
"""system_settings global config table

Revision ID: 009_system_settings
Revises: <paste revision from Step 1>
Create Date: 2026-06-03
"""

from alembic import op
import sqlalchemy as sa

revision = "009_system_settings"
down_revision = "<paste revision from Step 1>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("system_settings")
```

- [ ] **Step 3: Run migration**

```bash
cd backend && uv run alembic upgrade head
```

Expected: `Running upgrade ... -> 009_system_settings, system_settings global config table`

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/009_system_settings.py
git commit -m "feat(db): add system_settings global config table"
```

---

### Task 2: `SystemSetting` model + `SettingsService`

**Files:**
- Modify: `backend/finacialsim_saas/data/models.py`
- Create: `backend/finacialsim_saas/services/settings_service.py`
- Create: `backend/tests/test_settings_service.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_settings_service.py
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from finacialsim_saas.data.database import build_session_factory
from finacialsim_saas.services.settings_service import SettingsService


@pytest.mark.asyncio
async def test_get_all_returns_env_defaults_when_table_empty(engine: AsyncEngine):
    """When system_settings is empty, get_all falls back to env values."""
    factory = build_session_factory(engine)
    async with factory() as session:
        svc = SettingsService(session)
        result = await svc.get_all()
    # All managed keys present
    assert "smtp_host" in result
    assert "smtp_port" in result
    assert "pix_provider" in result
    # Pix is always env
    assert result["pix_provider"][1] == "env"
    # SMTP with empty DB is also env
    assert result["smtp_host"][1] == "env"


@pytest.mark.asyncio
async def test_update_and_get_round_trip(engine: AsyncEngine):
    """update() persists to DB; subsequent get_all returns source=db."""
    factory = build_session_factory(engine)
    async with factory() as session:
        svc = SettingsService(session)
        await svc.update("smtp_host", "mail.example.com", updated_by="admin@test.com")
        await session.commit()

    async with factory() as session:
        svc = SettingsService(session)
        result = await svc.get_all()
    assert result["smtp_host"][0] == "mail.example.com"
    assert result["smtp_host"][1] == "db"


@pytest.mark.asyncio
async def test_update_readonly_key_raises(engine: AsyncEngine):
    factory = build_session_factory(engine)
    async with factory() as session:
        svc = SettingsService(session)
        with pytest.raises(ValueError, match="read-only"):
            await svc.update("pix_provider", "external", updated_by="admin@test.com")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_settings_service.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `SettingsService` doesn't exist yet.

- [ ] **Step 3: Add `SystemSetting` model to `models.py`**

Open `backend/finacialsim_saas/data/models.py`. Add after the last import block at the top:

```python
# (add to existing imports near top of file)
```

Then add at the end of the file:

```python
class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(sa.String, primary_key=True)
    value: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )
    updated_by: Mapped[str | None] = mapped_column(sa.String, nullable=True)
```

- [ ] **Step 4: Create `SettingsService`**

```python
# backend/finacialsim_saas/services/settings_service.py
from __future__ import annotations

from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.data.models import SystemSetting
from finacialsim_saas.settings import get_settings

WRITABLE_KEYS: frozenset[str] = frozenset({
    "smtp_host", "smtp_port", "smtp_user", "smtp_password",
    "smtp_tls", "smtp_from", "email_provider",
})
READ_ONLY_KEYS: frozenset[str] = frozenset({"pix_provider", "pix_webhook_secret"})
ALL_KEYS: frozenset[str] = WRITABLE_KEYS | READ_ONLY_KEYS


def _env_default(key: str) -> str:
    s = get_settings()
    mapping: dict[str, str] = {
        "smtp_host": s.smtp_host,
        "smtp_port": str(s.smtp_port),
        "smtp_user": s.smtp_user,
        "smtp_password": s.smtp_password,
        "smtp_tls": str(s.smtp_tls).lower(),
        "smtp_from": s.smtp_from,
        "email_provider": s.email_provider,
        "pix_provider": s.pix_provider,
        "pix_webhook_secret": s.pix_webhook_secret,
    }
    return mapping[key]


class SettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_all(self) -> dict[str, tuple[str, Literal["db", "env"]]]:
        """Returns {key: (value, source)} for all managed keys."""
        db_rows = (await self._s.scalars(select(SystemSetting))).all()
        db_map = {row.key: row.value for row in db_rows}
        result: dict[str, tuple[str, Literal["db", "env"]]] = {}
        for key in ALL_KEYS:
            if key in READ_ONLY_KEYS:
                result[key] = (_env_default(key), "env")
            elif key in db_map:
                result[key] = (db_map[key], "db")
            else:
                result[key] = (_env_default(key), "env")
        return result

    async def update(self, key: str, value: str, updated_by: str) -> None:
        """Upsert a writable key. Caller must commit."""
        if key in READ_ONLY_KEYS:
            raise ValueError(f"Key {key!r} is read-only")
        if key not in WRITABLE_KEYS:
            raise ValueError(f"Unknown settings key: {key!r}")
        row = await self._s.get(SystemSetting, key)
        if row is None:
            self._s.add(SystemSetting(key=key, value=value, updated_by=updated_by))
        else:
            row.value = value
            row.updated_by = updated_by
```

- [ ] **Step 5: Run tests**

```bash
cd backend && uv run pytest tests/test_settings_service.py -v
```

Expected: All 3 pass.

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/data/models.py \
        backend/finacialsim_saas/services/settings_service.py \
        backend/tests/test_settings_service.py
git commit -m "feat(settings): SystemSetting model + SettingsService with env fallback"
```

---

### Task 3: Admin Settings API + tests

**Files:**
- Create: `backend/finacialsim_saas/schemas/admin_settings.py`
- Create: `backend/finacialsim_saas/api/admin_settings.py`
- Modify: `backend/finacialsim_saas/main.py`
- Create: `backend/tests/test_admin_settings.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_admin_settings.py
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.database import build_session_factory
from finacialsim_saas.data.models import Role, Tenant
from finacialsim_saas.settings import get_settings


async def _seed_user(engine: AsyncEngine, role: Role) -> str:
    factory = build_session_factory(engine)
    async with factory() as session:
        t = Tenant(
            name=f"AdminSettingsTest-{uuid.uuid4().hex[:6]}",
            slug=f"ast-{uuid.uuid4().hex[:6]}",
        )
        session.add(t)
        await session.flush()
        svc = AuthService(session, get_settings())
        user = await svc.register_user(
            tenant_id=t.id,
            email=f"u-{uuid.uuid4().hex[:6]}@test.com",
            password="pw",
            name="Test",
            role=role,
        )
        await session.flush()
        access_token, _ = await svc.issue_tokens(user)
        await session.commit()
    return access_token


@pytest.mark.asyncio
async def test_get_settings_returns_env_defaults(client: AsyncClient, engine: AsyncEngine):
    token = await _seed_user(engine, Role.admin)
    resp = await client.get(
        "/api/v1/admin/settings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "smtp_host" in data
    assert data["smtp_host"]["source"] == "env"
    assert "pix_provider" in data
    assert data["pix_provider"]["source"] == "env"


@pytest.mark.asyncio
async def test_put_get_round_trip(client: AsyncClient, engine: AsyncEngine):
    token = await _seed_user(engine, Role.admin)
    resp = await client.put(
        "/api/v1/admin/settings/smtp_host",
        json={"value": "mail.example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204

    resp2 = await client.get(
        "/api/v1/admin/settings",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp2.json()
    assert data["smtp_host"]["value"] == "mail.example.com"
    assert data["smtp_host"]["source"] == "db"


@pytest.mark.asyncio
async def test_put_non_admin_returns_403(client: AsyncClient, engine: AsyncEngine):
    token = await _seed_user(engine, Role.manager)
    resp = await client.put(
        "/api/v1/admin/settings/smtp_host",
        json={"value": "mail.example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_put_readonly_key_returns_422(client: AsyncClient, engine: AsyncEngine):
    token = await _seed_user(engine, Role.admin)
    resp = await client.put(
        "/api/v1/admin/settings/pix_provider",
        json={"value": "external"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_admin_settings.py -v
```

Expected: 404 errors — routes don't exist yet.

- [ ] **Step 3: Create schema**

```python
# backend/finacialsim_saas/schemas/admin_settings.py
from typing import Literal
from pydantic import BaseModel


class SettingItem(BaseModel):
    value: str
    source: Literal["db", "env"]


class SettingUpdateIn(BaseModel):
    value: str
```

- [ ] **Step 4: Create API router**

```python
# backend/finacialsim_saas/api/admin_settings.py
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_db_session, require_role
from finacialsim_saas.schemas.admin_settings import SettingItem, SettingUpdateIn
from finacialsim_saas.services.settings_service import (
    READ_ONLY_KEYS,
    WRITABLE_KEYS,
    SettingsService,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin-settings"])


@router.get("/settings", response_model=dict[str, SettingItem])
async def get_admin_settings(
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, SettingItem]:
    all_settings = await SettingsService(session).get_all()
    return {
        key: SettingItem(value=value, source=source)
        for key, (value, source) in all_settings.items()
    }


@router.put("/settings/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def update_admin_setting(
    key: str,
    body: SettingUpdateIn,
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    if key in READ_ONLY_KEYS:
        raise HTTPException(status_code=422, detail=f"Key '{key}' is read-only (env-only)")
    if key not in WRITABLE_KEYS:
        raise HTTPException(status_code=422, detail=f"Unknown settings key: '{key}'")
    svc = SettingsService(session)
    await svc.update(key, body.value, updated_by=str(ctx.user_id))
    await session.commit()
```

- [ ] **Step 5: Register router in `main.py`**

Add after the existing router imports (around line 94):

```python
from finacialsim_saas.api.admin_settings import router as admin_settings_router  # noqa: E402
```

Add after `app.include_router(pix_admin_router)`:

```python
app.include_router(admin_settings_router)
```

- [ ] **Step 6: Run tests**

```bash
cd backend && uv run pytest tests/test_admin_settings.py -v
```

Expected: All 4 pass.

- [ ] **Step 7: Commit**

```bash
git add backend/finacialsim_saas/schemas/admin_settings.py \
        backend/finacialsim_saas/api/admin_settings.py \
        backend/finacialsim_saas/main.py \
        backend/tests/test_admin_settings.py
git commit -m "feat(api): admin settings GET/PUT endpoints with env fallback"
```

---

### Task 4: `EmailChannel` refactor + wire notification worker

**Files:**
- Modify: `backend/finacialsim_saas/notifications/channel.py`
- Modify: `backend/finacialsim_saas/workers/notifications.py`

- [ ] **Step 1: Refactor `EmailChannel` to accept individual kwargs**

Replace the entire `channel.py`:

```python
# backend/finacialsim_saas/notifications/channel.py
from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib


class EmailChannel:
    def __init__(
        self,
        *,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        smtp_tls: bool,
        smtp_from: str,
    ) -> None:
        self._host = smtp_host
        self._port = smtp_port
        self._user = smtp_user or None
        self._password = smtp_password or None
        self._tls = smtp_tls
        self._from = smtp_from

    async def send(
        self, *, to: str, subject: str, body_html: str, body_txt: str
    ) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._from
        msg["To"] = to
        msg.attach(MIMEText(body_txt, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=self._host,
            port=self._port,
            username=self._user,
            password=self._password,
            use_tls=self._tls,
        )
```

- [ ] **Step 2: Wire notification worker to `SettingsService`**

In `backend/finacialsim_saas/workers/notifications.py`, replace lines 1–31 (through `channel = EmailChannel(settings)`) with:

```python
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import or_, and_, select

from finacialsim_saas.data.models import (
    NotificationsOutbox, ParcelaPayment, ParcelaPaymentStatus,
    Proposal, Role, Simulation, User,
)
from finacialsim_saas.notifications.channel import EmailChannel
from finacialsim_saas.notifications.service import NotificationService, render_template
from finacialsim_saas.services.settings_service import SettingsService

UTC = timezone.utc
_LOCK_TTL = 25
_STUCK_THRESHOLD_SECS = 60


async def drain_notifications_outbox(ctx: dict) -> None:
    """ARQ job: runs every 30 s. Drains pending outbox rows via EmailChannel."""
    redis = ctx["redis"]
    acquired = await redis.set("lock:drain_notifications_outbox", "1", nx=True, ex=_LOCK_TTL)
    if not acquired:
        logger.debug("drain_notifications_outbox: already running, skipping")
        return

    session_factory = ctx["session_factory"]

    # Read SMTP config from DB (falls back to env for any missing key)
    async with session_factory() as cfg_session:
        smtp = await SettingsService(cfg_session).get_all()

    channel = EmailChannel(
        smtp_host=smtp["smtp_host"][0],
        smtp_port=int(smtp["smtp_port"][0]),
        smtp_user=smtp["smtp_user"][0],
        smtp_password=smtp["smtp_password"][0],
        smtp_tls=smtp["smtp_tls"][0].lower() == "true",
        smtp_from=smtp["smtp_from"][0],
    )
```

Leave the rest of the function body unchanged.

- [ ] **Step 3: Run existing drain tests**

```bash
cd backend && uv run pytest tests/test_drain_outbox.py -v
```

Expected: All pass. The tests mock `EmailChannel.send` directly so the constructor change is transparent.

- [ ] **Step 4: Commit**

```bash
git add backend/finacialsim_saas/notifications/channel.py \
        backend/finacialsim_saas/workers/notifications.py
git commit -m "feat(notifications): read SMTP config from DB via SettingsService"
```

---

### Task 5: `AuditLogItem` enrichment with `usuario_email`

**Files:**
- Modify: `backend/finacialsim_saas/schemas/audit_log.py`
- Modify: `backend/finacialsim_saas/services/audit_service.py`

- [ ] **Step 1: Write failing test**

Add to `backend/tests/test_audit_log_endpoints.py` (or a new file `test_audit_email_enrichment.py`):

```python
# backend/tests/test_audit_email_enrichment.py
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.database import build_session_factory
from finacialsim_saas.data.models import AuditLog, Role, Tenant
from finacialsim_saas.settings import get_settings


@pytest.mark.asyncio
async def test_audit_log_includes_usuario_email(client: AsyncClient, engine: AsyncEngine):
    factory = build_session_factory(engine)
    async with factory() as session:
        t = Tenant(name=f"AuditEmail-{uuid.uuid4().hex[:6]}", slug=f"ae-{uuid.uuid4().hex[:6]}")
        session.add(t)
        await session.flush()
        svc = AuthService(session, get_settings())
        user = await svc.register_user(
            tenant_id=t.id,
            email=f"audit-{uuid.uuid4().hex[:6]}@test.com",
            password="pw",
            name="AuditUser",
            role=Role.admin,
        )
        await session.flush()
        # Create an audit log entry attributed to this user
        session.add(AuditLog(
            tenant_id=t.id,
            usuario_id=user.id,
            acao="update",
            entidade="test",
            entidade_id=uuid.uuid4(),
            diff_json={"x": 1},
        ))
        access_token, _ = await svc.issue_tokens(user)
        await session.commit()
        user_email = user.email

    resp = await client.get(
        "/api/v1/audit-log",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1
    assert items[0]["usuario_email"] == user_email
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_audit_email_enrichment.py -v
```

Expected: FAIL — `usuario_email` key missing from response.

- [ ] **Step 3: Add `usuario_email` to `AuditLogItem` schema**

In `backend/finacialsim_saas/schemas/audit_log.py`, add the field:

```python
class AuditLogItem(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    timestamp: datetime
    usuario_id: uuid.UUID | None
    usuario_email: str | None = None   # ← add this line
    acao: str
    entidade: str | None
    entidade_id: uuid.UUID | None
    diff_json: dict | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Update `AuditService.list()` to LEFT JOIN users**

In `backend/finacialsim_saas/services/audit_service.py`, update the imports and `list` method:

```python
# Change import line from:
from finacialsim_saas.data.models import AuditLog, Role
# To:
from finacialsim_saas.data.models import AuditLog, Role, User
```

Replace the `list` method body (from `q = select(AuditLog)...` through `return items, next_cursor`):

```python
    async def list(
        self,
        tenant_id: uuid.UUID,
        caller_role: Role,
        caller_user_id: uuid.UUID,
        usuario_id: uuid.UUID | None = None,
        entidade: str | None = None,
        acao: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        cursor: str | None = None,
    ) -> tuple[list, str | None]:
        q = (
            select(AuditLog, User.email.label("usuario_email"))
            .outerjoin(User, AuditLog.usuario_id == User.id)
            .where(AuditLog.tenant_id == tenant_id)
        )

        if caller_role == Role.user:
            q = q.where(AuditLog.usuario_id == caller_user_id)
        elif usuario_id is not None:
            q = q.where(AuditLog.usuario_id == usuario_id)

        if entidade:
            q = q.where(AuditLog.entidade == entidade)
        if acao:
            q = q.where(AuditLog.acao == acao)
        if date_from:
            q = q.where(AuditLog.timestamp >= datetime.combine(date_from, time.min, UTC))
        if date_to:
            q = q.where(AuditLog.timestamp <= datetime.combine(date_to, time.max, UTC))
        if cursor:
            ts, uid = _decode_cursor(cursor)
            q = q.where(
                (AuditLog.timestamp < ts)
                | ((AuditLog.timestamp == ts) & (AuditLog.id < uid))
            )

        q = q.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).limit(PAGE_SIZE + 1)
        result = (await self._s.execute(q)).all()

        has_more = len(result) > PAGE_SIZE
        rows = result[:PAGE_SIZE]
        items = []
        for row in rows:
            audit = row[0]
            audit.usuario_email = row[1]  # dynamic attr; Pydantic from_attributes picks it up
            items.append(audit)
        next_cursor = (
            _encode_cursor(items[-1].timestamp, items[-1].id) if has_more else None
        )
        return items, next_cursor
```

- [ ] **Step 5: Run all audit tests**

```bash
cd backend && uv run pytest tests/test_audit_email_enrichment.py tests/test_audit_log_endpoints.py tests/test_audit_service.py -v
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/schemas/audit_log.py \
        backend/finacialsim_saas/services/audit_service.py \
        backend/tests/test_audit_email_enrichment.py
git commit -m "feat(audit): enrich AuditLogItem with usuario_email via LEFT JOIN"
```

---

### Task 6: Admin health endpoint

**Files:**
- Create: `backend/finacialsim_saas/api/admin_health.py`
- Modify: `backend/finacialsim_saas/main.py`
- Create: `backend/tests/test_admin_health.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_admin_health.py
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.database import build_session_factory
from finacialsim_saas.data.models import Role, Tenant
from finacialsim_saas.settings import get_settings


async def _seed_admin(engine: AsyncEngine) -> str:
    factory = build_session_factory(engine)
    async with factory() as session:
        t = Tenant(name=f"HealthTest-{uuid.uuid4().hex[:6]}", slug=f"ht-{uuid.uuid4().hex[:6]}")
        session.add(t)
        await session.flush()
        svc = AuthService(session, get_settings())
        user = await svc.register_user(
            tenant_id=t.id, email=f"h-{uuid.uuid4().hex[:6]}@test.com",
            password="pw", name="Health", role=Role.admin,
        )
        await session.flush()
        token, _ = await svc.issue_tokens(user)
        await session.commit()
    return token


@pytest.mark.asyncio
async def test_admin_health_returns_expected_shape(client: AsyncClient, engine: AsyncEngine):
    token = await _seed_admin(engine)
    resp = await client.get(
        "/api/v1/admin/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "postgres" in data
    assert "redis" in data
    assert "providers" in data
    assert isinstance(data["providers"], dict)


@pytest.mark.asyncio
async def test_admin_health_non_admin_returns_403(client: AsyncClient, engine: AsyncEngine):
    factory = build_session_factory(engine)
    async with factory() as session:
        t = Tenant(name=f"HealthTest2-{uuid.uuid4().hex[:6]}", slug=f"ht2-{uuid.uuid4().hex[:6]}")
        session.add(t)
        await session.flush()
        svc = AuthService(session, get_settings())
        user = await svc.register_user(
            tenant_id=t.id, email=f"m-{uuid.uuid4().hex[:6]}@test.com",
            password="pw", name="Mgr", role=Role.manager,
        )
        await session.flush()
        token, _ = await svc.issue_tokens(user)
        await session.commit()

    resp = await client.get(
        "/api/v1/admin/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_admin_health.py -v
```

Expected: 404 — route doesn't exist.

- [ ] **Step 3: Create `admin_health.py`**

```python
# backend/finacialsim_saas/api/admin_health.py
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_db_session, require_role
from finacialsim_saas.data.models import ProviderHealth

router = APIRouter(prefix="/api/v1/admin", tags=["admin-health"])


@router.get("/health")
async def admin_health(
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
) -> dict[str, Any]:
    from finacialsim_saas.main import app_state  # local import avoids circular dep

    # Postgres
    postgres_status = "ok"
    try:
        async with app_state["engine"].connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        postgres_status = str(exc)[:100]

    # Redis
    redis_status = "ok"
    try:
        await request.app.state.redis.ping()
    except Exception as exc:
        redis_status = str(exc)[:100]

    # Provider health: latest row per provider_name (dedup in Python)
    all_rows = (
        await session.scalars(
            select(ProviderHealth).order_by(ProviderHealth.checked_at.desc())
        )
    ).all()
    providers: dict[str, dict] = {}
    for row in all_rows:
        if row.provider_name not in providers:
            providers[row.provider_name] = {
                "success": row.success,
                "latency_ms": row.latency_ms,
                "error": row.error,
                "checked_at": row.checked_at.isoformat() if row.checked_at else None,
            }

    return {"postgres": postgres_status, "redis": redis_status, "providers": providers}
```

- [ ] **Step 4: Register router in `main.py`**

Add import after `admin_settings_router`:

```python
from finacialsim_saas.api.admin_health import router as admin_health_router  # noqa: E402
```

Add include after `app.include_router(admin_settings_router)`:

```python
app.include_router(admin_health_router)
```

- [ ] **Step 5: Run tests**

```bash
cd backend && uv run pytest tests/test_admin_health.py -v
```

Expected: Both pass.

- [ ] **Step 6: Run full backend test suite**

```bash
cd backend && uv run pytest tests/ -v --tb=short
```

Expected: All existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add backend/finacialsim_saas/api/admin_health.py \
        backend/finacialsim_saas/main.py \
        backend/tests/test_admin_health.py
git commit -m "feat(api): admin health endpoint with Postgres, Redis, provider status"
```

---

## Phase 2: Frontend

### Task 7: API lib helpers

**Files:**
- Create: `frontend/src/lib/admin-settings.ts`
- Create: `frontend/src/lib/audit-log.ts`

- [ ] **Step 1: Create `admin-settings.ts`**

```typescript
// frontend/src/lib/admin-settings.ts
import { api } from "./api";

export interface SettingItem {
  value: string;
  source: "db" | "env";
}

export async function getAdminSettings(): Promise<Record<string, SettingItem>> {
  const { data } = await api.get<Record<string, SettingItem>>("/v1/admin/settings");
  return data;
}

export async function updateAdminSetting(key: string, value: string): Promise<void> {
  await api.put(`/v1/admin/settings/${key}`, { value });
}
```

- [ ] **Step 2: Create `audit-log.ts`**

```typescript
// frontend/src/lib/audit-log.ts
import { api } from "./api";

export interface AuditLogItem {
  id: string;
  timestamp: string;
  usuario_id: string | null;
  usuario_email: string | null;
  acao: string;
  entidade: string | null;
  entidade_id: string | null;
  diff_json: Record<string, unknown> | null;
}

export interface AuditLogPage {
  items: AuditLogItem[];
  next_cursor: string | null;
}

export interface AuditLogParams {
  acao?: string;
  cursor?: string;
}

export async function listAuditLog(params: AuditLogParams = {}): Promise<AuditLogPage> {
  const { data } = await api.get<AuditLogPage>("/v1/audit-log", { params });
  return data;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/admin-settings.ts frontend/src/lib/audit-log.ts
git commit -m "feat(frontend): admin-settings and audit-log API lib helpers"
```

---

### Task 8: `EditableField` shared component

**Files:**
- Create: `frontend/src/components/EditableField.tsx`

- [ ] **Step 1: Create component**

```tsx
// frontend/src/components/EditableField.tsx
import { useState } from "react";
import { Check, Pencil, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";

export interface SelectOption {
  label: string;
  value: string;
}

interface EditableFieldProps {
  label: string;
  value: string;
  type?: "text" | "number" | "password" | "select" | "toggle";
  onSave: (value: string, motivo?: string) => Promise<void>;
  motivo?: boolean;
  options?: SelectOption[];
}

export default function EditableField({
  label,
  value,
  type = "text",
  onSave,
  motivo = false,
  options = [],
}: EditableFieldProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [motivoText, setMotivoText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (type === "toggle") {
    return (
      <div className="flex items-center justify-between py-3 border-b border-[#1E293B] last:border-0">
        <span className="text-sm text-[#94A3B8]">{label}</span>
        <Switch
          checked={value === "true"}
          disabled={saving}
          onCheckedChange={async (checked) => {
            setSaving(true);
            try {
              await onSave(String(checked));
            } catch (e: unknown) {
              const msg = e instanceof Error ? e.message : "Erro ao salvar";
              setError(msg);
            } finally {
              setSaving(false);
            }
          }}
        />
      </div>
    );
  }

  const displayValue = type === "password" ? (value ? "••••••••" : "") : value;

  if (!editing) {
    return (
      <div className="flex items-center justify-between py-3 border-b border-[#1E293B] last:border-0 group">
        <div>
          <p className="text-xs text-[#64748B]">{label}</p>
          <p className="text-sm text-[#F8FAFC] mt-0.5">{displayValue || "—"}</p>
        </div>
        <button
          onClick={() => {
            setEditing(true);
            setDraft(value);
            setError(null);
            setMotivoText("");
          }}
          className="opacity-0 group-hover:opacity-100 text-[#475569] hover:text-[#94A3B8] transition-opacity cursor-pointer"
        >
          <Pencil size={14} />
        </button>
      </div>
    );
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await onSave(draft, motivo ? motivoText || undefined : undefined);
      setEditing(false);
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? (e instanceof Error ? e.message : "Erro ao salvar"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="py-3 border-b border-[#1E293B] last:border-0 bg-[#22C55E08] rounded px-2 -mx-2">
      <p className="text-xs text-[#64748B] mb-1.5">{label}</p>
      {type === "select" ? (
        <Select value={draft} onValueChange={setDraft}>
          <SelectTrigger className="h-8 text-sm bg-[#0F172A] border-[#22C55E]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {options.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : (
        <Input
          type={type === "password" ? "password" : type}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="h-8 text-sm bg-[#0F172A] border-[#22C55E]"
          autoFocus
          onKeyDown={(e) => e.key === "Enter" && handleSave()}
        />
      )}
      {motivo && (
        <Input
          placeholder="Motivo (opcional)"
          value={motivoText}
          onChange={(e) => setMotivoText(e.target.value)}
          className="h-7 text-xs bg-[#0F172A] border-[#334155] mt-1.5"
        />
      )}
      {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
      <div className="flex gap-2 mt-2">
        <Button
          size="sm"
          className="h-7 text-xs bg-[#22C55E] text-[#020617] hover:bg-[#16a34a]"
          onClick={handleSave}
          disabled={saving}
        >
          <Check size={12} className="mr-1" />
          Salvar
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="h-7 text-xs border-[#334155] text-[#64748B]"
          onClick={() => setEditing(false)}
          disabled={saving}
        >
          <X size={12} className="mr-1" />
          Cancelar
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/EditableField.tsx
git commit -m "feat(frontend): EditableField shared inline-edit component"
```

---

### Task 9: `AdminLayout` + routing wiring

**Files:**
- Create: `frontend/src/routes/admin/AdminLayout.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/routes/Index.tsx`

- [ ] **Step 1: Create `AdminLayout.tsx`**

```tsx
// frontend/src/routes/admin/AdminLayout.tsx
import { NavLink, Outlet } from "react-router-dom";
import {
  Activity,
  ArrowLeft,
  ClipboardList,
  CreditCard,
  Mail,
  Settings,
  TrendingUp,
  Users,
} from "lucide-react";

const NAV_ITEMS = [
  { label: "Regras de Negócio", href: "/admin/regras", icon: Settings },
  { label: "Indicadores", href: "/admin/indicadores", icon: TrendingUp },
  { label: "Auditoria", href: "/admin/auditoria", icon: ClipboardList },
  { label: "Saúde do Sistema", href: "/admin/saude", icon: Activity },
  { label: "SMTP", href: "/admin/smtp", icon: Mail },
  { label: "Pix", href: "/admin/pix", icon: CreditCard },
  { label: "Usuários", href: "/admin/users", icon: Users },
];

export default function AdminLayout() {
  return (
    <div className="min-h-screen bg-[#020617] text-[#F8FAFC] flex font-[IBM_Plex_Sans,sans-serif]">
      <aside className="w-56 bg-[#0F172A] border-r border-[#1E293B] flex flex-col flex-shrink-0">
        <div className="p-4 border-b border-[#1E293B]">
          <span className="text-[#22C55E] font-semibold text-sm">FinacialSim</span>
          <p className="text-[#475569] text-xs mt-0.5">Painel Admin</p>
        </div>
        <nav className="flex-1 py-2">
          {NAV_ITEMS.map(({ label, href, icon: Icon }) => (
            <NavLink
              key={href}
              to={href}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-4 py-2.5 text-sm transition-colors ${
                  isActive
                    ? "text-[#22C55E] bg-[#22C55E10] border-l-2 border-[#22C55E]"
                    : "text-[#64748B] hover:text-[#94A3B8] hover:bg-[#1E293B]"
                }`
              }
            >
              <Icon size={15} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="p-4 border-t border-[#1E293B]">
          <NavLink
            to="/"
            className="flex items-center gap-2 text-xs text-[#475569] hover:text-[#94A3B8] transition-colors"
          >
            <ArrowLeft size={13} />
            Voltar ao Dashboard
          </NavLink>
        </div>
      </aside>
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Update `App.tsx`**

Replace the entire file with the updated version that adds the nested admin routes and removes the old flat `/admin/users` route:

```tsx
// frontend/src/App.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Health from "./routes/Health";
import Index from "./routes/Index";
import Login from "./routes/Login";
import ForgotPassword from "./routes/ForgotPassword";
import ResetPassword from "./routes/ResetPassword";
import AdminLayout from "./routes/admin/AdminLayout";
import AdminUsers from "./routes/admin/Users";
import BusinessRules from "./routes/admin/BusinessRules";
import Indicators from "./routes/admin/Indicators";
import AuditLog from "./routes/admin/AuditLog";
import SystemHealth from "./routes/admin/SystemHealth";
import SmtpSettings from "./routes/admin/SmtpSettings";
import PixSettings from "./routes/admin/PixSettings";
import RequireRole from "./components/RequireRole";
import Simulacao from "./routes/Simulacao";
import SimulacaoEdit from "./routes/SimulacaoEdit";
import ClientesPage from "./routes/clientes/ClientesPage";
import VeiculosPage from "./routes/veiculos/VeiculosPage";
import PropostasPage from "./routes/propostas/PropostasPage";

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
              path="/admin"
              element={
                <RequireRole roles={["admin"]}>
                  <AdminLayout />
                </RequireRole>
              }
            >
              <Route index element={<Navigate to="regras" replace />} />
              <Route path="regras" element={<BusinessRules />} />
              <Route path="indicadores" element={<Indicators />} />
              <Route path="auditoria" element={<AuditLog />} />
              <Route path="saude" element={<SystemHealth />} />
              <Route path="smtp" element={<SmtpSettings />} />
              <Route path="pix" element={<PixSettings />} />
              <Route path="users" element={<AdminUsers />} />
            </Route>
            <Route path="/simulacao" element={<Simulacao />} />
            <Route path="/simulacao/:id" element={<SimulacaoEdit />} />
            <Route path="/clientes" element={<ClientesPage />} />
            <Route path="/veiculos" element={<VeiculosPage />} />
            <Route
              path="/propostas"
              element={
                <RequireRole roles={["admin", "manager", "user"]}>
                  <PropostasPage />
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

- [ ] **Step 3: Update `Index.tsx` nav card**

In `frontend/src/routes/Index.tsx`, find the "Usuários" item in `NAV_ITEMS` and replace it:

```tsx
// Replace:
{
  label: "Usuários",
  description: "Gerenciar usuários e permissões",
  href: "/admin/users",
  icon: ShieldCheck,
  roles: ["admin"],
},
// With:
{
  label: "Administração",
  description: "Regras, indicadores, auditoria, SMTP e usuários",
  href: "/admin",
  icon: ShieldCheck,
  roles: ["admin"],
},
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/admin/AdminLayout.tsx \
        frontend/src/App.tsx \
        frontend/src/routes/Index.tsx
git commit -m "feat(frontend): AdminLayout sidebar + nested /admin routing"
```

---

### Task 10: `BusinessRules.tsx`

**Files:**
- Create: `frontend/src/routes/admin/BusinessRules.tsx`

- [ ] **Step 1: Create component**

```tsx
// frontend/src/routes/admin/BusinessRules.tsx
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import EditableField from "../../components/EditableField";

interface BusinessRulesData {
  entrada_minima_pct: string;
  prazo_minimo_meses: number;
  prazo_maximo_meses: number;
  valor_minimo_financiado: string;
  taxa_minima_mes: string;
  taxa_maxima_mes: string;
  taxa_por_prazo_curva: Array<{ ate_meses: number; taxa_mensal: string }>;
  iof_fixo_pct: string;
  iof_diario_pct: string;
  iof_diario_max_dias: number;
  incluir_iof_default: boolean;
  dias_max_carencia: number;
  rateio_ipva_meses_default: number;
  rateio_emplacamento_meses_default: number;
}

async function fetchRules(): Promise<BusinessRulesData> {
  const { data } = await api.get<BusinessRulesData>("/v1/business-rules");
  return data;
}

async function updateRule(key: string, valor: unknown, motivo?: string): Promise<void> {
  await api.put(`/v1/business-rules/${key}`, { valor, motivo: motivo ?? null });
}

export default function BusinessRules() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["business-rules"], queryFn: fetchRules });

  if (isLoading || !data) {
    return <div className="p-8 text-[#64748B]">Carregando...</div>;
  }

  function makeSave(key: string) {
    return async (value: string, motivo?: string) => {
      await updateRule(key, value, motivo);
      await qc.invalidateQueries({ queryKey: ["business-rules"] });
    };
  }

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="text-xl font-semibold mb-6">Regras de Negócio</h1>

      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[#94A3B8] uppercase tracking-wider mb-3">Financiamento</h2>
        <div className="bg-[#0F172A] border border-[#1E293B] rounded-lg px-4">
          <EditableField label="Entrada mínima (%)" value={String(data.entrada_minima_pct)} type="number" onSave={makeSave("entrada_minima_pct")} motivo />
          <EditableField label="Prazo mínimo (meses)" value={String(data.prazo_minimo_meses)} type="number" onSave={makeSave("prazo_minimo_meses")} motivo />
          <EditableField label="Prazo máximo (meses)" value={String(data.prazo_maximo_meses)} type="number" onSave={makeSave("prazo_maximo_meses")} motivo />
          <EditableField label="Valor mínimo financiado (R$)" value={String(data.valor_minimo_financiado)} type="number" onSave={makeSave("valor_minimo_financiado")} motivo />
        </div>
      </section>

      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[#94A3B8] uppercase tracking-wider mb-3">Taxas</h2>
        <div className="bg-[#0F172A] border border-[#1E293B] rounded-lg px-4">
          <EditableField label="Taxa mínima (% a.m.)" value={String(data.taxa_minima_mes)} type="number" onSave={makeSave("taxa_minima_mes")} motivo />
          <EditableField label="Taxa máxima (% a.m.)" value={String(data.taxa_maxima_mes)} type="number" onSave={makeSave("taxa_maxima_mes")} motivo />
          <div className="py-3 border-b border-[#1E293B] last:border-0">
            <p className="text-xs text-[#64748B] mb-2">Curva de taxas por prazo <span className="text-[#475569]">(somente leitura)</span></p>
            <table className="text-xs w-full">
              <thead>
                <tr>
                  <th className="text-left text-[#475569] pb-1 font-normal">Até (meses)</th>
                  <th className="text-left text-[#475569] pb-1 font-normal">Taxa mensal (%)</th>
                </tr>
              </thead>
              <tbody>
                {data.taxa_por_prazo_curva.map((p) => (
                  <tr key={p.ate_meses}>
                    <td className="text-[#94A3B8] py-0.5">{p.ate_meses}</td>
                    <td className="text-[#94A3B8] py-0.5">{p.taxa_mensal}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[#94A3B8] uppercase tracking-wider mb-3">IOF</h2>
        <div className="bg-[#0F172A] border border-[#1E293B] rounded-lg px-4">
          <EditableField label="IOF fixo (%)" value={String(data.iof_fixo_pct)} type="number" onSave={makeSave("iof_fixo_pct")} motivo />
          <EditableField label="IOF diário (%)" value={String(data.iof_diario_pct)} type="number" onSave={makeSave("iof_diario_pct")} motivo />
          <EditableField label="IOF diário máx. dias" value={String(data.iof_diario_max_dias)} type="number" onSave={makeSave("iof_diario_max_dias")} motivo />
          <EditableField label="Incluir IOF por padrão" value={String(data.incluir_iof_default)} type="toggle" onSave={makeSave("incluir_iof_default")} />
        </div>
      </section>

      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[#94A3B8] uppercase tracking-wider mb-3">Padrões</h2>
        <div className="bg-[#0F172A] border border-[#1E293B] rounded-lg px-4">
          <EditableField label="Carência máxima (dias)" value={String(data.dias_max_carencia)} type="number" onSave={makeSave("dias_max_carencia")} motivo />
          <EditableField label="Rateio IPVA (meses)" value={String(data.rateio_ipva_meses_default)} type="number" onSave={makeSave("rateio_ipva_meses_default")} motivo />
          <EditableField label="Rateio emplacamento (meses)" value={String(data.rateio_emplacamento_meses_default)} type="number" onSave={makeSave("rateio_emplacamento_meses_default")} motivo />
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/routes/admin/BusinessRules.tsx
git commit -m "feat(frontend): BusinessRules admin panel with inline edit"
```

---

### Task 11: `Indicators.tsx`, `SystemHealth.tsx`, `PixSettings.tsx`

**Files:**
- Create: `frontend/src/routes/admin/Indicators.tsx`
- Create: `frontend/src/routes/admin/SystemHealth.tsx`
- Create: `frontend/src/routes/admin/PixSettings.tsx`

- [ ] **Step 1: Create `Indicators.tsx`**

```tsx
// frontend/src/routes/admin/Indicators.tsx
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";
import { useMutation } from "@tanstack/react-query";

interface IndicatorOut {
  codigo: string;
  valor: string;
  unidade: string;
  data: string;
}

const LABELS: Record<string, string> = { SELIC: "SELIC", CDI: "CDI", IPCA: "IPCA" };

export default function Indicators() {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["indicators-admin"],
    queryFn: async () => {
      const { data } = await api.get<IndicatorOut[]>("/v1/indicators");
      return data;
    },
  });

  const { mutate: doRefresh, isPending } = useMutation({
    mutationFn: async () => { await api.post("/v1/indicators/refresh"); },
    onSuccess: () => { setTimeout(() => refetch(), 2000); },
  });

  if (isLoading) return <div className="p-8 text-[#64748B]">Carregando...</div>;

  return (
    <div className="p-8 max-w-2xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Indicadores BACEN</h1>
        <Button
          size="sm"
          onClick={() => doRefresh()}
          disabled={isPending}
          className="bg-[#22C55E] text-[#020617] hover:bg-[#16a34a]"
        >
          <RefreshCw size={14} className={`mr-1.5 ${isPending ? "animate-spin" : ""}`} />
          Atualizar agora
        </Button>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {(data ?? []).map((ind) => (
          <div key={ind.codigo} className="bg-[#0F172A] border border-[#1E293B] rounded-lg p-5">
            <p className="text-xs text-[#64748B] uppercase tracking-wider">{LABELS[ind.codigo] ?? ind.codigo}</p>
            <p className="text-2xl font-semibold text-[#F8FAFC] mt-1">
              {ind.valor}
              <span className="text-sm text-[#64748B] ml-1">{ind.unidade}</span>
            </p>
            <p className="text-xs text-[#475569] mt-2">{ind.data}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create `SystemHealth.tsx`**

```tsx
// frontend/src/routes/admin/SystemHealth.tsx
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";

interface ProviderInfo {
  success: boolean;
  latency_ms: number | null;
  error: string | null;
  checked_at: string;
}

interface AdminHealth {
  postgres: string;
  redis: string;
  providers: Record<string, ProviderInfo>;
}

function StatusPill({ ok }: { ok: boolean }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${ok ? "bg-green-900/30 text-green-400" : "bg-red-900/30 text-red-400"}`}>
      {ok ? "ok" : "error"}
    </span>
  );
}

export default function SystemHealth() {
  const { data, isLoading, dataUpdatedAt } = useQuery({
    queryKey: ["admin-health"],
    queryFn: async () => {
      const { data } = await api.get<AdminHealth>("/v1/admin/health");
      return data;
    },
    refetchInterval: 30_000,
  });

  if (isLoading) return <div className="p-8 text-[#64748B]">Carregando...</div>;

  return (
    <div className="p-8 max-w-xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Saúde do Sistema</h1>
        <span className="text-xs text-[#475569]">
          {dataUpdatedAt ? `Atualizado: ${new Date(dataUpdatedAt).toLocaleTimeString("pt-BR")}` : ""}
        </span>
      </div>
      <div className="bg-[#0F172A] border border-[#1E293B] rounded-lg overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#1E293B]">
          <span className="text-sm text-[#94A3B8]">PostgreSQL</span>
          <StatusPill ok={data?.postgres === "ok"} />
        </div>
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#1E293B]">
          <span className="text-sm text-[#94A3B8]">Redis</span>
          <StatusPill ok={data?.redis === "ok"} />
        </div>
        {Object.entries(data?.providers ?? {}).map(([name, info]) => (
          <div key={name} className="flex items-center justify-between px-4 py-3 border-b border-[#1E293B] last:border-0">
            <div>
              <span className="text-sm text-[#94A3B8]">{name}</span>
              {info.latency_ms !== null && (
                <span className="text-xs text-[#475569] ml-2">{info.latency_ms}ms</span>
              )}
              {info.error && <p className="text-xs text-red-400 mt-0.5">{info.error}</p>}
            </div>
            <StatusPill ok={info.success} />
          </div>
        ))}
        {Object.keys(data?.providers ?? {}).length === 0 && (
          <div className="px-4 py-3 text-xs text-[#475569]">Nenhum dado de provider disponível ainda.</div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create `PixSettings.tsx`**

```tsx
// frontend/src/routes/admin/PixSettings.tsx
import { useQuery } from "@tanstack/react-query";
import { getAdminSettings } from "../../lib/admin-settings";

export default function PixSettings() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin-settings"],
    queryFn: getAdminSettings,
  });

  if (isLoading || !data) return <div className="p-8 text-[#64748B]">Carregando...</div>;

  return (
    <div className="p-8 max-w-xl">
      <h1 className="text-xl font-semibold mb-2">Configurações Pix</h1>
      <p className="text-sm text-[#64748B] mb-6">
        As configurações Pix são definidas por variáveis de ambiente e não podem ser alteradas pelo painel.
      </p>
      <div className="bg-[#0F172A] border border-[#1E293B] rounded-lg overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#1E293B]">
          <div>
            <p className="text-xs text-[#64748B]">Provedor Pix</p>
            <p className="text-sm text-[#F8FAFC] mt-0.5">{data.pix_provider?.value ?? "—"}</p>
          </div>
          <span className="text-xs bg-[#1E293B] text-[#475569] px-2 py-0.5 rounded">env</span>
        </div>
        <div className="flex items-center justify-between px-4 py-3">
          <div>
            <p className="text-xs text-[#64748B]">Webhook Secret</p>
            <p className="text-sm text-[#F8FAFC] mt-0.5">
              {data.pix_webhook_secret?.value ? "••••••••" : "não configurado"}
            </p>
          </div>
          <span className="text-xs bg-[#1E293B] text-[#475569] px-2 py-0.5 rounded">env</span>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/admin/Indicators.tsx \
        frontend/src/routes/admin/SystemHealth.tsx \
        frontend/src/routes/admin/PixSettings.tsx
git commit -m "feat(frontend): Indicators, SystemHealth, PixSettings panels"
```

---

### Task 12: `AuditLog.tsx` and `SmtpSettings.tsx`

**Files:**
- Create: `frontend/src/routes/admin/AuditLog.tsx`
- Create: `frontend/src/routes/admin/SmtpSettings.tsx`

- [ ] **Step 1: Create `AuditLog.tsx`**

```tsx
// frontend/src/routes/admin/AuditLog.tsx
import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listAuditLog, type AuditLogItem } from "../../lib/audit-log";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const ACAO_OPTIONS = [
  { label: "Todas as ações", value: "_all" },
  { label: "create", value: "create" },
  { label: "update", value: "update" },
  { label: "delete", value: "delete" },
];

export default function AuditLog() {
  const [acao, setAcao] = useState("_all");
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["audit-log", acao, cursor],
    queryFn: () =>
      listAuditLog({ acao: acao === "_all" ? undefined : acao, cursor }),
  });

  function handleExportCsv() {
    window.open("/api/v1/audit-log?format=csv", "_blank");
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Log de Auditoria</h1>
        <div className="flex items-center gap-3">
          <Select
            value={acao}
            onValueChange={(v) => { setAcao(v); setCursor(undefined); }}
          >
            <SelectTrigger className="w-40 h-8 text-xs bg-[#0F172A] border-[#1E293B]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ACAO_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button size="sm" variant="outline" className="h-8 text-xs border-[#334155]" onClick={handleExportCsv}>
            Exportar CSV
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="text-[#64748B]">Carregando...</div>
      ) : (
        <div className="bg-[#0F172A] border border-[#1E293B] rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1E293B] text-xs text-[#64748B]">
                <th className="text-left px-4 py-3 font-normal">Timestamp</th>
                <th className="text-left px-4 py-3 font-normal">Usuário</th>
                <th className="text-left px-4 py-3 font-normal">Ação</th>
                <th className="text-left px-4 py-3 font-normal">Entidade</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {(data?.items ?? []).map((item: AuditLogItem) => (
                <React.Fragment key={item.id}>
                  <tr className="border-b border-[#1E293B] hover:bg-[#1E293B] transition-colors">
                    <td className="px-4 py-3 text-[#94A3B8] text-xs">
                      {new Date(item.timestamp).toLocaleString("pt-BR")}
                    </td>
                    <td className="px-4 py-3 text-[#94A3B8] text-xs">
                      {item.usuario_email ?? "—"}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs bg-[#1E293B] px-2 py-0.5 rounded text-[#94A3B8]">
                        {item.acao}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-[#94A3B8] text-xs">
                      {item.entidade ?? "—"}
                    </td>
                    <td className="px-4 py-3">
                      {item.diff_json && (
                        <button
                          onClick={() =>
                            setExpandedId(expandedId === item.id ? null : item.id)
                          }
                          className="text-xs text-[#22C55E] hover:underline"
                        >
                          {expandedId === item.id ? "Fechar" : "Ver detalhes"}
                        </button>
                      )}
                    </td>
                  </tr>
                  {expandedId === item.id && item.diff_json && (
                    <tr className="border-b border-[#1E293B]">
                      <td colSpan={5} className="px-4 py-3 bg-[#020617]">
                        <pre className="text-xs text-[#94A3B8] overflow-x-auto whitespace-pre-wrap">
                          {JSON.stringify(item.diff_json, null, 2)}
                        </pre>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
              {(data?.items ?? []).length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-xs text-[#475569]">
                    Nenhum registro encontrado.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {data?.next_cursor && (
            <div className="p-4 border-t border-[#1E293B]">
              <Button
                size="sm"
                variant="outline"
                className="text-xs border-[#334155]"
                onClick={() => setCursor(data.next_cursor!)}
              >
                Carregar mais
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create `SmtpSettings.tsx`**

```tsx
// frontend/src/routes/admin/SmtpSettings.tsx
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getAdminSettings, updateAdminSetting } from "../../lib/admin-settings";
import EditableField from "../../components/EditableField";

const EMAIL_PROVIDERS = [
  { label: "SMTP", value: "smtp" },
  { label: "SES (AWS)", value: "ses" },
  { label: "Resend", value: "resend" },
];

export default function SmtpSettings() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["admin-settings"],
    queryFn: getAdminSettings,
  });

  if (isLoading || !data) return <div className="p-8 text-[#64748B]">Carregando...</div>;

  function makeSave(key: string) {
    return async (value: string) => {
      await updateAdminSetting(key, value);
      await qc.invalidateQueries({ queryKey: ["admin-settings"] });
    };
  }

  return (
    <div className="p-8 max-w-xl">
      <h1 className="text-xl font-semibold mb-6">Configurações SMTP</h1>
      <div className="bg-[#0F172A] border border-[#1E293B] rounded-lg px-4">
        <EditableField
          label="Provedor de e-mail"
          value={data.email_provider?.value ?? "smtp"}
          type="select"
          options={EMAIL_PROVIDERS}
          onSave={makeSave("email_provider")}
        />
        <EditableField
          label="Host SMTP"
          value={data.smtp_host?.value ?? ""}
          type="text"
          onSave={makeSave("smtp_host")}
        />
        <EditableField
          label="Porta SMTP"
          value={data.smtp_port?.value ?? ""}
          type="number"
          onSave={makeSave("smtp_port")}
        />
        <EditableField
          label="Usuário SMTP"
          value={data.smtp_user?.value ?? ""}
          type="text"
          onSave={makeSave("smtp_user")}
        />
        <EditableField
          label="Senha SMTP"
          value={data.smtp_password?.value ?? ""}
          type="password"
          onSave={makeSave("smtp_password")}
        />
        <EditableField
          label="Usar TLS"
          value={data.smtp_tls?.value ?? "false"}
          type="toggle"
          onSave={makeSave("smtp_tls")}
        />
        <EditableField
          label="Endereço remetente"
          value={data.smtp_from?.value ?? ""}
          type="text"
          onSave={makeSave("smtp_from")}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/admin/AuditLog.tsx \
        frontend/src/routes/admin/SmtpSettings.tsx
git commit -m "feat(frontend): AuditLog and SmtpSettings panels"
```

---

### Task 13: TypeScript build check + final smoke test

- [ ] **Step 1: TypeScript check**

```bash
cd frontend && npm run build 2>&1 | head -50
```

Expected: Build completes with no type errors. Fix any that appear before continuing.

- [ ] **Step 2: Start the full stack**

```bash
# Terminal 1 — backend
cd backend && uv run uvicorn finacialsim_saas.main:app --reload

# Terminal 2 — frontend
cd frontend && npm run dev
```

- [ ] **Step 3: Manual smoke test**

1. Log in as admin → dashboard shows "Administração" card → click it → lands at `/admin/regras`
2. Sidebar shows all 7 nav items; active item highlighted
3. Business Rules: all 4 groups render; edit a field → value updates after save
4. Indicators: SELIC/CDI/IPCA cards show; "Atualizar agora" spins then cards refetch
5. Audit Log: table loads; filter by ação works; "Ver detalhes" expands diff JSON; CSV export triggers download
6. System Health: Postgres/Redis show "ok"; provider rows show if any worker has run
7. SMTP: all fields editable; password masked; toggle works
8. Pix: read-only display with "env" badges
9. Users: existing Users.tsx renders inside the sidebar layout unchanged
10. "Voltar ao Dashboard" link in sidebar footer returns to `/`
11. Log in as manager → `/admin` redirects to `/` (RequireRole blocks access)

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(admin): complete admin dashboard — all 7 panels wired"
```
