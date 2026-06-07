# Phase 7A — Data Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Phase 1 placeholder `notifications_outbox` schema with the finalized Phase 7 schema, and add the `email_log` stub table.

**Architecture:** Migration 008 drops and recreates `notifications_outbox` (no prod data — dev env only). New columns: `channel`, `template_key`, `payload_json`, `target_email`, `target_phone`, `scheduled_for`, `status`, `last_error`, `sent_at`, `idempotency_key`, `updated_at`, `criado_em`. New `email_log` table stubs delivery callback storage. SQLAlchemy models updated to match.

**Tech Stack:** SQLAlchemy 2.x Mapped/mapped_column, Alembic, PostgreSQL 16

---

## File Map

| Action | File |
|--------|------|
| Create | `backend/alembic/versions/008_phase7_notifications.py` |
| Modify | `backend/finacialsim_saas/data/models.py` — replace `NotificationsOutbox`, add `EmailLog` |
| Modify | `backend/tests/test_models.py` — add assertions for new tables |

---

### Task 1: Write the failing model test

**Files:**
- Modify: `backend/tests/test_models.py`

- [ ] **Step 1: Add test for phase7 models**

Open `backend/tests/test_models.py` and append this test function at the end of the file:

```python
async def test_all_phase7_models_importable_and_tables_exist(db_session):
    from finacialsim_saas.data.models import NotificationsOutbox, EmailLog
    from sqlalchemy import inspect, text

    # Table existence check via raw SQL
    result = await db_session.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    )
    tables = {row[0] for row in result.fetchall()}
    assert "notifications_outbox" in tables
    assert "email_log" in tables

    # New column presence
    result = await db_session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='notifications_outbox'"
        )
    )
    columns = {row[0] for row in result.fetchall()}
    for col in ("channel", "template_key", "payload_json", "target_email",
                "scheduled_for", "status", "idempotency_key", "updated_at", "criado_em"):
        assert col in columns, f"Missing column: {col}"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd backend && uv run pytest tests/test_models.py::test_all_phase7_models_importable_and_tables_exist -v
```

Expected: FAIL — columns from old schema are there, new ones are missing.

---

### Task 2: Update SQLAlchemy models

**Files:**
- Modify: `backend/finacialsim_saas/data/models.py`

- [ ] **Step 1: Replace `NotificationsOutbox` class**

Find the existing `NotificationsOutbox` class (around line 136) and replace it entirely:

```python
class NotificationsOutbox(Base):
    __tablename__ = "notifications_outbox"
    __table_args__ = (
        sa.Index("ix_notifications_outbox_status_scheduled", "status", "scheduled_for"),
        sa.Index("ix_notifications_outbox_tenant", "tenant_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_notifications_outbox_idempotency_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(sa.Text, nullable=False, default="email", server_default="email")
    template_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    payload_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    target_email: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    target_phone: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    scheduled_for: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    status: Mapped[str] = mapped_column(
        sa.Text, nullable=False, default="pending", server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    last_error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    criado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
```

- [ ] **Step 2: Add `EmailLog` class immediately after `NotificationsOutbox`**

```python
class EmailLog(Base):
    __tablename__ = "email_log"
    __table_args__ = (
        sa.Index("ix_email_log_outbox_id", "outbox_id"),
        sa.Index("ix_email_log_tenant", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    outbox_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("notifications_outbox.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_message_id: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    # accepted | delivered | bounced | complained — populated by provider webhooks (v2)
    status: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    provider_payload_json: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
```

- [ ] **Step 3: Verify no import errors**

```bash
cd backend && uv run python -c "from finacialsim_saas.data.models import NotificationsOutbox, EmailLog; print('OK')"
```

Expected: `OK`

---

### Task 3: Write migration 008

**Files:**
- Create: `backend/alembic/versions/008_phase7_notifications.py`

- [ ] **Step 1: Create the migration file**

```python
"""phase7 — finalize notifications_outbox schema; add email_log stub

Revision ID: 008
Revises: 007
Create Date: 2026-06-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop placeholder outbox (dev env only — no prod data to preserve)
    op.drop_table("notifications_outbox")

    # Recreate with finalized schema
    op.create_table(
        "notifications_outbox",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), primary_key=True,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.Text, nullable=False, server_default="email"),
        sa.Column("template_key", sa.Text, nullable=False),
        sa.Column("payload_json", sa.JSON, nullable=False),
        sa.Column("target_email", sa.Text, nullable=True),
        sa.Column("target_phone", sa.Text, nullable=True),
        sa.Column(
            "scheduled_for", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.Text, nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
    )
    op.create_index(
        "ix_notifications_outbox_status_scheduled",
        "notifications_outbox", ["status", "scheduled_for"],
    )
    op.create_index("ix_notifications_outbox_tenant", "notifications_outbox", ["tenant_id"])
    op.create_unique_constraint(
        "uq_notifications_outbox_idempotency_key",
        "notifications_outbox", ["idempotency_key"],
    )

    # email_log — stub table for future delivery-callback writes
    op.create_table(
        "email_log",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), primary_key=True,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "outbox_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notifications_outbox.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider_message_id", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=True),
        sa.Column("provider_payload_json", sa.JSON, nullable=True),
        sa.Column(
            "observed_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
    )
    op.create_index("ix_email_log_outbox_id", "email_log", ["outbox_id"])
    op.create_index("ix_email_log_tenant", "email_log", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("email_log")
    op.drop_table("notifications_outbox")
    # Note: original notifications_outbox schema from migration 002 is not restored.
```

- [ ] **Step 2: Run migration against dev database**

```bash
cd backend && uv run alembic upgrade head
```

Expected: Migration completes without error. Output includes `Running upgrade 007 -> 008`.

- [ ] **Step 3: Verify migration ran**

```bash
cd backend && uv run alembic current
```

Expected: `008 (head)`

---

### Task 4: Run the test suite

- [ ] **Step 1: Run full test suite to confirm no regressions**

```bash
cd backend && uv run pytest tests/ -v --tb=short
```

Expected: All previously passing tests pass. `test_all_phase7_models_importable_and_tables_exist` now passes.

- [ ] **Step 2: Commit**

```bash
git add backend/alembic/versions/008_phase7_notifications.py \
        backend/finacialsim_saas/data/models.py \
        backend/tests/test_models.py
git commit -m "feat(phase7a): finalize notifications_outbox schema; add email_log stub (migration 008)"
```
